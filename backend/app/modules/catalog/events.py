"""Catalog event handlers.

``clinic.created`` → seed VAT types (by country preset), categories and the
default treatment catalog so a fresh clinic can budget/bill on day one.
Idempotent: ``seed_catalog`` skips existing VAT rates / category keys /
internal codes.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.database import async_session_maker

from .seed import seed_catalog

logger = logging.getLogger(__name__)


async def on_clinic_created(data: dict[str, Any]) -> None:
    clinic_id_raw = data.get("clinic_id")
    if not clinic_id_raw:
        return
    try:
        clinic_id = UUID(str(clinic_id_raw))
    except (ValueError, TypeError):
        return

    vat_preset = data.get("vat_preset") or "generic"
    # Reference prices are Spanish EUR figures — meaningless in other currencies.
    with_prices = (data.get("currency") or "EUR") == "EUR"

    async with async_session_maker() as db:
        try:
            summary = await seed_catalog(
                db, clinic_id, vat_preset=vat_preset, with_prices=with_prices
            )
            await db.commit()
            logger.info("catalog.on_clinic_created seeded %s for %s", summary, clinic_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("catalog.on_clinic_created failed: %s", exc, exc_info=True)
            await db.rollback()
