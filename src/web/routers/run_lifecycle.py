"""Run lifecycle endpoints: start, stream, cancel, download, config generation."""

from __future__ import annotations

import asyncio
import json as _json
import os
import pathlib
import tempfile
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from src.config.env_context import async_env_override_context, get_env, missing_required_env_keys
from src.config.loader import load_configs as _load_configs
from src.llm.registry import env_key_for_model as _env_key_for_model
from src.search.csv_import import validate_csv_file
from src.web.run_concurrency import acquire_run_slot_or_raise
from src.web.shared import (
    RunRequest,
    RunResponse,
    _GenerateConfigRequest,
    _json_safe,
    _validate_db_path,
)
from src.web.state import (
    _allowed_roots,
    _lifecycle_coordinator,
    _run_wrapper,
    _RunRecord,
)

router = APIRouter(tags=["run_lifecycle"])


# ---------------------------------------------------------------------------
# Helpers (local to this router)
# ---------------------------------------------------------------------------


def _missing_required_llm_keys(env_overrides: dict[str, str]) -> list[str]:
    settings = _load_configs(settings_path="config/settings.yaml")[1]
    return missing_required_env_keys(settings, env_overrides)


def _extract_topic(review_yaml: str) -> str:
    try:
        data = yaml.safe_load(review_yaml)
        return str(data.get("research_question", "Untitled review"))
    except Exception:
        return "Untitled review"


def _validate_csv_upload(csv_file: UploadFile, content: bytes) -> None:
    filename = (csv_file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Uploaded CSV file must include a filename.")
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported for sheet upload.")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")


def _normalize_path(value: str) -> str:
    return str(pathlib.Path(value).expanduser().resolve(strict=False))


def _merge_supplementary_csv_paths(
    existing_paths: list[str],
    incoming_paths: list[str],
    *,
    run_root: str | None = None,
    replace_staged_existing: bool = False,
) -> list[str]:
    staging_root: str | None = None
    if replace_staged_existing and run_root:
        staging_root = _normalize_path(str(pathlib.Path(run_root) / "staging"))

    merged: list[str] = []
    seen: set[str] = set()

    for raw in existing_paths:
        normalized = _normalize_path(str(raw))
        if staging_root and normalized.startswith(staging_root + os.sep):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    for raw in incoming_paths:
        normalized = _normalize_path(str(raw))
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)

    return merged


def _inject_csv_paths_into_yaml(
    review_yaml: str,
    *,
    masterlist_csv_path: str | None = None,
    supplementary_csv_paths: list[str] | None = None,
    run_root: str | None = None,
    replace_staged_supplementary_paths: bool = False,
) -> str:
    try:
        config_data = yaml.safe_load(review_yaml) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid review YAML: {exc}") from exc

    if masterlist_csv_path is not None:
        config_data["masterlist_csv_path"] = masterlist_csv_path

    if supplementary_csv_paths is not None:
        existing = config_data.get("supplementary_csv_paths") or []
        if not isinstance(existing, list):
            raise HTTPException(status_code=400, detail="supplementary_csv_paths in YAML must be a list.")
        config_data["supplementary_csv_paths"] = _merge_supplementary_csv_paths(
            [str(p) for p in existing],
            [str(p) for p in supplementary_csv_paths],
            run_root=run_root,
            replace_staged_existing=replace_staged_supplementary_paths,
        )

    return yaml.dump(config_data, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/run", response_model=RunResponse)
async def start_run(req: RunRequest) -> RunResponse:
    env_overrides = req.resolved_env_overrides()
    missing_keys = _missing_required_llm_keys(env_overrides)
    if missing_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required LLM API key(s): {', '.join(missing_keys)}",
        )
    if req.parent_db_path is not None:
        _validate_db_path(req.parent_db_path, req.run_root)
    topic = _extract_topic(req.review_yaml)
    run_id = str(uuid.uuid4())[:8]

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{run_id}_",
        delete=False,
    )
    tmp.write(req.review_yaml)
    tmp.flush()
    tmp.close()

    record = _RunRecord(run_id=run_id, topic=topic)
    record.review_yaml = req.review_yaml
    _lifecycle_coordinator.set(run_id, record)

    await acquire_run_slot_or_raise()
    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@router.post("/api/run-with-masterlist", response_model=RunResponse)
