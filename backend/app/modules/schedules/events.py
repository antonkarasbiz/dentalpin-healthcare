"""Event handlers.

* Agenda appointment lifecycle — purely informational (analytics cache);
  never block the appointment flow. If schedules is uninstalled the bus
  simply stops calling these functions.
* ``clinic.created`` — seed a Mon–Fri weekly template so a fresh clinic
  doesn't start "open 24/7".
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.database import async_session_maker

from .services.clinic_hours import ClinicHoursService

logger = logging.getLogger(__name__)


async def on_clinic_created(data: dict[str, Any]) -> None:
    clinic_id_raw = data.get("clinic_id")
    if not clinic_id_raw:
        return
    try:
        clinic_id = UUID(str(clinic_id_raw))
    except (ValueError, TypeError):
        return

    async with async_session_maker() as db:
        try:
            await ClinicHoursService.create_default_weekly(
                db, clinic_id, split_shift=data.get("country") == "ES"
            )
            await db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("schedules.on_clinic_created failed: %s", exc, exc_info=True)
            await db.rollback()


async def on_appointment_scheduled(data: dict) -> None:
    logger.debug("schedules: appointment.scheduled received: %s", data.get("appointment_id"))


async def on_appointment_updated(data: dict) -> None:
    logger.debug("schedules: appointment.updated received: %s", data.get("appointment_id"))


async def on_appointment_cancelled(data: dict) -> None:
    logger.debug("schedules: appointment.cancelled received: %s", data.get("appointment_id"))
