from __future__ import annotations

import json

import pytest
import yaml

from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.llm import jev_client
from src.llm.jev_client import JevAskResult, jev_cost_phase, jev_mode
from src.llm.provider import LLMProvider
from src.models import ScreeningDecisionType, SettingsConfig
from src.models.config import JevConfig, ScreeningConfig
from src.screening import dual_screener as dual_screener_module
from src.screening import jev_screening
from src.screening.dual_screener import DualReviewerScreener
from tests.unit.test_screening import _batch_item, _paper, _review, _ScriptedClient


def test_legacy_booleans_map_to_modes() -> None:
    cfg = JevConfig(screening_reviewer_b=True, rag_rerank=False, batch_pre_rank="on", study_design="shadow")
    assert cfg.screening_reviewer_b == "live"
    assert cfg.rag_rerank == "off"
    assert cfg.batch_pre_rank == "live"
    assert cfg.study_design == "shadow"


def test_master_switch_forces_off() -> None:
    cfg = JevConfig(enabled=False, screening_reviewer_b="live")
    assert cfg.mode_for("screening_reviewer_b") == "off"
    assert cfg.mode_for("unknown_surface") == "off"


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        JevConfig(screening_reviewer_b="sometimes")


def test_default_model_is_off_and_repo_settings_are_shadow() -> None:
    assert all(JevConfig().mode_for(s) == "off" for s in JevConfig.SURFACES)
    with open("config/settings.yaml", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    settings = SettingsConfig.model_validate(raw)
    assert {jev_mode(settings, s) for s in JevConfig.SURFACES} == {"shadow"}


def test_cost_and_phase_labels() -> None:
    cfg = JevConfig(price_per_call_usd=0.001, price_input_per_mtok=1.0, price_output_per_mtok=2.0)
    assert cfg.cost_usd(1_000_000, 500_000) == pytest.approx(0.001 + 1.0 + 1.0)
    assert jev_cost_phase("phase_3_screening", "shadow") == "jev_shadow_phase_3_screening"
    assert jev_cost_phase("phase_3_screening", "live") == "phase_3_screening_jev"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self) -> dict:
        return self._payload


class _FakeSession:
    last_payload: dict | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
        _FakeSession.last_payload = json
        return _FakeResponse(
            {
                "model": json["model"],
                "answers": {"screen": {"choice": "INCLUDE", "confidence": 0.9}},
                "usage": {"input_tokens": 100, "output_tokens": 20},
            }
        )


@pytest.mark.asyncio
async def test_ask_jev_uses_http_client(monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(jev_client.aiohttp, "ClientSession", _FakeSession)
    result = await jev_client.ask_jev(model="jev-1.13.0", state={"x": 1}, questions={"screen": {"type": "choice"}})
    assert result.answers["screen"]["choice"] == "INCLUDE"
    assert result.usage == {"input_tokens": 100, "output_tokens": 20}
    assert _FakeSession.last_payload is not None and _FakeSession.last_payload["model"] == "jev-1.13.0"


def _jev_settings(mode: str, **jev_kwargs: object) -> SettingsConfig:
    return SettingsConfig(
        agents={
            "screening_reviewer_a": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.1},
            "screening_reviewer_b": {"model": "google:gemini-2.5-flash-lite", "temperature": 0.3},
            "screening_adjudicator": {"model": "google:gemini-2.5-pro", "temperature": 0.2},
        },
        screening=ScreeningConfig(reviewer_batch_size=10, insufficient_content_min_words=0),
        jev=JevConfig(screening_reviewer_b=mode, price_per_call_usd=0.002, **jev_kwargs),
    )


def _fake_ask(choice: str, confidence: float, calls: list[dict]):
    async def _ask(**kwargs: object) -> JevAskResult:
        calls.append(kwargs)
        return JevAskResult(
            answers={"screen": {"choice": choice, "confidence": confidence, "probabilities": {choice: confidence}}},
            model="jev-1.13.0",
            usage={"input_tokens": 300, "output_tokens": 40},
            latency_ms=180,
        )

    return _ask


async def _screen(tmp_path, settings: SettingsConfig, responses: list[object]):
    papers = [_paper("p1"), _paper("p2"), _paper("p3")]
    db_ctx = get_db(str(tmp_path / "jev.db"))
    db = await db_ctx.__aenter__()
    repo = WorkflowRepository(db)
    await repo.create_workflow("wf-jev", "topic", "hash")
    screener = DualReviewerScreener(
        repository=repo,
        provider=LLMProvider(settings, repo),
        review=_review(),
        settings=settings,
        llm_client=_ScriptedClient(responses),
    )
    results = await screener.screen_batch(workflow_id="wf-jev", stage="title_abstract", papers=papers)
    return db_ctx, db, results


