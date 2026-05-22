"""Map ``treatment_catalog_item`` → :class:`catalog.TreatmentCatalogItem`.

DPMF carries treatment templates (the clinic's offer) as their own
entity. We materialise them in the destination catalog so budget and
treatment_plan mappers can FK-reference them via the resolver.

**Match-then-create**: before falling back to a new catalog row we
look for an existing ``TreatmentCatalogItem`` whose Spanish name
matches the source. Matching is accent/punctuation-insensitive and
falls back to a similarity score (``difflib`` ratio ≥ 0.88) when the
exact normalised form misses — Gesdén labels carry abbreviations and
dots ("OBTUR. COMP.", "ENDODONCIA UNI.") that would otherwise never
match the destination seed ("Obturación composite", "Endodoncia
unirradicular"). A single best match (no tie at the top score) wins;
otherwise we fall through to creating a new row in the "Importado de
Gesdén" category so the operator can re-classify manually later.

A single ``TreatmentCategory`` keyed ``migrado_gesden`` is lazily
created per clinic on the first newly-created import.

``internal_code`` uses the source canonical UUID's first 8 chars
prefixed with ``MIG-`` instead of the raw Gesdén code, because the
source can carry duplicate codes (e.g. multiple tariff variants share
a code) which would violate the catalog's
``uq_catalog_item_clinic_code`` constraint.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.modules.catalog.models import TreatmentCatalogItem, TreatmentCategory
from app.modules.catalog.service import CatalogService

from ..models import ImportWarning
from .base import MapperContext

_MIGRATED_CATEGORY_KEY = "migrado_gesden"

# Minimum bidirectional token-prefix coverage for the fuzzy fallback
# to claim a match. 1.0 = every meaningful token on both sides found
# a partner (equality or one is the prefix of the other). 0.8 leaves
# room for a single small-token mismatch in long labels while still
# rejecting cousin treatments ("Corona metal" vs "Corona zirconio").
_FUZZY_MATCH_THRESHOLD = 0.8

# Tokens shorter than this are dropped from the comparison set so
# filler ("de", "el", "y") and aggressive Gesdén abbreviations ("co",
# "rx") don't false-match through prefix containment.
_MIN_TOKEN_LEN = 3


def _normalise(text: str | None) -> str:
    """Lower-case, accent-strip, punctuation-strip, collapse whitespace.

    Used both for exact comparison and as input to token matching.
    NFKD splits accented characters into base + combining mark; the
    combining marks are then dropped. Punctuation (``.``, ``-``, etc.)
    becomes whitespace so "obtur. comp." collapses to "obtur comp".
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    no_punct = re.sub(r"[^\w\s]", " ", stripped.lower())
    return re.sub(r"\s+", " ", no_punct).strip()


def _meaningful_tokens(normalised: str) -> list[str]:
    return [tok for tok in normalised.split() if len(tok) >= _MIN_TOKEN_LEN]


def _token_match_score(src_norm: str, dst_norm: str) -> float:
    """Bidirectional token-prefix coverage between two normalised labels.

    For each meaningful token on one side, look for an equal or
    prefix-related token on the other. The score is the minimum of
    the two directional coverages, so a short Gesdén label like
    "corona metal" does NOT win against the longer destination
    "corona metal cerámica" — the extra "ceramica" token on the
    destination drops dst-coverage and the min penalises the pair.

    Prefix containment in EITHER direction matches the abbreviation
    flavour Gesdén ships: "obtur" ↔ "obturacion", "uni" ↔
    "unirradicular", "zirc" ↔ "zirconio". Filler tokens (< 3 chars)
    are filtered out so "de", "y", "el" don't cause false hits.
    """
    s_tokens = _meaningful_tokens(src_norm)
    d_tokens = _meaningful_tokens(dst_norm)
    if not s_tokens or not d_tokens:
        return 0.0

    def _coverage(a_tokens: list[str], b_tokens: list[str]) -> float:
        matched = 0
        for at in a_tokens:
            for bt in b_tokens:
                if at == bt or at.startswith(bt) or bt.startswith(at):
                    matched += 1
                    break
        return matched / len(a_tokens)

    return min(_coverage(s_tokens, d_tokens), _coverage(d_tokens, s_tokens))


