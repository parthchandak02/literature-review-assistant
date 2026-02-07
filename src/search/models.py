"""
Bibliometric Data Models

Author, Affiliation, and bibliometric data models for enhanced database connectors.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class Affiliation:
    """Represents an institutional affiliation."""

    name: str
    id: Optional[str] = None  # Database-specific affiliation ID
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    organization_domain: Optional[str] = None
    organization_url: Optional[str] = None
    author_count: Optional[int] = None  # Number of authors at this affiliation
    parent_affiliation_id: Optional[str] = None
    parent_affiliation_name: Optional[str] = None
    affiliation_type: Optional[str] = None  # e.g., "parent", "child"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "id": self.id,
            "city": self.city,
            "country": self.country,
            "country_code": self.country_code,
            "address": self.address,
            "postal_code": self.postal_code,
            "organization_domain": self.organization_domain,
            "organization_url": self.organization_url,
            "author_count": self.author_count,
            "parent_affiliation_id": self.parent_affiliation_id,
            "parent_affiliation_name": self.parent_affiliation_name,
            "affiliation_type": self.affiliation_type,
        }


@dataclass
class Author:
    """Represents an author with bibliometric data."""

    name: str
    id: Optional[str] = None  # Database-specific author ID
    given_name: Optional[str] = None
    surname: Optional[str] = None
    indexed_name: Optional[str] = None  # Name as indexed by database
    initials: Optional[str] = None
    email: Optional[str] = None
    orcid: Optional[str] = None

    # Bibliometric metrics
    h_index: Optional[int] = None
    i10_index: Optional[int] = None
    h_index_5y: Optional[int] = None  # 5-year h-index
    i10_index_5y: Optional[int] = None  # 5-year i10-index
    citation_count: Optional[int] = None  # Total citations
    cited_by_count: Optional[int] = None  # Number of citing authors
    document_count: Optional[int] = None  # Number of publications

    # Affiliation information
    current_affiliations: List[Affiliation] = field(default_factory=list)
    historical_affiliations: List[Affiliation] = field(default_factory=list)

    # Subject areas and research interests
    subject_areas: List[str] = field(default_factory=list)
    research_interests: List[str] = field(default_factory=list)

    # Coauthors
    coauthor_count: Optional[int] = None
    coauthors: List["Author"] = field(default_factory=list)

    # Publication range
    first_publication_year: Optional[int] = None
    last_publication_year: Optional[int] = None

    # Database-specific fields
    database: Optional[str] = None
    url: Optional[str] = None
    profile_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "id": self.id,
            "given_name": self.given_name,
            "surname": self.surname,
            "indexed_name": self.indexed_name,
            "initials": self.initials,
            "email": self.email,
            "orcid": self.orcid,
            "h_index": self.h_index,
            "i10_index": self.i10_index,
            "h_index_5y": self.h_index_5y,
            "i10_index_5y": self.i10_index_5y,
            "citation_count": self.citation_count,
            "cited_by_count": self.cited_by_count,
            "document_count": self.document_count,
            "current_affiliations": [aff.to_dict() for aff in self.current_affiliations],
            "historical_affiliations": [aff.to_dict() for aff in self.historical_affiliations],
            "subject_areas": self.subject_areas,
            "research_interests": self.research_interests,
            "coauthor_count": self.coauthor_count,
            "coauthors": [
                coauth.to_dict() if isinstance(coauth, Author) else coauth
                for coauth in self.coauthors
            ],
            "first_publication_year": self.first_publication_year,
            "last_publication_year": self.last_publication_year,
            "database": self.database,
            "url": self.url,
            "profile_url": self.profile_url,
        }
