"""Citation lineage ledger implementation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.db.repositories import CitationRepository
from src.models import CitationEntryRecord, ClaimRecord, EvidenceLinkRecord


@dataclass
class ManuscriptValidationResult:
    unresolved_claims: list[str]
    unresolved_citations: list[str]


class CitationLedger:
    def __init__(self, repository: CitationRepository):
        self.repository = repository

    async def register_claim(self, claim: ClaimRecord) -> ClaimRecord:
        await self.repository.register_claim(claim)
        return claim

    async def register_citation(self, citation: CitationEntryRecord) -> CitationEntryRecord:
        await self.repository.register_citation(citation)
        return citation

    async def link_evidence(self, link: EvidenceLinkRecord) -> EvidenceLinkRecord:
        await self.repository.link_evidence(link)
        return link

    async def validate_manuscript(self, text: str) -> ManuscriptValidationResult:
        citekey_mentions = set(re.findall(r"\[([A-Za-z0-9_:-]+)\]", text))
        known_citekeys = set(await self.repository.get_citekeys())
        unresolved_citations = sorted(citekey_mentions - known_citekeys)

        unresolved_claims = await self.repository.get_unlinked_claim_ids()
        return ManuscriptValidationResult(
            unresolved_claims=sorted(unresolved_claims),
            unresolved_citations=unresolved_citations,
        )

    async def validate_section(self, section: str, text: str) -> ManuscriptValidationResult:
        """Validate a single section. Same logic as validate_manuscript, section-scoped."""
        _ = section
        return await self.validate_manuscript(text)

    async def block_export_if_invalid(
        self,
        text: str,
        block_on_unresolved: bool = True,
    ) -> bool:
        """Return True if the manuscript should be blocked from export.

        block_on_unresolved: when False, always returns False even if there are
        unresolved citekeys (allows export with warnings). Reads from
        CitationLineageConfig.block_export_on_unresolved in production call sites.
        """
        if not block_on_unresolved:
            return False
        result = await self.validate_manuscript(text)
        return bool(result.unresolved_claims or result.unresolved_citations)
