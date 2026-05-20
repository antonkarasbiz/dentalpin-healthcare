"""ProfessionalMapper — role and is_active wiring.

Guards against the canonical "doctor" role silently falling through to
"assistant" (it must map to DentalPin's "dentist") and against
imported professionals landing inactive in the Users page.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.auth.models import Clinic, ClinicMembership, User
from app.modules.migration_import.mappers.base import MapperContext, MappingResolver
from app.modules.migration_import.mappers.professional import ProfessionalMapper
from app.modules.migration_import.models import ImportJob


@pytest.mark.asyncio
async def test_doctor_role_maps_to_dentist(db_session) -> None:
    clinic, admin = await _bootstrap(db_session)
    ctx = await _ctx(db_session, clinic.id, admin.id)
    mapper = ProfessionalMapper()
    canonical = str(uuid4())

    await mapper.apply(
        ctx,
        entity_type="professional",
        payload={
            "email": "doc@example.com",
            "given_name": "Ana",
            "family_name": "García",
            "role": "doctor",
        },
        raw={},
        canonical_uuid=canonical,
        source_id="1",
        source_system="gesden",
    )
    await db_session.flush()

    membership = (
        await db_session.execute(
            select(ClinicMembership).where(ClinicMembership.clinic_id == clinic.id)
        )
    ).scalar_one()
    assert membership.role == "dentist"
    user = (
        await db_session.execute(select(User).where(User.id == membership.user_id))
    ).scalar_one()
    assert user.is_active is True


@pytest.mark.asyncio
async def test_unknown_role_falls_back_to_assistant(db_session) -> None:
    clinic, admin = await _bootstrap(db_session)
    ctx = await _ctx(db_session, clinic.id, admin.id)
    canonical = str(uuid4())

    await ProfessionalMapper().apply(
        ctx,
        entity_type="professional",
        payload={"email": "x@example.com", "role": "other"},
        raw={},
        canonical_uuid=canonical,
        source_id="2",
        source_system="gesden",
    )
    await db_session.flush()

    membership = (
        await db_session.execute(
            select(ClinicMembership).where(ClinicMembership.clinic_id == clinic.id)
        )
    ).scalar_one()
    assert membership.role == "assistant"


@pytest.mark.asyncio
async def test_deactivated_payload_imports_as_inactive(db_session) -> None:
    clinic, admin = await _bootstrap(db_session)
    ctx = await _ctx(db_session, clinic.id, admin.id)
    canonical = str(uuid4())

    await ProfessionalMapper().apply(
        ctx,
        entity_type="professional",
        payload={
            "email": "left@example.com",
            "role": "doctor",
            "deactivated": True,
        },
        raw={},
        canonical_uuid=canonical,
        source_id="3",
        source_system="gesden",
    )
    await db_session.flush()

    user = (
        await db_session.execute(select(User).where(User.email == "left@example.com"))
    ).scalar_one()
    assert user.is_active is False


async def _bootstrap(db_session):
    clinic = Clinic(id=uuid4(), name="C", tax_id="B1")
    admin = User(
        id=uuid4(),
        email=f"admin-{uuid4().hex[:8]}@test.local",
        password_hash="x",
        first_name="A",
        last_name="A",
    )
    db_session.add_all([clinic, admin])
    await db_session.flush()
    return clinic, admin


async def _ctx(db_session, clinic_id, admin_id):
    job = ImportJob(
        clinic_id=clinic_id,
        created_by=admin_id,
        status="executing",
        original_filename="t.dpm",
        file_path="/tmp/t.dpm",
        file_size=0,
    )
    db_session.add(job)
    await db_session.flush()
    return MapperContext(
        db=db_session,
        clinic_id=clinic_id,
        job_id=job.id,
        resolver=MappingResolver(db=db_session, clinic_id=clinic_id, job_id=job.id),
        import_fiscal_compliance=False,
        created_by=admin_id,
    )
