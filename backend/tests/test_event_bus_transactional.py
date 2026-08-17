"""EventBus transactional handlers (ADR 0019).

A handler declaring a ``db`` parameter runs inside the publisher's
session and its exceptions propagate; handlers without ``db`` keep the
fire-and-log contract.
"""

from __future__ import annotations

import pytest

from app.core.events.bus import EventBus


@pytest.mark.asyncio
async def test_db_is_passed_only_to_handlers_that_declare_it() -> None:
    bus = EventBus()
    seen: list = []
    session = object()

    async def plain(data):
        seen.append(("plain", data["x"]))

    async def transactional(data, *, db):
        seen.append(("tx", data["x"], db))

    bus.subscribe("t.evt", plain)
    bus.subscribe("t.evt", transactional)
    await bus.publish("t.evt", {"x": 1}, db=session)

    assert seen == [("plain", 1), ("tx", 1, session)]


@pytest.mark.asyncio
async def test_transactional_handler_errors_propagate_plain_are_swallowed() -> None:
    bus = EventBus()

    async def plain(data):
        raise ValueError("swallowed")

    async def transactional(data, *, db):
        raise ValueError("propagates")

    bus.subscribe("t.evt", plain)
    await bus.publish("t.evt", {}, db=object())  # no raise

    bus.subscribe("t.evt", transactional)
    with pytest.raises(ValueError, match="propagates"):
        await bus.publish("t.evt", {}, db=object())


@pytest.mark.asyncio
async def test_transactional_handler_requires_db_at_publish() -> None:
    bus = EventBus()

    async def transactional(data, *, db):
        pass

    bus.subscribe("t.evt", transactional)
    with pytest.raises(RuntimeError, match="transactional publish"):
        await bus.publish("t.evt", {})
