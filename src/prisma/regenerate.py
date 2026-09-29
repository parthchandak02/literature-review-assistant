"""Figure-only PRISMA regeneration: recompute counts from runtime.db, redraw, write sidecar. No LLM calls."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite

from src.db.repositories import WorkflowRepository
from src.models import PRISMACounts
from src.prisma.diagram import render_prisma_diagram
from src.prisma.sidecar import (
    compute_live_prisma_counts,
    read_prisma_counts_sidecar,
    sidecar_path_for,
)

PRISMA_FIGURE_NAME = "fig_prisma_flow.png"
MANUSCRIPT_NAME = "doc_manuscript.md"

_N = r"(\d{1,3}(?:,\d{3})+|\d+)"
_MANUSCRIPT_COUNT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (field_name, re.compile(pattern, re.IGNORECASE))
    for field_name, pattern in (
        ("records_screened", rf"\bscreened (?:those |a total of )?{_N} records\b"),
        ("records_screened", rf"\b{_N} records (?:were screened|proceeded to title and abstract screening)\b"),
        ("records_excluded_screening", rf"\b{_N} records were excluded at title(?:/| and )abstract"),
        ("automation_excluded", rf"\b(?:automation tools )?removed {_N} records before\b"),
        ("reports_sought", rf"\b{_N} reports sought\b"),
        ("reports_sought", rf"\bsought {_N} full-text reports\b"),
        ("reports_not_retrieved", rf"\bdid not retrieve {_N}\b"),
        ("reports_not_retrieved", rf"\b{_N} (?:reports )?were not retrieved\b"),
        ("reports_assessed", rf"\b{_N} reports were assessed\b"),
        ("reports_assessed", rf"\bassessed {_N} reports\b"),
    )
)

FLOW_FIELDS: tuple[str, ...] = (
    "total_identified_databases",
    "total_identified_other",
    "duplicates_removed",
    "automation_excluded",
    "records_screened",
    "records_excluded_screening",
    "reports_sought",
    "reports_not_retrieved",
    "reports_assessed",
    "total_included",
    "arithmetic_valid",
)


@dataclass
class RegenerateResult:
    run_dir: Path
    workflow_id: str
    old: PRISMACounts | None
    new: PRISMACounts
    written: list[Path] = field(default_factory=list)
    stale_manuscript_examples: list[str] = field(default_factory=list)


async def resolve_runtime_db_path(run: str, run_root: str = "runs") -> Path:
    """Accept a run dir, a runtime.db path, or a workflow id."""
    candidate = Path(run).expanduser()
    if candidate.is_dir():
        db = candidate / "runtime.db"
        if db.is_file():
            return db.resolve()
        raise FileNotFoundError(f"No runtime.db in {candidate}")
    if candidate.is_file():
        return candidate.resolve()

    from src.db.workflow_registry import find_by_workflow_id, find_by_workflow_id_fallback

    entry = await find_by_workflow_id(run_root, run) or await find_by_workflow_id_fallback(run_root, run)
    if entry is None or not Path(entry.db_path).is_file():
        raise FileNotFoundError(f"Run not found: {run} (not a path, not a workflow id under {run_root})")
    return Path(entry.db_path).resolve()


async def _read_counts(db_path: Path) -> tuple[str, PRISMACounts]:
    async with aiosqlite.connect(f"file:{db_path}?mode=ro", uri=True) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1")
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"No workflow row in {db_path}")
        workflow_id = str(row["workflow_id"])
        counts = await compute_live_prisma_counts(WorkflowRepository(db), workflow_id)
    return workflow_id, counts


async def regenerate_prisma(run: str, *, dry_run: bool = False, run_root: str = "runs") -> RegenerateResult:
    db_path = await resolve_runtime_db_path(run, run_root)
    run_dir = db_path.parent
    figure = run_dir / PRISMA_FIGURE_NAME
    workflow_id, counts = await _read_counts(db_path)
    previous = read_prisma_counts_sidecar(sidecar_path_for(figure))
    result = RegenerateResult(
        run_dir=run_dir,
        workflow_id=workflow_id,
        old=previous.counts if previous else None,
        new=counts,
    )
    manuscript = run_dir / MANUSCRIPT_NAME
    if manuscript.is_file():
        result.stale_manuscript_examples = find_stale_manuscript_counts(
            manuscript.read_text(encoding="utf-8", errors="replace"), counts
        )
    if dry_run:
        return result

    render_prisma_diagram(counts, figure)
    result.written += [figure, sidecar_path_for(figure)]
    submission_copy = run_dir / "submission" / "figures" / PRISMA_FIGURE_NAME
    if submission_copy.is_file():
        shutil.copyfile(figure, submission_copy)
        shutil.copyfile(sidecar_path_for(figure), sidecar_path_for(submission_copy))
        result.written += [submission_copy, sidecar_path_for(submission_copy)]
    return result


def format_counts_diff(result: RegenerateResult) -> str:
    from src.prisma.diagram import automation_breakdown_lines

    def _val(counts: PRISMACounts | None, name: str) -> str:
        if counts is None:
            return "-"
        value = getattr(counts, name)
        return str(value).lower() if isinstance(value, bool) else f"{value:,}"

    lines = [f"workflow: {result.workflow_id}", f"run dir:  {result.run_dir}"]
    if result.old is None:
        lines.append("old: no prisma_counts.json sidecar (figure predates sidecars)")
    width = max(len(n) for n in FLOW_FIELDS)
    lines.append(f"{'field':<{width}}  {'old':>10}  {'new':>10}")
    for name in FLOW_FIELDS:
        old, new = _val(result.old, name), _val(result.new, name)
        marker = "  *" if result.old is not None and old != new else ""
        lines.append(f"{name:<{width}}  {old:>10}  {new:>10}{marker}")
    breakdown = automation_breakdown_lines(result.new)
    if breakdown:
        lines.append("automation breakdown (new): " + ", ".join(breakdown))
    return "\n".join(lines)


def find_stale_manuscript_counts(text: str, counts: PRISMACounts) -> list[str]:
    """Phrases in manuscript text whose PRISMA number differs from the new counts (heuristic)."""
    examples: list[str] = []
    for field_name, pattern in _MANUSCRIPT_COUNT_PATTERNS:
        expected = int(getattr(counts, field_name))
        for match in pattern.finditer(text):
            if int(match.group(1).replace(",", "")) != expected and match.group(0) not in examples:
                examples.append(match.group(0))
    return examples


def stale_manuscript_warning(result: RegenerateResult) -> str | None:
    if not result.stale_manuscript_examples:
        return None
    return (
        f"Manuscript text still states old PRISMA counts (e.g. '{result.stale_manuscript_examples[0]}'); "
        "re-run the writing phase to update it."
    )
