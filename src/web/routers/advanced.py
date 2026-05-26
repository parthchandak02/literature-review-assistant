"""Advanced analytics endpoints: knowledge graph, PRISMA, GRADE, living refresh, log streaming."""

from __future__ import annotations

import asyncio
import json as _json
import os
import pathlib
import tempfile
import uuid
from collections.abc import AsyncGenerator

import aiofiles
import aiosqlite
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from src.web.shared import RunRequest, RunResponse, _resolve_db_path
from src.web.state import (
    _active_runs,
    _get_db_path,
    _run_wrapper,
    _RunRecord,
)

router = APIRouter(tags=["advanced"])


# ---------------------------------------------------------------------------
# Helpers local to this router
# ---------------------------------------------------------------------------

_PM2_LOG_DIR = pathlib.Path.home() / ".pm2" / "logs"
_TAIL_LINES = 200


def _extract_topic(review_yaml: str) -> str:
    import yaml

    try:
        data = yaml.safe_load(review_yaml)
        return str(data.get("research_question", "Untitled review"))
    except Exception:
        return "Untitled review"


async def _log_stream_generator(log_path: pathlib.Path, request: Request) -> AsyncGenerator[dict[str, str], None]:
    """Yield the last N lines of a PM2 log file, then stream new lines as they arrive."""
    import watchfiles

    if log_path.exists():
        async with aiofiles.open(log_path, errors="replace") as fh:
            raw = await fh.read()
        tail = raw.splitlines()[-_TAIL_LINES:]
        for line in tail:
            if await request.is_disconnected():
                return
            yield {"event": "log", "data": line}

    if not log_path.exists():
        yield {"event": "log", "data": f"[waiting for {log_path.name}]"}

    last_pos = log_path.stat().st_size if log_path.exists() else 0

    async for _ in watchfiles.awatch(str(log_path.parent), stop_event=None):
        if await request.is_disconnected():
            return
        if not log_path.exists():
            continue
        current_size = log_path.stat().st_size
        if current_size <= last_pos:
            last_pos = current_size
            continue
        async with aiofiles.open(log_path, errors="replace") as fh:
            await fh.seek(last_pos)
            new_content = await fh.read()
        last_pos = last_pos + len(new_content.encode("utf-8", errors="replace"))
        for line in new_content.splitlines():
            if await request.is_disconnected():
                return
            yield {"event": "log", "data": line}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/run/{run_id}/knowledge-graph")
async def get_knowledge_graph(run_id: str) -> dict:
    """Return the evidence knowledge graph for a completed run."""
    db_path = _get_db_path(run_id)
    if not pathlib.Path(db_path).exists():
        raise HTTPException(status_code=404, detail="Run database not found")

    async with aiosqlite.connect(db_path) as _kg_db:
        _kg_db.row_factory = aiosqlite.Row

        async with _kg_db.execute("SELECT workflow_id FROM workflows LIMIT 1") as _wc:
            _wf_row = await _wc.fetchone()
        if not _wf_row:
            raise HTTPException(status_code=404, detail="No workflow found")
        _wf_id = _wf_row[0]

        nodes: list[dict] = []
        async with _kg_db.execute(
            "SELECT p.paper_id, p.title, p.year, COALESCE(er.study_design, 'unknown'), p.authors"
            " FROM papers p"
            " LEFT JOIN extraction_records er"
            "  ON er.paper_id = p.paper_id AND er.workflow_id = ?"
            " WHERE p.paper_id IN (SELECT paper_id FROM extraction_records WHERE workflow_id = ?)",
            (_wf_id, _wf_id),
        ) as _nc:
            async for _nr in _nc:
                _authors_raw = _nr[4] or ""
                _first_author = ""
                if _authors_raw:
                    try:
                        _authors_list = _json.loads(_authors_raw)
                        if isinstance(_authors_list, list) and _authors_list:
                            _first = str(_authors_list[0])
                            _first_author = _first.split()[-1] if _first.split() else _first
                        elif isinstance(_authors_list, str):
                            _first_author = _authors_list.split(",")[0].strip().split()[-1]
                    except (ValueError, TypeError):
                        _first_part = _authors_raw.split(",")[0].strip()
                        _first_author = _first_part.split()[-1] if _first_part.split() else _first_part
                nodes.append(
                    {
                        "id": _nr[0],
                        "title": _nr[1] or "",
                        "year": _nr[2],
                        "study_design": _nr[3] or "unknown",
                        "community_id": -1,
                        "first_author": _first_author,
                        "has_multiple_authors": "," in _authors_raw,
                    }
                )

        community_map: dict[str, int] = {}
        async with _kg_db.execute(
            "SELECT community_id, paper_ids FROM graph_communities WHERE workflow_id = ?",
            (_wf_id,),
        ) as _cc:
            async for _cr in _cc:
                try:
                    pids = _json.loads(_cr[1])
                    for pid in pids:
                        community_map[pid] = _cr[0]
                except (TypeError, ValueError):
                    pass
        for node in nodes:
            node["community_id"] = community_map.get(node["id"], -1)

        edges: list[dict] = []
        async with _kg_db.execute(
            "SELECT source_paper_id, target_paper_id, rel_type, weight FROM paper_relationships WHERE workflow_id = ?",
            (_wf_id,),
        ) as _ec:
            async for _er in _ec:
                edges.append({"source": _er[0], "target": _er[1], "rel_type": _er[2], "weight": _er[3]})

        communities: list[dict] = []
        async with _kg_db.execute(
            "SELECT community_id, paper_ids, label FROM graph_communities WHERE workflow_id = ?",
            (_wf_id,),
        ) as _comm_c:
            async for _comm_r in _comm_c:
                try:
                    pids = _json.loads(_comm_r[1])
                except (TypeError, ValueError):
                    pids = []
                communities.append(
                    {"id": _comm_r[0], "paper_ids": pids, "label": _comm_r[2] or f"Cluster {_comm_r[0]}"}
                )

        gaps: list[dict] = []
        async with _kg_db.execute(
            "SELECT gap_id, description, gap_type, related_paper_ids FROM research_gaps WHERE workflow_id = ?",
            (_wf_id,),
        ) as _gc:
            async for _gr in _gc:
                try:
                    rids = _json.loads(_gr[3]) if _gr[3] else []
                except (TypeError, ValueError):
                    rids = []
                gaps.append({"id": _gr[0], "description": _gr[1], "gap_type": _gr[2], "related_paper_ids": rids})

    return {"run_id": run_id, "nodes": nodes, "edges": edges, "communities": communities, "gaps": gaps}


