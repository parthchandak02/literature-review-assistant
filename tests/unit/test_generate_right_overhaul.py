"""Unit tests for the Pipeline Generate-Right Overhaul (WS1-WS5).

Covers:
- WS1: PydanticAIClient.complete_validated() validation retry logic
- WS2: Citation budget computation and coverage checking
- WS5: PRISMACounts.validate_arithmetic() and pre-computed fields
- WS3: WritingPrepOutput / SectionWriteResult / AssemblyInput contracts
"""

from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, Field

from src.models.additional import PRISMACounts
from src.models.writing import (
    AssemblyInput,
    SectionBlock,
    SectionWriteResult,
    StructuredSectionDraft,
    WritingPrepOutput,
)
from src.writing.orchestration import (
    _citation_coverage_issues,
    _compute_section_citation_budget,
    _extract_included_study_citekeys,
    _extract_valid_citekeys,
)

# ---------------------------------------------------------------------------
# WS1: PydanticAIClient.complete_validated
# ---------------------------------------------------------------------------


class _TestResponseModel(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)


class _TestResponseModelStrict(BaseModel):
    label: str = Field(min_length=3)
    value: float = Field(ge=0.0)


@pytest.mark.asyncio
async def test_complete_validated_success_on_first_try() -> None:
    from src.llm.pydantic_client import PydanticAIClient

    valid_json = json.dumps({"name": "test", "score": 85})
    client = PydanticAIClient()

    with patch.object(
        client,
        "complete_with_usage",
        new_callable=AsyncMock,
        return_value=(valid_json, 100, 50, 0, 0),
    ):
        result, tok_in, tok_out, cw, cr, retries = await client.complete_validated(
            "prompt",
            model="google-gla:gemini-2.0-flash",
            temperature=0.1,
            response_model=_TestResponseModel,
        )

    assert isinstance(result, _TestResponseModel)
    assert result.name == "test"
    assert result.score == 85
    assert retries == 0
    assert tok_in == 100
    assert tok_out == 50


@pytest.mark.asyncio
async def test_complete_validated_retries_on_validation_error() -> None:
    from src.llm.pydantic_client import PydanticAIClient

    bad_json = json.dumps({"name": "test", "score": 200})
    good_json = json.dumps({"name": "test", "score": 85})

    client = PydanticAIClient()
    mock = AsyncMock(
        side_effect=[
            (bad_json, 90, 40, 0, 0),
            (good_json, 110, 55, 0, 0),
        ]
    )

    with patch.object(client, "complete_with_usage", mock):
        result, tok_in, tok_out, cw, cr, retries = await client.complete_validated(
            "prompt",
            model="google-gla:gemini-2.0-flash",
            temperature=0.1,
            response_model=_TestResponseModel,
        )

    assert isinstance(result, _TestResponseModel)
    assert result.score == 85
    assert retries == 1
    assert tok_in == 200
    assert tok_out == 95
    second_call_prompt = mock.call_args_list[1][0][0]
    assert "FAILED VALIDATION" in second_call_prompt


@pytest.mark.asyncio
async def test_complete_validated_raises_after_max_retries() -> None:
    from src.llm.pydantic_client import PydanticAIClient

    bad_json = json.dumps({"name": "test", "score": 200})

    client = PydanticAIClient()
    mock = AsyncMock(return_value=(bad_json, 50, 30, 0, 0))

    with patch.object(client, "complete_with_usage", mock):
        with pytest.raises(Exception):
            await client.complete_validated(
                "prompt",
                model="google-gla:gemini-2.0-flash",
                temperature=0.1,
                response_model=_TestResponseModel,
                max_validation_retries=2,
            )

    assert mock.call_count == 3


@pytest.mark.asyncio
async def test_complete_validated_uses_provided_json_schema() -> None:
    from src.llm.pydantic_client import PydanticAIClient

    valid_json = json.dumps({"name": "custom", "score": 50})
    custom_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "integer"},
        },
    }

    client = PydanticAIClient()
    mock = AsyncMock(return_value=(valid_json, 80, 40, 0, 0))

    with patch.object(client, "complete_with_usage", mock):
        result, _, _, _, _, retries = await client.complete_validated(
            "prompt",
            model="google-gla:gemini-2.0-flash",
            temperature=0.1,
            response_model=_TestResponseModel,
            json_schema=custom_schema,
        )

    assert retries == 0
    call_kwargs = mock.call_args_list[0][1]
    assert call_kwargs["json_schema"] is custom_schema


