"""Map ``applied_treatment`` → :class:`treatment_plan.PlannedTreatmentItem`.

DPMF's ``applied_treatment`` row is the clinical event: a patient
underwent (or is scheduled to undergo) a specific catalog entry. In
DentalPin this requires three rows in cooperation:

1. **One ``TreatmentPlan`` per patient** ("Migrado de Gesdén") — created
   lazily, cached by patient.
2. **One ``odontogram.Treatment``** for the actual tooth treatment
   record. We bypass ``odontogram.service`` because the
   migration-friendly model (no enforced clinical_type vocabulary,
   accepting whatever ``catalog_item`` we're handed) is the model
   constructor directly. The teeth detail (``TreatmentTooth``) is
   skipped — the canonical odontogram_raw bit-mask isn't decoded
   yet (see ``CanonicalAppliedTreatment.odontogram_raw`` docstring
   in dental-bridge), so we record the treatment header only.
3. **One ``PlannedTreatmentItem``** linking the plan and the
   treatment.

The ``applied_treatment_phase`` mapper attaches sessions to the
``PlannedTreatmentItem`` produced here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.odontogram.models import Treatment
from app.modules.treatment_plan.models import PlannedTreatmentItem, TreatmentPlan
from app.modules.treatment_plan.service import TreatmentPlanService

from ..models import ImportWarning
from .base import MapperContext

# Gesdén status_code 5 == realised/billable per docs/schema_map.md.
_REALISED_CODE = 5


class AppliedTreatmentMapper:
    def __init__(self) -> None:
        # (clinic_id, patient_id) -> plan_id. One migrated plan per patient.
        self._plan_cache: dict[tuple[UUID, UUID], UUID] = {}
        # plan_id -> next sequence_order to assign. Avoids a SELECT per item.
        self._next_sequence: dict[UUID, int] = {}

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
        existing = await ctx.resolver.get("applied_treatment", canonical_uuid)
        if existing is not None:
            return existing

        patient_uuid = payload.get("patient_uuid")
        if not patient_uuid:
            await _warn(ctx, source_id, "applied_treatment.no_patient", "Tratamiento omitido: sin paciente.")
            return None
        patient_id = await ctx.resolver.get("patient", str(patient_uuid))
        if patient_id is None:
            await _warn(
                ctx, source_id, "applied_treatment.unmapped_patient",
                "Tratamiento omitido: paciente no mapeado previamente.",
            )
            return None

        professional_id: UUID | None = None
        prof_uuid = payload.get("professional_uuid")
        if prof_uuid:
            professional_id = await ctx.resolver.get("professional", str(prof_uuid))

        catalog_item_id: UUID | None = None
        variant_uuid = payload.get("treatment_variant_uuid")
        if variant_uuid:
            catalog_item_id = await ctx.resolver.get(
                "treatment_catalog_variant", str(variant_uuid)
            )

        plan_id = await self._get_or_create_plan(ctx, patient_id, professional_id)

        # Status & timestamps.
        status_code = payload.get("status_code")
        is_realised = status_code == _REALISED_CODE
        start_dt = _parse_datetime(payload.get("start_date")) or datetime.now(UTC)
        end_dt = _parse_datetime(payload.get("end_date"))
        amount = _decimal_or_none(payload.get("amount"))

        # 1) odontogram.Treatment header — clinical record.
        treatment = Treatment(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            clinical_type="migrated",
            scope="tooth",
            catalog_item_id=catalog_item_id,
            status="performed" if is_realised else "planned",
            recorded_at=start_dt,
            performed_at=end_dt if is_realised else None,
            performed_by=professional_id if is_realised else None,
            price_snapshot=amount,
            notes=payload.get("notes"),
            source_module="migration_import",
        )
        ctx.db.add(treatment)
        await ctx.db.flush()

        # 2) PlannedTreatmentItem — links the plan to the Treatment.
        sequence = self._next_sequence.get(plan_id, 0) + 1
        self._next_sequence[plan_id] = sequence
        item = PlannedTreatmentItem(
            clinic_id=ctx.clinic_id,
            treatment_plan_id=plan_id,
            treatment_id=treatment.id,
            sequence_order=sequence,
            status="completed" if is_realised else "pending",
            completed_at=end_dt if is_realised else None,
            completed_by=professional_id if is_realised else None,
            assigned_professional_id=professional_id,
            notes=payload.get("notes"),
        )
        ctx.db.add(item)
        await ctx.db.flush()

        await ctx.resolver.set(
            entity_type="applied_treatment",
            canonical_uuid=canonical_uuid,
            source_system=source_system,
            dentalpin_table="planned_treatment_items",
            dentalpin_id=item.id,
        )
        return item.id

    async def _get_or_create_plan(
        self,
        ctx: MapperContext,
        patient_id: UUID,
        professional_id: UUID | None,
    ) -> UUID:
        cache_key = (ctx.clinic_id, patient_id)
        if cache_key in self._plan_cache:
            return self._plan_cache[cache_key]

        # Try to find an existing imported plan first (re-import safety).
        result = await ctx.db.execute(
            select(TreatmentPlan.id).where(
                TreatmentPlan.clinic_id == ctx.clinic_id,
                TreatmentPlan.patient_id == patient_id,
                TreatmentPlan.title == "Migrado de Gesdén",
            )
        )
        plan_id = result.scalar_one_or_none()
        if plan_id is None:
            plan = await TreatmentPlanService.create(
                ctx.db,
                ctx.clinic_id,
                ctx.created_by,
                {
                    "patient_id": patient_id,
                    "title": "Migrado de Gesdén",
                    "assigned_professional_id": professional_id,
                    "internal_notes": "Plan generado por dental-bridge para alojar tratamientos históricos.",
                },
            )
            plan_id = plan.id

        self._plan_cache[cache_key] = plan_id
        return plan_id


async def _warn(ctx: MapperContext, source_id: str, code: str, message: str) -> None:
    ctx.db.add(
        ImportWarning(
            job_id=ctx.job_id,
            entity_type="applied_treatment",
            source_id=source_id,
            severity="warn",
            code=code,
            message=message,
        )
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        try:
            d = date.fromisoformat(str(value)[:10])
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except (TypeError, ValueError):
            return None