async def start_run_with_masterlist(
    csv_file: UploadFile = File(...),
    review_yaml: str = Form(...),
    gemini_api_key: str = Form(default=""),
    deepseek_api_key: str | None = Form(default=None),
    openrouter_api_key: str | None = Form(default=None),
    openai_api_key: str | None = Form(default=None),
    anthropic_api_key: str | None = Form(default=None),
    groq_api_key: str | None = Form(default=None),
    mistral_api_key: str | None = Form(default=None),
    cohere_api_key: str | None = Form(default=None),
    openalex_api_key: str | None = Form(default=None),
    ieee_api_key: str | None = Form(default=None),
    pubmed_email: str | None = Form(default=None),
    pubmed_api_key: str | None = Form(default=None),
    perplexity_api_key: str | None = Form(default=None),
    semantic_scholar_api_key: str | None = Form(default=None),
    crossref_email: str | None = Form(default=None),
    wos_api_key: str | None = Form(default=None),
    scopus_api_key: str | None = Form(default=None),
    run_root: str = Form(default="runs"),
) -> RunResponse:
    """Start a review run using a pre-assembled master list CSV instead of running connectors."""
    run_id = str(uuid.uuid4())[:8]
    staging_dir = pathlib.Path(run_root) / "staging" / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    csv_path = staging_dir / "masterlist.csv"

    content = await csv_file.read()
    _validate_csv_upload(csv_file, content)
    csv_path.write_bytes(content)

    try:
        validate_csv_file(str(csv_path.resolve()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid master list CSV: {exc}") from exc

    modified_yaml = _inject_csv_paths_into_yaml(
        review_yaml,
        masterlist_csv_path=str(csv_path.resolve()),
    )

    req = RunRequest(
        review_yaml=modified_yaml,
        gemini_api_key=gemini_api_key,
        deepseek_api_key=deepseek_api_key,
        openrouter_api_key=openrouter_api_key,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        groq_api_key=groq_api_key,
        mistral_api_key=mistral_api_key,
        cohere_api_key=cohere_api_key,
        openalex_api_key=openalex_api_key,
        ieee_api_key=ieee_api_key,
        pubmed_email=pubmed_email,
        pubmed_api_key=pubmed_api_key,
        perplexity_api_key=perplexity_api_key,
        semantic_scholar_api_key=semantic_scholar_api_key,
        crossref_email=crossref_email,
        wos_api_key=wos_api_key,
        scopus_api_key=scopus_api_key,
        run_root=run_root,
    )
    env_overrides = req.resolved_env_overrides()
    missing_keys = _missing_required_llm_keys(env_overrides)
    if missing_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required LLM API key(s): {', '.join(missing_keys)}",
        )

    topic = _extract_topic(modified_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{run_id}_",
        delete=False,
    )
    tmp.write(modified_yaml)
    tmp.flush()
    tmp.close()

    record = _RunRecord(run_id=run_id, topic=topic)
    record.review_yaml = modified_yaml
    _lifecycle_coordinator.set(run_id, record)

    await acquire_run_slot_or_raise()
    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@router.post("/api/run-with-supplementary-csv", response_model=RunResponse)
async def start_run_with_supplementary_csv(
    csv_file: UploadFile = File(...),
    review_yaml: str = Form(...),
    gemini_api_key: str = Form(default=""),
    deepseek_api_key: str | None = Form(default=None),
    openrouter_api_key: str | None = Form(default=None),
    openai_api_key: str | None = Form(default=None),
    anthropic_api_key: str | None = Form(default=None),
    groq_api_key: str | None = Form(default=None),
    mistral_api_key: str | None = Form(default=None),
    cohere_api_key: str | None = Form(default=None),
    openalex_api_key: str | None = Form(default=None),
    ieee_api_key: str | None = Form(default=None),
    pubmed_email: str | None = Form(default=None),
    pubmed_api_key: str | None = Form(default=None),
    perplexity_api_key: str | None = Form(default=None),
    semantic_scholar_api_key: str | None = Form(default=None),
    crossref_email: str | None = Form(default=None),
    wos_api_key: str | None = Form(default=None),
    scopus_api_key: str | None = Form(default=None),
    run_root: str = Form(default="runs"),
) -> RunResponse:
    """Start a review run using connectors plus one supplementary CSV import."""
    run_id = str(uuid.uuid4())[:8]
    staging_dir = pathlib.Path(run_root) / "staging" / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    csv_path = staging_dir / "supplementary.csv"

    content = await csv_file.read()
    _validate_csv_upload(csv_file, content)
    csv_path.write_bytes(content)

    try:
        validate_csv_file(str(csv_path.resolve()))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid supplementary CSV: {exc}") from exc

    modified_yaml = _inject_csv_paths_into_yaml(
        review_yaml,
        supplementary_csv_paths=[str(csv_path.resolve())],
        run_root=run_root,
        replace_staged_supplementary_paths=True,
    )

    req = RunRequest(
        review_yaml=modified_yaml,
        gemini_api_key=gemini_api_key,
        deepseek_api_key=deepseek_api_key,
        openrouter_api_key=openrouter_api_key,
        openai_api_key=openai_api_key,
        anthropic_api_key=anthropic_api_key,
        groq_api_key=groq_api_key,
        mistral_api_key=mistral_api_key,
        cohere_api_key=cohere_api_key,
        openalex_api_key=openalex_api_key,
        ieee_api_key=ieee_api_key,
        pubmed_email=pubmed_email,
        pubmed_api_key=pubmed_api_key,
        perplexity_api_key=perplexity_api_key,
        semantic_scholar_api_key=semantic_scholar_api_key,
        crossref_email=crossref_email,
        wos_api_key=wos_api_key,
        scopus_api_key=scopus_api_key,
        run_root=run_root,
    )
    env_overrides = req.resolved_env_overrides()
    missing_keys = _missing_required_llm_keys(env_overrides)
    if missing_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required LLM API key(s): {', '.join(missing_keys)}",
        )

    topic = _extract_topic(modified_yaml)

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"review_{run_id}_",
        delete=False,
    )
    tmp.write(modified_yaml)
    tmp.flush()
    tmp.close()

    record = _RunRecord(run_id=run_id, topic=topic)
    record.review_yaml = modified_yaml
    _lifecycle_coordinator.set(run_id, record)

    await acquire_run_slot_or_raise()
    task = asyncio.create_task(_run_wrapper(record, tmp.name, req))
    record.task = task

    return RunResponse(run_id=run_id, topic=topic)