class CatalogItemMapper:
    def __init__(self) -> None:
        # Lazy per-process cache so repeated import jobs in the same
        # backend don't re-query the category on every entity.
        self._category_cache: dict[UUID, UUID] = {}
        # Snapshot of (normalised_name, item_id, original_es_label)
        # for active catalog items in each clinic. Built once per
        # clinic on first _find_match call; lets us skip a SELECT per
        # source row.
        self._catalog_snapshot: dict[UUID, list[tuple[str, UUID, str]]] = {}

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

        # Display label order: the canonical spec lists ``short_name``
        # first (Gesdén's ``DescCorta``), then ``description``
        # (``Descrip``), then ``agenda_description`` (``DescAgenda``).
        # ``name`` is not in the v0.1 spec but we accept it for
        # adapters that emit a generic label — falling all the way to
        # ``code`` produces clinic UIs full of "COD001" entries which
        # the user cannot recognise.
        name = (
            payload.get("short_name")
            or payload.get("description")
            or payload.get("patient_facing_description")
            or payload.get("agenda_description")
            or payload.get("name")
            or payload.get("code")
            or source_id
        )

        # Try to reuse an existing DentalPin catalog item before creating
        # a "Migrado" duplicate. Single unique match wins (exact or
        # fuzzy); ambiguous or missing matches fall through to the
        # create path.
        match = await self._find_match(ctx, name)
        if match is not None:
            matched_id, matched_name, was_fuzzy = match
            await ctx.resolver.set(
                entity_type="treatment_catalog_item",
                canonical_uuid=canonical_uuid,
                source_system=source_system,
                dentalpin_table="treatment_catalog_items",
                dentalpin_id=matched_id,
            )
            if was_fuzzy:
                code = "catalog.fuzzy_matched"
                message = (
                    f"Catálogo Gesdén '{name}' enlazado por similitud a DentalPin '{matched_name}'."
                )
            else:
                code = "catalog.matched_existing"
                message = (
                    f"Reutilizado catálogo existente con nombre '{name}'. "
                    "No se ha creado fila nueva."
                )
            ctx.db.add(
                ImportWarning(
                    job_id=ctx.job_id,
                    entity_type="treatment_catalog_item",
                    source_id=source_id,
                    severity="info",
                    code=code,
                    message=message,
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

    async def _find_match(self, ctx: MapperContext, name: str) -> tuple[UUID, str, bool] | None:
        """Return ``(id, matched_es_name, was_fuzzy)`` for the best
        DentalPin catalog item match, or ``None`` when no acceptable
        candidate exists.

        Matching strategy:
        1. Normalise (accents stripped, lower-case, punctuation →
           whitespace, whitespace collapsed).
        2. Exact normalised hit on a single candidate → unambiguous
           win.
        3. Otherwise score every active candidate with
           ``_token_match_score``. The single strict-best candidate
           above ``_FUZZY_MATCH_THRESHOLD`` wins. Ties at the top
           score fall through (we'd rather create "Importado de
           Gesdén" than mis-link a row).

        Soft-deleted and inactive rows are excluded so we don't
        resurrect retired catalog entries.
        """
        normalised = _normalise(name)
        if len(normalised) < 3:
            return None

        snapshot = await self._catalog_snapshot_for_clinic(ctx)
        if not snapshot:
            return None

        exact: list[tuple[UUID, str]] = [
            (item_id, label) for norm_name, item_id, label in snapshot if norm_name == normalised
        ]
        if len(exact) == 1:
            return (exact[0][0], exact[0][1], False)
        if len(exact) > 1:
            # Ambiguous — multiple destination items share the same
            # normalised label. Don't pick one at random.
            return None

        best_id: UUID | None = None
        best_label = ""
        best_score = 0.0
        tie = False
        for norm_name, item_id, label in snapshot:
            score = _token_match_score(normalised, norm_name)
            if score > best_score:
                best_score = score
                best_id = item_id
                best_label = label
                tie = False
            elif score == best_score and score > 0:
                tie = True
        if best_id is not None and best_score >= _FUZZY_MATCH_THRESHOLD and not tie:
            return (best_id, best_label, True)
        return None

    async def _catalog_snapshot_for_clinic(self, ctx: MapperContext) -> list[tuple[str, UUID, str]]:
        """Cache of (normalised_es_name, item_id, original_label) per
        clinic. Rebuilt on the first call per job. Inside a single
        import job the destination catalog isn't expected to change
        under us, so snapshotting avoids one SELECT per source
        Tratamiento.
        """
        cached = self._catalog_snapshot.get(ctx.clinic_id)
        if cached is not None:
            return cached
        result = await ctx.db.execute(
            select(
                TreatmentCatalogItem.id,
                TreatmentCatalogItem.names["es"].astext,
            ).where(
                TreatmentCatalogItem.clinic_id == ctx.clinic_id,
                TreatmentCatalogItem.is_active.is_(True),
                TreatmentCatalogItem.deleted_at.is_(None),
            )
        )
        snapshot = [(_normalise(label), item_id, label) for item_id, label in result.all() if label]
        self._catalog_snapshot[ctx.clinic_id] = snapshot
        return snapshot

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
