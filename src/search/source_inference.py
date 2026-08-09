"""Infer literature-database provenance from URLs, CSV fields, and file hints.

Shared by CSV import, Perplexity search, and PRISMA attribution so connector
and imported records consolidate under the same canonical database names.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from src.models.enums import SourceCategory

# Canonical snake_case names used across connectors and PRISMA counts.
OTHER_SOURCE = "other"
PERPLEXITY_WEB = "perplexity_web"

_CANONICAL_ALIASES: dict[str, str] = {
    "scopus": "scopus",
    "pubmed": "pubmed",
    "medline": "pubmed",
    "embase": "embase",
    "cinahl": "cinahl",
    "ieee xplore": "ieee_xplore",
    "ieee_xplore": "ieee_xplore",
    "ieee": "ieee_xplore",
    "semantic scholar": "semantic_scholar",
    "semantic_scholar": "semantic_scholar",
    "web of science": "web_of_science",
    "web_of_science": "web_of_science",
    "wos": "web_of_science",
    "openalex": "openalex",
    "crossref": "crossref",
    "arxiv": "arxiv",
    "dblp": "dblp",
    "core": "core",
    "europepmc": "europepmc",
    "europe pmc": "europepmc",
    "clinicaltrials": "clinicaltrials_gov",
    "clinicaltrials_gov": "clinicaltrials_gov",
    "clinicaltrials.gov": "clinicaltrials_gov",
    "csv import": OTHER_SOURCE,
    "other": OTHER_SOURCE,
}

_DATABASE_SOURCES: frozenset[str] = frozenset(
    {
        "pubmed",
        "scopus",
        "embase",
        "cinahl",
        "ieee_xplore",
        "semantic_scholar",
        "web_of_science",
        "openalex",
        "crossref",
        "arxiv",
        "dblp",
        "core",
        "europepmc",
        "clinicaltrials_gov",
    }
)

# Full-URL regex rules checked before host-only mapping. Order matters.
_URL_PATTERN_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"scopus\.com/(?:inward/)?record", re.I), "scopus"),
    (re.compile(r"[?&]eid=2-s2\.0-\d+", re.I), "scopus"),
    (re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/\d+", re.I), "pubmed"),
    (re.compile(r"ncbi\.nlm\.nih\.gov/pmc/", re.I), "pubmed"),
    (re.compile(r"pmc\.ncbi\.nlm\.nih\.gov/", re.I), "pubmed"),
    (re.compile(r"ieeexplore\.ieee\.org/document/\d+", re.I), "ieee_xplore"),
    (re.compile(r"semanticscholar\.org/paper/", re.I), "semantic_scholar"),
    (re.compile(r"openalex\.org/W\d+", re.I), "openalex"),
    (re.compile(r"arxiv\.org/(?:abs|pdf|html)/", re.I), "arxiv"),
    (re.compile(r"webofscience\.com/", re.I), "web_of_science"),
    (re.compile(r"webofknowledge\.com/", re.I), "web_of_science"),
    (re.compile(r"embase\.com/", re.I), "embase"),
    (re.compile(r"cinahl\.ebsco", re.I), "cinahl"),
    (re.compile(r"ebscohost\.com/", re.I), "cinahl"),
]

# URL host -> canonical database name. More specific hosts first.
_URL_HOST_TO_SOURCE: list[tuple[list[str], str]] = [
    (["pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"], "pubmed"),
    (["ncbi.nlm.nih.gov"], "pubmed"),
    (["scopus.com"], "scopus"),
    (["embase.com"], "embase"),
    (["arxiv.org"], "arxiv"),
    (["ieeexplore.ieee.org", "ieee.org"], "ieee_xplore"),
    (["semanticscholar.org"], "semantic_scholar"),
    (["openalex.org"], "openalex"),
    (["webofscience.com", "webofknowledge.com"], "web_of_science"),
    # doi.org / publisher hosts -> crossref for URL-based inference (Perplexity/web).
    # PRISMA identification counts require the searched database (PubMed, Scopus, ...);
    # Crossref and doi.org are DOI resolvers, not databases searched at identification.
    (["doi.org", "dx.doi.org"], "crossref"),
    (
        [
            "frontiersin.org",
            "link.springer.com",
            "springer.com",
            "nature.com",
            "sciencedirect.com",
            "tandfonline.com",
            "wiley.com",
            "acm.org",
            "dl.acm.org",
            "plos.org",
            "mdpi.com",
            "hindawi.com",
            "iop.org",
            "iopscience.iop.org",
            "iacis.org",
            "srcpublishers.com",
            "dialoguessr.com",
        ],
        "crossref",
    ),
]

# CSV column names that carry an explicit database / index label (not journal title).
_DATABASE_COLUMN_ALIASES: list[str] = [
    "Database",
    "DATABASE",
    "Source Database",
    "Source database",
    "Index",
    "Data source",
    "Data Source",
    "Retrieved from",
    "Origin",
]

_EID_COLUMN_ALIASES: list[str] = ["EID", "E-ID", "Scopus EID", "Scopus ID"]


def canonical_database_name(raw: str | None) -> str | None:
    """Normalize a human or connector label to canonical snake_case."""
    if not raw or not str(raw).strip():
        return None
    key = re.sub(r"[_\s]+", " ", str(raw).strip().lower())
    return _CANONICAL_ALIASES.get(key, str(raw).strip().lower().replace(" ", "_"))


def source_category_for_database(database_name: str) -> SourceCategory:
    return SourceCategory.DATABASE if database_name in _DATABASE_SOURCES else SourceCategory.OTHER_SOURCE


def _match_url_patterns(url: str) -> str | None:
    for pattern, db_name in _URL_PATTERN_RULES:
        if pattern.search(url):
            return db_name
    return None


def _match_url_host(url: str) -> str | None:
    try:
        parsed = urlparse(url.strip())
        host = (parsed.netloc or parsed.path or "").lower().strip()
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return None
        for domains, db_name in _URL_HOST_TO_SOURCE:
            for domain in domains:
                if host == domain or host.endswith("." + domain):
                    return db_name
    except Exception:
        return None
    return None


def infer_source_from_url(
    url: str | None,
    *,
    fallback: str = OTHER_SOURCE,
    file_hint: str | None = None,
) -> tuple[str, SourceCategory]:
    """Infer database_name and source_category from a record URL.

    Checks path/query patterns (Scopus inward URI, IEEE document ID, etc.)
    before host-only mapping. Generic DOI resolvers inherit *file_hint* when
    the URL alone does not name an index.
    """
    if not url or not url.strip():
        hinted = canonical_database_name(file_hint)
        if hinted and hinted != OTHER_SOURCE:
            return hinted, source_category_for_database(hinted)
        return fallback, source_category_for_database(fallback)

    normalized = url.strip()

    from_pattern = _match_url_patterns(normalized)
    if from_pattern:
        return from_pattern, source_category_for_database(from_pattern)

    from_host = _match_url_host(normalized)
    if from_host:
        # doi.org / dx.doi.org are publisher resolvers, not index names.
        if from_host == "crossref" and file_hint:
            hinted = canonical_database_name(file_hint)
            if hinted and hinted != OTHER_SOURCE:
                return hinted, source_category_for_database(hinted)
        return from_host, source_category_for_database(from_host)

    hinted = canonical_database_name(file_hint)
    if hinted and hinted != OTHER_SOURCE:
        return hinted, source_category_for_database(hinted)

    return fallback, source_category_for_database(fallback)


def infer_source_from_row_ids(row: dict[str, str], fieldnames: list[str]) -> str | None:
    """Row-level ID columns that imply a specific bibliographic index."""
    if "PMID" in fieldnames and (row.get("PMID") or "").strip():
        return "pubmed"
    if "Medline PMID" in fieldnames and (row.get("Medline PMID") or "").strip():
        return "pubmed"
    if "Embase EMID" in fieldnames and (row.get("Embase EMID") or "").strip():
        return "embase"
    if "CINAHL AN" in fieldnames and (row.get("CINAHL AN") or "").strip():
        return "cinahl"
    if "Accession Number" in fieldnames and (row.get("Accession Number") or "").strip():
        return "cinahl"
    for alias in _EID_COLUMN_ALIASES:
        if alias in fieldnames:
            eid = (row.get(alias) or "").strip()
            if eid and re.match(r"2-s2\.0-\d+", eid):
                return "scopus"
    return None


def resolve_database_column(fieldnames: list[str]) -> str | None:
    for alias in _DATABASE_COLUMN_ALIASES:
        if alias in fieldnames:
            return alias
    return None


def detect_csv_export_format(fieldnames: list[str], url_samples: list[str]) -> str | None:
    """Infer export format from column signatures and a sample of row URLs."""
    names = set(fieldnames)
    lowered_urls = [u.lower() for u in url_samples if u and u.strip()]

    def _url_share(substr: str) -> float:
        if not lowered_urls:
            return 0.0
        return sum(1 for u in lowered_urls if substr in u) / len(lowered_urls)

    # Filename-independent format fingerprints.
    if "CINAHL AN" in names or ("Accession Number" in names and "Major Subjects" in names):
        return "cinahl"
    if "Medline PMID" in names or "Embase EMID" in names:
        return "embase"
    if "PMID" in names and "MeSH Terms" in names:
        return "pubmed"

    # Scopus CSV export: Source title + Author Keywords; often scopus.com inward URIs.
    if "Author Keywords" in names and "Source title" in names:
        if _url_share("scopus.com") >= 0.15 or any("eid=2-s2.0-" in u for u in lowered_urls):
            return "scopus"
        return "scopus"

    if _url_share("scopus.com") >= 0.5:
        return "scopus"
    if _url_share("pubmed.ncbi.nlm.nih.gov") >= 0.5 or _url_share("ncbi.nlm.nih.gov") >= 0.5:
        return "pubmed"
    if _url_share("ieeexplore.ieee.org") >= 0.5:
        return "ieee_xplore"
    if _url_share("semanticscholar.org") >= 0.5:
        return "semantic_scholar"
    if _url_share("webofscience.com") >= 0.5 or _url_share("webofknowledge.com") >= 0.5:
        return "web_of_science"
    if _url_share("embase.com") >= 0.5:
        return "embase"

    return None


def infer_csv_row_source(
    *,
    url: str | None,
    doi: str | None,
    explicit_database: str | None,
    row: dict[str, str],
    fieldnames: list[str],
    file_hint: str | None,
) -> tuple[str, SourceCategory]:
    """Resolve per-row database for CSV imports.

    Precedence:
      1. Explicit database/index column value
      2. URL path/host patterns (Scopus inward URI, PubMed, IEEE, ...)
      3. Row ID columns (PMID, Scopus EID, EMID, CINAHL AN, ...)
      4. File-level export format hint (column signature + URL sample)
      5. ``other`` (last resort; bare DOI alone does not imply a searched database)
    """
    if explicit_database:
        canonical = canonical_database_name(explicit_database)
        if canonical and canonical != OTHER_SOURCE:
            return canonical, source_category_for_database(canonical)

    from_url, cat = infer_source_from_url(url, fallback=OTHER_SOURCE, file_hint=file_hint)
    if from_url != OTHER_SOURCE:
        return from_url, cat

    from_ids = infer_source_from_row_ids(row, fieldnames)
    if from_ids:
        return from_ids, source_category_for_database(from_ids)

    if file_hint:
        canonical_hint = canonical_database_name(file_hint)
        if canonical_hint and canonical_hint != OTHER_SOURCE:
            return canonical_hint, source_category_for_database(canonical_hint)

    # PRISMA: a bare DOI does not identify which database was searched at identification.
    return OTHER_SOURCE, SourceCategory.OTHER_SOURCE
