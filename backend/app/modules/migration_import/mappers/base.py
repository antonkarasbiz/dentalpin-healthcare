"""Mapper foundations: :class:`MapperContext` and :class:`MappingResolver`.

Both live in a single module so concrete mappers can keep their imports
tight (``from .base import MapperContext, MappingResolver``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EntityMapping

if TYPE_CHECKING:
    from ..dpmf import DpmfHandle


_SKIP_SUFFIX = ".__skipped__"
_SKIP_SENTINEL_TABLE = "__skipped__"
_SKIP_SENTINEL_ID = UUID("00000000-0000-0000-0000-000000000000")


class MappingResolver:
    """Read / write the ``entity_mappings`` table.

    All FK resolution between DPMF entities goes through this object —
    mappers never use canonical UUIDs directly as DentalPin row IDs.

    Memoisation is per-instance (one resolver per job), bounded by the
    number of distinct entity_type+canonical_uuid pairs in the file.

    "Skipped" sidecar: mappers that decide to drop a canonical row (e.g.
    a non-clinical Gesdén entry, an appointment with no schedule) can
    call :meth:`mark_skipped` so a re-execute short-circuits via
    :meth:`was_skipped` instead of re-running the side effects
    (duplicate Treatment / PlannedTreatmentItem rows, redundant warning
    emissions). The skipped marks live in ``entity_mappings`` under a
    suffixed entity_type so :meth:`get` never returns them.
    """

    def __init__(self, db: AsyncSession, clinic_id: UUID, job_id: UUID) -> None:
        self._db = db
        self._clinic_id = clinic_id
        self._job_id = job_id
        self._cache: dict[tuple[str, str], UUID] = {}
        self._skipped_cache: set[tuple[str, str]] = set()

    async def get(self, entity_type: str, canonical_uuid: str) -> UUID | None:
        """Return the DentalPin row id mapped to ``(entity_type, canonical_uuid)``.

        Scoped to ``clinic_id`` so two clinics importing the same DPMF
        do not see each other's resolutions.
        """
        key = (entity_type, canonical_uuid)
        if key in self._cache:
            return self._cache[key]
        result = await self._db.execute(
            select(EntityMapping.dentalpin_id).where(
                EntityMapping.clinic_id == self._clinic_id,
                EntityMapping.entity_type == entity_type,
                EntityMapping.source_canonical_uuid == canonical_uuid,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            self._cache[key] = row
        return row

    async def set(
        self,
        entity_type: str,
        canonical_uuid: str,
        source_system: str,
        dentalpin_table: str,
        dentalpin_id: UUID,
    ) -> None:
        """Persist the mapping. Idempotent — duplicate inserts no-op via
        the UNIQUE constraint."""
        mapping = EntityMapping(
            clinic_id=self._clinic_id,
            job_id=self._job_id,
            source_system=source_system,
            entity_type=entity_type,
            source_canonical_uuid=canonical_uuid,
            dentalpin_table=dentalpin_table,
            dentalpin_id=dentalpin_id,
        )
        self._db.add(mapping)
        self._cache[(entity_type, canonical_uuid)] = dentalpin_id

    async def mark_skipped(
        self,
        entity_type: str,
        canonical_uuid: str,
        source_system: str,
    ) -> None:
        """Record that this canonical was intentionally dropped.

        Subsequent calls to :meth:`was_skipped` for the same key return
        ``True`` so re-executes can short-circuit. Stored under a
        suffixed entity_type so ordinary :meth:`get` lookups are not
        polluted with the sentinel.
        """
        key = (entity_type, canonical_uuid)
        if key in self._skipped_cache:
            return
        mapping = EntityMapping(
            clinic_id=self._clinic_id,
            job_id=self._job_id,
            source_system=source_system,
            entity_type=f"{entity_type}{_SKIP_SUFFIX}",
            source_canonical_uuid=canonical_uuid,
            dentalpin_table=_SKIP_SENTINEL_TABLE,
            dentalpin_id=_SKIP_SENTINEL_ID,
        )
        self._db.add(mapping)
        self._skipped_cache.add(key)

    async def was_skipped(self, entity_type: str, canonical_uuid: str) -> bool:
        key = (entity_type, canonical_uuid)
        if key in self._skipped_cache:
            return True
        result = await self._db.execute(
            select(EntityMapping.id).where(
                EntityMapping.clinic_id == self._clinic_id,
                EntityMapping.entity_type == f"{entity_type}{_SKIP_SUFFIX}",
                EntityMapping.source_canonical_uuid == canonical_uuid,
            )
        )
        if result.scalar_one_or_none() is not None:
            self._skipped_cache.add(key)
            return True
        return False


@dataclass
class MapperContext:
    """Per-job context handed to every mapper invocation."""

    db: AsyncSession
    clinic_id: UUID
    job_id: UUID
    resolver: MappingResolver
    import_fiscal_compliance: bool
    created_by: UUID  # The admin who launched the import; used as actor for created_by FKs.
    # Optional reference to the open DPMF handle. Populated by the
    # service orchestrator inside ``_run_pipeline``. Mappers that need
    # to peek at sibling rows (e.g. the applied_treatment shadow-pairing
    # pre-pass) read it; the rest can ignore it. Tests and other call
    # sites that don't open a DPMF leave it ``None``.
    handle: DpmfHandle | None = field(default=None)
    # ``client_uuid`` → list of patient_ids linked to that client.
    # Populated by ``PatientClientLinkMapper`` (Gesdén's ``PacCli`` is
    # M:N) and read by ``PaymentMapper`` to split a ``PagoCli`` across
    # every family member instead of attributing the whole amount to
    # the first patient mapped. Empty by default so test paths that
    # bypass the link mapper just see the 1:1 fallback.
    client_to_patients: dict[str, list[UUID]] = field(default_factory=dict)


class Mapper(Protocol):
    """Structural interface every concrete mapper satisfies."""

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
    ) -> UUID | None: ...
