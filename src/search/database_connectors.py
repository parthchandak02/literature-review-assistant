"""
Database Connectors

Connectors for various academic databases: PubMed, Scopus, Web of Science, IEEE Xplore, Google Scholar,
arXiv, Semantic Scholar, Crossref.

This module maintains backward compatibility by re-exporting from the refactored connector modules.
"""

# Re-export base classes and Paper for backward compatibility
from .connectors.base import Paper, DatabaseConnector
from .models import Author, Affiliation
from .proxy_manager import ProxyManager
from .integrity_checker import IntegrityChecker
from ..utils.html_utils import html_unescape, clean_abstract

# Re-export connectors (will be imported from individual files once created)
# For now, keep the implementations here but mark them for migration
from typing import List, Dict, Optional
import os
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import logging

from .exceptions import (
    DatabaseSearchError,
    RateLimitError,
    NetworkError,
    ParsingError,
    APIKeyError,
)
from .rate_limiter import retry_with_backoff
from .cache import SearchCache

load_dotenv()

logger = logging.getLogger(__name__)


class PubMedConnector(DatabaseConnector):
    """PubMed/NCBI connector using Entrez API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        super().__init__(
            api_key or os.getenv("PUBMED_API_KEY"),
            cache,
            proxy_manager,
            integrity_checker,
            persistent_session,
            cookie_jar,
        )
        self.email = email or os.getenv("PUBMED_EMAIL")
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search PubMed with proper XML parsing."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "PubMed")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            rate_limiter = self._get_rate_limiter()
            rate_limiter.acquire()

            # Search endpoint
            search_url = f"{self.base_url}/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": min(max_results, 10000),  # PubMed allows up to 10k
                "retmode": "json",
                "usehistory": "y",
            }
            if self.api_key:
                params["api_key"] = self.api_key
            if self.email:
                params["email"] = self.email

            session = self._get_session()
            request_kwargs = self._get_request_kwargs()
            request_kwargs.setdefault("timeout", 30)
            
            response = session.get(search_url, params=params, **request_kwargs)
            response.raise_for_status()
            search_data = response.json()

            if "esearchresult" not in search_data:
                return papers

            pmids = search_data["esearchresult"].get("idlist", [])

            if not pmids:
                return papers

            # Limit to requested max_results
            pmids = pmids[:max_results]

            # Fetch details in batches (PubMed recommends batches of 200)
            batch_size = 200
            for i in range(0, len(pmids), batch_size):
                batch_pmids = pmids[i : i + batch_size]

                rate_limiter.acquire()

                fetch_url = f"{self.base_url}/efetch.fcgi"
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(batch_pmids),
                    "retmode": "xml",
                    "rettype": "abstract",
                }
                if self.api_key:
                    fetch_params["api_key"] = self.api_key

                fetch_response = session.get(fetch_url, params=fetch_params, **request_kwargs)
                fetch_response.raise_for_status()

                # Parse XML
                try:
                    root = ET.fromstring(fetch_response.content)
                    # PubMed XML doesn't use namespaces, so use empty namespace dict
                    namespace = {}

                    for article in root.findall(".//PubmedArticle", namespace):
                        paper = self._parse_pubmed_article(article, namespace)
                        if paper:
                            papers.append(paper)
                except ET.ParseError as e:
                    logger.error(f"Error parsing PubMed XML: {e}")
                    raise ParsingError(f"Failed to parse PubMed XML: {e}") from e

        except requests.RequestException as e:
            logger.error(f"Network error searching PubMed: {e}")
            raise NetworkError(f"PubMed search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching PubMed: {e}")
            raise DatabaseSearchError(f"PubMed search error: {e}") from e

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "PubMed", papers)

        return papers

    def _parse_pubmed_article(
        self, article: ET.Element, namespace: Dict[str, str]
    ) -> Optional[Paper]:
        """Parse a single PubMed article from XML."""
        try:
            # Title (PubMed XML doesn't use namespaces)
            title_elem = article.find(".//ArticleTitle", namespace)
            title = html_unescape(title_elem.text) if title_elem is not None and title_elem.text else ""

            # Abstract
            abstract_elems = article.findall(".//AbstractText", namespace)
            abstract_parts = []
            for elem in abstract_elems:
                if elem.text:
                    label = elem.get("Label", "")
                    text = html_unescape(elem.text)
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract = clean_abstract(" ".join(abstract_parts) if abstract_parts else "")

            # Authors
            authors = []
            affiliations = []
            author_list = article.find(".//AuthorList", namespace)
            if author_list is not None:
                for author in author_list.findall("Author", namespace):
                    last_name = author.find("LastName", namespace)
                    first_name = author.find("ForeName", namespace)
                    if last_name is not None and last_name.text:
                        name = last_name.text
                        if first_name is not None and first_name.text:
                            name = f"{first_name.text} {name}"
                        authors.append(name)
                    
                    # Extract affiliations from Author elements
                    affiliation_elems = author.findall("Affiliation", namespace)
                    for aff in affiliation_elems:
                        if aff.text and aff.text.strip():
                            affiliations.append(aff.text.strip())

            # Year
            pub_date = article.find(".//PubDate", namespace)
            year = None
            if pub_date is not None:
                year_elem = pub_date.find("Year", namespace)
                if year_elem is not None and year_elem.text:
                    try:
                        year = int(year_elem.text)
                    except ValueError:
                        pass

            # DOI
            doi = None
            article_id_list = article.find(".//ArticleIdList", namespace)
            if article_id_list is not None:
                for article_id in article_id_list.findall("ArticleId", namespace):
                    if article_id.get("IdType") == "doi":
                        doi = article_id.text
                        break

            # Journal
            journal_elem = article.find(".//Journal/Title", namespace)
            journal = journal_elem.text if journal_elem is not None and journal_elem.text else None

            # PMID for URL
            pmid_elem = article.find(".//PMID", namespace)
            pmid = pmid_elem.text if pmid_elem is not None else None
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}" if pmid else None

            # Keywords
            keywords = []
            keyword_list = article.find(".//KeywordList", namespace)
            if keyword_list is not None:
                for keyword in keyword_list.findall("Keyword", namespace):
                    if keyword.text:
                        keywords.append(keyword.text)

            return Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                doi=doi,
                journal=journal,
                database="PubMed",
                url=url,
                keywords=keywords if keywords else None,
                subjects=keywords if keywords else None,  # Use keywords as subjects
                affiliations=affiliations if affiliations else None,
            )
        except Exception as e:
            logger.warning(f"Error parsing individual PubMed article: {e}")
            return None

    def get_database_name(self) -> str:
        return "PubMed"


class ArxivConnector(DatabaseConnector):
    """arXiv connector using official arxiv Python library."""

    def __init__(
        self,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        super().__init__(
            cache=cache,
            proxy_manager=proxy_manager,
            integrity_checker=integrity_checker,
            persistent_session=persistent_session,
            cookie_jar=cookie_jar,
        )
        try:
            import arxiv

            self.arxiv_client = arxiv.Client(page_size=100, delay_seconds=0.5, num_retries=3)
        except ImportError:
            raise ImportError("arxiv library required. Install with: pip install arxiv")

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search arXiv."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "arXiv")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            rate_limiter = self._get_rate_limiter()
            rate_limiter.acquire()

            import arxiv

            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            for result in self.arxiv_client.results(search):
                # Extract year from published date
                year = result.published.year if result.published else None

                # Extract authors
                authors = [author.name for author in result.authors]

                # Extract categories
                categories = result.categories if hasattr(result, "categories") else []

                paper = Paper(
                    title=result.title,
                    abstract=result.summary,
                    authors=authors,
                    year=year,
                    doi=None,  # arXiv doesn't have DOI, use arxiv_id
                    journal=None,
                    database="arXiv",
                    url=result.entry_id,
                    keywords=categories if categories else None,
                )
                papers.append(paper)

                if len(papers) >= max_results:
                    break

        except ImportError:
            raise ImportError("arxiv library required. Install with: pip install arxiv")
        except Exception as e:
            logger.error(f"Error searching arXiv: {e}")
            raise DatabaseSearchError(f"arXiv search error: {e}") from e

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "arXiv", papers)

        return papers

    def get_database_name(self) -> str:
        return "arXiv"


class SemanticScholarConnector(DatabaseConnector):
    """Semantic Scholar connector."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        super().__init__(
            api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
            cache,
            proxy_manager,
            integrity_checker,
            persistent_session,
            cookie_jar,
        )
        self.base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search Semantic Scholar."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "Semantic Scholar")
            if cached:
                return cached[:max_results]

        papers = []
        offset = 0
        limit = min(100, max_results)  # Semantic Scholar max is 100 per request

        try:
            while len(papers) < max_results:
                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()

                params = {
                    "query": query,
                    "limit": limit,
                    "offset": offset,
                    "fields": "title,authors,abstract,year,url,externalIds,publicationTypes,venue,fieldsOfStudy",
                }

                headers = {}
                if self.api_key:
                    headers["x-api-key"] = self.api_key

                session = self._get_session()
                request_kwargs = self._get_request_kwargs()
                request_kwargs.setdefault("timeout", 30)
                
                response = session.get(self.base_url, params=params, headers=headers, **request_kwargs)

                if response.status_code == 429:
                    raise RateLimitError("Semantic Scholar rate limit exceeded")

                response.raise_for_status()
                data = response.json()

                if "data" not in data:
                    break

                for paper_data in data["data"]:
                    if len(papers) >= max_results:
                        break

                    # Extract authors
                    authors = []
                    affiliations = []
                    if "authors" in paper_data:
                        for author in paper_data["authors"]:
                            if author.get("name"):
                                authors.append(author.get("name"))
                            
                            # Extract affiliations from author objects
                            if "affiliation" in author:
                                aff = author["affiliation"]
                                if isinstance(aff, str) and aff.strip():
                                    affiliations.append(aff.strip())
                                elif isinstance(aff, dict):
                                    # Try different possible fields
                                    aff_name = aff.get("name") or aff.get("affiliation") or aff.get("institution")
                                    if aff_name and aff_name.strip():
                                        affiliations.append(aff_name.strip())

                    # Extract DOI
                    doi = None
                    if "externalIds" in paper_data and paper_data["externalIds"]:
                        doi = paper_data["externalIds"].get("DOI")

                    # Extract year
                    year = paper_data.get("year")

                    # Extract venue/journal
                    venue = paper_data.get("venue")

                    # Extract fields of study
                    fields = paper_data.get("fieldsOfStudy", [])

                    paper = Paper(
                        title=paper_data.get("title", ""),
                        abstract=paper_data.get("abstract", ""),
                        authors=authors,
                        year=year,
                        doi=doi,
                        journal=venue,
                        database="Semantic Scholar",
                        url=paper_data.get("url"),
                        keywords=fields if fields else None,
                        subjects=fields if fields else None,  # Use fieldsOfStudy as subjects
                        affiliations=affiliations if affiliations else None,
                    )
                    papers.append(paper)

                # Check if we have more results
                if len(data.get("data", [])) < limit:
                    break

                offset += limit

                if offset >= 10000:  # Semantic Scholar has a limit
                    break

        except requests.RequestException as e:
            logger.error(f"Network error searching Semantic Scholar: {e}")
            raise NetworkError(f"Semantic Scholar search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching Semantic Scholar: {e}")
            raise DatabaseSearchError(f"Semantic Scholar search error: {e}") from e

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Semantic Scholar", papers)

        return papers

    def get_database_name(self) -> str:
        return "Semantic Scholar"


