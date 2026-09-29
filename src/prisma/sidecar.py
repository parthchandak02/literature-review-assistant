"""prisma_counts.json sidecar: the counts a PRISMA figure was drawn from."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from src.models import PRISMACounts, PrismaCountsSidecar

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

_logger = logging.getLogger(__name__)

PRISMA_COUNTS_SIDECAR_NAME = "prisma_counts.json"
PRISMA_COUNTS_SIDECAR_VERSION = 1


def sidecar_path_for(figure_path: str | Path) -> Path:
    return Path(figure_path).parent / PRISMA_COUNTS_SIDECAR_NAME


def write_prisma_counts_sidecar(counts: PRISMACounts, figure_path: str | Path) -> Path:
    sidecar = PrismaCountsSidecar(
        version=PRISMA_COUNTS_SIDECAR_VERSION,
        figure=Path(figure_path).name,
        counts=counts,
    )
    path = sidecar_path_for(figure_path)
    path.write_text(sidecar.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_prisma_counts_sidecar(path: str | Path) -> PrismaCountsSidecar | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return PrismaCountsSidecar.model_validate_json(p.read_text(encoding="utf-8"))
    except (ValidationError, OSError, ValueError) as exc:
        _logger.warning("Unreadable PRISMA counts sidecar %s: %s", p, exc)
        return None


def prisma_counts_differ(a: PRISMACounts, b: PRISMACounts) -> bool:
    return a.model_dump(mode="json") != b.model_dump(mode="json")


async def compute_live_prisma_counts(repo: WorkflowRepository, workflow_id: str) -> PRISMACounts:
    """PRISMA counts for a workflow from its runtime DB (same inputs as writing and export)."""
    from src.manuscript.review_facts import build_review_facts

    dedup_count = int(await repo.get_dedup_count(workflow_id) or 0)
    included_ids, _ = await repo.resolve_canonical_included_paper_ids(workflow_id)
    facts = await build_review_facts(
        repo,
        workflow_id,
        dedup_count=dedup_count,
        included_qualitative=0,
        included_quantitative=len(included_ids),
    )
    return facts.prisma