@pytest.mark.asyncio
async def test_complete_validated_aggregates_tokens_across_retries() -> None:
    from src.llm.pydantic_client import PydanticAIClient

    bad_json = json.dumps({"label": "ab", "value": -1.0})
    good_json = json.dumps({"label": "abc", "value": 1.5})

    client = PydanticAIClient()
    mock = AsyncMock(
        side_effect=[
            (bad_json, 100, 50, 5, 10),
            (bad_json, 120, 60, 3, 8),
            (good_json, 130, 70, 4, 12),
        ]
    )

    with patch.object(client, "complete_with_usage", mock):
        result, tok_in, tok_out, cw, cr, retries = await client.complete_validated(
            "prompt",
            model="google-gla:gemini-2.0-flash",
            temperature=0.1,
            response_model=_TestResponseModelStrict,
            max_validation_retries=2,
        )

    assert isinstance(result, _TestResponseModelStrict)
    assert retries == 2
    assert tok_in == 350
    assert tok_out == 180
    assert cw == 12
    assert cr == 30


@pytest.mark.asyncio
async def test_complete_validated_handles_json_decode_error() -> None:
    from src.llm.pydantic_client import PydanticAIClient

    bad_text = "NOT JSON AT ALL"
    good_json = json.dumps({"name": "ok", "score": 50})

    client = PydanticAIClient()
    mock = AsyncMock(
        side_effect=[
            (bad_text, 50, 30, 0, 0),
            (good_json, 80, 40, 0, 0),
        ]
    )

    with patch.object(client, "complete_with_usage", mock):
        result, _, _, _, _, retries = await client.complete_validated(
            "prompt",
            model="google-gla:gemini-2.0-flash",
            temperature=0.1,
            response_model=_TestResponseModel,
        )

    assert retries == 1
    assert result.name == "ok"


# ---------------------------------------------------------------------------
# WS2: Citation budget and coverage
# ---------------------------------------------------------------------------


def test_extract_included_study_citekeys_parses_catalog() -> None:
    catalog = (
        "## INCLUDED STUDIES\n"
        "[Smith2023] A study about things (2023)\n"
        "[Jones2024] Another study (2024)\n"
        "## METHODOLOGY REFERENCES\n"
        "[Page2021] PRISMA 2020\n"
    )
    keys = _extract_included_study_citekeys(catalog)
    assert keys == {"Smith2023", "Jones2024"}


def test_extract_included_study_citekeys_empty_catalog() -> None:
    assert _extract_included_study_citekeys("") == set()


def test_extract_included_study_citekeys_no_methodology_block() -> None:
    catalog = (
        "## INCLUDED STUDIES\n"
        "[Alpha2020] Study (2020)\n"
        "[Beta2021] Study (2021)\n"
    )
    keys = _extract_included_study_citekeys(catalog)
    assert keys == {"Alpha2020", "Beta2021"}


def test_compute_citation_budget_results_section() -> None:
    catalog = (
        "## INCLUDED STUDIES\n"
        "[Smith2023] A study (2023)\n"
        "[Jones2024] Another study (2024)\n"
        "## METHODOLOGY REFERENCES\n"
        "[Page2021] PRISMA\n"
    )
    valid = {"Smith2023", "Jones2024", "Page2021"}
    budget = _compute_section_citation_budget("results", catalog, valid)
    assert budget == {"Smith2023", "Jones2024"}


def test_compute_citation_budget_methods_section_empty() -> None:
    catalog = "## INCLUDED STUDIES\n[Smith2023] Study\n"
    valid = {"Smith2023"}
    budget = _compute_section_citation_budget("methods", catalog, valid)
    assert budget == set()


def test_compute_citation_budget_abstract_section_empty() -> None:
    catalog = "## INCLUDED STUDIES\n[Smith2023] Study\n"
    valid = {"Smith2023"}
    budget = _compute_section_citation_budget("abstract", catalog, valid)
    assert budget == set()


