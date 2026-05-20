"""Map ``patient`` → :class:`patients.Patient`.

Field mapping from `CanonicalPatient` (DPMF v0.1):

| DPMF                | DentalPin                |
|---------------------|--------------------------|
| given_name          | first_name (required)    |
| family_name         | last_name  (required)    |
| national_id         | national_id              |
| date_of_birth       | date_of_birth            |
| sex                 | gender (mapped)          |
| patient_number      | notes prefix (we don't have a column) |
| tenant_label        | _ignored_ — DPMF is single-tenant; DentalPin's clinic_id wins |

Unmapped DPMF fields (registered_at, deactivated_at, deceased,
gdpr_consent, default_center_uuid, default_professional_uuid,
guardian_client_uuid, referrer_patient_uuid) survive in
``raw_source_data`` for later passes — querying that table is the
forward-compat escape hatch.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from app.modules.patients.service import PatientService

from .base import MapperContext
from .patient_alert import PatientAlertMapper

_SEX_MAP: dict[str, str] = {
    "male": "male",
    "female": "female",
    "other": "other",
    "unknown": "prefer_not_say",
}


class PatientMapper:
    def __init__(self) -> None:
        # Reuse the alert pipeline across patients so the
        # ``_context_cache`` inside it amortises the
        # ``MedicalContext`` upsert. Created lazily — clinics whose
        # source has no ``Pacientes.Notas`` content pay nothing.
        self._alert_pipeline: PatientAlertMapper | None = None

    async def apply(
        self,
        ctx: MapperContext,
        *,
        entity_type: str,
        payload: dict[str, Any],
        raw: dict[str, Any],
        canonical_uuid: str,
        source_id: str,
        source_system: str,
    ) -> UUID | None:
        existing = await ctx.resolver.get("patient", canonical_uuid)
        if existing is not None:
            return existing

        first_name = (payload.get("given_name") or "").strip() or "Sin nombre"
        last_name = (payload.get("family_name") or "").strip() or "—"

        dob_raw = payload.get("date_of_birth")
        dob: date | None = None
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
            except (TypeError, ValueError):
                dob = None

        gender = _SEX_MAP.get((payload.get("sex") or "").lower())

        national_id = payload.get("national_id") or None
        national_id_type = "nif" if national_id else None

        patient_number = payload.get("patient_number")
        notes = (
            f"Migración dental-bridge: nº paciente origen {patient_number}"
            if patient_number
            else None
        )

        data: dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": dob,
            "gender": gender,
            "national_id": national_id,
            "national_id_type": national_id_type,
            "notes": notes,
            "status": "active",
            "do_not_contact": False,
            "preferred_language": "es",
        }
        # Drop None to let SQLAlchemy column defaults apply.
        data = {k: v for k, v in data.items() if v is not None}

        patient = await PatientService.create_patient(ctx.db, ctx.clinic_id, data)

        # Gesdén stores a free-text patient-level narrative in
        # ``Pacientes.Notas`` (dental-bridge exports it as
        # ``payload['notes']`` from adapter_version 0.0.2). Clinics
        # use it interchangeably with the ``AlertPac`` popup table —
        # allergies, medications, conditions and admin tags routinely
        # appear in *both* places. Run each non-empty line through the
        # same classifier the patient_alert mapper uses so the
        # structured destinations (Allergy, Medication,
        # SystemicDisease, MedicalContext flags) absorb whatever fits
        # the rules; the catch-all "general" branch appends the
        # remainder to ``Patient.notes``.
        notes_blob = (payload.get("notes") or "").strip()
        if notes_blob:
            await self._absorb_patient_notes(ctx, patient.id, notes_blob, source_id)

        await ctx.resolver.set(
            entity_type="patient",
            canonical_uuid=canonical_uuid,
            source_system=source_system,
            dentalpin_table="patients",
            dentalpin_id=patient.id,
        )
        return patient.id

    async def _absorb_patient_notes(
        self,
        ctx: MapperContext,
        patient_id: UUID,
        notes_blob: str,
        source_id: str,
    ) -> None:
        """Split ``Pacientes.Notas`` by newline and pipe each line
        through the alert classifier. Empty lines and pure separators
        are skipped. We never raise — a single weird line can't fail
        the whole patient row."""
        if self._alert_pipeline is None:
            self._alert_pipeline = PatientAlertMapper()
        lines = [
            ln.strip(" .-") for ln in notes_blob.replace("\r", "\n").split("\n") if ln.strip(" .-")
        ]
        for idx, line in enumerate(lines):
            await self._alert_pipeline.dispatch_freetext(
                ctx,
                patient_id,
                line,
                source_id=f"patient_notes:{source_id}:{idx}",
            )
