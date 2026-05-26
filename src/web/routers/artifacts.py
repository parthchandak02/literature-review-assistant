"""Run artifacts, export, readiness, diagnostics, and document download endpoints."""

from __future__ import annotations

import asyncio
import io
import json as _json
import logging
import pathlib
import zipfile
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

import aiosqlite
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from src.config.loader import load_configs as _load_configs
from src.export.submission_packager import package_submission
from src.manuscript.readiness import compute_readiness_scorecard
from src.web.diagnostics_utils import summarize_phase_performance
from src.web.shared import (
    _format_manuscript_audit_summary,
    _get_topic_for_db,
    _make_download_slug,
    _query_included_papers_rows,
    _resolve_db_path,
    _resolve_workflow_id_from_db,
)
from src.web.state import (
    _active_runs,
    _get_db_path,
    _resolve_db_path_from_run_or_workflow,
)

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["artifacts"])


# ---------------------------------------------------------------------------
# Helpers local to this router
# ---------------------------------------------------------------------------


async def _load_phase_metric_map(
    db: aiosqlite.Connection,
    workflow_id: str,
    *,
    phase: str,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    async with db.execute(
        """
        SELECT rationale
        FROM decision_log
        WHERE workflow_id = ?
          AND decision_type = 'screening_metric'
          AND phase = ?
        ORDER BY id ASC
        """,
        (workflow_id, phase),
    ) as cur:
        rows = await cur.fetchall()
    for row in rows:
        try:
            payload = _json.loads(str(row["rationale"] or "{}"))
        except Exception:
            continue
        metric_name = payload.get("metric")
        metric_value = payload.get("value")
        if isinstance(metric_name, str) and isinstance(metric_value, (int, float)):
            metrics[metric_name] = float(metric_value)
    return metrics


async def _load_latest_event_payload(
    db: aiosqlite.Connection,
    workflow_id: str,
    event_type: str,
) -> dict[str, Any]:
    async with db.execute(
        """
        SELECT payload
        FROM event_log
        WHERE workflow_id = ? AND event_type = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (workflow_id, event_type),
    ) as cur:
        row = await cur.fetchone()
    if not row or not row["payload"]:
        return {}
    try:
        payload = _json.loads(str(row["payload"]))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _build_screening_diagnostics(
    db: aiosqlite.Connection,
    workflow_id: str,
) -> dict[str, Any]:
    metrics = await _load_phase_metric_map(db, workflow_id, phase="phase_3_screening")
    prefilter_event = await _load_latest_event_payload(db, workflow_id, "screening_prefilter_done")
    batch_event = await _load_latest_event_payload(db, workflow_id, "batch_screen_done")

    stage_summary: dict[str, dict[str, int]] = {
        "title_abstract": {"total": 0, "disagreements": 0, "adjudications": 0},
        "fulltext": {"total": 0, "disagreements": 0, "adjudications": 0},
    }
    async with db.execute(
        """
        SELECT stage,
               COUNT(*) AS total,
               SUM(CASE WHEN agreement = 0 THEN 1 ELSE 0 END) AS disagreements,
               SUM(CASE WHEN adjudication_needed = 1 THEN 1 ELSE 0 END) AS adjudications
        FROM dual_screening_results
        WHERE workflow_id = ?
        GROUP BY stage
        """,
        (workflow_id,),
    ) as cur:
        rows = await cur.fetchall()
    for row in rows:
        stage_name = str(row["stage"] or "")
        if stage_name not in stage_summary:
            continue
        stage_summary[stage_name] = {
            "total": int(row["total"] or 0),
            "disagreements": int(row["disagreements"] or 0),
            "adjudications": int(row["adjudications"] or 0),
        }

    async with db.execute(
        """
        SELECT COUNT(*) AS count
        FROM screening_decisions
        WHERE workflow_id = ?
          AND stage = 'fulltext'
          AND exclusion_reason = ?
        """,
        (workflow_id, "no_full_text"),
    ) as cur:
        no_fulltext_row = await cur.fetchone()
    no_fulltext_excluded = int(no_fulltext_row["count"] or 0) if no_fulltext_row else 0

    fulltext_sought = int(metrics.get("fulltext_sought", stage_summary["fulltext"]["total"]))
    fulltext_not_retrieved = int(metrics.get("fulltext_not_retrieved", no_fulltext_excluded))
    fulltext_retrieved = max(fulltext_sought - fulltext_not_retrieved, 0)

    reason_breakdown = prefilter_event.get("reason_breakdown", {})
    if not isinstance(reason_breakdown, dict):
        reason_breakdown = {}

    return {
        "prefilter": {
            "metadata_rejected": int(
                prefilter_event.get("metadata_rejected", metrics.get("prefilter_metadata_rejected", 0))
            ),
            "automation_excluded": int(
                prefilter_event.get("automation_excluded", metrics.get("prefilter_automation_excluded", 0))
            ),
            "to_llm": int(prefilter_event.get("to_llm", metrics.get("prefilter_to_llm", 0))),
            "keyword_filter_excluded": int(
                prefilter_event.get("keyword_filter_excluded", metrics.get("keyword_filter_excluded", 0))
            ),
            "keyword_fallback_applied": bool(
                prefilter_event.get("keyword_fallback_applied", metrics.get("keyword_fallback_applied", 0))
            ),
            "keyword_fallback_threshold": float(prefilter_event.get("keyword_fallback_threshold", 0.0) or 0.0),
            "empty_abstract_pool": int(
                prefilter_event.get("empty_abstract_pool", metrics.get("empty_abstract_pool", 0))
            ),
            "empty_abstract_excluded": int(
                prefilter_event.get("empty_abstract_excluded", metrics.get("empty_abstract_excluded", 0))
            ),
            "empty_abstract_rescued": int(
                prefilter_event.get("empty_abstract_rescued", metrics.get("empty_abstract_rescued", 0))
            ),
            "reason_breakdown": {str(k): int(v) for k, v in reason_breakdown.items() if isinstance(v, (int, float))},
        },
        "batch_ranker": {
            "scored": int(batch_event.get("scored", 0)),
            "forwarded": int(batch_event.get("forwarded", 0)),
            "excluded": int(batch_event.get("excluded", 0)),
            "borderline_forwarded": int(
                batch_event.get("borderline_forwarded", metrics.get("batch_borderline_forwarded", 0))
            ),
            "skipped_resume": int(batch_event.get("skipped_resume", 0)),
            "threshold": float(batch_event.get("threshold", 0.0) or 0.0),
            "validation_forwarded": int(metrics.get("bm25_validation_forwarded", 0)),
            "parse_degraded": int(metrics.get("batch_parse_degraded", 0)),
            "id_mismatch": int(metrics.get("batch_id_mismatch", 0)),
            "missing_fallback": int(metrics.get("batch_missing_fallback", 0)),
            "contract_violation_count": int(metrics.get("contract_violation_count", 0)),
        },
        "dual_review": {
            "fast_path_include": int(metrics.get("title_abstract_fast_path_include", 0)),
            "fast_path_exclude": int(metrics.get("title_abstract_fast_path_exclude", 0)),
            "cross_reviewed": int(metrics.get("title_abstract_cross_reviewed", 0)),
            "title_abstract": stage_summary["title_abstract"],
            "fulltext": stage_summary["fulltext"],
        },
        "fulltext": {
            "sought": fulltext_sought,
            "retrieved": fulltext_retrieved,
            "not_retrieved": fulltext_not_retrieved,
            "no_full_text_excluded": int(metrics.get("fulltext_no_full_text_excluded", no_fulltext_excluded)),
        },
    }


async def _build_extraction_diagnostics(
    repo: Any,
    db: aiosqlite.Connection,
    workflow_id: str,
    db_path: str,
) -> dict[str, Any]:
    from src.orchestration.helpers.extraction_metrics import (
        ABSTRACT_ONLY_EXTRACTION_SOURCES as _ABSTRACT_ONLY_EXTRACTION_SOURCES,
    )
    from src.orchestration.helpers.extraction_metrics import (
        compute_extraction_quality_metrics as _compute_extraction_quality_metrics,
    )
    from src.orchestration.helpers.extraction_metrics import (
        load_fulltext_artifact_paper_ids as _load_fulltext_artifact_paper_ids,
    )
    from src.writing.context_builder import sanitize_summary_text_for_writing

    records = await repo.load_extraction_records(workflow_id)
    included_ids = await repo.get_included_paper_ids(workflow_id)
    included_papers = await repo.load_papers_by_ids(included_ids) if included_ids else []
    fulltext_paper_ids = _load_fulltext_artifact_paper_ids(
        {"papers_manifest": str(pathlib.Path(db_path).parent / "data_papers_manifest.json")},
        db_path,
    )
    relevant_ids = {paper.paper_id for paper in included_papers if paper.paper_id}
    relevant_records = [record for record in records if record.paper_id in relevant_ids] if relevant_ids else records
    if not relevant_records:
        return {
            "included_records": 0,
            "summary_backed_count": 0,
            "participant_detail_count": 0,
            "fulltext_backed_count": 0,
            "abstract_only_count": 0,
            "weak_evidence_count": 0,
            "completeness_ratio": 0.0,
            "weak_evidence_rate": 0.0,
            "metric_details": "included_records=0",
            "gate_result": None,
        }

    completeness_ratio, weak_evidence_rate, metric_details = _compute_extraction_quality_metrics(
        records,
        included_papers,
        fulltext_paper_ids=fulltext_paper_ids,
    )
    summary_backed_count = 0
    participant_detail_count = 0
    fulltext_backed_count = 0
    weak_evidence_count = 0
    for record in relevant_records:
        summary_text = sanitize_summary_text_for_writing((record.results_summary or {}).get("summary", ""))
        has_summary = summary_text != "NR"
        has_participants = bool(record.participant_count and record.participant_count > 0)
        if fulltext_paper_ids:
            has_fulltext = record.paper_id in fulltext_paper_ids
        else:
            has_fulltext = (record.extraction_source or "text") not in _ABSTRACT_ONLY_EXTRACTION_SOURCES
        summary_backed_count += int(has_summary)
        participant_detail_count += int(has_participants)
        fulltext_backed_count += int(has_fulltext)
        if not (has_summary and has_participants and has_fulltext):
            weak_evidence_count += 1

    async with db.execute(
        """
        SELECT status, details, threshold, actual_value
        FROM gate_results
        WHERE workflow_id = ?
          AND phase = 'phase_4_extraction_quality'
          AND gate_name = 'extraction_completeness'
        ORDER BY id DESC
        LIMIT 1
        """,
        (workflow_id,),
    ) as cur:
        gate_row = await cur.fetchone()

    gate_result = None
    if gate_row:
        gate_result = {
            "status": str(gate_row["status"] or ""),
            "details": str(gate_row["details"] or ""),
            "threshold": str(gate_row["threshold"] or ""),
            "actual_value": str(gate_row["actual_value"] or ""),
        }

    if gate_result:
        parsed: dict[str, float] = {}
        for part in str(gate_result["details"]).split(","):
            key, sep, value = part.strip().partition("=")
            if not sep:
                continue
            try:
                parsed[key.strip()] = float(value.strip())
            except ValueError:
                continue
        actual_parts: dict[str, float] = {}
        for part in str(gate_result["actual_value"]).split(","):
            key, sep, value = part.strip().partition("=")
            if not sep:
                continue
            try:
                actual_parts[key.strip()] = float(value.strip())
            except ValueError:
                continue
        included_from_gate = int(round(parsed.get("included_records", float(len(relevant_records)))))
        summary_ratio = float(parsed.get("summary_ratio", 0.0))
        participant_ratio = float(parsed.get("participant_ratio", 0.0))
        fulltext_ratio = float(parsed.get("fulltext_ratio", 0.0))
        completeness_ratio = float(actual_parts.get("completeness", completeness_ratio))
        weak_evidence_rate = float(actual_parts.get("weak", weak_evidence_rate))
        summary_backed_count = int(round(included_from_gate * summary_ratio))
        participant_detail_count = int(round(included_from_gate * participant_ratio))
        fulltext_backed_count = int(round(included_from_gate * fulltext_ratio))
        weak_evidence_count = int(round(included_from_gate * weak_evidence_rate))
        relevant_record_count = included_from_gate
        metric_details = str(gate_result["details"])
    else:
        relevant_record_count = len(relevant_records)

    return {
        "included_records": relevant_record_count,
        "summary_backed_count": summary_backed_count,
        "participant_detail_count": participant_detail_count,
        "fulltext_backed_count": fulltext_backed_count,
        "abstract_only_count": max(relevant_record_count - fulltext_backed_count, 0),
        "weak_evidence_count": weak_evidence_count,
        "completeness_ratio": round(completeness_ratio, 4),
        "weak_evidence_rate": round(weak_evidence_rate, 4),
        "metric_details": metric_details,
        "gate_result": gate_result,
    }


def _extract_topic(review_yaml: str) -> str:
    import yaml

    try:
        data = yaml.safe_load(review_yaml)
        return str(data.get("research_question", "Untitled review"))
    except Exception:
        return "Untitled review"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/run/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> dict[str, Any]:
    db_path = _get_db_path(run_id)
    summary = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    return _json.loads(summary.read_text(encoding="utf-8"))


@router.get("/api/results/{run_id}", include_in_schema=False)
async def get_results_legacy(run_id: str) -> dict[str, Any]:
    return await get_run_artifacts(run_id)


@router.get("/api/run/{run_id}/manuscript")
async def get_run_manuscript(run_id: str, fmt: str = "md") -> dict[str, Any]:
    if fmt not in {"md", "tex"}:
        raise HTTPException(status_code=422, detail="fmt must be 'md' or 'tex'")
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    workflow_id = await _resolve_workflow_id_from_db(db_path)
    if workflow_id:
        try:
            from src.db.database import get_db as _get_db
            from src.db.repositories import WorkflowRepository as _WorkflowRepository

            async with _get_db(db_path) as db:
                repo = _WorkflowRepository(db)
                assembly = await repo.load_latest_manuscript_assembly(workflow_id, fmt)
            if assembly:
                return {
                    "source": "assembly",
                    "format": fmt,
                    "workflow_id": workflow_id,
                    "content": assembly.content,
                    "assembly_id": assembly.assembly_id,
                }
        except Exception:
            pass

    run_dir = pathlib.Path(db_path).parent
    file_path = run_dir / ("doc_manuscript.md" if fmt == "md" else "doc_manuscript.tex")
    if file_path.exists():
        return {
            "source": "file",
            "format": fmt,
            "workflow_id": workflow_id or "",
            "content": file_path.read_text(encoding="utf-8"),
            "path": str(file_path),
        }
    raise HTTPException(status_code=404, detail=f"manuscript ({fmt}) not found")


@router.get("/api/run/{run_id}/papers-reference")
async def get_papers_reference(run_id: str) -> dict[str, Any]:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    manifest_path = run_dir / "data_papers_manifest.json"

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            _resolved_workflow_id = run_id
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as _wf_cur:
                _wf_row = await _wf_cur.fetchone()
                if _wf_row and _wf_row[0]:
                    _resolved_workflow_id = str(_wf_row[0])
            rows = await _query_included_papers_rows(db, _resolved_workflow_id, for_fetch=False)

        papers_out = []
        for row in rows:
            paper_id = row["paper_id"]
            raw_authors = row["authors"] or ""
            try:
                authors_list = _json.loads(raw_authors) if raw_authors.startswith("[") else [raw_authors]
                authors_fmt = ", ".join(
                    (a.get("name") or a.get("raw_name") or str(a)) if isinstance(a, dict) else str(a)
                    for a in authors_list
                )
            except Exception:
                authors_fmt = raw_authors

            entry = manifest.get(paper_id, {})
            file_type = entry.get("file_type")
            has_file = bool(entry.get("file_path") and pathlib.Path(entry["file_path"]).exists())

            papers_out.append(
                {
                    "paper_id": paper_id,
                    "title": row["title"],
                    "authors": authors_fmt,
                    "year": row["year"],
                    "source_database": row["source_database"],
                    "doi": row["doi"] or entry.get("doi", ""),
                    "url": row["url"] or entry.get("url", ""),
                    "country": row["country"],
                    "retrieval_source": entry.get("source", "abstract"),
                    "has_file": has_file,
                    "file_type": file_type,
                }
            )

        return {"papers": papers_out, "total": len(papers_out)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/run/{run_id}/papers/{paper_id}/file")
async def get_paper_file(run_id: str, paper_id: str) -> StreamingResponse:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    manifest_path = run_dir / "data_papers_manifest.json"

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="No papers manifest found for this run.")

    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read manifest: {exc}") from exc

    entry = manifest.get(paper_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Paper {paper_id} not in manifest.")

    file_path_str = entry.get("file_path")
    if not file_path_str:
        raise HTTPException(
            status_code=404, detail="Full-text file not available for this paper. Extraction used abstract only."
        )

    file_path = pathlib.Path(file_path_str)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Full-text file not found on disk.")

    media_type = "application/pdf" if file_path.suffix == ".pdf" else "text/plain"
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in (entry.get("title", paper_id)[:60]))
    filename = f"{safe_title}{file_path.suffix}"

    async def file_iterator() -> Any:
        with open(file_path, "rb") as fh:
            while chunk := fh.read(65536):
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/run/{run_id}/studies-files.zip")
async def download_study_files_zip(run_id: str) -> StreamingResponse:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    manifest_path = run_dir / "data_papers_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="No papers manifest found for this run.")

    try:
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=500, detail="Invalid papers manifest format.")

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            resolved_workflow_id = run_id
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as wf_cur:
                wf_row = await wf_cur.fetchone()
                if wf_row and wf_row[0]:
                    resolved_workflow_id = str(wf_row[0])
            rows = await _query_included_papers_rows(db, resolved_workflow_id, for_fetch=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=404, detail="No included studies found for this run.")

    included_ids = {str(row["paper_id"]) for row in rows}
    zip_entries: list[tuple[pathlib.Path, str]] = []
    for paper_id in sorted(included_ids):
        entry = manifest.get(paper_id, {})
        if not isinstance(entry, dict):
            continue
        file_path_str = entry.get("file_path")
        if not file_path_str:
            continue
        file_path = pathlib.Path(file_path_str)
        if not file_path.exists() or not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix not in {".pdf", ".txt"}:
            continue
        zip_entries.append((file_path, f"{paper_id}{suffix}"))

    if not zip_entries:
        raise HTTPException(
            status_code=404, detail="No downloadable study files found (PDF/TXT not available for included studies)."
        )

    workflow_id = await _resolve_workflow_id_from_db(db_path)
    topic = await _get_topic_for_db(db_path)
    zip_name = _make_download_slug(workflow_id or run_id, topic) + "-studies-files.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path, arcname in zip_entries:
            zf.write(file_path, arcname=arcname)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.post("/api/run/{run_id}/fetch-pdfs")
async def fetch_pdfs_for_run(run_id: str) -> StreamingResponse:
    """Retroactively fetch full-text PDFs/text for all included papers in a completed run."""
    from src.models.papers import CandidatePaper
    from src.search.pdf_retrieval import PDFRetriever

    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    run_dir = pathlib.Path(db_path).parent
    papers_dir = run_dir / "papers"
    manifest_path = run_dir / "data_papers_manifest.json"

    papers_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA synchronous = NORMAL")
            await db.execute("PRAGMA foreign_keys = ON")
            _resolved_workflow_id = run_id
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as _wf_cur:
                _wf_row = await _wf_cur.fetchone()
                if _wf_row and _wf_row[0]:
                    _resolved_workflow_id = str(_wf_row[0])
            rows = await _query_included_papers_rows(db, _resolved_workflow_id, for_fetch=True)
    except Exception as exc:
        _fetch_err = str(exc)

        async def _error_stream() -> AsyncGenerator[str, None]:
            yield f"data: {_json.dumps({'type': 'error', 'detail': _fetch_err})}\n\n"

        return StreamingResponse(
            _error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _pdf_fetch_stream() -> AsyncGenerator[str, None]:
        def _reason_class(reason_code: str | None) -> str:
            if not reason_code:
                return "unknown"
            if reason_code == "oa_recovered":
                return "success"
            if reason_code in {"publisher_401", "publisher_403", "paywalled"}:
                return "paywall_or_auth"
            if reason_code in {"bot_blocked", "cookie_wall", "rate_limited"}:
                return "bot_or_access_blocked"
            if reason_code in {"metadata_only_endpoint", "pdf_link_missing", "no_pdf_signal"}:
                return "metadata_or_no_pdf"
            if reason_code in {"identifier_missing", "doi_unresolved", "no_identifier"}:
                return "identifier_resolution"
            if reason_code in {"timeout", "unexpected_error", "exception"}:
                return "execution_error"
            return "resolver_exhausted"

        def _host_from_url(value: str | None) -> str:
            if not value:
                return "unknown"
            host = urlparse(value).netloc.lower()
            return host or "unknown"

        retriever = PDFRetriever()
        results: list[dict[str, Any]] = []
        succeeded = 0
        skipped = 0
        total = len(rows)

        yield f"data: {_json.dumps({'type': 'start', 'total': total})}\n\n"

        fetch_work: list[tuple[int, Any]] = []
        for idx, row in enumerate(rows):
            paper_id = row["paper_id"]
            title = row["title"] or "Untitled"
            existing = manifest.get(paper_id, {})
            existing_path = existing.get("file_path")
            if existing_path and pathlib.Path(existing_path).exists():
                skipped += 1
                results.append(
                    {
                        "paper_id": paper_id,
                        "status": "skipped",
                        "source": existing.get("source"),
                        "reason_code": existing.get("reason_code"),
                        "reason_class": _reason_class(existing.get("reason_code")),
                        "host": _host_from_url(existing.get("url")),
                        "diagnostics": existing.get("diagnostics", []),
                    }
                )
                yield f"data: {_json.dumps({'type': 'progress', 'current': idx + 1, 'total': total, 'paper_id': paper_id, 'title': title, 'status': 'skipped', 'source': existing.get('source')})}\n\n"
            else:
                fetch_work.append((idx, row))

        if fetch_work:
            _sem = asyncio.Semaphore(8)

            async def _fetch_one(orig_idx: int, row: Any) -> tuple:
                paper_id = row["paper_id"]
                doi = row["doi"] or ""
                url = row["url"] or ""
                title = row["title"] or "Untitled"
                saved_path: str | None = None
                source: str = "abstract"
                reason_code: str | None = None
                diagnostics: list[str] = []
                error_msg: str | None = None
                async with _sem:
                    try:
                        paper = CandidatePaper(
                            paper_id=paper_id,
                            title=title,
                            authors=[],
                            year=row["year"],
                            source_database=row["source_database"] or "",
                            doi=doi or None,
                            url=url or None,
                        )
                        ft_result = await retriever.retrieve(paper)
                        reason_code = ft_result.reason_code
                        diagnostics = list(ft_result.diagnostics or [])
                        if ft_result.success and ft_result.pdf_bytes and len(ft_result.pdf_bytes) > 1000:
                            pdf_dest = papers_dir / f"{paper_id}.pdf"
                            pdf_dest.write_bytes(ft_result.pdf_bytes)
                            saved_path = str(pdf_dest)
                            source = ft_result.source
                        elif ft_result.success and ft_result.full_text and len(ft_result.full_text) >= 500:
                            txt_dest = papers_dir / f"{paper_id}.txt"
                            txt_dest.write_text(ft_result.full_text, encoding="utf-8")
                            saved_path = str(txt_dest)
                            source = ft_result.source
                        else:
                            source = ft_result.source if ft_result.success else "abstract"
                            if not ft_result.success and ft_result.error:
                                error_msg = ft_result.error
                    except Exception as exc:  # noqa: BLE001
                        error_msg = str(exc)
                        reason_code = "exception"
                        _logger.warning("fetch-pdfs: failed for %s: %s", paper_id, exc)
                return (orig_idx, paper_id, title, saved_path, source, reason_code, diagnostics, error_msg)

            gathered = await asyncio.gather(
                *[_fetch_one(idx, row) for idx, row in fetch_work],
                return_exceptions=True,
            )
            for item in sorted(
                (r for r in gathered if not isinstance(r, BaseException)),
                key=lambda t: t[0],
            ):
                orig_idx, paper_id, title, saved_path, source, reason_code, diagnostics, error_msg = item
                doi = rows[orig_idx]["doi"] or ""
                url = rows[orig_idx]["url"] or ""
                file_type = "pdf" if (saved_path and saved_path.endswith(".pdf")) else ("txt" if saved_path else None)
                manifest[paper_id] = {
                    "title": title,
                    "authors": rows[orig_idx]["authors"] or "",
                    "year": rows[orig_idx]["year"],
                    "doi": doi,
                    "url": url,
                    "source": source,
                    "reason_code": reason_code,
                    "diagnostics": diagnostics[-8:] if diagnostics else [],
                    "file_path": saved_path,
                    "file_type": file_type,
                }
                result_status = "ok" if saved_path else "failed"
                if saved_path:
                    succeeded += 1
                results.append(
                    {
                        "paper_id": paper_id,
                        "status": result_status,
                        "source": source,
                        "reason_code": reason_code,
                        "reason_class": _reason_class(reason_code),
                        "host": _host_from_url(url),
                        "file_type": file_type,
                        "diagnostics": diagnostics[-6:] if diagnostics else [],
                        "error": error_msg,
                    }
                )
                yield f"data: {_json.dumps({'type': 'progress', 'current': orig_idx + 1, 'total': total, 'paper_id': paper_id, 'title': title, 'status': result_status, 'source': source, 'file_type': file_type})}\n\n"

        manifest_path.write_text(_json.dumps(manifest, indent=2), encoding="utf-8")

        attempted = total - skipped
        failed = attempted - succeeded
        reason_counts: dict[str, int] = {}
        reason_class_counts: dict[str, int] = {}
        host_rollups: dict[str, dict[str, int]] = {}
        for r in results:
            host = r.get("host") or "unknown"
            host_bucket = host_rollups.setdefault(host, {"ok": 0, "failed": 0, "skipped": 0})
            status = r.get("status")
            if status in {"ok", "failed", "skipped"}:
                host_bucket[status] += 1
            reason = r.get("reason_code")
            if not reason:
                continue
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            reason_class = r.get("reason_class") or "unknown"
            reason_class_counts[reason_class] = reason_class_counts.get(reason_class, 0) + 1
        yield f"data: {_json.dumps({'type': 'done', 'attempted': attempted, 'succeeded': succeeded, 'failed': failed, 'skipped': skipped, 'reason_counts': reason_counts, 'reason_class_counts': reason_class_counts, 'host_rollups': host_rollups, 'results': results})}\n\n"

    return StreamingResponse(
        _pdf_fetch_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/run/{run_id}/events")
async def get_run_events(run_id: str) -> dict[str, Any]:
    record = _active_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"events": record.event_log}


@router.get("/api/workflow/{workflow_id}/events")
async def get_workflow_events(workflow_id: str, run_root: str = "runs") -> dict[str, Any]:
    from src.web.state import _load_event_log_from_db

    db_path = await _resolve_db_path(run_root, workflow_id)
    if not db_path:
        raise HTTPException(status_code=404, detail="Workflow not found in registry")
    events = await _load_event_log_from_db(db_path)
    return {"events": events}


@router.post("/api/run/{run_id}/export")
async def trigger_export(run_id: str, run_root: str = "runs", force: bool = False) -> dict[str, Any]:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    workflow_id: str | None = summary.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id not found in run_summary")

    if not force:
        output_dir = summary.get("output_dir", "")
        if output_dir:
            _sub_dir = pathlib.Path(output_dir) / "submission"
            _study_pdfs_dir = _sub_dir / "study_pdfs"
            _key_files = [_sub_dir / "manuscript.tex", _sub_dir / "references.bib", _sub_dir / "manuscript.docx"]
            if all(f.exists() for f in _key_files) and _study_pdfs_dir.exists():
                files = sorted(str(f) for f in _sub_dir.rglob("*") if f.is_file())
                return {"submission_dir": str(_sub_dir), "files": files}
    try:
        submission_dir = await package_submission(workflow_id, run_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
    if submission_dir is None:
        raise HTTPException(status_code=500, detail="Export failed: manuscript not found")
    files = sorted(str(f) for f in submission_dir.rglob("*") if f.is_file())
    return {"submission_dir": str(submission_dir), "files": files}


@router.get("/api/run/{run_id}/readiness")
async def get_run_readiness(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    workflow_id = summary.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id not found in run_summary")
    manuscript_md = summary.get("artifacts", {}).get("manuscript_md")
    if not manuscript_md or not pathlib.Path(str(manuscript_md)).exists():
        raise HTTPException(status_code=404, detail="manuscript_md not found")
    manuscript_tex = summary.get("artifacts", {}).get("manuscript_tex")
    cfg = _load_configs()[1]
    mode = getattr(getattr(cfg, "gates", None), "manuscript_contract_mode", "strict")
    latest_audit: dict[str, Any] | None = None
    try:
        from src.db.database import get_db as _get_db
        from src.db.repositories import WorkflowRepository as _WorkflowRepository

        async with _get_db(db_path) as db:
            latest_audit = await _WorkflowRepository(db).get_latest_manuscript_audit(str(workflow_id))
    except Exception:
        latest_audit = None
    extra_paths: list[str] = []
    for _k in ("protocol", "prospero_form_md"):
        _p = summary.get("artifacts", {}).get(_k)
        if _p and pathlib.Path(str(_p)).is_file():
            extra_paths.append(str(_p))
    tex_resolved = str(manuscript_tex) if manuscript_tex and pathlib.Path(str(manuscript_tex)).is_file() else None
    try:
        scorecard = await compute_readiness_scorecard(
            db_path=db_path,
            workflow_id=str(workflow_id),
            manuscript_md_path=str(manuscript_md),
            manuscript_tex_path=tex_resolved,
            extra_artifact_paths=extra_paths,
            contract_mode=mode,
            abstract_word_limit=cfg.ieee_export.max_abstract_words,
            abstract_minimum_words=cfg.writing.abstract_trim_floor_words,
        )
        payload = scorecard.model_dump()
    except Exception as exc:
        payload = {
            "workflow_id": str(workflow_id),
            "ready": False,
            "contract_ready": False,
            "audit_ready": False,
            "submission_ready": False,
            "checks": [{"name": "readiness_runtime", "ok": False, "detail": str(exc)}],
            "contract_passed": False,
            "citation_lineage_valid": False,
            "fallback_event_count": 0,
            "blocking_reasons": [f"readiness computation failed: {exc}"],
        }
    payload["audit_summary"] = _format_manuscript_audit_summary(latest_audit)
    return payload


@router.get("/api/run/{run_id}/diagnostics")
async def get_run_diagnostics(run_id: str, run_root: str = "runs") -> dict[str, Any]:
    from src.db.database import get_db as _get_db
    from src.db.repositories import WorkflowRepository as _WorkflowRepository

    db_path = await _resolve_db_path_from_run_or_workflow(run_id, run_root)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    workflow_id: str | None = None
    if summary_path.exists():
        summary = _json.loads(summary_path.read_text(encoding="utf-8"))
        workflow_id = summary.get("workflow_id")
    if not workflow_id:
        async with _get_db(db_path) as db:
            cur = await db.execute("SELECT workflow_id FROM workflows LIMIT 1")
            row = await cur.fetchone()
            if row:
                workflow_id = str(row[0])
    if not workflow_id:
        raise HTTPException(status_code=404, detail="workflow_id not found")
    async with _get_db(db_path) as db:
        repo = _WorkflowRepository(db)
        step_summary = await repo.get_step_summary(workflow_id)
        step_failures = await repo.count_step_failures(workflow_id)
        running_steps = await repo.count_running_steps(workflow_id)
        fallback_count = await repo.count_fallback_events(workflow_id)
        fallback_summary = await repo.get_fallback_event_summary(workflow_id)
        writing_manifests = await repo.get_writing_manifests(workflow_id)
        latest_audit = await repo.get_latest_manuscript_audit(workflow_id)
        phase_performance_rows = await repo.get_phase_performance_summary(workflow_id)
        screening_diagnostics = await _build_screening_diagnostics(db, workflow_id)
        extraction_diagnostics = await _build_extraction_diagnostics(repo, db, workflow_id, db_path)
    return {
        "workflow_id": workflow_id,
        "step_summary": step_summary,
        "step_failures": step_failures,
        "running_steps": running_steps,
        "fallback_count": fallback_count,
        "fallback_summary": fallback_summary,
        "phase_performance": summarize_phase_performance(phase_performance_rows),
        "screening_diagnostics": screening_diagnostics,
        "extraction_diagnostics": extraction_diagnostics,
        "writing_manifests": [m.model_dump(mode="json") for m in writing_manifests],
        "audit_summary": _format_manuscript_audit_summary(latest_audit),
    }


@router.get("/api/run/{run_id}/submission.zip")
async def download_submission_zip(run_id: str) -> StreamingResponse:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found -- run export first")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    submission_dir = pathlib.Path(output_dir) / "submission"
    if not submission_dir.exists():
        raise HTTPException(status_code=404, detail="Submission directory not found -- click 'Export to LaTeX' first")
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + ".zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fpath in sorted(submission_dir.rglob("*")):
            if fpath.is_file():
                zf.write(fpath, arcname=fpath.relative_to(submission_dir))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={download_name}"},
    )


@router.get("/api/run/{run_id}/manuscript.docx")
async def download_manuscript_docx(run_id: str) -> FileResponse:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found -- run export first")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    docx_path = pathlib.Path(output_dir) / "submission" / "manuscript.docx"
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="manuscript.docx not found -- click 'Export to LaTeX' first")
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + ".docx"
    return FileResponse(
        path=str(docx_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/api/run/{run_id}/prospero-form.docx")
async def download_prospero_form(run_id: str) -> FileResponse:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    docx_path = pathlib.Path(output_dir) / "doc_prospero_registration.docx"
    if not docx_path.exists():
        raise HTTPException(
            status_code=404, detail="doc_prospero_registration.docx not found -- run must have completed finalization"
        )
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + "_prospero.docx"
    return FileResponse(
        path=str(docx_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/api/run/{run_id}/prospero-form.md")
async def download_prospero_form_markdown(run_id: str) -> FileResponse:
    db_path = await _resolve_db_path_from_run_or_workflow(run_id)
    summary_path = pathlib.Path(db_path).parent / "run_summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="run_summary.json not found")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))
    output_dir: str | None = summary.get("output_dir")
    if not output_dir:
        raise HTTPException(status_code=404, detail="output_dir not in run_summary")
    md_path = pathlib.Path(output_dir) / "doc_prospero_registration.md"
    if not md_path.exists():
        raise HTTPException(
            status_code=404, detail="doc_prospero_registration.md not found -- run must have completed finalization"
        )
    workflow_id: str = summary.get("workflow_id", run_id)
    topic = await _get_topic_for_db(db_path)
    download_name = _make_download_slug(workflow_id, topic) + "_prospero.md"
    return FileResponse(
        path=str(md_path),
        filename=download_name,
        media_type="text/markdown; charset=utf-8",
    )
