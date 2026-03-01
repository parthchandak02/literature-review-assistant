from __future__ import annotations

import pytest

from src.models import ExtractionRecord, StudyDesign
from src.synthesis.effect_size import compute_mean_difference_effect_size
from src.synthesis.feasibility import assess_meta_analysis_feasibility
from src.synthesis.meta_analysis import pool_effects
from src.synthesis.narrative import build_narrative_synthesis
from src.visualization.forest_plot import render_forest_plot
from src.visualization.funnel_plot import render_funnel_plot


def _record(paper_id: str, summary: str, effect_size: str = "0.5", se: str = "0.12") -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=StudyDesign.RCT,
        intervention_description="AI tutoring support",
        outcomes=[{
            "name": "knowledge_retention",
            "description": "Exam score retention",
            "effect_size": effect_size,
            "se": se,
        }],
        results_summary={"summary": summary, "source": "metadata"},
    )


@pytest.mark.asyncio
async def test_synthesis_pipeline_meta_analysis_and_narrative(tmp_path) -> None:
    records = [
        _record("p1", "Students showed improved retention with higher scores."),
        _record("p2", "Results were better for intervention students."),
        _record("p3", "Mixed outcomes but generally improved engagement and retention."),
    ]
    feasibility = assess_meta_analysis_feasibility(records)
    assert feasibility.feasible is True
    assert "knowledge_retention" in feasibility.groupings

    study_data = [
        (82.0, 10.0, 60, 76.0, 10.5, 60),
        (80.0, 9.5, 55, 75.0, 10.0, 55),
        (84.0, 10.2, 58, 77.0, 10.8, 58),
    ]
    effects: list[float] = []
    variances: list[float] = []
    for mean_t, sd_t, n_t, mean_c, sd_c, n_c in study_data:
        effect, variance = compute_mean_difference_effect_size(mean_t, sd_t, n_t, mean_c, sd_c, n_c)
        effects.append(effect)
        variances.append(variance)

    pooled = pool_effects(
        outcome_name="knowledge_retention",
        effect_measure="mean_difference",
        effects=effects,
        variances=variances,
    )
    assert pooled.n_studies == 3
    assert pooled.ci_lower <= pooled.pooled_effect <= pooled.ci_upper

    forest_path = render_forest_plot(
        effects=effects,
        variances=variances,
        labels=["study_1", "study_2", "study_3"],
        output_path=str(tmp_path / "forest_plot.png"),
        title="Knowledge Retention Meta-analysis",
    )
    assert forest_path.endswith("forest_plot.png")
    assert (tmp_path / "forest_plot.png").exists()

    narrative = await build_narrative_synthesis("knowledge_retention", records)
    assert narrative.n_studies == 3
    assert narrative.effect_direction_summary in {"predominantly_positive", "mixed", "predominantly_negative"}

    below_threshold_path = render_funnel_plot(
        effect_sizes=effects,
        standard_errors=[variance**0.5 for variance in variances],
        pooled_effect=pooled.pooled_effect,
        output_path=str(tmp_path / "funnel_plot_below_threshold.png"),
        title="Below threshold funnel",
    )
    assert below_threshold_path is None
    assert not (tmp_path / "funnel_plot_below_threshold.png").exists()

    long_effects = effects + [effects[i % len(effects)] + 0.1 * ((i % 3) - 1) for i in range(7)]
    long_ses = [variance**0.5 for variance in variances] + [0.45, 0.42, 0.40, 0.44, 0.41, 0.43, 0.39]
    funnel_path = render_funnel_plot(
        effect_sizes=long_effects,
        standard_errors=long_ses,
        pooled_effect=pooled.pooled_effect,
        output_path=str(tmp_path / "funnel_plot.png"),
        title="Knowledge Retention Funnel Plot",
    )
    assert funnel_path is not None
    assert (tmp_path / "funnel_plot.png").exists()