@router.get("/api/run/{run_id}/prisma-checklist")
async def get_prisma_checklist(run_id: str) -> dict:
    """Run the PRISMA 2020 checklist validator against the manuscript draft."""
    from src.export.prisma_checklist import validate_prisma

    resolved_db: str | None = None
    try:
        resolved_db = _get_db_path(run_id)
    except HTTPException:
        resolved_db = await _resolve_db_path("runs", run_id)
        if resolved_db is None:
            raise HTTPException(status_code=404, detail="Run not found")

    db_path = resolved_db
    run_path = pathlib.Path(db_path).parent

    md_content: str | None = None
    tex_content: str | None = None

    for candidate in [
        run_path / "doc_manuscript.md",
        run_path / "manuscript.md",
        run_path / "manuscript_draft.md",
        run_path / "outputs" / "manuscript.md",
    ]:
        if candidate.exists():
            md_content = candidate.read_text(encoding="utf-8", errors="replace")
            break

    for candidate in [run_path / "submission" / "manuscript.tex", run_path / "manuscript.tex"]:
        if candidate.exists():
            tex_content = candidate.read_text(encoding="utf-8", errors="replace")
            break

    result = validate_prisma(tex_content=tex_content, md_content=md_content)
    return {
        "run_id": run_id,
        "source_state": result.source_state,
        "reported_count": result.reported_count,
        "partial_count": result.partial_count,
        "missing_count": result.missing_count,
        "not_applicable_count": result.not_applicable_count,
        "passed": result.passed,
        "total": result.primary_total,
        "item_total": len(result.items),
        "items": [
            {
                "item_id": item.item_id,
                "section": item.section,
                "description": item.description,
                "status": item.status,
                "rationale": item.rationale,
                "applies": item.applies,
                "evidence_terms": item.evidence_terms,
            }
            for item in result.items
        ],
    }


@router.get("/api/run/{run_id}/grade-sof")
async def get_grade_sof(run_id: str, fmt: str = "json") -> dict:
    """Return the GRADE Summary of Findings table for a completed run."""
    from src.db.repositories import WorkflowRepository
    from src.quality.grade import build_sof_table

    resolved_db: str | None = None
    try:
        resolved_db = _get_db_path(run_id)
    except HTTPException:
        resolved_db = await _resolve_db_path("runs", run_id)
        if resolved_db is None:
            raise HTTPException(status_code=404, detail="Run not found")

    async with aiosqlite.connect(resolved_db) as db:
        db.row_factory = aiosqlite.Row
        repo = WorkflowRepository(db)

        wf_id = run_id
        try:
            async with db.execute("SELECT workflow_id FROM workflows ORDER BY rowid DESC LIMIT 1") as cur:
                row = await cur.fetchone()
                if row:
                    wf_id = row[0]
        except Exception:
            pass

        assessments = await repo.load_grade_assessments(wf_id)

    if not assessments:
        raise HTTPException(
            status_code=404,
            detail="No GRADE assessments found for this run. Run the quality assessment phase first.",
        )

    topic = run_id
    try:
        async with aiosqlite.connect(resolved_db) as db2:
            async with db2.execute("SELECT topic FROM workflows LIMIT 1") as cur2:
                row2 = await cur2.fetchone()
                if row2:
                    topic = row2[0]
    except Exception:
        pass

    table = build_sof_table(assessments, topic=topic)

    if fmt == "latex":
        from src.export.ieee_latex import render_grade_sof_latex

        return {"run_id": run_id, "latex": render_grade_sof_latex(table)}

    return {"run_id": run_id, "topic": table.topic, "rows": [r.model_dump() for r in table.rows]}


