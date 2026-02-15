from src.restart.citation_publishing import CitationPublishingPipeline
from src.restart.reliability_gates import ReliabilityGateRunner


def test_citation_publishing_creates_layout(tmp_path):
    pipeline = CitationPublishingPipeline(output_dir=str(tmp_path))
    artifacts = pipeline.prepare_layout()
    produced = {artifact.format_name for artifact in artifacts}
    assert "markdown" in produced
    assert "csl_json" in produced
    assert (tmp_path / "references.csl.json").exists()


def test_reliability_gates_enforce_citation_threshold():
    gates = ReliabilityGateRunner(max_invalid_citation_ratio=0.10, max_cost_usd=2.0)
    results = gates.run(
        {
            "checkpoint_resume_enabled": True,
            "invalid_citation_count": 2,
            "total_citation_count": 10,
            "total_cost_usd": 3.0,
        }
    )
    by_name = {result.gate_name: result for result in results}
    assert by_name["checkpoint_resume"].passed is True
    assert by_name["citation_quality"].passed is False
    assert by_name["cost_budget"].passed is False
