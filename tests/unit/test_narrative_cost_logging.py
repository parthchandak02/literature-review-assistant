from __future__ import annotations

import pytest

from src.llm.provider import LLMProvider
from src.llm.pydantic_client import PydanticAIClient
from src.models import AgentConfig, ExtractionRecord, SettingsConfig, StudyDesign
from src.models.extraction import OutcomeRecord
from src.synthesis.narrative import build_narrative_synthesis


class _StubNarrativeClient(PydanticAIClient):
    async def complete_with_usage(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> tuple[str, int, int, int, int]:
        return ('{"direction":"positive","justification":"clear benefit"}', 100, 20, 0, 10)


class _StubProvider(LLMProvider):
    def __init__(self) -> None:
        self.reserve_calls = 0
        self.logged: list[dict] = []

    async def reserve_call_slot(self, agent_name: str):  # type: ignore[override]
        self.reserve_calls += 1
        return None

    def estimate_cost(
        self, model: str, tokens_in: int, tokens_out: int, cache_write: int = 0, cache_read: int = 0
    ) -> float:  # type: ignore[override]
        return 0.0123

    async def log_cost(self, **kwargs) -> None:  # type: ignore[override]
        self.logged.append(kwargs)


def _record(paper_id: str) -> ExtractionRecord:
    return ExtractionRecord(
        paper_id=paper_id,
        study_design=StudyDesign.RCT,
        intervention_description="AI tutoring support",
        outcomes=[OutcomeRecord(name="knowledge_retention", description="Exam score retention")],
        results_summary={"summary": "Intervention group improved retention outcomes."},
    )


@pytest.mark.asyncio
async def test_narrative_llm_logs_cost_per_study() -> None:
    settings = SettingsConfig(agents={"narrative": AgentConfig(model="google:gemini-2.5-flash-lite", temperature=0.0)})
    llm_client = _StubNarrativeClient()
    provider = _StubProvider()

    result = await build_narrative_synthesis(
        "primary_outcome",
        [_record("p1"), _record("p2")],
        llm_client=llm_client,
        settings=settings,
        llm_provider=provider,
        workflow_id="wf-test",
    )

    assert result.n_studies == 2
    assert provider.reserve_calls == 2
    assert len(provider.logged) == 2
    assert all(entry["phase"] == "phase_5_narrative_direction" for entry in provider.logged)
    assert all(entry["workflow_id"] == "wf-test" for entry in provider.logged)