def test_compute_citation_budget_filters_by_valid_keys() -> None:
    catalog = (
        "## INCLUDED STUDIES\n"
        "[Smith2023] Study\n"
        "[Invalid2000] Ghost\n"
    )
    valid = {"Smith2023"}
    budget = _compute_section_citation_budget("results", catalog, valid)
    assert budget == {"Smith2023"}


def test_citation_coverage_issues_all_cited() -> None:
    draft = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Study by [Smith2023].",
                citations=["Smith2023"],
            ),
            SectionBlock(
                block_type="paragraph",
                text="Also [Jones2024].",
                citations=["Jones2024"],
            ),
        ],
        cited_keys=["Smith2023", "Jones2024"],
    )
    issues, missing = _citation_coverage_issues(
        "results", draft, {"Smith2023", "Jones2024"}
    )
    assert issues == []
    assert missing == set()


def test_citation_coverage_issues_detects_missing() -> None:
    draft = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Study by [Smith2023].",
                citations=["Smith2023"],
            ),
        ],
        cited_keys=["Smith2023"],
    )
    issues, missing = _citation_coverage_issues(
        "results", draft, {"Smith2023", "Jones2024"}
    )
    assert len(issues) == 1
    assert "missing_required_citations:1" in issues
    assert missing == {"Jones2024"}


def test_citation_coverage_issues_empty_budget() -> None:
    draft = StructuredSectionDraft(section_key="methods", blocks=[])
    issues, missing = _citation_coverage_issues("methods", draft, set())
    assert issues == []
    assert missing == set()


def test_citation_coverage_finds_inline_citekeys_in_text() -> None:
    draft = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="See [Jones2024] for evidence.",
                citations=[],
            ),
        ],
        cited_keys=[],
    )
    issues, missing = _citation_coverage_issues(
        "results", draft, {"Smith2023", "Jones2024"}
    )
    assert "Smith2023" in missing
    assert "Jones2024" not in missing


# ---------------------------------------------------------------------------
# WS5: PRISMACounts.validate_arithmetic
# ---------------------------------------------------------------------------


def test_prisma_counts_validate_arithmetic_valid() -> None:
    counts = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=90,
        records_excluded_screening=70,
        reports_sought=20,
        reports_not_retrieved=5,
        reports_assessed=15,
        reports_excluded_with_reasons={"other": 5},
        studies_included_qualitative=0,
        studies_included_quantitative=10,
        arithmetic_valid=True,
        records_after_deduplication=90,
        total_included=10,
    )
    assert counts.validate_arithmetic() is True


def test_prisma_counts_validate_arithmetic_strict_raises() -> None:
    counts = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=90,
        records_excluded_screening=70,
        reports_sought=20,
        reports_not_retrieved=5,
        reports_assessed=10,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=10,
        arithmetic_valid=False,
        records_after_deduplication=90,
        total_included=10,
    )
    with pytest.raises(ValueError, match="PRISMA arithmetic violations"):
        counts.validate_arithmetic(strict=True)


def test_prisma_counts_validate_warns_not_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    counts = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=90,
        records_excluded_screening=70,
        reports_sought=20,
        reports_not_retrieved=5,
        reports_assessed=10,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=10,
        arithmetic_valid=False,
        records_after_deduplication=90,
        total_included=10,
    )
    with caplog.at_level(logging.WARNING):
        result = counts.validate_arithmetic()
    assert result is False
    assert "PRISMA arithmetic violations" in caplog.text


def test_prisma_counts_precomputed_fields_default_zero() -> None:
    counts = PRISMACounts(
        databases_records={},
        other_sources_records={},
        total_identified_databases=0,
        total_identified_other=0,
        duplicates_removed=0,
        records_screened=0,
        records_excluded_screening=0,
        reports_sought=0,
        reports_not_retrieved=0,
        reports_assessed=0,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=0,
        arithmetic_valid=True,
    )
    assert counts.records_after_deduplication == 0
    assert counts.total_included == 0


def test_prisma_counts_detects_after_dedup_mismatch() -> None:
    counts = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=90,
        records_excluded_screening=70,
        reports_sought=20,
        reports_not_retrieved=5,
        reports_assessed=15,
        reports_excluded_with_reasons={},
        studies_included_qualitative=0,
        studies_included_quantitative=10,
        arithmetic_valid=True,
        records_after_deduplication=999,
        total_included=10,
    )
    with pytest.raises(ValueError, match="records_after_deduplication mismatch"):
        counts.validate_arithmetic(strict=True)


