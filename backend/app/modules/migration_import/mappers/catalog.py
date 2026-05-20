"""Map ``treatment_catalog_item`` → :class:`catalog.TreatmentCatalogItem`.

DPMF carries treatment templates (the clinic's offer) as their own
entity. We materialise them in the destination catalog so budget and
treatment_plan mappers can FK-reference them via the resolver.

**Match-then-create**: before falling back to a new catalog row we
look for an existing ``TreatmentCatalogItem`` whose Spanish name
(``names->>'es'``, case- and whitespace-normalised) matches the
source name exactly and is unique within the clinic. If a single
match exists the imported budget/treatment lines reuse it — which
preserves DentalPin's pricing strategy, session template, VAT type
and odontogram mapping for that treatment. Ambiguous matches (≥ 2
candidates) or no match fall through to creating a new row in the
"Importado de Gesdén" category so the operator can re-classify
manually later.

A single ``TreatmentCategory`` keyed ``migrado_gesden`` is lazily
created per clinic on the first newly-created import.

``internal_code`` uses the source canonical UUID's first 8 chars
prefixed with ``MIG-`` instead of the raw Gesdén code, because the
source can carry duplicate codes (e.g. multiple tariff variants share
a code) which would violate the catalog's
``uq_catalog_item_clinic_code`` constraint.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from app.modules.catalog.models import TreatmentCatalogItem, TreatmentCategory
from app.modules.catalog.service import CatalogService

from ..models import ImportWarning
from .base import MapperContext

_MIGRATED_CATEGORY_KEY = "migrado_gesden"


class CatalogItemMapper:
    def __init__(self) -> None:
        # Lazy per-process cache so repeated import jobs in the same
        # backend don't re-query the category on every entity.
        self._category_cache: dict[UUID, UUID] = {}

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
        existing = await ctx.resolver.get("treatment_catalog_item", canonical_uuid)
        if existing is not None:
            return existing

        name = (
            payload.get("short_name")
            or payload.get("description")
            or payload.get("agenda_description")
            or payload.get("code")
            or source_id
        )

        # Try to reuse an existing DentalPin catalog item before creating
        # a "Migrado" duplicate. Single unique match wins; ambiguous or
        # missing matches fall through to the create path.
        matched_id = await self._find_match(ctx, name)
        if matched_id is not None:
            await ctx.resolver.set(
                entity_type="treatment_catalog_item",
                canonical_uuid=canonical_uuid,
                source_system=source_system,
                dentalpin_table="treatment_catalog_items",
                dentalpin_id=matched_id,
            )
            ctx.db.add(
                ImportWarning(
                    job_id=ctx.job_id,
                    entity_type="treatment_catalog_item",
                    source_id=source_id,
                    severity="info",
                    code="catalog.matched_existing",
                    message=(
                        f"Reutilizado catálogo existente con nombre '{name}'. "
                        "No se ha creado fila nueva."
                    ),
                )
            )
            return matched_id

        category_id = await self._get_or_create_category(ctx)
        internal_code = f"MIG-{canonical_uuid[:8]}"
        price = _decimal_or_none(payload.get("reference_price"))
        duration = payload.get("duration_minutes")

        data: dict[str, Any] = {
            "category_id": category_id,
            "internal_code": internal_code,
            "names": {"es": str(name)[:200]},
            "default_price": price,
            "default_duration_minutes": int(duration) if duration else None,
            "requires_appointment": True,
            "pricing_strategy": "flat",
            "treatment_scope": "tooth",
            "is_diagnostic": False,
            "requires_surfaces": False,
            "billing_mode": "on_completion",
            "is_active": not bool(payload.get("deactivated", False)),
        }
        data = {k: v for k, v in data.items() if v is not None}

        item = await CatalogService.create_item(ctx.db, ctx.clinic_id, data)
        await ctx.resolver.set(
            entity_type="treatment_catalog_item",
            canonical_uuid=canonical_uuid,
            source_system=source_system,
            dentalpin_table="treatment_catalog_items",
            dentalpin_id=item.id,
        )
        return item.id

    async def _find_match(self, ctx: MapperContext, name: str) -> UUID | None:
        """Return the DentalPin catalog item id whose Spanish name matches
        ``name`` exactly (case + whitespace insensitive), or ``None`` if
        the lookup is empty or ambiguous. Soft-deleted and inactive rows
        are excluded so we don't resurrect retired catalog entries.
        """
        normalised = (name or "").strip().lower()
        if len(normalised) < 3:
            return None
        result = await ctx.db.execute(
            select(TreatmentCatalogItem.id).where(
                TreatmentCatalogItem.clinic_id == ctx.clinic_id,
                TreatmentCatalogItem.is_active.is_(True),
                TreatmentCatalogItem.deleted_at.is_(None),
                func.lower(func.trim(TreatmentCatalogItem.names["es"].astext))
                == normalised,
            ).limit(2)
        )
        rows = list(result.scalars().all())
        if len(rows) == 1:
            return rows[0]
        return None

    async def _get_or_create_category(self, ctx: MapperContext) -> UUID:
        if ctx.clinic_id in self._category_cache:
            return self._category_cache[ctx.clinic_id]

        result = await ctx.db.execute(
            select(TreatmentCategory.id).where(
                TreatmentCategory.clinic_id == ctx.clinic_id,
                TreatmentCategory.key == _MIGRATED_CATEGORY_KEY,
            )
        )
        category_id = result.scalar_one_or_none()
        if category_id is None:
            category = TreatmentCategory(
                clinic_id=ctx.clinic_id,
                key=_MIGRATED_CATEGORY_KEY,
                names={"es": "Importado de Gesdén", "en": "Imported from Gesdén"},
                display_order=999,
                is_active=True,
                is_system=False,
            )
            ctx.db.add(category)
            await ctx.db.flush()
            category_id = category.id

        self._category_cache[ctx.clinic_id] = category_id
        return category_id


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
