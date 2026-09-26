"""Web hardening: secret redaction, artifact serving, path guards, slot leaks, SSE disconnect."""

from __future__ import annotations

import asyncio
import logging
import pathlib
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

import src.web.app as web_app
import src.web.routers.run_lifecycle as run_lifecycle
import src.web.run_concurrency as run_concurrency
from src.config.env_context import async_env_override_context, get_env, missing_required_env_keys
from src.llm.shared_rate_limiter import clear_shared_rate_limiters, get_shared_rate_limiter
from src.models import SettingsConfig
from src.web.path_guard import RUNS_ROOTS_ENV, is_sensitive_file
from src.web.shared import AttachRequest, ResumeRequest, RunRequest
from src.web.state import _active_runs, _lifecycle_coordinator, _RunRecord

_MINIMAL_YAML = "research_question: Q\n"


@pytest.fixture
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=web_app.app), base_url="http://test")


@pytest.fixture
def only_tmp_runs_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Restrict configured run roots to <tmp>/runs (cwd-relative default) only."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(RUNS_ROOTS_ENV, raising=False)
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr("src.web.state._allowed_roots", set())
    monkeypatch.setattr("src.web.routers.run_lifecycle._allowed_roots", set())
    return (tmp_path / "runs").resolve()


def _raise_429() -> Any:
    async def _acquire() -> None:
        raise HTTPException(status_code=429, detail="full")

    return _acquire


@pytest.mark.asyncio
async def test_env_keys_blanks_secrets_but_keeps_emails(client: httpx.AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw-secret-value")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-secret-value")
    monkeypatch.setenv("PUBMED_EMAIL", "a@example.org")
    monkeypatch.setenv("CROSSREF_EMAIL", "b@example.org")
    async with client:
        body = (await client.get("/api/config/env-keys")).json()
    assert body["fireworks"] == ""
    assert body["gemini"] == ""
    assert body["pubmedEmail"] == "a@example.org"
    assert body["crossrefEmail"] == "b@example.org"
    assert "fw-secret-value" not in str(body)
    assert {"openai", "anthropic", "scopus", "wos", "pubmedApiKey"} <= set(body)
    assert all(v == "" for k, v in body.items() if k not in {"pubmedEmail", "crossrefEmail"})


@pytest.mark.asyncio
async def test_blank_browser_keys_fall_back_to_server_env(monkeypatch) -> None:
    monkeypatch.setenv("FIREWORKS_API_KEY", "server-fw")
    req = RunRequest(review_yaml=_MINIMAL_YAML, gemini_api_key="", fireworks_api_key="")
    overrides = req.resolved_env_overrides()
    assert "FIREWORKS_API_KEY" not in overrides
    settings = SettingsConfig(agents={"search": {"model": "fireworks:accounts/x/models/y", "temperature": 0.1}})
    assert missing_required_env_keys(settings, overrides) == []
    async with async_env_override_context(overrides):
        assert get_env("FIREWORKS_API_KEY") == "server-fw"


@pytest.mark.parametrize(
    ("name", "sensitive"),
    [
        ("runtime.db", True),
        ("runtime.db-wal", True),
        ("runtime.db-shm", True),
        ("x.sqlite", True),
        (".env", True),
        (".env.local", True),
        ("prod.env", True),
        ("doc_manuscript.md", False),
        ("submission.zip", False),
        ("fig.png", False),
        ("manuscript.tex", False),
    ],
)
def test_is_sensitive_file(name: str, sensitive: bool) -> None:
    assert is_sensitive_file(pathlib.Path(name)) is sensitive


