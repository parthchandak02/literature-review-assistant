"""
Database Connectors

Connectors for various academic databases: PubMed, Scopus, Web of Science, IEEE Xplore, Google Scholar,
arXiv, Semantic Scholar, Crossref.

This module maintains backward compatibility by re-exporting from the refactored connector modules.
"""

# Re-export base classes and Paper for backward compatibility
from .connectors.base import Paper, DatabaseConnector

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
    ):
        super().__init__(api_key or os.getenv("PUBMED_API_KEY"), cache)
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

            response = requests.get(search_url, params=params, timeout=30)
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

                fetch_response = requests.get(fetch_url, params=fetch_params, timeout=30)
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
            title = title_elem.text if title_elem is not None and title_elem.text else ""

            # Abstract
            abstract_elems = article.findall(".//AbstractText", namespace)
            abstract_parts = []
            for elem in abstract_elems:
                if elem.text:
                    label = elem.get("Label", "")
                    text = elem.text
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract = " ".join(abstract_parts) if abstract_parts else ""

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

    def __init__(self, cache: Optional[SearchCache] = None):
        super().__init__(cache=cache)
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

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "arXiv", papers)

        return papers

    def get_database_name(self) -> str:
        return "arXiv"


class SemanticScholarConnector(DatabaseConnector):
    """Semantic Scholar connector."""

    def __init__(self, api_key: Optional[str] = None, cache: Optional[SearchCache] = None):
        super().__init__(api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY"), cache)
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

                response = requests.get(self.base_url, params=params, headers=headers, timeout=30)

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

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Semantic Scholar", papers)

        return papers

    def get_database_name(self) -> str:
        return "Semantic Scholar"


class CrossrefConnector(DatabaseConnector):
    """Crossref connector using REST API."""

    def __init__(self, email: Optional[str] = None, cache: Optional[SearchCache] = None):
        super().__init__(cache=cache)
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

                response = requests.get(self.base_url, params=params, timeout=30)

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

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Crossref", papers)

        return papers

    def get_database_name(self) -> str:
        return "Crossref"


class ScopusConnector(DatabaseConnector):
    """Scopus connector (requires API key)."""

    def __init__(self, api_key: Optional[str] = None, cache: Optional[SearchCache] = None):
        super().__init__(api_key or os.getenv("SCOPUS_API_KEY"), cache)
        self.base_url = "https://api.elsevier.com/content/search/scopus"

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

            params = {
                "query": query,
                "count": min(max_results, 25),  # Scopus API limit per request
                "start": 0,
                "view": "COMPLETE",  # Required to get abstracts and full author info
            }

            while len(papers) < max_results:
                rate_limiter = self._get_rate_limiter()
                rate_limiter.acquire()

                response = requests.get(self.base_url, headers=headers, params=params, timeout=30)

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

        # Cache results
        if self.cache and papers:
            self.cache.set(query, "Scopus", papers)

        return papers

    def get_database_name(self) -> str:
        return "Scopus"


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
