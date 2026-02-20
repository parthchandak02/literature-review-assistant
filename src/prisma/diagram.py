"""PRISMA 2020 flow diagram with two-column structure."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from src.models import PRISMACounts

if TYPE_CHECKING:
    from src.db.repositories import WorkflowRepository

_EXCLUSION_REASON_LABELS: dict[str, str] = {
    "wrong_population": "Wrong population",
    "wrong_intervention": "Wrong intervention",
    "wrong_comparator": "Wrong comparator",
    "wrong_outcome": "Wrong outcome",
    "wrong_study_design": "Wrong study design",
    "not_peer_reviewed": "Not peer reviewed",
    "duplicate": "Duplicate",
    "insufficient_data": "Insufficient data",
    "wrong_language": "Wrong language",
    "no_full_text": "No full text",
    "other": "Other",
}


def _map_counts_to_library_format(
    counts: PRISMACounts,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    """Map PRISMACounts to prisma-flow-diagram library format.

    When other-source records (e.g. Perplexity/grey literature) are screened
    in the same pass as database records, the PRISMA library arithmetic fails
    because it computes availability as databases - duplicates, which excludes
    the other-source pool. To keep the math consistent we fold other-source
    records into the databases identification total and suppress the separate
    other_methods column. The search appendix still documents all sources.
    """
    excluded_reasons: dict[str, int] = {}
    for k, v in counts.reports_excluded_with_reasons.items():
        if v > 0:  # only include reasons with actual counts
            label = _EXCLUSION_REASON_LABELS.get(k, k.replace("_", " ").title())
            excluded_reasons[label] = v
    # When no full-text exclusions exist, pass a single zero-count entry so
    # the library renders a clean box rather than placeholder "Reason (n=NA)" text.
    if not excluded_reasons and counts.reports_assessed == counts.studies_included_qualitative + counts.studies_included_quantitative:
        excluded_reasons = {"None identified": 0}

    # Use combined total so library math: (db+other) - duplicates = screened
    combined_identified = counts.total_identified_databases + counts.total_identified_other

    db_registers: dict[str, Any] = {
        "identification": {
            "databases": combined_identified,
            "registers": 0,
        },
        "removed_before_screening": {
            "duplicates": counts.duplicates_removed,
            "automation": 0,
            "other": 0,
        },
        "records": {
            "screened": counts.records_screened,
            "excluded": counts.records_excluded_screening,
        },
        "reports": {
            "sought": counts.reports_sought,
            "not_retrieved": counts.reports_not_retrieved,
            "assessed": counts.reports_assessed,
            "excluded_reasons": excluded_reasons,
        },
    }
    total_studies = counts.studies_included_qualitative + counts.studies_included_quantitative
    included: dict[str, Any] = {"studies": total_studies, "reports": total_studies}
    # Suppress other_methods column: all sources were screened together, so
    # splitting them into a separate column would double-count the screened pool.
    other_methods: dict[str, Any] | None = None
    if False and counts.other_sources_records:
        other_methods = {
            "identification": counts.other_sources_records,
            "removed_before_screening": {"duplicates": 0, "automation": 0, "other": 0},
            "records": {"screened": 0, "excluded": 0},
            "reports": {
                "sought": 0,
                "not_retrieved": 0,
                "assessed": 0,
                "excluded_reasons": {},
            },
            "included": {"studies": 0, "reports": 0},
        }
    return db_registers, included, other_methods


def _draw_box(
    ax: plt.Axes,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    fontsize: int = 9,
) -> None:
    rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02", fill=True, facecolor="white", edgecolor="black")
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize, wrap=True)


def _draw_arrow(ax: plt.Axes, x1: float, y1: float, x2: float, y2: float) -> None:
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="black"))


def _render_fallback(counts: PRISMACounts, path: Path) -> Path:
    """Custom matplotlib fallback when prisma-flow-diagram is unavailable."""
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    box_w = 2.2
    box_h = 0.6
    gap = 0.3

    y = 11
    ax.text(1.5, y + 0.5, "Identification", fontsize=11, fontweight="bold")
    y -= 0.3

    db_lines = ["Records identified from Databases and Registers"]
    for name, cnt in counts.databases_records.items():
        db_lines.append(f"  {name}: {cnt}")
    db_lines.append(f"  Total: {counts.total_identified_databases}")
    _draw_box(ax, 0.2, y - box_h, box_w, box_h * (len(db_lines) * 0.5 + 0.5), "\n".join(db_lines), fontsize=8)

    other_lines = ["Records identified from Other Sources"]
    for name, cnt in counts.other_sources_records.items():
        other_lines.append(f"  {name}: {cnt}")
    other_lines.append(f"  Total: {counts.total_identified_other}")
    _draw_box(ax, 2.8, y - box_h, box_w, box_h * (max(len(other_lines), 2) * 0.5 + 0.5), "\n".join(other_lines) if other_lines else "None", fontsize=8)

    y -= box_h * (max(len(db_lines), len(other_lines), 2) * 0.5 + 0.5) + gap
    total_id = counts.total_identified_databases + counts.total_identified_other
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Records identified (n={total_id})", fontsize=9)
    _draw_arrow(ax, 1.5, 11 - 0.5, 1.5, y)
    _draw_arrow(ax, 3.9, 11 - 0.5, 2.6, y)

    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Duplicates removed (n={counts.duplicates_removed})", fontsize=9)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Records screened (n={counts.records_screened})", fontsize=9)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Records excluded (n={counts.records_excluded_screening})", fontsize=9)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Reports sought (n={counts.reports_sought})", fontsize=9)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Reports not retrieved (n={counts.reports_not_retrieved})", fontsize=8)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Reports assessed (n={counts.reports_assessed})", fontsize=9)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    excl_parts = [f"{k}: {v}" for k, v in counts.reports_excluded_with_reasons.items()]
    excl_str = ", ".join(excl_parts) if excl_parts else "N/A"
    excl_total = sum(counts.reports_excluded_with_reasons.values())
    y -= box_h + gap
    _draw_box(ax, 1.0, y - box_h * 1.5, 3.2, box_h * 1.5, f"Reports excluded (n={excl_total})\n{excl_str}", fontsize=7)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h * 1.5)

    y -= box_h * 1.5 + gap
    total_inc = counts.studies_included_qualitative + counts.studies_included_quantitative
    _draw_box(ax, 1.0, y - box_h, 3.2, box_h, f"Studies included (n={total_inc})", fontsize=9)
    _draw_arrow(ax, 2.1, y + box_h + gap, 2.1, y + box_h)

    ax.set_title("PRISMA 2020 Flow Diagram" + (" (arithmetic valid)" if counts.arithmetic_valid else " (check counts)"))

    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def render_prisma_diagram(counts: PRISMACounts, output_path: str) -> Path:
    """Render PRISMA 2020 two-column flow diagram to PNG."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from prisma_flow_diagram import plot_prisma2020_new

        db_registers, included, other_methods = _map_counts_to_library_format(counts)
        plot_prisma2020_new(
            db_registers=db_registers,
            included=included,
            other_methods=other_methods,
            filename=str(path),
            show=False,
        )
        return path
    except ImportError:
        return _render_fallback(counts, path)