@pytest.mark.asyncio
async def test_runs_static_refuses_databases_and_traversal(
    client: httpx.AsyncClient, tmp_path: pathlib.Path, monkeypatch
) -> None:
    runs = tmp_path / "runs"
    run_dir = runs / "wf" / "run_1"
    run_dir.mkdir(parents=True)
    for name in ("runtime.db", "runtime.db-wal", "runtime.db-shm", "x.sqlite", ".env"):
        (run_dir / name).write_text("secret")
    (runs / "workflows_registry.db").write_text("secret")
    (run_dir / "doc_manuscript.md").write_text("# ok")
    (run_dir / "fig.svg").write_text("<svg/>")
    (tmp_path / "outside.txt").write_text("outside")
    monkeypatch.setattr(web_app, "_runs_dir_resolved", runs.resolve())

    async with client:
        for name in ("runtime.db", "runtime.db-wal", "runtime.db-shm", "x.sqlite", ".env"):
            assert (await client.get(f"/runs/wf/run_1/{name}")).status_code == 404
        assert (await client.get("/runs/workflows_registry.db")).status_code == 404
        assert (await client.get("/runs/%2e%2e/outside.txt")).status_code == 404
        md = await client.get("/runs/wf/run_1/doc_manuscript.md")
        assert md.status_code == 200
        assert md.text == "# ok"
        assert (await client.get("/runs/wf/run_1/fig.svg")).status_code == 200
    with pytest.raises(HTTPException) as exc:
        await web_app.serve_run_artifact("../outside.txt")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_download_uses_path_containment_and_refuses_databases(
    client: httpx.AsyncClient, only_tmp_runs_root: pathlib.Path
) -> None:
    runs = only_tmp_runs_root
    (runs / "a.md").write_text("ok")
    (runs / "runtime.db").write_text("secret")
    sibling = runs.parent / "runs_evil"
    sibling.mkdir()
    (sibling / "leak.txt").write_text("leak")

    async with client:
        assert (await client.get("/api/download", params={"path": str(runs / "a.md")})).status_code == 200
        assert (await client.get("/api/download", params={"path": str(runs / "runtime.db")})).status_code == 403
        assert (await client.get("/api/download", params={"path": str(sibling / "leak.txt")})).status_code == 403
        assert (await client.get("/api/download", params={"path": str(runs)})).status_code == 404


@pytest.mark.asyncio
async def test_attach_history_rejects_db_outside_run_roots(only_tmp_runs_root: pathlib.Path) -> None:
    outside = only_tmp_runs_root.parent / "elsewhere" / "runtime.db"
    outside.parent.mkdir()
    outside.write_text("")
    with pytest.raises(HTTPException) as exc:
        await _lifecycle_coordinator.attach_history(AttachRequest(workflow_id="wf-x", topic="t", db_path=str(outside)))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_start_run_rejects_run_root_outside_configured_roots(
    client: httpx.AsyncClient, only_tmp_runs_root: pathlib.Path, monkeypatch
) -> None:
    monkeypatch.setattr(run_lifecycle, "_missing_required_llm_keys", lambda _o: [])
    outside = only_tmp_runs_root.parent / "not_runs"
    async with client:
        resp = await client.post("/api/run", json={"review_yaml": _MINIMAL_YAML, "run_root": str(outside)})
        assert resp.status_code == 400
        resp = await client.post(
            "/api/run-with-masterlist",
            data={"review_yaml": _MINIMAL_YAML, "run_root": str(outside)},
            files={"csv_file": ("m.csv", b"title\nx\n", "text/csv")},
        )
        assert resp.status_code == 400
    assert not (outside / "staging").exists()


@pytest.mark.asyncio
async def test_delete_history_rejects_run_root_outside_configured_roots(
    client: httpx.AsyncClient, only_tmp_runs_root: pathlib.Path
) -> None:
    victim = only_tmp_runs_root.parent / "victim"
    victim.mkdir()
    async with client:
        resp = await client.delete("/api/history/wf-1", params={"run_root": str(victim)})
    assert resp.status_code == 400
    assert victim.exists()


@pytest.mark.asyncio
async def test_launch_new_run_429_leaves_no_orphan_record(monkeypatch) -> None:
    monkeypatch.setattr(run_lifecycle, "acquire_run_slot_or_raise", _raise_429())
    before = set(_active_runs)
    req = RunRequest(review_yaml=_MINIMAL_YAML)
    with pytest.raises(HTTPException) as exc:
        await run_lifecycle.launch_new_run("slot-leak", "t", _MINIMAL_YAML, req)
    assert exc.value.status_code == 429
    assert set(_active_runs) == before


@pytest.mark.asyncio
async def test_start_resume_429_does_not_claim_or_register(monkeypatch) -> None:
    monkeypatch.setattr(run_concurrency, "acquire_run_slot_or_raise", _raise_429())
    claimed: list[str] = []

    async def _claim(workflow_id: str, db_path: str) -> Any:
        claimed.append(workflow_id)
        raise AssertionError("claim must not run when no slot is available")

    monkeypatch.setattr(_lifecycle_coordinator, "claim_for_resume", _claim)
    before = set(_active_runs)
    with pytest.raises(HTTPException) as exc:
        await _lifecycle_coordinator.start_resume(
            ResumeRequest(workflow_id="wf-resume-429", db_path="runs/x/runtime.db", topic="t"),
            resume_wrapper=None,
        )
    assert exc.value.status_code == 429
    assert claimed == []
    assert set(_active_runs) == before
    assert _lifecycle_coordinator.find_active_by_workflow("wf-resume-429") is None


