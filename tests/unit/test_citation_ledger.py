import pytest

from src.citation.ledger import CitationLedger
from src.db.database import get_db
from src.db.repositories import CitationRepository
from src.models import CitationEntryRecord, ClaimRecord, EvidenceLinkRecord


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