@pytest.mark.asyncio
async def test_shadow_keeps_llm_decision_and_records_both(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(jev_screening, "ask_jev", _fake_ask("EXCLUDE", 0.99, calls))
    monkeypatch.setattr(dual_screener_module, "jev_key_available", lambda: True)
    batch_a = [_batch_item("p1", "include", 0.95), _batch_item("p2", "include", 0.91), _batch_item("p3", "include", 0.6)]
    batch_b = [_batch_item("p3", "include", 0.8)]
    db_ctx, db, results = await _screen(tmp_path, _jev_settings("shadow"), [batch_a, batch_b])
    try:
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        assert len(calls) == 1
        cur = await db.execute("SELECT paper_id, choice, confidence, routed, details_json FROM jev_decisions")
        rows = await cur.fetchall()
        assert len(rows) == 1
        paper_id, choice, confidence, routed, details_json = rows[0]
        details = json.loads(details_json)
        assert (paper_id, choice, routed) == ("p3", "EXCLUDE", "shadow")
        assert confidence == pytest.approx(0.99)
        assert details["llm_decision"] == "include"
        assert details["would_route"] == "jev"
        assert details["latency_ms"] == 180
        assert details["cost_usd"] == pytest.approx(0.002)
        cur = await db.execute("SELECT phase, cost_usd FROM cost_records WHERE phase LIKE '%jev%'")
        assert [tuple(r) for r in await cur.fetchall()] == [("jev_shadow_phase_3_screening", pytest.approx(0.002))]
        cur = await db.execute("SELECT reason FROM screening_decisions WHERE reviewer_type = 'reviewer_b'")
        assert not str((await cur.fetchone())[0]).startswith("Jev screening")
    finally:
        await db_ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_shadow_is_fail_open(tmp_path, monkeypatch) -> None:
    async def _boom(**kwargs: object) -> JevAskResult:
        raise TimeoutError("jev timed out")

    monkeypatch.setattr(jev_screening, "ask_jev", _boom)
    monkeypatch.setattr(dual_screener_module, "jev_key_available", lambda: True)
    batch_a = [_batch_item("p1", "include", 0.95), _batch_item("p2", "include", 0.91), _batch_item("p3", "include", 0.6)]
    batch_b = [_batch_item("p3", "include", 0.8)]
    db_ctx, db, results = await _screen(tmp_path, _jev_settings("shadow"), [batch_a, batch_b])
    try:
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        cur = await db.execute("SELECT routed FROM jev_decisions")
        assert [r[0] for r in await cur.fetchall()] == ["shadow_error"]
    finally:
        await db_ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_live_batch_mode_uses_jev_for_reviewer_b(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(jev_screening, "ask_jev", _fake_ask("INCLUDE", 0.9, calls))
    batch_a = [_batch_item("p1", "include", 0.95), _batch_item("p2", "include", 0.91), _batch_item("p3", "include", 0.6)]
    db_ctx, db, results = await _screen(tmp_path, _jev_settings("live"), [batch_a])
    try:
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        cur = await db.execute("SELECT reason FROM screening_decisions WHERE reviewer_type = 'reviewer_b'")
        assert str((await cur.fetchone())[0]).startswith("Jev screening")
        cur = await db.execute("SELECT routed FROM jev_decisions")
        assert [r[0] for r in await cur.fetchall()] == ["jev"]
        cur = await db.execute("SELECT phase FROM cost_records WHERE phase LIKE '%jev%'")
        assert [r[0] for r in await cur.fetchall()] == ["phase_3_screening_jev"]
    finally:
        await db_ctx.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_live_low_confidence_escalates_to_llm(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(jev_screening, "ask_jev", _fake_ask("EXCLUDE", 0.5, calls))
    batch_a = [_batch_item("p1", "include", 0.95), _batch_item("p2", "include", 0.91), _batch_item("p3", "include", 0.6)]
    batch_b = [_batch_item("p3", "include", 0.8)]
    db_ctx, db, results = await _screen(tmp_path, _jev_settings("live"), [batch_a, batch_b])
    try:
        assert all(r.decision == ScreeningDecisionType.INCLUDE for r in results)
        cur = await db.execute("SELECT routed FROM jev_decisions")
        assert [r[0] for r in await cur.fetchall()] == ["escalate"]
    finally:
        await db_ctx.__aexit__(None, None, None)


def test_screening_cap_only_raised_when_live() -> None:
    assert jev_mode(_jev_settings("shadow"), "screening_reviewer_b") != "live"
    assert jev_mode(_jev_settings("live"), "screening_reviewer_b") == "live"