@pytest.mark.asyncio
async def test_start_resume_failed_claim_releases_slot(monkeypatch) -> None:
    released: list[bool] = []

    async def _acquire() -> None:
        return None

    async def _claim(workflow_id: str, db_path: str) -> Any:
        raise HTTPException(status_code=409, detail="running")

    monkeypatch.setattr(run_concurrency, "acquire_run_slot_or_raise", _acquire)
    monkeypatch.setattr(run_concurrency, "release_run_slot", lambda: released.append(True))
    monkeypatch.setattr(_lifecycle_coordinator, "claim_for_resume", _claim)
    before = set(_active_runs)
    with pytest.raises(HTTPException):
        await _lifecycle_coordinator.start_resume(
            ResumeRequest(workflow_id="wf-resume-409", db_path="runs/x/runtime.db", topic="t"),
            resume_wrapper=None,
        )
    assert released == [True]
    assert set(_active_runs) == before


class _DisconnectedRequest:
    headers: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_stream_run_stops_when_client_disconnects() -> None:
    record = _RunRecord(run_id="sse-disc", topic="t")
    record.event_log.append({"type": "phase_start", "phase": "search"})
    _active_runs["sse-disc"] = record
    try:
        response = await run_lifecycle.stream_run("sse-disc", _DisconnectedRequest())  # type: ignore[arg-type]

        async def _drain() -> list[Any]:
            return [item async for item in response.body_iterator]

        items = await asyncio.wait_for(_drain(), timeout=2.0)
    finally:
        _active_runs.pop("sse-disc", None)
    assert len(items) == 1


def _fireworks_settings() -> SettingsConfig:
    return SettingsConfig(agents={"writing": {"model": "fireworks:accounts/x/models/y", "temperature": 0.1}})


@pytest.mark.asyncio
async def test_rate_limiter_keyed_on_provider_credential_in_use() -> None:
    clear_shared_rate_limiters()
    try:
        settings = _fireworks_settings()
        async with async_env_override_context({"FIREWORKS_API_KEY": "fw-a", "GEMINI_API_KEY": "g-1"}):
            a = get_shared_rate_limiter(settings)
        async with async_env_override_context({"FIREWORKS_API_KEY": "fw-a", "GEMINI_API_KEY": "g-2"}):
            same_fw = get_shared_rate_limiter(settings)
        async with async_env_override_context({"FIREWORKS_API_KEY": "fw-b", "GEMINI_API_KEY": "g-1"}):
            other_fw = get_shared_rate_limiter(settings)
        assert a is same_fw
        assert a is not other_fw
    finally:
        clear_shared_rate_limiters()


def test_rate_limiter_missing_keys_share_one_limiter(monkeypatch) -> None:
    monkeypatch.setenv("FIREWORKS_API_KEY", "")
    clear_shared_rate_limiters()
    try:
        settings = _fireworks_settings()
        assert get_shared_rate_limiter(settings) is get_shared_rate_limiter(settings)
        bare = SettingsConfig(agents={"writing": {"model": "unknown-model", "temperature": 0.1}})
        assert get_shared_rate_limiter(bare) is get_shared_rate_limiter(bare)
    finally:
        clear_shared_rate_limiters()


@pytest.mark.asyncio
async def test_lifespan_logs_registry_repair_failures(
    tmp_path: pathlib.Path, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "workflows_registry.db").write_text("not a sqlite db")

    def _broken_open(_path: str) -> Any:
        raise RuntimeError("registry boom")

    async def _broken_repair(_root: str = "runs") -> None:
        raise RuntimeError("repair boom")

    async def _noop() -> None:
        return None

    monkeypatch.setattr(web_app, "_open_registry_db", _broken_open)
    monkeypatch.setattr(web_app, "_repair_registry_statuses_from_runtime", _broken_repair)
    monkeypatch.setattr(web_app, "_refresh_allowed_roots", _noop)
    caplog.set_level(logging.ERROR, logger="src.web.app")
    async with web_app.lifespan(web_app.app):
        pass
    messages = [r.getMessage() for r in caplog.records if r.exc_info]
    assert any("could not mark running workflows interrupted" in m for m in messages)
    assert any("from runtime evidence failed" in m for m in messages)