def test_prisma_counts_detects_total_included_mismatch() -> None:
    counts = PRISMACounts(
        databases_records={"pubmed": 100},
        other_sources_records={},
        total_identified_databases=100,
        total_identified_other=0,
        duplicates_removed=10,
        records_screened=90,
        records_excluded_screening=70,
        reports_sought=20,
        reports_not_retrieved=5,
        reports_assessed=15,
        reports_excluded_with_reasons={},
        studies_included_qualitative=3,
        studies_included_quantitative=7,
        arithmetic_valid=True,
        records_after_deduplication=90,
        total_included=999,
    )
    with pytest.raises(ValueError, match="total_included mismatch"):
        counts.validate_arithmetic(strict=True)


# ---------------------------------------------------------------------------
# WS3: Writing phase contracts (model construction)
# ---------------------------------------------------------------------------


def test_writing_prep_output_construction() -> None:
    prep = WritingPrepOutput(
        workflow_id="wf-123",
        citation_catalog="## INCLUDED STUDIES\n[Smith2023] Study\n",
        valid_citekeys=["Smith2023", "Page2021"],
        included_study_citekeys=["Smith2023"],
        section_order=[
            "abstract",
            "introduction",
            "methods",
            "results",
            "discussion",
            "conclusion",
        ],
        already_completed=["abstract"],
    )
    assert prep.workflow_id == "wf-123"
    assert len(prep.valid_citekeys) == 2
    assert prep.already_completed == ["abstract"]


def test_section_write_result_construction() -> None:
    draft = StructuredSectionDraft(
        section_key="methods",
        blocks=[
            SectionBlock(block_type="paragraph", text="Methods text."),
        ],
    )
    result = SectionWriteResult(
        section_key="methods",
        content_markdown="## Methods\n\nMethods text.",
        structured_draft=draft,
        cited_keys=["Page2021"],
        word_count=3,
        validation_retries=1,
        used_deterministic_fallback=False,
    )
    assert result.section_key == "methods"
    assert result.validation_retries == 1
    assert not result.used_deterministic_fallback


def test_assembly_input_construction() -> None:
    r1 = SectionWriteResult(
        section_key="abstract",
        content_markdown="Abstract text.",
        structured_draft=StructuredSectionDraft(section_key="abstract"),
    )
    r2 = SectionWriteResult(
        section_key="methods",
        content_markdown="Methods text.",
        structured_draft=StructuredSectionDraft(section_key="methods"),
    )
    assembly = AssemblyInput(
        workflow_id="wf-123",
        section_results=[r1, r2],
        citation_catalog="catalog",
        valid_citekeys=["Page2021"],
    )
    assert len(assembly.section_results) == 2
    assert assembly.section_results[0].section_key == "abstract"


def test_section_write_result_serialization_round_trip() -> None:
    draft = StructuredSectionDraft(
        section_key="results",
        blocks=[
            SectionBlock(
                block_type="paragraph",
                text="Results.",
                citations=["Smith2023"],
            ),
        ],
        cited_keys=["Smith2023"],
    )
    result = SectionWriteResult(
        section_key="results",
        content_markdown="## Results\n\nResults.",
        structured_draft=draft,
        cited_keys=["Smith2023"],
        word_count=1,
    )
    json_str = result.model_dump_json()
    restored = SectionWriteResult.model_validate_json(json_str)
    assert restored.section_key == "results"
    assert restored.structured_draft.blocks[0].text == "Results."
    assert restored.cited_keys == ["Smith2023"]


def test_extract_valid_citekeys_consistent_with_budget() -> None:
    catalog = (
        "## INCLUDED STUDIES\n"
        "[Smith2023] A study (2023)\n"
        "[Jones2024] Another (2024)\n"
        "## METHODOLOGY REFERENCES\n"
        "[Page2021] PRISMA\n"
    )
    valid = _extract_valid_citekeys(catalog)
    included = _extract_included_study_citekeys(catalog)
    assert included.issubset(valid)
    assert "Page2021" in valid
    assert "Page2021" not in included
