"""Copilot morning digest (proactivity v1).

Covers the settings opt-in (PATCH validation + recipient defaulting)
and the task itself: disabled clinics are skipped, enabled clinics get
one digest built through the tool registry with the recipient's role
permissions, and ``copilot.digest.sent`` is published.

The task opens its own sessions via ``async_session_maker``, so test
fixtures must be committed before invoking it.
"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.core.events.types import EventType
from app.database import engine
from app.modules.copilot.service import CopilotSettingsService
from app.modules.copilot.tasks import send_morning_digests


@pytest_asyncio.fixture(autouse=True)
async def _dispose_global_pool():
    """Drop the global engine's pool around every test.

    ``send_morning_digests`` opens sessions through the global
    ``async_session_maker``; lingering pool connections from a previous
    test's event loop trigger "attached to a different loop" (same
    pattern as ``test_patient_timeline.py``).
    """
    await engine.dispose()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_settings_patch_enables_digest_and_defaults_recipient(
    client: AsyncClient, auth_headers: dict, test_clinic
) -> None:
    res = await client.patch(
        "/api/v1/copilot/settings",
        json={"digest_enabled": True, "digest_hour": 7},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["digest_enabled"] is True
    assert data["digest_hour"] == 7
    # Recipient defaults to the user who flipped the switch.
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert data["digest_recipient_user_id"] == me.json()["data"]["user"]["id"]


@pytest.mark.asyncio
async def test_settings_patch_digest_only_does_not_require_openai_key(
    client: AsyncClient, auth_headers: dict, test_clinic, monkeypatch
) -> None:
    """Digest opt-in is no-LLM: must work even when OPENAI_API_KEY is unset."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "OPENAI_API_KEY", "")
    res = await client.patch(
        "/api/v1/copilot/settings",
        json={"digest_enabled": True},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_settings_patch_provider_change_requires_openai_key(
    client: AsyncClient, auth_headers: dict, test_clinic, monkeypatch
) -> None:
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "OPENAI_API_KEY", "")
    res = await client.patch(
        "/api/v1/copilot/settings",
        json={"provider": "openai"},
        headers=auth_headers,
    )
    assert res.status_code == 400
    assert "OPENAI_API_KEY" in res.text


@pytest.mark.asyncio
async def test_settings_patch_rejects_bad_hour(
    client: AsyncClient, auth_headers: dict, test_clinic
) -> None:
    res = await client.patch(
        "/api/v1/copilot/settings",
        json={"digest_hour": 25},
        headers=auth_headers,
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_digest_skips_disabled_clinics(db_session: AsyncSession, test_clinic) -> None:
    await CopilotSettingsService.get_or_create(db_session, test_clinic.id)
    await db_session.commit()

    seen: list[dict] = []
    event_bus.subscribe(EventType.COPILOT_DIGEST_SENT, lambda data: seen.append(data))
    await send_morning_digests(datetime(2032, 1, 5, 8, 0))
    assert seen == []


@pytest.mark.asyncio
async def test_digest_sends_for_enabled_clinic(
    db_session: AsyncSession, client: AsyncClient, auth_headers: dict, test_clinic
) -> None:
    # The /me user is admin of test_clinic (conftest fixture).
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = me.json()["data"]["user"]["id"]

    from uuid import UUID

    row = await CopilotSettingsService.update(
        db_session,
        test_clinic.id,
        {"digest_enabled": True, "digest_hour": 8},
        acting_user_id=UUID(user_id),
    )
    assert row.digest_recipient_user_id is not None
    await db_session.commit()

    seen: list[dict] = []
    event_bus.subscribe(EventType.COPILOT_DIGEST_SENT, lambda data: seen.append(data))

    # Hour mismatch → nothing.
    await send_morning_digests(datetime(2032, 1, 5, 9, 0))
    assert seen == []

    # Hour match → one digest, event published.
    await send_morning_digests(datetime(2032, 1, 5, 8, 0))
    assert len(seen) == 1
    assert seen[0]["clinic_id"] == str(test_clinic.id)
    assert seen[0]["recipient_user_id"] == user_id
    assert seen[0]["date"] == "2032-01-05"


@pytest.mark.asyncio
async def test_digest_audit_trail_lands_in_agent_logs(
    db_session: AsyncSession, client: AsyncClient, auth_headers: dict, test_clinic
) -> None:
    """Digest tool calls go through the registry → audit rows exist."""
    from uuid import UUID

    from app.core.agents.models import AgentAuditLog

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    await CopilotSettingsService.update(
        db_session,
        test_clinic.id,
        {"digest_enabled": True, "digest_hour": 6},
        acting_user_id=UUID(me.json()["data"]["user"]["id"]),
    )
    await db_session.commit()

    await send_morning_digests(datetime(2032, 1, 6, 6, 0))

    names = list(
        await db_session.scalars(
            select(AgentAuditLog.tool_name).where(AgentAuditLog.clinic_id == test_clinic.id)
        )
    )
    assert "agenda.get_day_overview" in names
    assert "recalls.list_due_recalls" in names
    assert "budget.list_budgets" in names