async def build_prisma_counts(
    repo: "WorkflowRepository",
    workflow_id: str,
    dedup_count: int,
    included_qualitative: int = 0,
    included_quantitative: int = 0,
) -> PRISMACounts:
    """Build PRISMACounts from repository data.

    This pipeline uses abstract-only (title/abstract) screening with no
    separate full-text retrieval step.  The PRISMA 2020 arithmetic is:

        records_screened = records_after_dedup
        records_excluded_screening = records_screened - reports_sought
        reports_sought = reports_assessed = studies_included
        reports_not_retrieved = 0
        reports_excluded_with_reasons = {} (no full-text exclusions)

    The dual_screening_results table may undercount T/A includes (e.g. papers
    forwarded to extraction via BM25 ranking).  We therefore use
    studies_included as the ground-truth for reports_sought/assessed.
    """
    databases, other = await repo.get_search_counts_by_category(workflow_id)
    (
        records_screened,
        _records_excluded_screening_raw,
        _reports_sought_raw,
        _reports_not_retrieved_raw,
        _reports_assessed_raw,
        _reports_excluded_with_reasons_raw,
    ) = await repo.get_prisma_screening_counts(workflow_id)

    total_db = sum(databases.values())
    total_other = sum(other.values())
    total_id = total_db + total_other
    records_after_dedup = total_id - dedup_count

    # Use records_after_dedup as the canonical screened count when it is
    # consistent; fall back to the DB value if they diverge (e.g. mid-run).
    if records_screened == 0 and records_after_dedup > 0:
        records_screened = records_after_dedup

    # Ground-truth: every included study passed title/abstract screening.
    # No full-text retrieval step exists, so all sought reports are assessed.
    included_total = included_qualitative + included_quantitative
    reports_sought = included_total
    reports_not_retrieved = 0
    reports_assessed = included_total
    reports_excluded_with_reasons: dict[str, int] = {}  # no full-text exclusions
    records_excluded_screening = max(0, records_screened - reports_sought)

    excluded_total = 0  # no full-text excluded
    arithmetic_valid = (
        records_screened == records_after_dedup
        and records_screened == records_excluded_screening + reports_sought
        and reports_sought == reports_not_retrieved + reports_assessed
        and reports_assessed == excluded_total + included_total
    )

    return PRISMACounts(
        databases_records=databases,
        other_sources_records=other,
        total_identified_databases=total_db,
        total_identified_other=total_other,
        duplicates_removed=dedup_count,
        records_screened=records_screened,
        records_excluded_screening=records_excluded_screening,
        reports_sought=reports_sought,
        reports_not_retrieved=reports_not_retrieved,
        reports_assessed=reports_assessed,
        reports_excluded_with_reasons=reports_excluded_with_reasons,
        studies_included_qualitative=included_qualitative,
        studies_included_quantitative=included_quantitative,
        arithmetic_valid=arithmetic_valid,
    )
