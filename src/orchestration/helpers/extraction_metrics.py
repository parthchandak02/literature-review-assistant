from __future__ import annotations

import json
import logging
from pathlib import Path

from src.models import CandidatePaper, ExtractionRecord
from src.writing.context_builder import sanitize_summary_text_for_writing

logger = logging.getLogger(__name__)

ABSTRACT_ONLY_EXTRACTION_SOURCES = frozenset({"text", "heuristic", "", None})


def has_participant_evidence(record: ExtractionRecord) -> bool:
    if bool(record.participant_count and record.participant_count > 0):
        return True
    demographics_text = sanitize_summary_text_for_writing(record.participant_demographics or "")
    return demographics_text != "NR"


def compute_extraction_quality_metrics(
    records: list[ExtractionRecord],
    included_papers: list[CandidatePaper],
    fulltext_paper_ids: set[str] | None = None,
) -> tuple[float, float, str]:
    if not records:
        return 1.0, 0.0, "included_records=0"

    included_ids = {paper.paper_id for paper in included_papers if paper.paper_id}
    relevant_records = [record for record in records if record.paper_id in included_ids] if included_ids else records
    if not relevant_records:
        relevant_records = records

    total = len(relevant_records)
    summary_present = 0
    participant_present = 0
    fulltext_backed = 0
    weak_evidence_records = 0

    for record in relevant_records:
        summary_text = sanitize_summary_text_for_writing((record.results_summary or {}).get("summary", ""))
        has_summary = summary_text != "NR"
        has_participants = has_participant_evidence(record)
        if fulltext_paper_ids is not None:
            has_fulltext = record.paper_id in fulltext_paper_ids
        else:
            has_fulltext = (record.extraction_source or "text") not in ABSTRACT_ONLY_EXTRACTION_SOURCES
        summary_present += int(has_summary)
        participant_present += int(has_participants)
        fulltext_backed += int(has_fulltext)
        if not (has_summary and has_participants and has_fulltext):
            weak_evidence_records += 1

    summary_ratio = summary_present / total
    participant_ratio = participant_present / total
    fulltext_ratio = fulltext_backed / total
    completeness_ratio = (summary_ratio + participant_ratio + fulltext_ratio) / 3.0
    weak_evidence_rate = weak_evidence_records / total
    details = (
        f"included_records={total}, summary_ratio={summary_ratio:.2f}, "
        f"participant_ratio={participant_ratio:.2f}, fulltext_ratio={fulltext_ratio:.2f}"
    )
    return completeness_ratio, weak_evidence_rate, details


def load_fulltext_artifact_paper_ids(run_artifacts: dict[str, str], db_path: str) -> set[str]:
    fulltext_paper_ids: set[str] = set()
    manifest_path = Path(run_artifacts.get("papers_manifest", ""))
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest_data, dict):
                for paper_id, entry in manifest_data.items():
                    if isinstance(entry, dict) and entry.get("file_path"):
                        fulltext_paper_ids.add(str(paper_id))
            elif isinstance(manifest_data, list):
                for entry in manifest_data:
                    if isinstance(entry, dict) and entry.get("paper_id") and entry.get("file_path"):
                        fulltext_paper_ids.add(str(entry["paper_id"]))
        except Exception as exc:
            logger.warning("Could not read papers manifest for extraction metrics: %s", exc)
    if fulltext_paper_ids:
        return fulltext_paper_ids

    papers_dir = (
        Path(run_artifacts.get("papers_dir", ""))
        if run_artifacts.get("papers_dir")
        else Path(db_path).parent / "papers"
    )
    if papers_dir.exists():
        for paper_file in papers_dir.iterdir():
            if paper_file.is_file() and paper_file.suffix.lower() in {".pdf", ".txt"}:
                fulltext_paper_ids.add(paper_file.stem)
    return fulltext_paper_ids