@router.post("/api/run/{run_id}/living-refresh")
async def living_refresh(run_id: str) -> RunResponse:
    """Launch an incremental living-review run based on a completed run."""
    from datetime import date as _date

    import yaml as _yaml

    record = _active_runs.get(run_id)
    if record is None:
        resolved_parent_db = await _resolve_db_path("runs", run_id)
        if resolved_parent_db is None:
            raise HTTPException(status_code=404, detail="Run not found")
        parent_yaml_path = pathlib.Path(resolved_parent_db).parent / "review.yaml"
        if not parent_yaml_path.exists():
            raise HTTPException(
                status_code=422, detail="review.yaml not found next to prior runtime.db; cannot refresh."
            )
        prior_yaml = parent_yaml_path.read_text(encoding="utf-8")
        parent_db_path_value = resolved_parent_db
        prior_run_root = str(pathlib.Path(resolved_parent_db).parent.parent.parent.parent)
    else:
        if not record.done:
            raise HTTPException(
                status_code=409, detail="Living refresh only allowed on completed runs; this run has not finished yet."
            )
        prior_yaml = getattr(record, "review_yaml", None)
        parent_db_path_value = record.db_path or None
        prior_run_root = record.run_root

    if not prior_yaml:
        raise HTTPException(status_code=422, detail="Prior run has no review YAML stored; cannot refresh.")

    try:
        config_dict = _yaml.safe_load(prior_yaml) or {}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse prior review YAML: {exc}") from exc

    config_dict["living_review"] = True
    config_dict["last_search_date"] = str(_date.today())

    new_yaml = _yaml.dump(config_dict, allow_unicode=True, default_flow_style=False)

    req = RunRequest(
        review_yaml=new_yaml,
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        openalex_api_key=os.environ.get("OPENALEX_API_KEY"),
        ieee_api_key=os.environ.get("IEEE_API_KEY"),
        pubmed_email=os.environ.get("PUBMED_EMAIL"),
        pubmed_api_key=os.environ.get("PUBMED_API_KEY"),
        perplexity_api_key=os.environ.get("PERPLEXITY_SEARCH_API_KEY"),
        semantic_scholar_api_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
        crossref_email=os.environ.get("CROSSREF_EMAIL"),
        wos_api_key=os.environ.get("WOS_API_KEY"),
        scopus_api_key=os.environ.get("SCOPUS_API_KEY"),
        run_root=prior_run_root,
        parent_db_path=parent_db_path_value,
    )

    new_run_id = str(uuid.uuid4())[:8]
    topic = _extract_topic(new_yaml)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", prefix=f"review_{new_run_id}_", delete=False)
    tmp.write(new_yaml)
    tmp.flush()
    tmp.close()

    new_record = _RunRecord(run_id=new_run_id, topic=topic)
    new_record.review_yaml = new_yaml
    _active_runs[new_run_id] = new_record

    task = asyncio.create_task(_run_wrapper(new_record, tmp.name, req))
    new_record.task = task

    return RunResponse(run_id=new_run_id, topic=f"[Living refresh] {topic}")


@router.get("/api/logs/stream")
async def stream_logs(
    request: Request,
    run_id: str | None = None,
    workflow_id: str | None = None,
    run_root: str = "runs",
    process: str = "backend",
    log_type: str = "out",
) -> EventSourceResponse:
    """Stream a run's app.jsonl log file or a PM2 log file over SSE."""
    if run_id:
        record = _active_runs.get(run_id)
        if record and record.db_path:
            log_path = pathlib.Path(record.db_path).parent / "app.jsonl"
        elif workflow_id:
            db_path = await _resolve_db_path(run_root, workflow_id)
            if not db_path:
                raise HTTPException(status_code=404, detail="Workflow not found in registry")
            log_path = pathlib.Path(db_path).parent / "app.jsonl"
        else:
            raise HTTPException(status_code=404, detail="Run not found or log not yet available")
    elif workflow_id:
        db_path = await _resolve_db_path(run_root, workflow_id)
        if not db_path:
            raise HTTPException(status_code=404, detail="Workflow not found in registry")
        log_path = pathlib.Path(db_path).parent / "app.jsonl"
    else:
        if log_type not in ("out", "err"):
            raise HTTPException(status_code=400, detail="log_type must be 'out' or 'err'")
        log_path = _PM2_LOG_DIR / f"{process}-{log_type}.log"
    return EventSourceResponse(
        _log_stream_generator(log_path, request),
        headers={"X-Accel-Buffering": "no"},
    )
