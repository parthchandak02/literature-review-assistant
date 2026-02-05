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
        subscriber: Optional[bool] = None,
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
        # Subscriber: True for institutional access, False for free tier
        # Default to False (free tier) unless explicitly set or environment variable exists
        if subscriber is None:
            subscriber_env = os.getenv("SCOPUS_SUBSCRIBER", "false").lower()
            self.subscriber = subscriber_env in ("true", "1", "yes")
        else:
            self.subscriber = subscriber

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search Scopus using pybliometrics."""
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
            # Import pybliometrics
            try:
                import pybliometrics
                from pybliometrics.scopus import ScopusSearch
            except ImportError:
                logger.error("pybliometrics not installed. Install with: uv pip install pybliometrics")
                raise ImportError("pybliometrics required for Scopus search. Install with: uv pip install pybliometrics")
            
            # Initialize pybliometrics with API key if not already configured
            try:
                pybliometrics.init(keys=[self.api_key])
            except Exception as e:
                # Config might already exist, that's OK
                logger.debug(f"pybliometrics init note: {e}")
            
            # Determine view: COMPLETE for subscribers, STANDARD for free tier
            view = self.view
            if view is None:
                view = "COMPLETE" if self.subscriber else "STANDARD"
            
            # Apply rate limiting
            rate_limiter = self._get_rate_limiter()
            rate_limiter.acquire()
            
            # Perform search using pybliometrics
            logger.debug(f"Searching Scopus with pybliometrics (subscriber={self.subscriber}, view={view})")
            search = ScopusSearch(
                query,
                subscriber=self.subscriber,
                view=view,
                verbose=False,
                download=True
            )
            
            # Get results size
            results_size = search.get_results_size()
            logger.info(f"Scopus search found {results_size} documents")
            
            if results_size == 0:
                logger.warning("No results found in Scopus")
                return []
            
            # Convert pybliometrics Document NamedTuple to Paper objects
            for doc in search.results[:max_results]:
                if len(papers) >= max_results:
                    break
                
                # Extract authors (semicolon-separated in pybliometrics)
                authors = []
                if doc.author_names:
                    authors = [name.strip() for name in doc.author_names.split(";") if name.strip()]
                
                # Extract year from coverDate
                year = None
                if doc.coverDate:
                    try:
                        year = int(doc.coverDate[:4])
                    except (ValueError, TypeError):
                        pass
                
                # Extract affiliations (semicolon-separated)
                affiliations = []
                if doc.affilname:
                    affiliations = [aff.strip() for aff in doc.affilname.split(";") if aff.strip()]
                
                # Extract subject areas (if available in authkeywords or other fields)
                subject_areas = None
                if doc.authkeywords:
                    # Subject areas might be in authkeywords, but this is not standard
                    # We'll leave it as None for now since pybliometrics doesn't expose it directly
                    pass
                
                # Build URL from EID
                url = None
                if doc.eid:
                    url = f"https://www.scopus.com/record/display.uri?eid={doc.eid}"
                
                paper = Paper(
                    title=doc.title or "",
                    abstract=doc.description or "",
                    authors=authors,
                    year=year,
                    doi=doc.doi,
                    journal=doc.publicationName or "",
                    database="Scopus",
                    url=url,
                    affiliations=affiliations if affiliations else None,
                    citation_count=doc.citedby_count if doc.citedby_count else None,
                    eid=doc.eid,
                    subject_areas=subject_areas,
                    scopus_id=doc.eid,  # Store EID as scopus_id
                )
                papers.append(paper)
            
            logger.info(f"Retrieved {len(papers)} papers from Scopus")

        except Exception as e:
            error_msg = str(e)
            # Handle specific pybliometrics errors
            if "400" in error_msg or "maximum number" in error_msg.lower():
                logger.warning(f"Scopus API limit reached: {error_msg}")
                logger.warning("This may be due to free tier restrictions. Consider:")
                logger.warning("  1. Using more specific queries")
                logger.warning("  2. Setting SCOPUS_SUBSCRIBER=true if you have institutional access")
                logger.warning("  3. Waiting before retrying")
                # Return empty list instead of raising error for API limits
                return []
            elif "401" in error_msg or "Invalid" in error_msg or "API key" in error_msg:
                logger.error(f"Invalid Scopus API key: {error_msg}")
                raise APIKeyError(f"Invalid Scopus API key: {error_msg}") from e
            else:
                logger.error(f"Error searching Scopus with pybliometrics: {e}")
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

            session = self._get_session()
            request_kwargs = self._get_request_kwargs()
            request_kwargs.setdefault("timeout", 30)
            
            # Enhanced browser headers to avoid 403 errors
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://dl.acm.org/",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
            }
            
            # Visit homepage first to establish session and get cookies
            try:
                logger.debug("Visiting ACM homepage to establish session...")
                homepage_response = session.get(
                    self.base_url,
                    headers=headers,
                    **request_kwargs
                )
                # Check for 403 on homepage - if we get it here, we'll likely get it on search too
                if homepage_response.status_code == 403:
                    logger.warning(
                        "ACM Digital Library returned 403 Forbidden on homepage. "
                        "This may be due to anti-scraping measures. "
                        "Skipping ACM search for this query."
                    )
                    return []
                homepage_response.raise_for_status()
                # Save cookies if persistent session is enabled
                self._save_session_cookies()
            except requests.HTTPError as e:
                # Check if it's a 403 error
                if hasattr(e.response, 'status_code') and e.response.status_code == 403:
                    logger.warning(
                        "ACM Digital Library returned 403 Forbidden. "
                        "This may be due to anti-scraping measures. "
                        "Skipping ACM search for this query."
                    )
                    return []
                logger.warning(f"Failed to visit ACM homepage: {e}. Continuing with search anyway...")
            except requests.RequestException as e:
                logger.warning(f"Failed to visit ACM homepage: {e}. Continuing with search anyway...")

            # ACM search parameters
            page_size = 20  # ACM typically shows 20 results per page
            start_page = 0
            pages_needed = (max_results + page_size - 1) // page_size

            for page in range(pages_needed):
                if len(papers) >= max_results:
                    break

                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()
                
                # Add delay between page requests to avoid rate limiting
                if page > 0:
                    import time
                    time.sleep(1.0)  # 1 second delay between pages

                params = {
                    "AllField": query,
                    "pageSize": page_size,
                    "startPage": start_page + page,
                }
                
                response = session.get(self.search_url, params=params, headers=headers, **request_kwargs)
                
                # Handle 403 errors gracefully
                if response.status_code == 403:
                    logger.warning(
                        "ACM Digital Library returned 403 Forbidden. "
                        "This may be due to anti-scraping measures. "
                        "Skipping ACM search for this query."
                    )
                    # Return empty list instead of raising error
                    return []
                
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
        except requests.HTTPError as e:
            # Check if it's a 403 error - don't retry on 403
            if hasattr(e.response, 'status_code') and e.response.status_code == 403:
                logger.warning(
                    "ACM Digital Library returned 403 Forbidden. "
                    "This may be due to anti-scraping measures. "
                    "Skipping ACM search for this query."
                )
                return []
            logger.error(f"HTTP error searching ACM: {e}")
            raise NetworkError(f"ACM search failed: {e}") from e
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
            # Try multiple possible selectors in order of likelihood
            result_items = []
            
            # Try most common selectors first
            selectors = [
                ("div", {"class": "search__item"}),
                ("div", {"class": "search-result-item"}),
                ("article", {"class": "search-result-item"}),
                ("div", {"class": "item"}),
                ("div", {"data-testid": "search-result-item"}),
                ("li", {"class": "search__item"}),
                ("div", {"class": "hlFld-Title"}),  # Sometimes results are grouped differently
            ]
            
            for tag, attrs in selectors:
                if isinstance(attrs, dict) and "class" in attrs:
                    result_items = soup.find_all(tag, class_=attrs["class"])
                elif isinstance(attrs, dict) and "data-testid" in attrs:
                    result_items = soup.find_all(tag, {"data-testid": attrs["data-testid"]})
                else:
                    result_items = soup.find_all(tag, attrs)
                
                if result_items:
                    logger.debug(f"Found {len(result_items)} ACM results using selector: {tag} with {attrs}")
                    break
            
            # If still no results, try finding by structure (title links)
            if not result_items:
                # Look for title links which are always present
                title_links = soup.find_all("a", href=lambda x: x and "/doi/" in str(x))
                if title_links:
                    # Group by parent containers
                    seen_parents = set()
                    for link in title_links:
                        parent = link.find_parent("div") or link.find_parent("article") or link.find_parent("li")
                        if parent and id(parent) not in seen_parents:
                            result_items.append(parent)
                            seen_parents.add(id(parent))
                    logger.debug(f"Found {len(result_items)} ACM results by grouping title links")

            if not result_items:
                logger.warning("No ACM search results found - page structure may have changed")
                return papers

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
            import re
            
            # Title - try multiple selectors with better fallbacks
            title_elem = None
            title_selectors = [
                ("h5", {"class": "hlFld-Title"}),
                ("span", {"class": "hlFld-Title"}),
                ("a", {"class": "hlFld-Title"}),
                ("h3", {}),
                ("h4", {}),
                ("h2", {}),
                ("a", {"href": lambda x: x and "/doi/" in str(x)}),  # DOI link often contains title
            ]
            
            for tag, attrs in title_selectors:
                if "class" in attrs:
                    title_elem = item.find(tag, class_=attrs["class"])
                elif "href" in attrs:
                    title_elem = item.find(tag, href=attrs["href"])
                else:
                    title_elem = item.find(tag)
                if title_elem:
                    break
            
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # If title is in a link, get it from the link text
            if not title and title_elem and title_elem.name == "a":
                title = title_elem.get_text(strip=True)
            
            # Fallback: extract from any text that looks like a title (longest text block)
            if not title:
                text_blocks = [elem.get_text(strip=True) for elem in item.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "a", "span"])]
                if text_blocks:
                    # Find longest non-empty text block that's not too short
                    title = max([t for t in text_blocks if len(t) > 10], key=len, default="")

            if not title:
                return None

            # Authors - try multiple selectors with better extraction
            authors = []
            author_selectors = [
                ("a", {"class": "author-name"}),
                ("span", {"class": "author-name"}),
                ("a", {"class": lambda x: x and "author" in str(x).lower()}),
                ("span", {"class": lambda x: x and "author" in str(x).lower()}),
            ]
            
            author_links = []
            for tag, attrs in author_selectors:
                if "class" in attrs:
                    author_links = item.find_all(tag, class_=attrs["class"])
                elif "class" in attrs and callable(attrs["class"]):
                    author_links = item.find_all(tag, class_=attrs["class"])
                if author_links:
                    break
            
            # If no author links found, try finding by text pattern
            if not author_links:
                author_section = (
                    item.find("div", class_="authors")
                    or item.find("span", class_="authors")
                    or item.find("div", class_="author")
                    or item.find("span", class_="author")
                )
                if author_section:
                    author_links = author_section.find_all("a")
                    if not author_links:
                        # Try extracting from text (comma or semicolon separated)
                        author_text = author_section.get_text(strip=True)
                        if author_text:
                            # Split by common separators
                            authors = [a.strip() for a in re.split(r'[,;]', author_text) if a.strip()]

            for author_link in author_links:
                author_name = author_link.get_text(strip=True)
                if author_name and author_name not in authors:
                    authors.append(author_name)
            
            # If still no authors, try regex pattern matching
            if not authors:
                item_text = item.get_text()
                # Look for patterns like "Author1, Author2, Author3"
                author_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[A-Z]\.?)?)'
                potential_authors = re.findall(author_pattern, item_text[:500])  # Limit to first 500 chars
                # Filter out common false positives
                false_positives = {"Abstract", "Journal", "Conference", "Proceedings", "Volume", "Issue", "Pages"}
                authors = [a for a in potential_authors[:10] if a not in false_positives]  # Limit to 10

            # Abstract - improved extraction with better selectors
            abstract_elem = None
            abstract_selectors = [
                ("div", {"class": "abstract"}),
                ("span", {"class": "abstract"}),
                ("p", {"class": "abstract"}),
                ("div", {"class": "snippet"}),
                ("span", {"class": "snippet"}),
                ("p", {"class": "snippet"}),
            ]
            
            for tag, attrs in abstract_selectors:
                abstract_elem = item.find(tag, class_=attrs["class"])
                if abstract_elem:
                    break
            
            abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""
            
            # Handle truncated abstracts (look for "..." or "more" indicators)
            if abstract and len(abstract) < 50:
                # Might be truncated, try to find full abstract
                full_abstract_elem = item.find("div", {"data-abstract": True}) or item.find("span", {"data-abstract": True})
                if full_abstract_elem:
                    abstract = full_abstract_elem.get("data-abstract", abstract)

            # DOI - improved extraction
            doi = None
            # Try DOI link first
            doi_link = item.find("a", href=lambda x: x and ("doi.org" in str(x) or "/doi/" in str(x)))
            if doi_link:
                href = doi_link.get("href", "")
                # Extract DOI from URL
                if "doi.org/" in href:
                    doi = href.split("doi.org/")[-1].split("?")[0]  # Remove query params
                elif "/doi/" in href:
                    doi = href.split("/doi/")[-1].split("?")[0]
            else:
                # Try finding DOI in text using regex
                doi_text = item.get_text()
                doi_match = re.search(r"10\.\d+/[^\s\)]+", doi_text)
                if doi_match:
                    doi = doi_match.group(0).rstrip(".,;:)]}")

            # URL - improved extraction
            url = None
            # Try title link first
            if title_elem and title_elem.name == "a":
                href = title_elem.get("href", "")
                if href:
                    if href.startswith("/"):
                        url = f"{self.base_url}{href}"
                    elif href.startswith("http"):
                        url = href
            else:
                # Try DOI link
                if doi_link:
                    href = doi_link.get("href", "")
                    if href:
                        if href.startswith("/"):
                            url = f"{self.base_url}{href}"
                        elif href.startswith("http"):
                            url = href
                else:
                    # Try any link with /doi/ in it
                    doi_url_link = item.find("a", href=lambda x: x and "/doi/" in str(x))
                    if doi_url_link:
                        href = doi_url_link.get("href", "")
                        if href.startswith("/"):
                            url = f"{self.base_url}{href}"
                        elif href.startswith("http"):
                            url = href

            # Year - improved extraction with better patterns
            year = None
            year_elem = (
                item.find("span", class_="year")
                or item.find("div", class_="year")
                or item.find("span", class_="date")
                or item.find("div", class_="date")
            )
            
            if year_elem:
                year_text = year_elem.get_text(strip=True)
                year_match = re.search(r"\b(19|20)\d{2}\b", year_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                        # Sanity check: year should be reasonable
                        if year < 1900 or year > 2030:
                            year = None
                    except ValueError:
                        pass
            
            # If no year found, try searching in the entire item text
            if not year:
                item_text = item.get_text()
                year_match = re.search(r"\b(19|20)\d{2}\b", item_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                        if year < 1900 or year > 2030:
                            year = None
                    except ValueError:
                        pass

            # Venue/Journal - improved extraction
            venue = None
            venue_selectors = [
                ("span", {"class": "venue"}),
                ("div", {"class": "venue"}),
                ("span", {"class": "publication"}),
                ("div", {"class": "publication"}),
                ("span", {"class": "journal"}),
                ("div", {"class": "journal"}),
                ("a", {"class": "venue"}),
            ]
            
            for tag, attrs in venue_selectors:
                venue_elem = item.find(tag, class_=attrs["class"])
                if venue_elem:
                    venue = venue_elem.get_text(strip=True)
                    break
            
            # If no venue found, try looking for publication info in text
            if not venue:
                item_text = item.get_text()
                # Look for patterns like "In: Journal Name" or "Proceedings of..."
                venue_match = re.search(r"(?:In:|Proceedings of|Journal:)\s*([A-Z][^,\.]+)", item_text)
                if venue_match:
                    venue = venue_match.group(1).strip()

            # Citation count (if available)
            citation_count = None
            citation_elem = item.find("span", class_="citation") or item.find("div", class_="citation")
            if citation_elem:
                citation_text = citation_elem.get_text(strip=True)
                citation_match = re.search(r"(\d+)", citation_text)
                if citation_match:
                    try:
                        citation_count = int(citation_match.group(1))
                    except ValueError:
                        pass

            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors if authors else [],
                year=year,
                doi=doi,
                journal=venue,
                database="ACM",
                url=url,
                citation_count=citation_count,
            )

            return paper

        except Exception as e:
            logger.warning(f"Error extracting paper from ACM item: {e}")
            return None

    def get_database_name(self) -> str:
        return "ACM"


class SpringerConnector(DatabaseConnector):
    """Springer Link connector using web scraping."""

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
        self.base_url = "https://link.springer.com"
        self.search_url = f"{self.base_url}/search"

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search Springer Link."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "Springer")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            from bs4 import BeautifulSoup
            import time

            session = self._get_session()
            request_kwargs = self._get_request_kwargs()
            request_kwargs.setdefault("timeout", 30)
            
            # Enhanced browser headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://link.springer.com/",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            # Visit homepage first to establish session
            try:
                logger.debug("Visiting Springer homepage to establish session...")
                homepage_response = session.get(
                    self.base_url,
                    headers=headers,
                    **request_kwargs
                )
                if homepage_response.status_code == 403:
                    logger.warning(
                        "Springer Link returned 403 Forbidden on homepage. "
                        "This may be due to anti-scraping measures. "
                        "Skipping Springer search for this query."
                    )
                    return []
                homepage_response.raise_for_status()
                self._save_session_cookies()
            except requests.HTTPError as e:
                if hasattr(e.response, 'status_code') and e.response.status_code == 403:
                    logger.warning(
                        "Springer Link returned 403 Forbidden. "
                        "Skipping Springer search for this query."
                    )
                    return []
                logger.warning(f"Failed to visit Springer homepage: {e}. Continuing with search anyway...")
            except requests.RequestException as e:
                logger.warning(f"Failed to visit Springer homepage: {e}. Continuing with search anyway...")

            # Springer search parameters
            page_size = 20  # Springer typically shows 20 results per page
            pages_needed = (max_results + page_size - 1) // page_size

            for page in range(pages_needed):
                if len(papers) >= max_results:
                    break

                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()
                
                # Add delay between page requests
                if page > 0:
                    time.sleep(1.0)

                params = {
                    "query": query,
                    "page": page + 1,
                }
                
                response = session.get(self.search_url, params=params, headers=headers, **request_kwargs)
                
                if response.status_code == 403:
                    logger.warning(
                        "Springer Link returned 403 Forbidden. "
                        "Skipping Springer search for this query."
                    )
                    return []
                
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.content, "html.parser")
                page_papers = self._parse_search_results(soup)

                if not page_papers:
                    break

                papers.extend(page_papers)

                if len(page_papers) < page_size:
                    break

        except ImportError:
            raise ImportError("beautifulsoup4 required for Springer connector. Install with: pip install beautifulsoup4")
        except requests.HTTPError as e:
            if hasattr(e.response, 'status_code') and e.response.status_code == 403:
                logger.warning(
                    "Springer Link returned 403 Forbidden. "
                    "Skipping Springer search for this query."
                )
                return []
            logger.error(f"HTTP error searching Springer: {e}")
            raise NetworkError(f"Springer search failed: {e}") from e
        except requests.RequestException as e:
            logger.error(f"Network error searching Springer: {e}")
            raise NetworkError(f"Springer search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching Springer: {e}")
            raise DatabaseSearchError(f"Springer search error: {e}") from e

        # Limit to max_results
        papers = papers[:max_results]

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Springer", papers)

        return papers

    def _parse_search_results(self, soup) -> List[Paper]:
        """Parse HTML search results page."""
        papers = []

        try:
            # Springer search results are typically in list items or divs
            result_items = []
            
            selectors = [
                ("li", {"class": "search-result-item"}),
                ("div", {"class": "search-result-item"}),
                ("article", {"class": "search-result-item"}),
                ("li", {"class": "result-item"}),
                ("div", {"class": "result-item"}),
                ("li", {"data-testid": "search-result-item"}),
            ]
            
            for tag, attrs in selectors:
                if "class" in attrs:
                    result_items = soup.find_all(tag, class_=attrs["class"])
                elif "data-testid" in attrs:
                    result_items = soup.find_all(tag, {"data-testid": attrs["data-testid"]})
                if result_items:
                    logger.debug(f"Found {len(result_items)} Springer results using selector: {tag} with {attrs}")
                    break
            
            # Fallback: find by title links
            if not result_items:
                title_links = soup.find_all("a", href=lambda x: x and "/article/" in str(x))
                if title_links:
                    seen_parents = set()
                    for link in title_links:
                        parent = link.find_parent("li") or link.find_parent("div") or link.find_parent("article")
                        if parent and id(parent) not in seen_parents:
                            result_items.append(parent)
                            seen_parents.add(id(parent))
                    logger.debug(f"Found {len(result_items)} Springer results by grouping title links")

            if not result_items:
                logger.warning("No Springer search results found - page structure may have changed")
                return papers

            for item in result_items:
                try:
                    paper = self._extract_paper_from_item(item)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"Error parsing Springer result item: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error parsing Springer search results: {e}")

        return papers

    def _extract_paper_from_item(self, item) -> Optional[Paper]:
        """Extract paper metadata from a single result item."""
        try:
            import re
            
            # Title
            title_elem = None
            title_selectors = [
                ("h3", {}),
                ("h2", {}),
                ("h4", {}),
                ("a", {"class": "title"}),
                ("span", {"class": "title"}),
                ("a", {"href": lambda x: x and "/article/" in str(x)}),
            ]
            
            for tag, attrs in title_selectors:
                if "class" in attrs:
                    title_elem = item.find(tag, class_=attrs["class"])
                elif "href" in attrs:
                    title_elem = item.find(tag, href=attrs["href"])
                else:
                    title_elem = item.find(tag)
                if title_elem:
                    break
            
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            if not title:
                return None

            # Authors
            authors = []
            author_selectors = [
                ("span", {"class": "authors"}),
                ("div", {"class": "authors"}),
                ("a", {"class": "author"}),
                ("span", {"class": "author"}),
            ]
            
            author_links = []
            for tag, attrs in author_selectors:
                author_links = item.find_all(tag, class_=attrs["class"])
                if author_links:
                    break
            
            if not author_links:
                author_section = item.find("div", class_="authors") or item.find("span", class_="authors")
                if author_section:
                    author_links = author_section.find_all("a")
                    if not author_links:
                        author_text = author_section.get_text(strip=True)
                        if author_text:
                            authors = [a.strip() for a in re.split(r'[,;]', author_text) if a.strip()]

            for author_link in author_links:
                author_name = author_link.get_text(strip=True)
                if author_name and author_name not in authors:
                    authors.append(author_name)

            # Abstract
            abstract_elem = (
                item.find("p", class_="snippet")
                or item.find("div", class_="snippet")
                or item.find("span", class_="snippet")
                or item.find("p", class_="abstract")
            )
            abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""

            # DOI
            doi = None
            doi_link = item.find("a", href=lambda x: x and ("doi.org" in str(x) or "/doi/" in str(x)))
            if doi_link:
                href = doi_link.get("href", "")
                if "doi.org/" in href:
                    doi = href.split("doi.org/")[-1].split("?")[0]
                elif "/doi/" in href:
                    doi = href.split("/doi/")[-1].split("?")[0]
            else:
                doi_text = item.get_text()
                doi_match = re.search(r"10\.\d+/[^\s\)]+", doi_text)
                if doi_match:
                    doi = doi_match.group(0).rstrip(".,;:)]}")

            # URL
            url = None
            if title_elem and title_elem.name == "a":
                href = title_elem.get("href", "")
                if href:
                    if href.startswith("/"):
                        url = f"{self.base_url}{href}"
                    elif href.startswith("http"):
                        url = href
            else:
                article_link = item.find("a", href=lambda x: x and "/article/" in str(x))
                if article_link:
                    href = article_link.get("href", "")
                    if href.startswith("/"):
                        url = f"{self.base_url}{href}"
                    elif href.startswith("http"):
                        url = href

            # Year
            year = None
            year_elem = (
                item.find("span", class_="year")
                or item.find("div", class_="year")
                or item.find("span", class_="date")
            )
            
            if year_elem:
                year_text = year_elem.get_text(strip=True)
                year_match = re.search(r"\b(19|20)\d{2}\b", year_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                        if year < 1900 or year > 2030:
                            year = None
                    except ValueError:
                        pass
            
            if not year:
                item_text = item.get_text()
                year_match = re.search(r"\b(19|20)\d{2}\b", item_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                        if year < 1900 or year > 2030:
                            year = None
                    except ValueError:
                        pass

            # Journal
            journal = None
            journal_elem = (
                item.find("span", class_="journal")
                or item.find("div", class_="journal")
                or item.find("a", class_="journal")
            )
            if journal_elem:
                journal = journal_elem.get_text(strip=True)

            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors if authors else [],
                year=year,
                doi=doi,
                journal=journal,
                database="Springer",
                url=url,
            )

            return paper

        except Exception as e:
            logger.warning(f"Error extracting paper from Springer item: {e}")
            return None

    def get_database_name(self) -> str:
        return "Springer"


class IEEEXploreConnector(DatabaseConnector):
    """IEEE Xplore connector using API (preferred) or web scraping (fallback)."""

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
            api_key=api_key or os.getenv("IEEE_API_KEY"),
            cache=cache,
            proxy_manager=proxy_manager,
            integrity_checker=integrity_checker,
            persistent_session=persistent_session,
            cookie_jar=cookie_jar,
        )
        self.base_url = "https://ieeexplore.ieee.org"
        self.search_url = f"{self.base_url}/search/searchresult.jsp"
        self.api_base_url = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
        self.use_api = bool(self.api_key)

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search IEEE Xplore using API if available, otherwise web scraping."""
        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "IEEE Xplore")
            if cached:
                return cached[:max_results]

        # Try API first if API key is available
        if self.use_api:
            try:
                return self._search_via_api(query, max_results)
            except Exception as e:
                logger.warning(f"IEEE Xplore API search failed: {e}. Falling back to web scraping.")
                # Fall through to web scraping
        
        # Fallback to web scraping
        return self._search_via_scraping(query, max_results)

    def _search_via_api(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search IEEE Xplore using official API."""
        papers = []
        
        try:
            session = self._get_session()
            request_kwargs = self._get_request_kwargs()
            request_kwargs.setdefault("timeout", 60)  # API can be slower
            
            # IEEE Xplore API parameters
            params = {
                "apikey": self.api_key,
                "querytext": query,
                "max_records": min(max_results, 200),  # API limit is 200 per request
                "start_record": 1,
                "sort_order": "desc",
                "sort_field": "article_title",
            }
            
            response = session.get(self.api_base_url, params=params, **request_kwargs)
            
            if response.status_code == 401:
                raise APIKeyError("Invalid IEEE Xplore API key")
            elif response.status_code == 429:
                raise RateLimitError("IEEE Xplore API rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            if "articles" not in data:
                logger.warning("IEEE Xplore API returned unexpected response format")
                return []
            
            for article in data["articles"]:
                try:
                    # Extract authors
                    authors = []
                    if "authors" in article and "authors" in article["authors"]:
                        for author in article["authors"]["authors"]:
                            if "full_name" in author:
                                authors.append(author["full_name"])
                    
                    # Extract year
                    year = None
                    if "publication_year" in article:
                        try:
                            year = int(article["publication_year"])
                        except (ValueError, TypeError):
                            pass
                    
                    # Extract DOI
                    doi = None
                    if "doi" in article:
                        doi = article["doi"]
                    
                    # Extract URL
                    url = None
                    if "html_url" in article:
                        url = article["html_url"]
                    elif "pdf_url" in article:
                        url = article["pdf_url"]
                    
                    # Extract abstract
                    abstract = article.get("abstract", "")
                    
                    # Extract keywords
                    keywords = None
                    if "index_terms" in article:
                        if "ieee_terms" in article["index_terms"]:
                            keywords = article["index_terms"]["ieee_terms"].get("terms", [])
                        elif "author_terms" in article["index_terms"]:
                            keywords = article["index_terms"]["author_terms"].get("terms", [])
                    
                    paper = Paper(
                        title=article.get("title", ""),
                        abstract=abstract,
                        authors=authors,
                        year=year,
                        doi=doi,
                        journal=article.get("publication_title", ""),
                        database="IEEE Xplore",
                        url=url,
                        keywords=keywords,
                    )
                    papers.append(paper)
                    
                    if len(papers) >= max_results:
                        break
                        
                except Exception as e:
                    logger.warning(f"Error parsing IEEE Xplore API result: {e}")
                    continue
            
        except APIKeyError:
            raise
        except RateLimitError:
            raise
        except requests.RequestException as e:
            logger.error(f"Network error searching IEEE Xplore API: {e}")
            raise NetworkError(f"IEEE Xplore API search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching IEEE Xplore API: {e}")
            raise DatabaseSearchError(f"IEEE Xplore API search error: {e}") from e
        
        # Validate papers
        papers = self._validate_papers(papers)
        
        # Cache results
        if self.cache and papers:
            self.cache.set(query, "IEEE Xplore", papers)
        
        return papers

    def _search_via_scraping(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search IEEE Xplore using web scraping (fallback method)."""
        papers = []

        try:
            from bs4 import BeautifulSoup
            import time

            session = self._get_session()
            request_kwargs = self._get_request_kwargs()
            request_kwargs.setdefault("timeout", 60)  # Increased timeout for reliability
            
            # Enhanced browser headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://ieeexplore.ieee.org/",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            
            # Visit homepage first to establish session with retry logic
            max_homepage_retries = 2
            for retry in range(max_homepage_retries):
                try:
                    logger.debug(f"Visiting IEEE Xplore homepage to establish session (attempt {retry + 1})...")
                    homepage_response = session.get(
                        self.base_url,
                        headers=headers,
                        **request_kwargs
                    )
                    if homepage_response.status_code == 403:
                        logger.warning(
                            "IEEE Xplore returned 403 Forbidden on homepage. "
                            "This may be due to anti-scraping measures. "
                            "Skipping IEEE Xplore search for this query."
                        )
                        return []
                    homepage_response.raise_for_status()
                    self._save_session_cookies()
                    break  # Success, exit retry loop
                except requests.HTTPError as e:
                    if hasattr(e.response, 'status_code') and e.response.status_code == 403:
                        logger.warning(
                            "IEEE Xplore returned 403 Forbidden. "
                            "Skipping IEEE Xplore search for this query."
                        )
                        return []
                    if retry < max_homepage_retries - 1:
                        import time
                        wait_time = 2 ** retry  # Exponential backoff
                        logger.debug(f"Homepage request failed, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.warning(f"Failed to visit IEEE Xplore homepage after {max_homepage_retries} attempts: {e}. Continuing with search anyway...")
                except requests.RequestException as e:
                    if retry < max_homepage_retries - 1:
                        import time
                        wait_time = 2 ** retry  # Exponential backoff
                        logger.debug(f"Homepage request failed, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.warning(f"Failed to visit IEEE Xplore homepage after {max_homepage_retries} attempts: {e}. Continuing with search anyway...")

            # IEEE Xplore search parameters
            page_size = 25  # IEEE typically shows 25 results per page
            pages_needed = (max_results + page_size - 1) // page_size

            for page in range(pages_needed):
                if len(papers) >= max_results:
                    break

                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()
                
                # Add delay between page requests
                if page > 0:
                    time.sleep(1.5)  # Slightly longer delay for IEEE

                params = {
                    "queryText": query,
                    "pageNumber": page + 1,
                    "rowsPerPage": page_size,
                }
                
                response = session.get(self.search_url, params=params, headers=headers, **request_kwargs)
                
                if response.status_code == 403:
                    logger.warning(
                        "IEEE Xplore returned 403 Forbidden. "
                        "Skipping IEEE Xplore search for this query."
                    )
                    return []
                
                response.raise_for_status()

                # Parse HTML
                soup = BeautifulSoup(response.content, "html.parser")
                page_papers = self._parse_search_results(soup)

                if not page_papers:
                    break

                papers.extend(page_papers)

                if len(page_papers) < page_size:
                    break

        except ImportError:
            raise ImportError("beautifulsoup4 required for IEEE Xplore connector. Install with: pip install beautifulsoup4")
        except requests.HTTPError as e:
            if hasattr(e.response, 'status_code') and e.response.status_code == 403:
                logger.warning(
                    "IEEE Xplore returned 403 Forbidden. "
                    "Skipping IEEE Xplore search for this query."
                )
                return []
            logger.error(f"HTTP error searching IEEE Xplore: {e}")
            raise NetworkError(f"IEEE Xplore search failed: {e}") from e
        except requests.RequestException as e:
            logger.error(f"Network error searching IEEE Xplore: {e}")
            raise NetworkError(f"IEEE Xplore search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching IEEE Xplore: {e}")
            raise DatabaseSearchError(f"IEEE Xplore search error: {e}") from e

        # Limit to max_results
        papers = papers[:max_results]

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "IEEE Xplore", papers)

        return papers

    def _parse_search_results(self, soup) -> List[Paper]:
        """Parse HTML search results page."""
        papers = []

        try:
            # IEEE Xplore search results are typically in list items or divs
            result_items = []
            
            selectors = [
                ("li", {"class": "List-item"}),
                ("div", {"class": "List-item"}),
                ("li", {"class": "result-item"}),
                ("div", {"class": "result-item"}),
                ("article", {"class": "result-item"}),
                ("li", {"data-testid": "search-result-item"}),
            ]
            
            for tag, attrs in selectors:
                if "class" in attrs:
                    result_items = soup.find_all(tag, class_=attrs["class"])
                elif "data-testid" in attrs:
                    result_items = soup.find_all(tag, {"data-testid": attrs["data-testid"]})
                if result_items:
                    logger.debug(f"Found {len(result_items)} IEEE Xplore results using selector: {tag} with {attrs}")
                    break
            
            # Fallback: find by title links
            if not result_items:
                title_links = soup.find_all("a", href=lambda x: x and "/document/" in str(x))
                if title_links:
                    seen_parents = set()
                    for link in title_links:
                        parent = link.find_parent("li") or link.find_parent("div") or link.find_parent("article")
                        if parent and id(parent) not in seen_parents:
                            result_items.append(parent)
                            seen_parents.add(id(parent))
                    logger.debug(f"Found {len(result_items)} IEEE Xplore results by grouping title links")

            if not result_items:
                logger.warning("No IEEE Xplore search results found - page structure may have changed")
                return papers

            for item in result_items:
                try:
                    paper = self._extract_paper_from_item(item)
                    if paper:
                        papers.append(paper)
                except Exception as e:
                    logger.warning(f"Error parsing IEEE Xplore result item: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error parsing IEEE Xplore search results: {e}")

        return papers

    def _extract_paper_from_item(self, item) -> Optional[Paper]:
        """Extract paper metadata from a single result item."""
        try:
            import re
            
            # Title
            title_elem = None
            title_selectors = [
                ("h3", {}),
                ("h2", {}),
                ("h4", {}),
                ("a", {"class": "title"}),
                ("span", {"class": "title"}),
                ("a", {"href": lambda x: x and "/document/" in str(x)}),
            ]
            
            for tag, attrs in title_selectors:
                if "class" in attrs:
                    title_elem = item.find(tag, class_=attrs["class"])
                elif "href" in attrs:
                    title_elem = item.find(tag, href=attrs["href"])
                else:
                    title_elem = item.find(tag)
                if title_elem:
                    break
            
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            if not title:
                return None

            # Authors
            authors = []
            author_selectors = [
                ("span", {"class": "authors"}),
                ("div", {"class": "authors"}),
                ("a", {"class": "author"}),
                ("span", {"class": "author"}),
            ]
            
            author_links = []
            for tag, attrs in author_selectors:
                author_links = item.find_all(tag, class_=attrs["class"])
                if author_links:
                    break
            
            if not author_links:
                author_section = item.find("div", class_="authors") or item.find("span", class_="authors")
                if author_section:
                    author_links = author_section.find_all("a")
                    if not author_links:
                        author_text = author_section.get_text(strip=True)
                        if author_text:
                            authors = [a.strip() for a in re.split(r'[,;]', author_text) if a.strip()]

            for author_link in author_links:
                author_name = author_link.get_text(strip=True)
                if author_name and author_name not in authors:
                    authors.append(author_name)

            # Abstract
            abstract_elem = (
                item.find("p", class_="abstract")
                or item.find("div", class_="abstract")
                or item.find("span", class_="abstract")
                or item.find("p", class_="snippet")
            )
            abstract = abstract_elem.get_text(strip=True) if abstract_elem else ""

            # DOI
            doi = None
            doi_link = item.find("a", href=lambda x: x and ("doi.org" in str(x) or "/doi/" in str(x)))
            if doi_link:
                href = doi_link.get("href", "")
                if "doi.org/" in href:
                    doi = href.split("doi.org/")[-1].split("?")[0]
                elif "/doi/" in href:
                    doi = href.split("/doi/")[-1].split("?")[0]
            else:
                doi_text = item.get_text()
                doi_match = re.search(r"10\.\d+/[^\s\)]+", doi_text)
                if doi_match:
                    doi = doi_match.group(0).rstrip(".,;:)]}")

            # URL
            url = None
            if title_elem and title_elem.name == "a":
                href = title_elem.get("href", "")
                if href:
                    if href.startswith("/"):
                        url = f"{self.base_url}{href}"
                    elif href.startswith("http"):
                        url = href
            else:
                doc_link = item.find("a", href=lambda x: x and "/document/" in str(x))
                if doc_link:
                    href = doc_link.get("href", "")
                    if href.startswith("/"):
                        url = f"{self.base_url}{href}"
                    elif href.startswith("http"):
                        url = href

            # Year
            year = None
            year_elem = (
                item.find("span", class_="year")
                or item.find("div", class_="year")
                or item.find("span", class_="date")
            )
            
            if year_elem:
                year_text = year_elem.get_text(strip=True)
                year_match = re.search(r"\b(19|20)\d{2}\b", year_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                        if year < 1900 or year > 2030:
                            year = None
                    except ValueError:
                        pass
            
            if not year:
                item_text = item.get_text()
                year_match = re.search(r"\b(19|20)\d{2}\b", item_text)
                if year_match:
                    try:
                        year = int(year_match.group(0))
                        if year < 1900 or year > 2030:
                            year = None
                    except ValueError:
                        pass

            # Journal/Conference
            journal = None
            journal_elem = (
                item.find("span", class_="publication")
                or item.find("div", class_="publication")
                or item.find("a", class_="publication")
                or item.find("span", class_="journal")
            )
            if journal_elem:
                journal = journal_elem.get_text(strip=True)

            paper = Paper(
                title=title,
                abstract=abstract,
                authors=authors if authors else [],
                year=year,
                doi=doi,
                journal=journal,
                database="IEEE Xplore",
                url=url,
            )

            return paper

        except Exception as e:
            logger.warning(f"Error extracting paper from IEEE Xplore item: {e}")
            return None

    def get_database_name(self) -> str:
        return "IEEE Xplore"


class PerplexityConnector(DatabaseConnector):
    """Perplexity Search API connector with academic filter."""

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
            api_key or os.getenv("PERPLEXITY_SEARCH_API_KEY") or os.getenv("PERPLEXITY_API_KEY"),
            cache,
            proxy_manager,
            integrity_checker,
            persistent_session,
            cookie_jar,
        )
        self.base_url = "https://api.perplexity.ai/search"

    @retry_with_backoff(max_attempts=3)
    def search(self, query: str, max_results: int = 100) -> List[Paper]:
        """Search Perplexity with academic filter."""
        if not self.api_key:
            logger.warning("Perplexity API key required")
            return []

        # Check cache first
        if self.cache:
            cached = self.cache.get(query, "Perplexity")
            if cached:
                return cached[:max_results]

        papers = []

        try:
            rate_limiter = self._get_rate_limiter()
            rate_limiter.acquire()

            # Prepare request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # Perplexity Search API request body
            # Note: search_mode is NOT supported by Search API, only by Chat Completions API
            # Domain filtering options:
            # - PERPLEXITY_DOMAIN_FILTER_MODE=allowlist (default): Include only academic domains (max 20)
            # - PERPLEXITY_DOMAIN_FILTER_MODE=denylist: Exclude non-academic domains (max 20)
            # - PERPLEXITY_DOMAIN_FILTER_MODE=none or PERPLEXITY_NO_DOMAIN_FILTER=true: No filtering
            filter_mode = os.getenv("PERPLEXITY_DOMAIN_FILTER_MODE", "allowlist").lower()
            if os.getenv("PERPLEXITY_NO_DOMAIN_FILTER", "false").lower() == "true":
                filter_mode = "none"
            
            # Common non-academic domains to exclude (if using denylist mode)
            # This allows us to capture ALL academic sources while filtering out noise
            # Perplexity allows max 20 domains, prioritized by empirical analysis:
            # Top domains from generic research queries: Wikipedia (14.9%), YouTube (6.9%), IBM (3.4%), etc.
            non_academic_domains = [
                # Wikipedia (most common - 14.9% of non-academic results)
                "en.wikipedia.org",
                # Video platforms (6.9% combined)
                "youtube.com",
                "youtu.be",
                # Social media (high noise, low academic value)
                "twitter.com",
                "x.com",
                "facebook.com",
                "instagram.com",
                "linkedin.com",
                "reddit.com",
                "quora.com",
                "pinterest.com",
                "tumblr.com",
                # Tech company blogs (not peer-reviewed) - IBM (3.4%)
                "ibm.com",
                "aws.amazon.com",
                "developers.google.com",
                "cloud.google.com",
                # Tutorial platforms (not academic papers)
                "geeksforgeeks.org",
                "w3schools.com",
                "tutorialspoint.com",
                "codecademy.com",
            ]
            
            # Key academic domains (for allowlist mode - max 20)
            # Using main domains covers subdomains (e.g., "springer.com" covers "link.springer.com")
            academic_domains = [
                # Preprint servers (highest priority - open access)
                "arxiv.org",
                "biorxiv.org",
                "medrxiv.org",
                "chemrxiv.org",
                "ssrn.com",  # Social Science Research Network
                # PubMed and medical databases
                "pubmed.ncbi.nlm.nih.gov",
                "ncbi.nlm.nih.gov",
                "pmc.ncbi.nlm.nih.gov",
                # Major academic publishers (main domains cover subdomains)
                "nature.com",
                "science.org",
                "cell.com",
                "springer.com",  # Covers springerlink.com, link.springer.com
                "ieee.org",  # Covers ieeexplore.ieee.org
                "acm.org",  # Covers dl.acm.org
                "elsevier.com",  # Covers sciencedirect.com
                "wiley.com",  # Covers onlinelibrary.wiley.com
                "tandfonline.com",  # Taylor & Francis
                "plos.org",  # Covers journals.plos.org
                # Academic search engines and repositories
                "semanticscholar.org",
                "scholar.google.com",
            ]
            
            request_body = {
                "query": query,
                "max_results": min(max_results, 20),  # Perplexity Search API allows max 20 per request
            }
            
            # Apply domain filtering based on mode
            if filter_mode == "allowlist":
                # Include only academic domains (may miss some academic sources)
                request_body["search_domain_filter"] = academic_domains
            elif filter_mode == "denylist":
                # Exclude non-academic domains (captures ALL academic sources, filters noise)
                # Prefix domains with "-" for denylist mode
                request_body["search_domain_filter"] = [f"-{domain}" for domain in non_academic_domains]
            # else: filter_mode == "none" - no filtering applied

            session = self._get_session()
            request_kwargs = self._get_request_kwargs()
            request_kwargs.setdefault("timeout", 30)

            response = session.post(
                self.base_url,
                json=request_body,
                headers=headers,
                **request_kwargs
            )

            if response.status_code == 401:
                error_detail = ""
                try:
                    error_data = response.json()
                    error_detail = f" - {error_data.get('detail', response.text)}"
                except Exception:
                    error_detail = f" - {response.text[:200]}"
                raise APIKeyError(f"Invalid Perplexity API key or key doesn't have Search API access{error_detail}")
            elif response.status_code == 429:
                raise RateLimitError("Perplexity rate limit exceeded")
            elif response.status_code == 400:
                # Get detailed error message
                error_detail = ""
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        error_detail = f" - {error_data.get('detail', error_data.get('message', response.text[:500]))}"
                    else:
                        error_detail = f" - {str(error_data)[:500]}"
                except Exception:
                    error_detail = f" - {response.text[:500]}"
                logger.error(f"Perplexity API 400 error. Request body: {request_body}, Response: {error_detail}")
                raise DatabaseSearchError(
                    f"Perplexity API returned 400 Bad Request. "
                    f"This usually means the request format is incorrect.{error_detail}"
                )

            response.raise_for_status()
            data = response.json()

            if "results" not in data:
                return papers

            # Convert results to Paper objects
            import re
            
            for result in data["results"]:
                if len(papers) >= max_results:
                    break

                # Extract title
                title = result.get("title", "")

                # Extract abstract from snippet
                abstract = result.get("snippet", "")

                # Extract URL
                url = result.get("url", "")

                # Extract year from date if available
                year = None
                date_str = result.get("date") or result.get("last_updated")
                if date_str:
                    try:
                        # Try to parse year from date string (format: YYYY-MM-DD or similar)
                        year_match = re.search(r"\b(19|20)\d{2}\b", str(date_str))
                        if year_match:
                            year = int(year_match.group(0))
                            # Sanity check
                            if year < 1900 or year > 2030:
                                year = None
                    except (ValueError, TypeError):
                        pass

                # Try to extract DOI from URL or snippet
                doi = None
                if url:
                    # Check if URL contains DOI
                    doi_match = re.search(r"10\.\d+/[^\s\)]+", url)
                    if doi_match:
                        doi = doi_match.group(0).rstrip(".,;:)]}")
                if not doi and abstract:
                    # Try to extract DOI from snippet
                    doi_match = re.search(r"10\.\d+/[^\s\)]+", abstract)
                    if doi_match:
                        doi = doi_match.group(0).rstrip(".,;:)]}")

                # Try to extract authors from snippet (may not always be available)
                authors = []
                if abstract:
                    # Look for common author patterns in academic snippets
                    # This is heuristic and may not always work
                    author_patterns = [
                        r"([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)",  # First Last or First M. Last
                    ]
                    for pattern in author_patterns:
                        matches = re.findall(pattern, abstract[:500])  # Check first 500 chars
                        if matches:
                            authors = matches[:5]  # Limit to 5 authors
                            break

                # Try to extract journal/venue from URL domain or snippet
                journal = None
                if url:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        domain = parsed.netloc.lower()
                        # Common academic domains
                        if "arxiv.org" in domain:
                            journal = "arXiv"
                        elif "pubmed" in domain or "ncbi.nlm.nih.gov" in domain:
                            journal = "PubMed"
                        elif "ieee.org" in domain:
                            journal = "IEEE"
                        elif "springer.com" in domain:
                            journal = "Springer"
                        elif "acm.org" in domain:
                            journal = "ACM"
                        elif "doi.org" in domain:
                            # Try to extract journal from DOI metadata later if needed
                            pass
                    except Exception:
                        pass

                # Create Paper object
                paper = Paper(
                    title=title,
                    abstract=abstract,
                    authors=authors if authors else [],
                    year=year,
                    doi=doi,
                    journal=journal,
                    database="Perplexity",
                    url=url,
                )
                papers.append(paper)

        except requests.RequestException as e:
            logger.error(f"Network error searching Perplexity: {e}")
            raise NetworkError(f"Perplexity search failed: {e}") from e
        except Exception as e:
            logger.error(f"Error searching Perplexity: {e}")
            raise DatabaseSearchError(f"Perplexity search error: {e}") from e

        # Validate papers
        papers = self._validate_papers(papers)

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Perplexity", papers)

        return papers

    def get_database_name(self) -> str:
        return "Perplexity"


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
