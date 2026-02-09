"""
Citation Registry

Manages citation identities, citekey generation, and reference formatting.
Provides deterministic mapping between papers and citations.
"""

import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from ..search.database_connectors import Paper

logger = logging.getLogger(__name__)


class CitationRegistry:
    """Central registry for managing citations and generating references."""

    def __init__(self, papers: List[Paper]):
        """
        Initialize citation registry from list of papers.

        Args:
            papers: List of Paper objects to register
        """
        self.papers = papers
        self.citekey_to_paper: Dict[str, Paper] = {}
        self.paper_to_citekey: Dict[int, str] = {}  # paper index -> citekey
        self.doi_to_citekey: Dict[str, str] = {}
        self.pmid_to_citekey: Dict[str, str] = {}
        
        # Build registry
        self._build_registry()

    def _build_registry(self):
        """Build citekey mappings from papers."""
        # Group papers by author+year for disambiguation
        author_year_counts: Dict[str, int] = defaultdict(int)
        author_year_papers: Dict[str, List[Tuple[int, Paper]]] = defaultdict(list)

        # First pass: count duplicates
        for idx, paper in enumerate(self.papers):
            base_key = self._generate_base_citekey(paper)
            if base_key:
                author_year_counts[base_key] += 1
                author_year_papers[base_key].append((idx, paper))

        # Second pass: assign citekeys with disambiguation
        for base_key, paper_list in author_year_papers.items():
            if author_year_counts[base_key] == 1:
                # No disambiguation needed
                idx, paper = paper_list[0]
                self._register_paper(idx, paper, base_key)
            else:
                # Add disambiguation suffix (a, b, c, ...)
                for suffix_idx, (idx, paper) in enumerate(sorted(paper_list, key=lambda x: x[1].title or "")):
                    suffix = chr(ord('a') + suffix_idx)
                    citekey = f"{base_key}{suffix}"
                    self._register_paper(idx, paper, citekey)

    def _generate_base_citekey(self, paper: Paper) -> Optional[str]:
        """
        Generate base citekey (without disambiguation suffix).

        Args:
            paper: Paper to generate citekey for

        Returns:
            Base citekey like "Smith2023" or None if cannot generate
        """
        if not paper.authors or not paper.year:
            logger.warning(f"Cannot generate citekey for paper without author/year: {paper.title[:50] if paper.title else 'Untitled'}")
            return None

        # Extract first author surname
        first_author = paper.authors[0]
        surname = self._extract_surname(first_author)
        
        if not surname:
            logger.warning(f"Cannot extract surname from author: {first_author}")
            return None

        # Clean surname (remove non-alphanumeric)
        surname_clean = re.sub(r'[^a-zA-Z]', '', surname)
        
        # Capitalize first letter
        surname_clean = surname_clean.capitalize()

        return f"{surname_clean}{paper.year}"

    def _extract_surname(self, author_name: str) -> str:
        """
        Extract surname from author name.

        Handles formats:
        - "Surname, Firstname"
        - "Firstname Surname"
        - "Firstname Middle Surname"

        Args:
            author_name: Author name string

        Returns:
            Extracted surname
        """
        author_name = author_name.strip()
        
        # Handle "Surname, Firstname" format
        if ',' in author_name:
            return author_name.split(',')[0].strip()
        
        # Handle "Firstname Surname" format - take last word
        parts = author_name.split()
        if parts:
            return parts[-1]
        
        return author_name

    def _register_paper(self, idx: int, paper: Paper, citekey: str):
        """
        Register a paper with its citekey.

        Args:
            idx: Paper index in original list
            paper: Paper object
            citekey: Generated citekey
        """
        self.citekey_to_paper[citekey] = paper
        self.paper_to_citekey[idx] = citekey

        # Register alternative identifiers
        if paper.doi:
            self.doi_to_citekey[paper.doi.lower()] = citekey
        if paper.pubmed_id:
            self.pmid_to_citekey[paper.pubmed_id] = citekey

    def get_citekey(self, paper: Paper) -> Optional[str]:
        """
        Get citekey for a paper.

        Args:
            paper: Paper to look up

        Returns:
            Citekey or None if not found
        """
        # Try to find by paper index
        for idx, p in enumerate(self.papers):
            if p is paper:
                return self.paper_to_citekey.get(idx)

        # Try DOI
        if paper.doi and paper.doi.lower() in self.doi_to_citekey:
            return self.doi_to_citekey[paper.doi.lower()]

        # Try PMID
        if paper.pubmed_id and paper.pubmed_id in self.pmid_to_citekey:
            return self.pmid_to_citekey[paper.pubmed_id]

        return None

    def resolve_citekey(self, citekey: str) -> Optional[Paper]:
        """
        Resolve citekey to paper with fallback strategies.

        Priority:
        1. Direct citekey match
        2. DOI match
        3. PMID match
        4. Author+year fuzzy match

        Args:
            citekey: Citekey to resolve

        Returns:
            Paper or None if not found
        """
        # Direct match
        if citekey in self.citekey_to_paper:
            return self.citekey_to_paper[citekey]

        # Check if it's a DOI
        if citekey.startswith('10.'):
            doi_lower = citekey.lower()
            if doi_lower in self.doi_to_citekey:
                return self.citekey_to_paper[self.doi_to_citekey[doi_lower]]

        # Check if it's a PMID
        if citekey.isdigit():
            if citekey in self.pmid_to_citekey:
                return self.citekey_to_paper[self.pmid_to_citekey[citekey]]

        # Try fuzzy author+year match
        match = re.match(r'([A-Z][a-zA-Z]+)(\d{4})([a-z]?)', citekey)
        if match:
            surname = match.group(1).lower()
            year = match.group(2)
            
            for paper in self.papers:
                if not paper.authors or not paper.year:
                    continue
                
                paper_surname = self._extract_surname(paper.authors[0]).lower()
                paper_surname_clean = re.sub(r'[^a-z]', '', paper_surname)
                
                if paper_surname_clean == surname.lower() and str(paper.year) == year:
                    return paper

        return None

    def catalog_for_prompt(self, max_entries: int = 50) -> str:
        """
        Generate compact citation catalog for LLM prompt.

        Args:
            max_entries: Maximum number of entries to include

        Returns:
            Formatted catalog string
        """
        catalog_lines = ["AVAILABLE CITATIONS (use exact citekey in brackets, e.g., [Smith2023]):\n"]
        
        # Sort by citekey for consistency
        sorted_citekeys = sorted(self.citekey_to_paper.keys())[:max_entries]
        
        for citekey in sorted_citekeys:
            paper = self.citekey_to_paper[citekey]
            
            # Format: [Smith2023] Smith et al. (2023) - "Short title..."
            authors_str = self._format_authors_short(paper)
            title_short = (paper.title[:60] + "...") if paper.title and len(paper.title) > 60 else (paper.title or "Untitled")
            
            catalog_lines.append(f"  [{citekey}] {authors_str} ({paper.year}) - \"{title_short}\"")
        
        if len(self.citekey_to_paper) > max_entries:
            catalog_lines.append(f"\n  ... and {len(self.citekey_to_paper) - max_entries} more papers")
        
        catalog_lines.append("\nIMPORTANT: Use ONLY these exact citekeys. Do NOT invent citations or use [Citation X] format.")
        
        return "\n".join(catalog_lines)

    def _format_authors_short(self, paper: Paper) -> str:
        """Format authors for short display (first author et al.)."""
        if not paper.authors:
            return "Unknown"
        
        first_author = paper.authors[0]
        surname = self._extract_surname(first_author)
        
        if len(paper.authors) == 1:
            return surname
        elif len(paper.authors) == 2:
            second_surname = self._extract_surname(paper.authors[1])
            return f"{surname} and {second_surname}"
        else:
            return f"{surname} et al."

    def replace_citekeys_with_numbers(self, text: str) -> Tuple[str, List[str]]:
        """
        Replace citekeys in text with numbered citations.

        Args:
            text: Text containing citekeys like [Smith2023]

        Returns:
            Tuple of (transformed text, list of used citekeys in order)
        """
        # Extract all citekeys in order of first appearance.
        # Supports single cites: [Smith2023]
        # and multi cites: [Smith2023, Jones2024]
        cite_pattern = r'[A-Z][a-zA-Z]+\d{4}[a-z]?'
        bracket_pattern = rf'\[((?:{cite_pattern})(?:\s*,\s*{cite_pattern})*)\]'
        found_groups = re.findall(bracket_pattern, text)
        found_keys: List[str] = []
        for group in found_groups:
            found_keys.extend([k.strip() for k in group.split(",") if k.strip()])
        
        # Build mapping preserving first-appearance order
        seen_keys: Set[str] = set()
        ordered_keys: List[str] = []
        
        for key in found_keys:
            if key not in seen_keys:
                ordered_keys.append(key)
                seen_keys.add(key)
        
        # Create citekey -> number mapping
        citekey_to_num = {key: idx + 1 for idx, key in enumerate(ordered_keys)}
        
        # Replace citekeys with numbers (including multi-citation brackets).
        def replace_func(match):
            group = match.group(1)
            keys = [k.strip() for k in group.split(",") if k.strip()]
            mapped = []
            for citekey in keys:
                if citekey in citekey_to_num:
                    mapped.append(str(citekey_to_num[citekey]))
                else:
                    logger.warning(f"Unknown citekey in text: {citekey}")
                    mapped.append(citekey)
            return f"[{', '.join(mapped)}]"

        transformed_text = re.sub(bracket_pattern, replace_func, text)
        
        return transformed_text, ordered_keys

    def references_markdown(self, used_citekeys: List[str]) -> str:
        """
        Generate references section in IEEE/Vancouver format.

        Args:
            used_citekeys: List of citekeys in citation order

        Returns:
            Formatted references section as markdown
        """
        if not used_citekeys:
            return "## References\n\nNo citations found in the document.\n\n"
        
        refs = ["## References\n"]
        
        for idx, citekey in enumerate(used_citekeys, 1):
            paper = self.resolve_citekey(citekey)
            
            if not paper:
                refs.append(f"[{idx}] {citekey} (paper not found)\n\n")
                logger.warning(f"Cannot generate reference for citekey: {citekey}")
                continue
            
            # Format: [1] Authors. Title. Journal, Year. DOI: ...
            authors_str = self._format_authors_full(paper)
            title = paper.title or "Untitled"
            journal = paper.journal or ""
            year = paper.year or "n.d."
            doi = paper.doi or ""
            
            ref = f"[{idx}] {authors_str}. {title}."
            if journal:
                ref += f" *{journal}*,"
            ref += f" {year}."
            if doi:
                ref += f" DOI: {doi}"
            
            refs.append(ref + "\n\n")
        
        return "".join(refs)

    def _format_authors_full(self, paper: Paper) -> str:
        """Format authors for full reference (up to 3, then et al.)."""
        if not paper.authors:
            return "Unknown"
        
        authors = paper.authors[:3]
        
        if len(paper.authors) <= 3:
            return ", ".join(authors)
        else:
            return ", ".join(authors) + " et al."

    def to_bibtex(self, used_citekeys: List[str]) -> str:
        """
        Generate BibTeX format for used references.

        Args:
            used_citekeys: List of citekeys to export

        Returns:
            BibTeX formatted string
        """
        entries = []
        
        for citekey in used_citekeys:
            paper = self.resolve_citekey(citekey)
            if not paper:
                logger.warning(f"Cannot generate BibTeX for citekey: {citekey}")
                continue
            
            # Determine entry type
            entry_type = "article" if paper.journal else "misc"
            
            # Build BibTeX entry
            entry_lines = [f"@{entry_type}{{{citekey},"]
            
            # Required/common fields
            if paper.title:
                entry_lines.append(f"  title = {{{paper.title}}},")
            if paper.authors:
                authors_bibtex = " and ".join(paper.authors)
                entry_lines.append(f"  author = {{{authors_bibtex}}},")
            if paper.year:
                entry_lines.append(f"  year = {{{paper.year}}},")
            if paper.journal:
                entry_lines.append(f"  journal = {{{paper.journal}}},")
            if paper.doi:
                entry_lines.append(f"  doi = {{{paper.doi}}},")
            if paper.url:
                entry_lines.append(f"  url = {{{paper.url}}},")
            
            entry_lines.append("}")
            entries.append("\n".join(entry_lines))
        
        return "\n\n".join(entries)

    def to_ris(self, used_citekeys: List[str]) -> str:
        """
        Generate RIS format for used references.

        Args:
            used_citekeys: List of citekeys to export

        Returns:
            RIS formatted string
        """
        entries = []
        
        for citekey in used_citekeys:
            paper = self.resolve_citekey(citekey)
            if not paper:
                logger.warning(f"Cannot generate RIS for citekey: {citekey}")
                continue
            
            # Build RIS entry
            entry_lines = []
            
            # Type
            entry_lines.append("TY  - JOUR" if paper.journal else "TY  - GEN")
            
            # Authors
            if paper.authors:
                for author in paper.authors:
                    entry_lines.append(f"AU  - {author}")
            
            # Title
            if paper.title:
                entry_lines.append(f"TI  - {paper.title}")
            
            # Journal
            if paper.journal:
                entry_lines.append(f"JO  - {paper.journal}")
            
            # Year
            if paper.year:
                entry_lines.append(f"PY  - {paper.year}")
            
            # DOI
            if paper.doi:
                entry_lines.append(f"DO  - {paper.doi}")
            
            # URL
            if paper.url:
                entry_lines.append(f"UR  - {paper.url}")
            
            # End of record
            entry_lines.append("ER  -")
            
            entries.append("\n".join(entry_lines))
        
        return "\n\n".join(entries)

    def extract_citekeys_from_text(self, text: str) -> List[str]:
        """
        Extract all citekeys from text.

        Args:
            text: Text to scan for citekeys

        Returns:
            List of found citekeys (with duplicates)
        """
        cite_pattern = r'[A-Z][a-zA-Z]+\d{4}[a-z]?'
        bracket_pattern = rf'\[((?:{cite_pattern})(?:\s*,\s*{cite_pattern})*)\]'
        groups = re.findall(bracket_pattern, text)
        keys: List[str] = []
        for group in groups:
            keys.extend([k.strip() for k in group.split(",") if k.strip()])
        return keys

    def validate_citekeys(self, citekeys: List[str]) -> Tuple[List[str], List[str]]:
        """
        Validate list of citekeys.

        Args:
            citekeys: List of citekeys to validate

        Returns:
            Tuple of (valid_citekeys, invalid_citekeys)
        """
        valid = []
        invalid = []
        
        for citekey in citekeys:
            if self.resolve_citekey(citekey):
                valid.append(citekey)
            else:
                invalid.append(citekey)
        
        return valid, invalid
