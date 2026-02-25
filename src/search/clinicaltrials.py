"""ClinicalTrials.gov search connector (grey literature).

Uses the ClinicalTrials.gov REST API v2 to search registered clinical trials.
Results are tagged as source_category=OTHER_SOURCE for PRISMA attribution
(grey literature, not a bibliographic database).

Enable by adding "clinicaltrials" to target_databases in config/review.yaml.
This connector is OFF by default to keep production runs fast.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import aiohttp

from src.models import CandidatePaper, SearchResult, SourceCategory
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

_CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalTrialsConnector:
    """Search ClinicalTrials.gov for registered clinical trials.

    Results are classified as SourceCategory.OTHER_SOURCE because
    ClinicalTrials.gov is a trial registry, not a bibliographic database.
    Per PRISMA 2020, trial registry searches must be reported separately
    under "Other methods" or "Registers".
    """

    name = "clinicaltrials_gov"
    source_category = SourceCategory.OTHER_SOURCE

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

    @staticmethod
    def _to_candidate(study: dict) -> Optional[CandidatePaper]:
        """Convert a ClinicalTrials.gov study JSON object to a CandidatePaper."""
        proto = study.get("protocolSection") or {}
        id_module = proto.get("identificationModule") or {}
        desc_module = proto.get("descriptionModule") or {}
        status_module = proto.get("statusModule") or {}
        contacts_module = proto.get("contactsLocationsModule") or {}

        nct_id = id_module.get("nctId", "")
        title = (
            id_module.get("briefTitle")
            or id_module.get("officialTitle")
            or "Untitled"
        ).strip()

        if not title or not nct_id:
            return None

        brief_summary = (desc_module.get("briefSummary") or "").strip()[:4000]
        start_date = (status_module.get("startDateStruct") or {}).get("date") or ""
        year: Optional[int] = None
        if start_date and len(start_date) >= 4:
            try:
                year = int(start_date[:4])
            except ValueError:
                pass

        # Build a rough author list from responsible party / sponsor
        responsible = proto.get("sponsorCollaboratorsModule") or {}
        sponsor_name = (responsible.get("leadSponsor") or {}).get("name", "")
        authors = [sponsor_name] if sponsor_name else ["Unknown"]

        # URL to the study on ClinicalTrials.gov
        url = f"https://clinicaltrials.gov/study/{nct_id}"

        return CandidatePaper(
            title=title,
            authors=authors,
            year=year,
            source_database="clinicaltrials_gov",
            doi=None,
            abstract=brief_summary or None,
            url=url,
            source_category=SourceCategory.OTHER_SOURCE,
        )

    async def search(
        self,
        query: str,
        max_results: int = 50,
        date_start: Optional[int] = None,
        date_end: Optional[int] = None,
    ) -> list[SearchResult]:
        """Search ClinicalTrials.gov using the v2 API."""
        page_size = min(max_results, 25)
        params: dict[str, str | int] = {
            "query.term": query,
            "pageSize": page_size,
            "fields": ",".join([
                "NCTId",
                "BriefTitle",
                "OfficialTitle",
                "BriefSummary",
                "StartDate",
                "LeadSponsorName",
            ]),
        }
        if date_start:
            params["filter.advanced"] = f"AREA[StartDate]RANGE[{date_start}-01-01, MAX]"

        papers: list[CandidatePaper] = []
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(
                timeout=timeout, connector=tcp_connector_with_certifi()
            ) as session:
                async with session.get(_CT_API_BASE, params=params) as response:
                    if response.status != 200:
                        logger.warning(
                            "ClinicalTrials.gov returned status %s for query: %s",
                            response.status,
                            query[:80],
                        )
                        return []
                    data = await response.json()
                    for study in data.get("studies") or []:
                        candidate = self._to_candidate(study)
                        if candidate:
                            papers.append(candidate)
        except Exception as exc:
            logger.warning("ClinicalTrials.gov search failed: %s", exc)
            return []

        if not papers:
            return []

        return [
            SearchResult(
                workflow_id=self.workflow_id,
                database_name=self.name,
                source_category=self.source_category,
                search_date=date.today().isoformat(),
                search_query=query,
                limits_applied=f"pageSize={page_size}",
                records_retrieved=len(papers),
                papers=papers,
            )
        ]