class CrossrefConnector(DatabaseConnector):
    """Crossref connector using REST API."""

    def __init__(
        self,
        email: Optional[str] = None,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        super().__init__(
            cache=cache,
            proxy_manager=proxy_manager,
            integrity_checker=integrity_checker,
            persistent_session=persistent_session,
            cookie_jar=cookie_jar,
        )
        self.email = email or os.getenv("CROSSREF_EMAIL", "user@example.com")
        self.base_url = "https://api.crossref.org/works"

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search Crossref using cursor-based pagination."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "Crossref")
            if cached:
                return cached[:max_results]

        papers = []
        cursor = "*"
        rows_per_page = min(1000, max_results)  # Crossref allows up to 1000

        try:
            while len(papers) < max_results:
                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()

                params = {
                    "query": query,
                    "rows": rows_per_page,
                    "cursor": cursor,
                    "mailto": self.email,
                }

                session = self._get_session()
                request_kwargs = self._get_request_kwargs()
                request_kwargs.setdefault("timeout", 30)
                
                response = session.get(self.base_url, params=params, **request_kwargs)

                if response.status_code == 429:
                    raise RateLimitError("Crossref rate limit exceeded")

                response.raise_for_status()
                data = response.json()

                if "message" not in data or "items" not in data["message"]:
                    break

                items = data["message"]["items"]

                for item in items:
                    if len(papers) >= max_results:
                        break

                    # Extract title
                    title = ""
                    if "title" in item and item["title"]:
                        title = " ".join(item["title"])

                    # Extract abstract - Crossref abstracts can be in different formats
                    abstract = ""
                    if "abstract" in item:
                        abstract_text = item["abstract"]
                        if isinstance(abstract_text, str):
                            abstract = abstract_text.strip()
                        elif isinstance(abstract_text, list) and abstract_text:
                            # Join list items
                            abstract = " ".join(str(t) for t in abstract_text if t).strip()
                        elif isinstance(abstract_text, dict):
                            # Some abstracts are nested objects
                            abstract = abstract_text.get("text", "") or abstract_text.get("value", "")
                            if isinstance(abstract, list):
                                abstract = " ".join(str(t) for t in abstract if t).strip()
                            else:
                                abstract = str(abstract).strip() if abstract else ""

                    # Extract authors - handle various formats
                    authors = []
                    affiliations = []
                    if "author" in item and isinstance(item["author"], list):
                        for author in item["author"]:
                            if isinstance(author, dict):
                                given = author.get("given", "")
                                family = author.get("family", "")
                                # Some entries have name as a single field
                                if not family and "name" in author:
                                    name = author["name"]
                                    if name:
                                        authors.append(name)
                                elif family:
                                    # Format: "Given Family" or just "Family" if no given name
                                    name = f"{given} {family}".strip()
                                    if name:
                                        authors.append(name)
                                
                                # Extract affiliations from author objects
                                if "affiliation" in author:
                                    aff_list = author["affiliation"] if isinstance(author["affiliation"], list) else [author["affiliation"]]
                                    for aff in aff_list:
                                        if isinstance(aff, dict):
                                            # Try different possible fields
                                            aff_name = aff.get("name") or aff.get("affiliation") or aff.get("institution")
                                            if aff_name and aff_name.strip():
                                                affiliations.append(aff_name.strip())
                                        elif isinstance(aff, str) and aff.strip():
                                            affiliations.append(aff.strip())
                            elif isinstance(author, str):
                                # Sometimes authors are just strings
                                if author.strip():
                                    authors.append(author.strip())

                    # Extract year
                    year = None
                    if "published-print" in item and item["published-print"]:
                        date_parts = item["published-print"].get("date-parts", [])
                        if date_parts and date_parts[0]:
                            year = date_parts[0][0]
                    elif "published-online" in item and item["published-online"]:
                        date_parts = item["published-online"].get("date-parts", [])
                        if date_parts and date_parts[0]:
                            year = date_parts[0][0]

                    # Extract DOI
                    doi = item.get("DOI")

                    # Extract journal
                    journal = None
                    if "container-title" in item and item["container-title"]:
                        journal = item["container-title"][0]

                    # Extract publisher
                    publisher = item.get("publisher")

                    # Build URL
                    url = None
                    if doi:
                        url = f"https://doi.org/{doi}"
                    elif "URL" in item:
                        url = item["URL"]

                    # Extract subjects/keywords from Crossref
                    subjects = None
                    keywords = None
                    if "subject" in item:
                        subjects = item["subject"] if isinstance(item["subject"], list) else [item["subject"]]
                        keywords = subjects  # Use subjects as keywords too
                    elif "keyword" in item:
                        keywords = item["keyword"] if isinstance(item["keyword"], list) else [item["keyword"]]
                        subjects = keywords

                    paper = Paper(
                        title=title,
                        abstract=abstract,
                        authors=authors,
                        year=year,
                        doi=doi,
                        journal=journal or publisher,
                        database="Crossref",
                        url=url,
                        keywords=keywords,
                        subjects=subjects,
                        affiliations=affiliations if affiliations else None,
                    )
                    papers.append(paper)

                # Get next cursor
                if "message" in data and "next-cursor" in data["message"]:
                    cursor = data["message"]["next-cursor"]
                else:
                    break

                # Stop if no more items
                if len(items) < rows_per_page:
                    break

        except requests.RequestException as e:
            logger.error(f"Network error searching Crossref: {e}")
            raise NetworkError(f"Crossref search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching Crossref: {e}")
            raise DatabaseSearchError(f"Crossref search error: {e}") from e

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Crossref", papers)

        return papers

    def get_database_name(self) -> str:
        return "Crossref"


class ScopusConnector(DatabaseConnector):
    """Scopus connector (requires API key)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        view: Optional[str] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        super().__init__(
            api_key or os.getenv("SCOPUS_API_KEY"),
            cache,
            proxy_manager,
            integrity_checker,
            persistent_session,
            cookie_jar,
        )
        self.base_url = "https://api.elsevier.com/content/search/scopus"
        # View: STANDARD (basic fields) or COMPLETE (all fields, requires subscription)
        # If None, defaults to COMPLETE if subscriber, STANDARD otherwise
        self.view = view

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search Scopus."""
        if not self.api_key:
            logger.warning("Scopus API key required")
            return []

        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "Scopus")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            headers = {"Accept": "application/json", "X-ELS-APIKey": self.api_key}

            # Determine view: COMPLETE for subscribers (more fields), STANDARD otherwise
            view = self.view or "COMPLETE"  # Default to COMPLETE for richer data
            
            params = {
                "query": query,
                "count": min(max_results, 25),  # Scopus API limit per request
                "start": 0,
                "view": view,
            }

            while len(papers) < max_results:
                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()

                session = self._get_session()
                request_kwargs = self._get_request_kwargs()
                request_kwargs.setdefault("timeout", 30)
                
                response = session.get(self.base_url, headers=headers, params=params, **request_kwargs)

                if response.status_code == 401:
                    raise APIKeyError("Invalid Scopus API key")

                response.raise_for_status()
                data = response.json()

                if "search-results" not in data or "entry" not in data["search-results"]:
                    break

                for entry in data["search-results"]["entry"]:
                    if len(papers) >= max_results:
                        break

                    # Extract abstract
                    abstract = entry.get("dc:description", "")
                    
                    # Extract authors - handle both formats
                    authors = []
                    
                    # Try detailed author array first (available with view=COMPLETE)
                    if "author" in entry and isinstance(entry["author"], list):
                        for author in entry["author"]:
                            # Try ce:indexed-name first (most reliable)
                            if "ce:indexed-name" in author:
                                authors.append(author["ce:indexed-name"])
                            # Fallback to given-name + surname
                            elif "given-name" in author or "surname" in author:
                                given = author.get("given-name", "")
                                surname = author.get("surname", "")
                                if surname:
                                    name = f"{given} {surname}".strip()
                                    if name:
                                        authors.append(name)
                            # Fallback to authname (legacy field)
                            elif "authname" in author:
                                authors.append(author["authname"])
                    
                    # Fallback to dc:creator string (semicolon-separated)
                    if not authors and "dc:creator" in entry:
                        creator_str = entry["dc:creator"]
                        if creator_str:
                            # Split by semicolon and clean up
                            authors = [name.strip() for name in creator_str.split(";") if name.strip()]

                    # Extract affiliations (available in COMPLETE view)
                    affiliations = []
                    if "affiliation" in entry:
                        aff_list = entry["affiliation"] if isinstance(entry["affiliation"], list) else [entry["affiliation"]]
                        for aff in aff_list:
                            if isinstance(aff, dict):
                                # Scopus provides affilname, affiliation-city, affiliation-country
                                aff_name = aff.get("affilname", "")
                                if aff_name and aff_name.strip():
                                    affiliations.append(aff_name.strip())
                            elif isinstance(aff, str) and aff.strip():
                                affiliations.append(aff.strip())

                    # Extract year
                    year = None
                    cover_date = entry.get("prism:coverDate", "")
                    if cover_date:
                        try:
                            year = int(cover_date[:4])
                        except (ValueError, TypeError):
                            pass

                    # Extract URL
                    url = None
                    if "link" in entry and entry["link"]:
                        # Find the 'scopus' link or use first available
                        for link in entry["link"]:
                            if isinstance(link, dict):
                                if link.get("@ref") == "scopus" or "@href" in link:
                                    url = link.get("@href")
                                    break
                        # If no scopus link found, use first href
                        if not url and entry["link"]:
                            first_link = entry["link"][0]
                            if isinstance(first_link, dict):
                                url = first_link.get("@href")

                    # Extract citation count
                    citation_count = None
                    if "citedby-count" in entry:
                        try:
                            citation_count = int(entry["citedby-count"])
                        except (ValueError, TypeError):
                            pass
                    
                    # Extract EID (Scopus ID)
                    eid = entry.get("eid", "")
                    
                    # Extract subject areas
                    subject_areas = []
                    if "subject-area" in entry:
                        subj_list = entry["subject-area"] if isinstance(entry["subject-area"], list) else [entry["subject-area"]]
                        for subj in subj_list:
                            if isinstance(subj, dict) and "$" in subj:
                                subject_areas.append(subj["$"])
                            elif isinstance(subj, str):
                                subject_areas.append(subj)
                    
                    # Extract author IDs for potential coauthor lookup
                    author_ids = []
                    if "author" in entry and isinstance(entry["author"], list):
                        for author in entry["author"]:
                            if isinstance(author, dict) and "authid" in author:
                                author_ids.append(author["authid"])

                    paper = Paper(
                        title=entry.get("dc:title", ""),
                        abstract=abstract,
                        authors=authors,
                        year=year,
                        doi=entry.get("prism:doi"),
                        journal=entry.get("prism:publicationName", ""),
                        database="Scopus",
                        url=url,
                        affiliations=affiliations if affiliations else None,
                        citation_count=citation_count,
                        eid=eid,
                        subject_areas=subject_areas if subject_areas else None,
                        scopus_id=eid,  # Store EID as scopus_id
                    )
                    papers.append(paper)

                if len(data["search-results"]["entry"]) < params["count"]:
                    break

                params["start"] += params["count"]

        except requests.RequestException as e:
            logger.error(f"Network error searching Scopus: {e}")
            raise NetworkError(f"Scopus search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching Scopus: {e}")
            raise DatabaseSearchError(f"Scopus search error: {e}") from e

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Scopus", papers)

        return papers

    def get_database_name(self) -> str:
        return "Scopus"
    
    def get_author_by_id(self, author_id: str) -> Optional["Author"]:
        """
        Retrieve author information by Scopus author ID using pybliometrics.
        
        Args:
            author_id: Scopus author ID
            
        Returns:
            Author object with bibliometric data, or None if pybliometrics not available
        """
        try:
            from pybliometrics.scopus import AuthorRetrieval
            from .models import Author, Affiliation
        except ImportError:
            logger.warning("pybliometrics not available. Install with: pip install pybliometrics or pip install -e '.[bibliometrics]'")
            return None
        
        if not self.api_key:
            logger.warning("Scopus API key required for author retrieval")
            return None
        
        try:
            # Set API key for pybliometrics
            import pybliometrics
            pybliometrics.init()
            
            # Retrieve author
            au = AuthorRetrieval(author_id, view="ENHANCED")
            
            # Convert to our Author model
            current_affiliations = []
            if au.affiliation_current:
                for aff in au.affiliation_current:
                    current_affiliations.append(Affiliation(
                        name=aff.preferred_name or "",
                        id=str(aff.id) if aff.id else None,
                        city=aff.city,
                        country=aff.country,
                        country_code=aff.country_code,
                        address=aff.address_part,
                        postal_code=aff.postal_code,
                        organization_domain=aff.org_domain,
                        organization_url=aff.org_URL,
                    ))
            
            historical_affiliations = []
            if au.affiliation_history:
                for aff in au.affiliation_history:
                    historical_affiliations.append(Affiliation(
                        name=aff.preferred_name or "",
                        id=str(aff.id) if aff.id else None,
                        city=aff.city,
                        country=aff.country,
                        country_code=aff.country_code,
                    ))
            
            subject_areas = []
            if au.subject_areas:
                subject_areas = [area.area for area in au.subject_areas]
            
            author = Author(
                name=au.indexed_name or "",
                id=str(au.identifier),
                given_name=au.given_name,
                surname=au.surname,
                indexed_name=au.indexed_name,
                initials=au.initials,
                orcid=au.orcid,
                h_index=int(au.h_index) if au.h_index else None,
                citation_count=int(au.citation_count) if au.citation_count else None,
                cited_by_count=int(au.cited_by_count) if au.cited_by_count else None,
                document_count=int(au.document_count) if au.document_count else None,
                coauthor_count=int(au.coauthor_count) if au.coauthor_count else None,
                current_affiliations=current_affiliations,
                historical_affiliations=historical_affiliations,
                subject_areas=subject_areas,
                first_publication_year=au.publication_range[0] if au.publication_range else None,
                last_publication_year=au.publication_range[1] if au.publication_range else None,
                database="Scopus",
                url=au.url,
                profile_url=au.scopus_author_link,
            )
            
            return author
            
        except Exception as e:
            logger.error(f"Error retrieving author {author_id}: {e}")
            return None
    
    def get_affiliation_by_id(self, affiliation_id: str) -> Optional["Affiliation"]:
        """
        Retrieve affiliation information by Scopus affiliation ID using pybliometrics.
        
        Args:
            affiliation_id: Scopus affiliation ID
            
        Returns:
            Affiliation object, or None if pybliometrics not available
        """
        try:
            from pybliometrics.scopus import AffiliationRetrieval
            from .models import Affiliation
        except ImportError:
            logger.warning("pybliometrics not available. Install with: pip install pybliometrics or pip install -e '.[bibliometrics]'")
            return None
        
        if not self.api_key:
            logger.warning("Scopus API key required for affiliation retrieval")
            return None
        
        try:
            import pybliometrics
            pybliometrics.init()
            
            aff = AffiliationRetrieval(affiliation_id)
            
            affiliation = Affiliation(
                name=aff.preferred_name or "",
                id=str(aff.identifier),
                city=aff.city,
                country=aff.country,
                country_code=aff.country_code,
                address=aff.address_part,
                postal_code=aff.postal_code,
                organization_domain=aff.org_domain,
                organization_url=aff.org_URL,
                author_count=int(aff.author_count) if aff.author_count else None,
            )
            
            return affiliation
            
        except Exception as e:
            logger.error(f"Error retrieving affiliation {affiliation_id}: {e}")
            return None
    
    def search_authors(self, query: str, max_results: int = 25) -> List["Author"]:
        """
        Search for authors by name using pybliometrics.
        
        Args:
            query: Author search query (e.g., "AUTHLAST(Smith) AND AUTHFIRST(John)")
            max_results: Maximum number of results
            
        Returns:
            List of Author objects
        """
        try:
            from pybliometrics.scopus import AuthorSearch
            from .models import Author, Affiliation
        except ImportError:
            logger.warning("pybliometrics not available. Install with: pip install pybliometrics or pip install -e '.[bibliometrics]'")
            return []
        
        if not self.api_key:
            logger.warning("Scopus API key required for author search")
            return []
        
        try:
            import pybliometrics
            pybliometrics.init()
            
            search = AuthorSearch(query)
            authors = []
            
            for result in search.results[:max_results]:
                # Get full author details
                author = self.get_author_by_id(result.identifier)
                if author:
                    authors.append(author)
            
            return authors
            
        except Exception as e:
            logger.error(f"Error searching authors: {e}")
            return []


