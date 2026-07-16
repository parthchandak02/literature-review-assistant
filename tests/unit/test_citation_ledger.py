import pytest

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository
from src.models import CitationEntryRecord, ClaimRecord, EvidenceLinkRecord
from src.models.writing import SectionBlock, StructuredSectionDraft
from src.writing.orchestration import extract_and_register_claims


@pytest.mark.asyncio
async def test_citation_lineage_and_blocking(tmp_path) -> None:
    db_path = tmp_path / "ledger.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        ledger = CitationLedger(repo)

        claim = await ledger.register_claim(
            ClaimRecord(claim_text="A factual claim", section="results", confidence=0.9)
        )
        citation = await ledger.register_citation(
            CitationEntryRecord(
                citekey="Smith2024",
                title="Study",
                authors=["Smith"],
                resolved=True,
            )
        )
        await ledger.link_evidence(
            EvidenceLinkRecord(
                claim_id=claim.claim_id,
                citation_id=citation.citation_id,
                evidence_span="p.2",
                evidence_score=0.9,
            )
        )

        valid = await ledger.validate_manuscript("This is supported [Smith2024].")
        assert valid.unresolved_claims == []
        assert valid.unresolved_citations == []
        assert await ledger.block_export_if_invalid("This is supported [Smith2024].") is False


@pytest.mark.asyncio
async def test_unresolved_citation_blocks_export(tmp_path) -> None:
    db_path = tmp_path / "ledger_unresolved.db"
    async with get_db(str(db_path)) as db:
        ledger = CitationLedger(CitationRepository(db))
        blocked = await ledger.block_export_if_invalid("Unknown cite [Missing2025].")
        assert blocked is True


@pytest.mark.asyncio
async def test_numeric_citation_within_catalog_range_is_valid(tmp_path) -> None:
    db_path = tmp_path / "ledger_numeric.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        ledger = CitationLedger(repo)
        await ledger.register_citation(
            CitationEntryRecord(citekey="Smith2024", title="Study A", authors=["Smith"], resolved=True)
        )
        await ledger.register_citation(
            CitationEntryRecord(citekey="Jones2025", title="Study B", authors=["Jones"], resolved=True)
        )

        result = await ledger.validate_manuscript("Evidence [1] and [2] supports this.")
        assert result.unresolved_citations == []


@pytest.mark.asyncio
async def test_validate_section_scopes_unlinked_claims_to_requested_section(tmp_path) -> None:
    db_path = tmp_path / "ledger_section_scope.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        ledger = CitationLedger(repo)
        await ledger.register_citation(
            CitationEntryRecord(citekey="Smith2024", title="Study", authors=["Smith"], resolved=True)
        )
        await ledger.register_claim(ClaimRecord(claim_text="Unlinked claim", section="results", confidence=0.9))

        discussion_result = await ledger.validate_section("discussion", "Narrative discussion [Smith2024].")
        results_result = await ledger.validate_section("results", "Results statement [Smith2024].")

        assert discussion_result.unresolved_claims == []
        assert len(results_result.unresolved_claims) == 1


@pytest.mark.asyncio
async def test_extract_and_register_claims_from_structured_blocks(tmp_path) -> None:
    db_path = tmp_path / "ledger_structured_claims.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        await repo.register_citation(
            CitationEntryRecord(citekey="Smith2024", title="Study", authors=["Smith"], resolved=True)
        )
        draft = StructuredSectionDraft(
            section_key="results",
            blocks=[
                SectionBlock(
                    block_type="paragraph",
                    text="Smith et al. reported improved outcomes in the target population.",
                    citations=["Smith2024"],
                ),
            ],
        )
        registered = await extract_and_register_claims(
            "results",
            "",
            repo,
            structured_draft=draft,
        )
        assert registered == 1


@pytest.mark.asyncio
async def test_extract_and_register_claims_falls_back_to_markdown_regex(tmp_path) -> None:
    db_path = tmp_path / "ledger_markdown_claims.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        await repo.register_citation(
            CitationEntryRecord(citekey="Jones2025", title="Study", authors=["Jones"], resolved=True)
        )
        draft = StructuredSectionDraft(
            section_key="results",
            blocks=[
                SectionBlock(
                    block_type="paragraph",
                    text="A paragraph without structured citation fields.",
                    citations=[],
                ),
            ],
        )
        content = "Jones et al. found a meaningful effect [Jones2025]."
        registered = await extract_and_register_claims(
            "results",
            content,
            repo,
            structured_draft=draft,
        )
        assert registered == 1


@pytest.mark.asyncio
async def test_extract_and_register_claims_prefers_structured_blocks_over_markdown(tmp_path) -> None:
    db_path = tmp_path / "ledger_structured_precedence.db"
    async with get_db(str(db_path)) as db:
        repo = CitationRepository(db)
        await repo.register_citation(
            CitationEntryRecord(citekey="Smith2024", title="Study", authors=["Smith"], resolved=True)
        )
        await repo.register_citation(
            CitationEntryRecord(citekey="Jones2025", title="Study", authors=["Jones"], resolved=True)
        )
        draft = StructuredSectionDraft(
            section_key="results",
            blocks=[
                SectionBlock(
                    block_type="paragraph",
                    text="Structured claim from block citations.",
                    citations=["Smith2024"],
                ),
            ],
        )
        content = "Markdown-only claim should not register [Jones2025]."
        registered = await extract_and_register_claims(
            "results",
            content,
            repo,
            structured_draft=draft,
        )
        assert registered == 1