@router.get("/api/stream/{run_id}")
async def stream_run(run_id: str, request: Request) -> EventSourceResponse:
    record = _lifecycle_coordinator.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")

    last_event_id_header = request.headers.get("last-event-id", "")
    resume_from: int = 0
    if last_event_id_header:
        try:
            resume_from = int(last_event_id_header) + 1
        except ValueError:
            resume_from = 0

    async def _generator() -> AsyncGenerator[dict[str, Any], None]:
        replay_index = max(0, resume_from)
        while replay_index < len(record.event_log):
            yield {"id": str(replay_index), "data": _json_safe(record.event_log[replay_index])}
            replay_index += 1

        while True:
            while replay_index < len(record.event_log):
                event = record.event_log[replay_index]
                yield {"id": str(replay_index), "data": _json_safe(event)}
                replay_index += 1
                if event.get("type") in ("done", "error", "cancelled"):
                    return

            if record.done:
                return

            try:
                async with record._event_cond:
                    await asyncio.wait_for(record._event_cond.wait(), timeout=15.0)
            except TimeoutError:
                yield {"event": "heartbeat", "data": "{}"}

    return EventSourceResponse(_generator())


@router.post("/api/cancel/{run_id}")
async def cancel_run(run_id: str) -> dict[str, str]:
    record = _lifecycle_coordinator.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if record.task and not record.task.done():
        record.task.cancel()
    return {"status": "cancelled"}


@router.get("/api/download")
async def download_file(path: str) -> FileResponse:
    resolved = pathlib.Path(path).resolve()
    resolved_str = str(resolved)
    if not any(resolved_str.startswith(root) for root in _allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=resolved_str, filename=resolved.name)


@router.post("/api/config/generate/stream")
async def generate_config_stream(req: _GenerateConfigRequest) -> StreamingResponse:
    """SSE streaming config generation."""
    from src.web.config_generator import evaluate_config_quality_yaml, generate_config_yaml

    if not req.research_question.strip():
        raise HTTPException(status_code=422, detail="research_question must not be empty")

    env_overrides: dict[str, str] = {}
    if req.deepseek_api_key.strip():
        env_overrides["DEEPSEEK_API_KEY"] = req.deepseek_api_key.strip()
    elif req.gemini_api_key.strip():
        env_overrides["GEMINI_API_KEY"] = req.gemini_api_key.strip()

    cfg = _load_configs(settings_path="config/settings.yaml")[1]
    agent_cfg = cfg.agents.get("config_generation") or cfg.agents.get("search")
    required_env_key = _env_key_for_model(agent_cfg.model) if agent_cfg is not None else "DEEPSEEK_API_KEY"
    if required_env_key is None:
        required_env_key = "DEEPSEEK_API_KEY"

    async with async_env_override_context(env_overrides):
        if not get_env(required_env_key):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{required_env_key} is required to generate a config. Add it in the API Keys section or .env."
                ),
            )

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def progress_cb(progress: dict[str, Any]) -> None:
        step = str(progress.get("step", "unknown"))
        payload: dict[str, Any] = {"type": "progress", "step": step}
        for key, value in progress.items():
            if key != "step":
                payload[key] = value
        queue.put_nowait(payload)

    async def run_generation() -> None:
        async with async_env_override_context(env_overrides):
            try:
                yaml_content = await generate_config_yaml(
                    req.research_question,
                    progress_cb=progress_cb,
                    generation_profile=req.generation_profile,
                )
                quality = evaluate_config_quality_yaml(yaml_content)
                queue.put_nowait({"type": "done", "yaml": yaml_content, "quality": quality})
            except RuntimeError as exc:
                queue.put_nowait({"type": "error", "detail": str(exc)})
            except Exception as exc:
                queue.put_nowait({"type": "error", "detail": f"Unexpected error: {exc}"})
            finally:
                queue.put_nowait(None)

    async def event_stream() -> AsyncGenerator[str, None]:
        task = asyncio.create_task(run_generation())
        yield f"data: {_json.dumps({'type': 'progress', 'step': 'start'})}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=180.0)
                except TimeoutError:
                    yield f"data: {_json.dumps({'type': 'error', 'detail': 'Generation timed out after 3 minutes'})}\n\n"
                    break
                if msg is None:
                    break
                yield f"data: {_json.dumps(msg)}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