class ACMConnector(DatabaseConnector):
    """ACM Digital Library connector using web scraping."""

    def __init__(
        self,
        cache: Optional[SearchCache] = None,
        proxy_manager: Optional[ProxyManager] = None,
        integrity_checker: Optional[IntegrityChecker] = None,
        persistent_session: bool = True,
        cookie_jar: Optional[str] = None,
    ):
        super().__init__(
            api_key=None,
            cache=cache,
            proxy_manager=proxy_manager,
            integrity_checker=integrity_checker,
            persistent_session=persistent_session,
            cookie_jar=cookie_jar,
        )
        self.base_url = "https://dl.acm.org"
        self.search_url = f"{self.base_url}/action/doSearch"

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search ACM Digital Library."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "ACM")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            from bs4 import BeautifulSoup

            # ACM search parameters
            page_size = 20  # ACM typically shows 20 results per page
            start_page = 0
            pages_needed = (max_results + page_size - 1) // page_size

            for page in range(pages_needed):
                if len(papers) >= max_results:
                    break

                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()

                params = {
                    "AllField": query,
                    "pageSize": page_size,
                    "startPage": start_page + page,
                }

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }

                session = self._get_session()
                request_kwargs = self._get_request_kwargs()
                request_kwargs.setdefault("timeout", 30)
                
                response = session.get(self.search_url, params=params, headers=headers, **request_kwargs)
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.content, "html.parser")
                page_papers = self._parse_search_results(soup)

                if not page_papers:
                    # No more results
                    break

                papers.extend(page_papers)

                if len(page_papers) < page_size:
                    # Last page
                    break

        except ImportError:
            raise ImportError("beautifulsoup4 required for ACM connector. Install with: pip install beautifulsoup4")
        except requests.RequestException as e:
            logger.error(f"Network error searching ACM: {e}")
            raise NetworkError(f"ACM search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching ACM: {e}")
            raise DatabaseSearchError(f"ACM search error: {e}") from e

        # Limit to max_results
        papers = papers[:max_results]

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "ACM", papers)

        return papers

    def _parse_search_results(self, soup) -> List[Paper]:
        """Parse HTML search results page."""
        papers = []

        try:
            # ACM search results are typically in divs with class "search__item" or similar
            # Try multiple possible selectors
            result_items = (
                soup.find_all("div", class_="search__item")
                or soup.find_all("div", class_="search-result-item")
                or soup.find_all("div", class_="item")
                or soup.find_all("article", class_="search-result-item")
            )

            if not result_items:
                # Try finding by data attributes or other patterns
                result_items = soup.find_all("div", {"data-testid": "search-result-item"})

            for item in result_items:
                try:
                    paper = self._extract_paper_from_item(item)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"Error parsing ACM result item: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error parsing ACM search results: {e}")

        return papers

    def _extract_paper_from_item(self, item) -> Optional[Paper]:
        """Extract paper metadata from a single result item."""
        try:
            # Title - try multiple selectors
            title_elem = (
                item.find("h5", class_="hlFld-Title")
                or item.find("span", class_="hlFld-Title")
                or item.find("a", class_="hlFld-Title")
                or item.find("h3")
                or item.find("h4")
            )
            title = title_elem.get_text(strip=True) if title_elem else ""

            if not title:
                return None

            # Authors - try multiple selectors
            authors = []
            author_links = item.find_all("a", class_="author-name") or item.find_all("span", class_="author-name")
            if not author_links:
                # Try finding by text pattern
                author_section = item.find("div", class_="authors") or item.find("span", class_="authors")
                if author_section:
                    author_links = author_section.find_all("a")

            for author_link in author_links:
                author_name = author_link.get_text(strip=True)
                if author_name:
                    authors.append(author_name)

            # Abstract
            abstract_elem = (
                item.find("div", class_="abstract")
                or item.find("span", class_="abstract")
                or item.find("p", class_="abstract")
            )
            abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""

            # DOI
            doi = None
            doi_link = item.find("a", href=lambda x: x and "doi.org" in x) if item else None
            if doi_link:
                href = doi_link.get("href", "")
                # Extract DOI from URL
                if "doi.org/" in href:
                    doi = href.split("doi.org/")[-1]
            else:
                # Try finding DOI in text
                doi_text = item.get_text()
                import re
                doi_match = re.search(r"10\.\d+/[^\s]+", doi_text)
                if doi_match:
                    doi = doi_match.group(0)

            # URL
            url = None
            title_link = title_elem.find("a") if title_elem else None
            if title_link:
                href = title_link.get("href", "")
                if href:
                    if href.startswith("/"):
                        url = f"{self.base_url}{href}"
                    elif href.startswith("http"):
                        url = href

            # Year
            year = None
            year_elem = item.find("span", class_="year") or item.find("div", class_="year")
            if year_elem:
                year_text = year_elem.get_text(strip=True)
                import re
                year_match = re.search(r"\d{4}", year_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                    except ValueError:
                        pass

            # Venue/Journal
            venue = None
            venue_elem = (
                item.find("span", class_="venue")
                or item.find("div", class_="venue")
                or item.find("span", class_="publication")
            )
            if venue_elem:
                venue = venue_elem.get_text(strip=True)

            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors if authors else [],
                year=year,
                doi=doi,
                journal=venue,
                database="ACM",
                url=url,
            )

            return paper

        except Exception as e:
            logger.warning(f"Error extracting paper from ACM item: {e}")
            return None

    def get_database_name(self) -> str:
        return "ACM"


class MockConnector(DatabaseConnector):
    """Mock connector for testing without API keys."""

    def __init__(self, database_name: str = "Mock"):
        super().__init__()
        self.database_name = database_name

    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Return mock papers for testing."""
        papers = []
        for i in range(min(max_results, 10)):  # Limit mock results
            papers.append(
                Paper(
                    title=f"Mock Paper {i + 1} about {query[:50]}",
                    abstract=f"This is a mock abstract for paper {i + 1} related to the search query.",
                    authors=[f"Author {j + 1}" for j in range(3)],
                    year=2020 + (i % 3),
                    doi=f"10.1000/mock.{i + 1}",
                    journal=f"Mock Journal {i + 1}",
                    database=self.database_name,
                )
            )
        return papers

    def get_database_name(self) -> str:
        return self.database_name


# Re-export MultiDatabaseSearcher from new location
from .multi_database_searcher import MultiDatabaseSearcher
