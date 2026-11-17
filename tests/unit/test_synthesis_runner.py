"""Tests for the synthesis runner's numeric pooling bridge.

`_try_meta_analysis` is the only path that turns extraction strings into a
pooled MetaAnalysisResult. `pool_effects` itself is tested separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import ExtractionRecord, MetaAnalysisResult, OutcomeRecord, StudyDesign
from src.orchestration.runners.synthesis_runner import _try_meta_analysis, run_synthesis_node
from src.orchestration.state import ReviewState
from src.synthesis.meta_analysis import pool_effects
from src.synthesis.narrative import NarrativeSynthesis

_RUNNER = "src.orchestration.runners.synthesis_runner"


def _record(
    paper_id: str,
    outcomes: list[OutcomeRecord] | None = None,
    *,
    effect: str | None = None,
    se: str = "",
    variance: str = "",
    name: str = "exam_score",
) -> ExtractionRecord:
    if outcomes is None:
        outcomes = [OutcomeRecord(name=name, effect_size=effect or "", se=se, variance=variance)]
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=StudyDesign.RCT,
        intervention_description="tutoring",
        outcomes=outcomes,
    )


def _pair(effect_a: str, effect_b: str, **kwargs: str) -> list[ExtractionRecord]:
    return [
        _record("paper-aaaa-1111", effect=effect_a, **kwargs),
        _record("paper-bbbb-2222", effect=effect_b, **kwargs),
    ]


def _patch_plots(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    captured: dict[str, list] = {"forest": [], "funnel": [], "pool": []}
    real_pool = pool_effects

    def _pool(*args, **kwargs):
        captured["pool"].append((args, kwargs))
        return real_pool(*args, **kwargs)

    def _forest(effects, variances, labels, output_path, title):
        captured["forest"].append(
            {"effects": list(effects), "variances": list(variances), "labels": list(labels), "title": title}
        )
        return output_path

    def _funnel(effect_sizes, standard_errors, pooled_effect, output_path, title, minimum_studies=10):
        captured["funnel"].append(
            {
                "effect_sizes": list(effect_sizes),
                "standard_errors": list(standard_errors),
                "pooled_effect": pooled_effect,
                "minimum_studies": minimum_studies,
            }
        )
        return output_path

    monkeypatch.setattr(f"{_RUNNER}.pool_effects", _pool)
    monkeypatch.setattr(f"{_RUNNER}.render_forest_plot", _forest)
    monkeypatch.setattr(f"{_RUNNER}.render_funnel_plot", _funnel)
    return captured


def test_try_meta_analysis_pools_se_as_variance_and_skips_funnel_below_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_plots(monkeypatch)
    records = _pair("0.20", "0.30", se="0.20")

    result, forest, funnel = _try_meta_analysis(
        records,
        outcome_name="exam_score",
        het_threshold=40.0,
        effect_measure="mean_difference",
        forest_path="figures/forest.png",
        funnel_path="figures/funnel.png",
        funnel_min_studies=10,
    )

    assert result is not None
    assert result.n_studies == 2
    assert result.effect_measure == "mean_difference"
    assert result.outcome_name == "exam_score"
    assert result.forest_plot_path == "figures/forest.png"
    assert result.funnel_plot_path is None
    assert forest == "figures/forest.png"
    assert funnel is None
    assert captured["forest"][0]["effects"] == [0.20, 0.30]
    assert captured["forest"][0]["variances"] == pytest.approx([0.04, 0.04])
    assert captured["forest"][0]["labels"] == ["paper-aaaa-1", "paper-bbbb-2"]
    assert captured["funnel"] == []
    assert captured["pool"][0][1]["heterogeneity_threshold"] == 40.0


def test_try_meta_analysis_prefers_explicit_variance_and_draws_funnel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_plots(monkeypatch)
    records = _pair("0.20", "0.30", se="0.90", variance="0.01")

    result, _forest, funnel = _try_meta_analysis(
        records,
        outcome_name="exam_score",
        het_threshold=40.0,
        effect_measure="smd",
        forest_path="figures/forest.png",
        funnel_path="figures/funnel.png",
        funnel_min_studies=2,
    )

    assert result is not None
    assert result.funnel_plot_path == "figures/funnel.png"
    assert funnel == "figures/funnel.png"
    assert captured["forest"][0]["variances"] == pytest.approx([0.01, 0.01])
    assert captured["funnel"][0]["standard_errors"] == pytest.approx([0.1, 0.1])
    assert captured["funnel"][0]["pooled_effect"] == pytest.approx(result.pooled_effect)
    assert captured["funnel"][0]["minimum_studies"] == 2


def test_try_meta_analysis_parses_first_finite_token_and_normalizes_outcome_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_plots(monkeypatch)
    records = [
        _record("paper-one", effect="SMD = 0.44 (95% CI 0.10 to 0.78)", se="SE=0.20", name="Exam Score"),
        _record("paper-two", effect="0.22, p<0.05", se="-0.10", name="primary exam score followup"),
    ]

    result, _forest, _funnel = _try_meta_analysis(
        records,
        outcome_name="exam_score",
        het_threshold=50.0,
        effect_measure="mean_difference",
        forest_path="forest.png",
        funnel_path="funnel.png",
        funnel_min_studies=10,
    )

    assert result is not None
    assert captured["forest"][0]["effects"] == pytest.approx([0.44, 0.22])
    # A leading minus on SE is squared, matching the current variance rule.
    assert captured["forest"][0]["variances"] == pytest.approx([0.04, 0.01])


def test_try_meta_analysis_uses_later_outcome_when_earlier_match_is_not_numeric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_plots(monkeypatch)
    records = [
        _record(
            "paper-one",
            outcomes=[
                OutcomeRecord(name="exam_score", effect_size="high", se="0.10"),
                OutcomeRecord(name="exam_score_followup", effect_size="0.15", se="0.10"),
            ],
        ),
        _record(
            "paper-two",
            outcomes=[
                OutcomeRecord(name="exam_score", effect_size="0.25", variance="0.02", se="0.90"),
                OutcomeRecord(name="exam_score_followup", effect_size="9.99", se="0.10"),
            ],
        ),
    ]

    result, _forest, _funnel = _try_meta_analysis(
        records,
        outcome_name="exam_score",
        het_threshold=40.0,
        effect_measure="mean_difference",
        forest_path="forest.png",
        funnel_path="funnel.png",
    )

    assert result is not None
    assert result.n_studies == 2
    assert captured["forest"][0]["effects"] == pytest.approx([0.15, 0.25])
    assert captured["forest"][0]["variances"] == pytest.approx([0.01, 0.02])


@pytest.mark.parametrize(
    "records",
    [
        [],
        [_record("only-one", effect="0.2", se="0.1")],
        _pair("0.2", "0.3", se="0"),
        _pair("0.2", "0.3", variance="0"),
        _pair("0.2", "0.3", variance="-0.01", se="0.2"),
        _pair("12%", "0.3", se="0.2"),
        _pair("nan", "0.3", se="0.2"),
        _pair("inf", "0.3", se="0.2"),
        _pair("0.2", "0.3", se="0.2", variance="not reported"),
        _pair("0.2", "0.3", se="0.2", name="blood_pressure"),
    ],
)
def test_try_meta_analysis_returns_none_without_two_positive_variances(
    records: list[ExtractionRecord],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch_plots(monkeypatch)

    result, forest, funnel = _try_meta_analysis(
        records,
        outcome_name="exam_score",
        het_threshold=40.0,
        effect_measure="mean_difference",
        forest_path="forest.png",
        funnel_path="funnel.png",
    )

    assert (result, forest, funnel) == (None, None, None)
    assert captured["pool"] == []
    assert captured["forest"] == []


def test_try_meta_analysis_drops_result_when_pooling_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    captured = _patch_plots(monkeypatch)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("statsmodels failed")

    monkeypatch.setattr(f"{_RUNNER}.pool_effects", _boom)

    with caplog.at_level("WARNING", logger=_RUNNER):
        result, forest, funnel = _try_meta_analysis(
            _pair("0.2", "0.3", se="0.1"),
            outcome_name="exam_score",
            het_threshold=40.0,
            effect_measure="mean_difference",
            forest_path="forest.png",
            funnel_path="funnel.png",
        )

    assert (result, forest, funnel) == (None, None, None)
    assert captured["forest"] == []
    pooling_warnings = [r for r in caplog.records if "Meta-analysis pooling failed" in r.message]
    assert len(pooling_warnings) == 1
    assert "outcome=exam_score" in pooling_warnings[0].message
    assert "measure=mean_difference" in pooling_warnings[0].message
    assert "n_studies=2" in pooling_warnings[0].message
    assert "RuntimeError" in pooling_warnings[0].message
    assert "statsmodels failed" in pooling_warnings[0].message


def test_try_meta_analysis_keeps_pooled_result_when_a_plot_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_plots(monkeypatch)

    def _forest_ok(*_args, **_kwargs):
        return "forest.png"

    def _forest_fails(*_args, **_kwargs):
        raise OSError("disk full")

    def _funnel_fails(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(f"{_RUNNER}.render_forest_plot", _forest_fails)
    with caplog.at_level("WARNING", logger=_RUNNER):
        result, forest, funnel = _try_meta_analysis(
            _pair("0.2", "0.3", se="0.1"),
            outcome_name="exam_score",
            het_threshold=40.0,
            effect_measure="mean_difference",
            forest_path="forest.png",
            funnel_path="funnel.png",
            funnel_min_studies=2,
        )
    assert result is not None
    assert result.forest_plot_path is None
    assert result.funnel_plot_path == "funnel.png"
    assert forest is None
    assert funnel == "funnel.png"
    forest_warnings = [r for r in caplog.records if "Forest plot render failed" in r.message]
    assert len(forest_warnings) == 1
    assert "outcome=exam_score" in forest_warnings[0].message
    assert "path=forest.png" in forest_warnings[0].message
    assert "OSError" in forest_warnings[0].message
    assert "disk full" in forest_warnings[0].message

    caplog.clear()
    monkeypatch.setattr(f"{_RUNNER}.render_forest_plot", _forest_ok)
    monkeypatch.setattr(f"{_RUNNER}.render_funnel_plot", _funnel_fails)
    with caplog.at_level("WARNING", logger=_RUNNER):
        result, forest, funnel = _try_meta_analysis(
            _pair("0.2", "0.3", se="0.1"),
            outcome_name="exam_score",
            het_threshold=40.0,
            effect_measure="mean_difference",
            forest_path="forest.png",
            funnel_path="funnel.png",
            funnel_min_studies=2,
        )
    assert result is not None
    assert result.forest_plot_path == "forest.png"
    assert result.funnel_plot_path is None
    assert forest == "forest.png"
    assert funnel is None
    funnel_warnings = [r for r in caplog.records if "Funnel plot render failed" in r.message]
    assert len(funnel_warnings) == 1
    assert "outcome=exam_score" in funnel_warnings[0].message
    assert "path=funnel.png" in funnel_warnings[0].message
    assert "OSError" in funnel_warnings[0].message
    assert "disk full" in funnel_warnings[0].message


def _narrative() -> NarrativeSynthesis:
    return NarrativeSynthesis(
        outcome_name="primary_outcome",
        n_studies=2,
        effect_direction_summary="mixed",
        key_themes=["learning"],
        synthesis_table=[],
        narrative_text="Narrative body.",
    )


def _meta(outcome_name: str) -> MetaAnalysisResult:
    return MetaAnalysisResult(
        outcome_name=outcome_name,
        n_studies=2,
        effect_measure="mean_difference",
        pooled_effect=0.25,
        ci_lower=0.10,
        ci_upper=0.40,
        p_value=0.01,
        model="fixed",
        cochrans_q=0.1,
        i_squared=0.0,
    )


def _settings(*, enabled: bool) -> MagicMock:
    settings = MagicMock()
    settings.llm.request_timeout_seconds = 120
    settings.meta_analysis.enabled = enabled
    settings.meta_analysis.heterogeneity_threshold = 40
    settings.meta_analysis.effect_measure_continuous = "mean_difference"
    settings.meta_analysis.funnel_plot_minimum_studies = 10
    return settings


def _state(tmp_path: Path, records: list[ExtractionRecord], *, enabled: bool, sparse: bool) -> ReviewState:
    return ReviewState(
        review_path="config/review.yaml",
        settings_path="config/settings.yaml",
        run_root=str(tmp_path),
        workflow_id="wf-synth",
        settings=_settings(enabled=enabled),
        db_path=str(tmp_path / "runtime.db"),
        extraction_records=records,
        sparse_evidence_mode=sparse,
        artifacts={
            "narrative_synthesis": str(tmp_path / "narrative.json"),
            "fig_forest_plot": str(tmp_path / "forest.png"),
            "fig_funnel_plot": str(tmp_path / "funnel.png"),
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("enabled", "sparse", "records"),
    [
        (True, True, None),
        (False, False, None),
        (True, False, []),
    ],
)
async def test_run_synthesis_node_skips_pooling_unless_feasible_and_enabled(
    tmp_path: Path,
    enabled: bool,
    sparse: bool,
    records: list[ExtractionRecord] | None,
) -> None:
    if records is None:
        records = _pair("0.20", "0.30", se="0.10")
    state = _state(tmp_path, records, enabled=enabled, sparse=sparse)
    with (
        patch(f"{_RUNNER}._llm_available", return_value=False),
        patch(f"{_RUNNER}.get_chat_client") as chat,
        patch(f"{_RUNNER}.get_db") as get_db,
        patch(f"{_RUNNER}.WorkflowRepository") as repo_cls,
        patch(f"{_RUNNER}.build_narrative_synthesis", new=AsyncMock(return_value=_narrative())),
        patch(f"{_RUNNER}._try_meta_analysis") as try_meta,
    ):
        get_db.return_value.__aenter__.return_value = AsyncMock()
        repo_cls.return_value = AsyncMock()
        await run_synthesis_node(state, MagicMock())

    try_meta.assert_not_called()
    chat.assert_not_called()
    payload = json.loads((tmp_path / "narrative.json").read_text(encoding="utf-8"))
    assert payload["sparse_evidence_mode"] is sparse
    assert "meta_analysis" not in payload
    assert payload["narrative"]["narrative_text"] == "Narrative body."
    assert state.sensitivity_results == []
    repo_cls.return_value.save_checkpoint.assert_awaited_with(
        "wf-synth",
        "phase_5_synthesis",
        papers_processed=len(records),
    )


@pytest.mark.asyncio
async def test_run_synthesis_node_uses_first_group_that_pools(tmp_path: Path) -> None:
    records = [
        _record(
            "paper-one",
            outcomes=[
                OutcomeRecord(name="exam_score", effect_size="0.20", se="0.10"),
                OutcomeRecord(name="knowledge_retention", effect_size="0.40", se="0.10"),
            ],
        ),
        _record(
            "paper-two",
            outcomes=[
                OutcomeRecord(name="exam_score", effect_size="0.30", se="0.10"),
                OutcomeRecord(name="knowledge_retention", effect_size="0.50", se="0.10"),
            ],
        ),
    ]
    state = _state(tmp_path, records, enabled=True, sparse=False)
    tried: list[str] = []

    def _fake_try(
        records, outcome_name, het_threshold, effect_measure, forest_path, funnel_path, funnel_min_studies=10
    ):
        del records, het_threshold, effect_measure, forest_path, funnel_path, funnel_min_studies
        tried.append(outcome_name)
        if outcome_name == "exam_score":
            return None, None, None
        return _meta(outcome_name), "forest.png", None

    sens = MagicMock()
    sens.to_grounding_text.return_value = "sens:knowledge_retention"

    with (
        patch(f"{_RUNNER}._llm_available", return_value=False),
        patch(f"{_RUNNER}.get_chat_client") as chat,
        patch(f"{_RUNNER}.get_db") as get_db,
        patch(f"{_RUNNER}.WorkflowRepository") as repo_cls,
        patch(f"{_RUNNER}.build_narrative_synthesis", new=AsyncMock(return_value=_narrative())),
        patch(f"{_RUNNER}._try_meta_analysis", side_effect=_fake_try),
        patch(f"{_RUNNER}.run_sensitivity_analysis", return_value=sens) as run_sens,
    ):
        get_db.return_value.__aenter__.return_value = AsyncMock()
        repo = AsyncMock()
        repo_cls.return_value = repo
        await run_synthesis_node(state, MagicMock())

    chat.assert_not_called()
    assert tried == ["exam_score", "knowledge_retention"]
    run_sens.assert_called_once()
    assert run_sens.call_args.kwargs["outcome_name"] == "knowledge_retention"
    assert run_sens.call_args.kwargs["effect_measure"] == "mean_difference"
    assert state.sensitivity_results == ["sens:knowledge_retention"]
    payload = json.loads((tmp_path / "narrative.json").read_text(encoding="utf-8"))
    assert payload["meta_analysis"]["outcome_name"] == "knowledge_retention"
    assert payload["meta_analysis"]["pooled_effect"] == pytest.approx(0.25)
    rationale = repo.append_decision_log.await_args.args[0].rationale
    assert "meta_analysis=yes" in rationale
    assert "forest=yes" in rationale
    assert "funnel=no" in rationale
    repo.save_synthesis_result.assert_awaited()
