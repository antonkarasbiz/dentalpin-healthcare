"""Map ``payment`` → :class:`payments.Payment`.

A DPMF Payment is a historical money-received record. It points at a
patient via the DPMF's `patient_uuid` (resolved through the mapping
table) and optionally carries `method` + `amount` + `paid_at`.

The DPMF debt / debt_payment_application graph is significantly richer
than DentalPin's flat Payment model — allocations land in `RawEntity`
today via the catch-all path. This MVP creates the Payment row only,
which is enough to keep the patient ledger balanced for the historical
data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select

from ..models import ImportWarning
from .base import MapperContext

_METHOD_MAP: dict[str, str] = {
    "cash": "cash",
    "card": "card",
    "bank_transfer": "bank_transfer",
    "transfer": "bank_transfer",
    "direct_debit": "direct_debit",
    "insurance": "insurance",
    "mutua": "insurance",
    "other": "other",
}

# Gesdén ``DCobros.Tipo`` numeric code → DentalPin payment method
# enum. Based on the dominant values in the source database (Tipo=1 is
# the by-far most common, payment is cash/in-clinic; the others map to
# typical Spanish clinic patterns). Unknown codes fall back to
# "other" so the row still imports cleanly.
_PAYMENT_KIND_MAP: dict[int, str] = {
    1: "cash",
    2: "bank_transfer",
    3: "card",
    4: "direct_debit",
    5: "insurance",
}


class PaymentMapper:
    def __init__(self) -> None:
        # Clinic.currency is a snapshot field on payments.Payment;
        # resolved once per clinic and reused for the whole job.
        self._currency_cache: dict[UUID, str] = {}

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
        existing = await ctx.resolver.get("payment", canonical_uuid)
        if existing is not None:
            return existing

        # DPMF payments reference a Client (payer), not a Patient. Resolve
        # through the ``patient_for_client`` sidecar populated by
        # ``PatientClientLinkMapper``. If that fails, accept a direct
        # ``patient_uuid`` for sources that carry it.
        patient_id: UUID | None = None
        client_uuid_external = payload.get("client_uuid")
        if client_uuid_external:
            patient_id = await ctx.resolver.get(
                "patient_for_client", str(client_uuid_external)
            )
        if patient_id is None:
            patient_uuid_external = payload.get("patient_uuid")
            if patient_uuid_external:
                patient_id = await ctx.resolver.get(
                    "patient", str(patient_uuid_external)
                )
        if patient_id is None:
            await _warn(
                ctx, source_id, "payment.no_patient_for_client",
                "Pago omitido: cliente/paciente no resoluble (sin link o link no importado).",
            )
            return None

        try:
            amount = Decimal(str(payload.get("amount") or "0"))
        except (InvalidOperation, TypeError):
            await _warn(ctx, source_id, "payment.invalid_amount", "Pago omitido: importe inválido.")
            return None
        if amount <= 0:
            await _warn(ctx, source_id, "payment.zero_amount", "Pago omitido: importe nulo o negativo.")
            return None

        # Canonical Payment exposes ``payment_kind`` (the source numeric
        # ``Tipo`` code) and ``payment_method_uuid`` (FK to the source
        # catalog). We only decode the numeric kind here — the catalog
        # path requires a payment_method catalog importer that doesn't
        # exist yet. Unknown kinds fall back to "other".
        method = _PAYMENT_KIND_MAP.get(payload.get("payment_kind"), "other")

        paid_at = _parse_date(payload.get("paid_on") or payload.get("paid_at") or payload.get("payment_date"))
        if paid_at is None:
            # Payment.payment_date is NOT NULL — fall back to today for
            # rows whose source date is missing/unparseable. The notes
            # field captures the migration provenance for audit.
            paid_at = date.today()

        currency = await self._currency_for_clinic(ctx)

        from app.modules.payments.models import Payment

        payment = Payment(
            clinic_id=ctx.clinic_id,
            patient_id=patient_id,
            amount=amount,
            currency=currency,
            method=method,
            payment_date=paid_at,
            notes=(payload.get("notes") or f"Importado dental-bridge ({source_id})"),
            recorded_by=ctx.created_by,
        )
        ctx.db.add(payment)
        await ctx.db.flush()

        await ctx.resolver.set(
            entity_type="payment",
            canonical_uuid=canonical_uuid,
            source_system=source_system,
            dentalpin_table="payments",
            dentalpin_id=payment.id,
        )
        return payment.id

    async def _currency_for_clinic(self, ctx: MapperContext) -> str:
        if ctx.clinic_id in self._currency_cache:
            return self._currency_cache[ctx.clinic_id]
        from app.core.auth.models import Clinic

        result = await ctx.db.execute(
            select(Clinic.currency).where(Clinic.id == ctx.clinic_id)
        )
        currency = result.scalar_one_or_none() or "EUR"
        self._currency_cache[ctx.clinic_id] = currency
        return currency


async def _warn(ctx: MapperContext, source_id: str, code: str, message: str) -> None:
    ctx.db.add(
        ImportWarning(
            job_id=ctx.job_id,
            entity_type="payment",
            source_id=source_id,
            severity="warn",
            code=code,
            message=message,
        )
    )


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
