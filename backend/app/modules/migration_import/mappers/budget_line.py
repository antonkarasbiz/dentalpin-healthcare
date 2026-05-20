"""Map ``budget_line`` → :class:`budget.BudgetItem`.

Each line needs:

- ``budget_id``   via the resolver against the already-mapped ``budget``.
- ``catalog_item_id`` via the resolver against ``treatment_catalog_item``
  (canonical ``treatment_uuid``). When the source line points at a
  ``treatment_variant_uuid`` we don't currently have a variant mapper,
  so the line is skipped with a warning until the variant landing is
  built.

Pricing fields (``unit_amount``, ``units``, ``discount_*``,
``vat_percent``) carry over verbatim — the destination service does
its own line-total recomputation, so we just hand it the snapshot.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.modules.budget.models import Budget
from app.modules.budget.service import BudgetItemService, BudgetService

from ..models import ImportWarning
from .base import MapperContext


class BudgetLineMapper:
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
        existing = await ctx.resolver.get("budget_line", canonical_uuid)
        if existing is not None:
            return existing

        budget_uuid = payload.get("budget_uuid")
        if not budget_uuid:
            await _warn(ctx, source_id, "budget_line.no_budget", "Línea sin presupuesto.")
            return None
        budget_id = await ctx.resolver.get("budget", str(budget_uuid))
        if budget_id is None:
            await _warn(
                ctx, source_id, "budget_line.unmapped_budget",
                "Línea omitida: presupuesto padre no mapeado.",
            )
            return None

        # Prefer the parent treatment; fall back to the variant if the
        # source only carries a per-tariff variant_uuid. Both resolve
        # to the same TreatmentCatalogItem (the variant mapper is a
        # pipe-through).
        catalog_item_id = None
        if payload.get("treatment_uuid"):
            catalog_item_id = await ctx.resolver.get(
                "treatment_catalog_item", str(payload["treatment_uuid"])
            )
        if catalog_item_id is None and payload.get("treatment_variant_uuid"):
            catalog_item_id = await ctx.resolver.get(
                "treatment_catalog_variant", str(payload["treatment_variant_uuid"])
            )
        if catalog_item_id is None:
            code = "budget_line.no_treatment" if not (
                payload.get("treatment_uuid") or payload.get("treatment_variant_uuid")
            ) else "budget_line.unmapped_treatment"
            msg = (
                "Línea omitida: sin tratamiento de catálogo en origen."
                if code == "budget_line.no_treatment"
                else "Línea omitida: tratamiento/variante de catálogo no mapeado."
            )
            await _warn(ctx, source_id, code, msg)
            return None

        unit_price = _decimal_or_none(payload.get("unit_amount")) or Decimal("0.00")
        units = payload.get("units")
        try:
            quantity = int(Decimal(str(units))) if units else 1
        except (InvalidOperation, TypeError, ValueError):
            quantity = 1
        quantity = max(quantity, 1)

        discount_percent = _decimal_or_none(payload.get("discount_percent"))
        discount_amount = _decimal_or_none(payload.get("discount_amount"))
        if discount_amount and discount_amount > 0:
            discount_type = "absolute"
            discount_value = discount_amount
        elif discount_percent and discount_percent > 0:
            discount_type = "percentage"
            discount_value = discount_percent
        else:
            discount_type = None
            discount_value = None

        # DPMF lines may resolve to several teeth (e.g. bridges). DentalPin's
        # BudgetItem.tooth_number is scalar, so we record the first decoded
        # FDI here and surface the full list in ``notes`` so the operator
        # can split the line afterwards if needed.
        teeth = payload.get("teeth") or []
        tooth_number = int(teeth[0]) if teeth else None
        extra_teeth_note = (
            f"Dientes adicionales en origen: {', '.join(str(t) for t in teeth[1:])}."
            if len(teeth) > 1
            else None
        )
        base_notes = payload.get("notes")
        combined_notes = "\n".join(n for n in (base_notes, extra_teeth_note) if n)

        data: dict[str, Any] = {
            "catalog_item_id": catalog_item_id,
            "unit_price": unit_price,
            "quantity": quantity,
            "discount_type": discount_type,
            "discount_value": discount_value,
            "tooth_number": tooth_number,
            "display_order": payload.get("order_within_budget") or 0,
            "notes": combined_notes or None,
        }
        data = {k: v for k, v in data.items() if v is not None}

        item = await BudgetItemService.create_item(ctx.db, ctx.clinic_id, budget_id, data)

        # Refresh aggregate totals on the parent budget. Each line
        # triggers one SELECT over budget_items — fine for migration
        # batches (~20 lines/budget) and keeps the budget header in
        # sync without a separate finalisation pass.
        budget = await ctx.db.get(Budget, budget_id)
        if budget is not None:
            await BudgetService._recalculate_totals(ctx.db, budget)

            # Source-truth signal for "was this budget accepted?" — Gesdén
            # stores the Presu↔TtosMed double link in
            # ``PresuTto.IdTtoMedOrig``, which dental-bridge exposes as
            # ``budget_line.applied_treatment_uuid``. If any line of a
            # budget points at an applied treatment, the patient acted on
            # the budget → it was accepted. Clinics with poor data
            # hygiene leave ``FecAcepta`` null but this signal still
            # fires because the clinical work happened. Promotion is
            # one-way (draft → accepted); never demote a budget that the
            # operator may have already updated manually.
            if (
                budget.status == "draft"
                and payload.get("applied_treatment_uuid") not in (None, "")
            ):
                budget.status = "accepted"
                budget.accepted_via = "manual"

        await ctx.resolver.set(
            entity_type="budget_line",
            canonical_uuid=canonical_uuid,
            source_system=source_system,
            dentalpin_table="budget_items",
            dentalpin_id=item.id,
        )
        return item.id


async def _warn(ctx: MapperContext, source_id: str, code: str, message: str) -> None:
    ctx.db.add(
        ImportWarning(
            job_id=ctx.job_id,
            entity_type="budget_line",
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
