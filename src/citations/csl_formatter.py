"""
CSL Citation Formatter

Formats citations using Citation Style Language (CSL) styles.
Supports multiple citation styles: IEEE, APA, Nature, PLOS, etc.
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import urllib.request
import urllib.error

from ..search.connectors.base import Paper

logger = logging.getLogger(__name__)

# CSL styles repository URL
CSL_STYLES_REPO = "https://raw.githubusercontent.com/citation-style-language/styles/master"
CSL_STYLES_CACHE_DIR = Path("data/cache/csl_styles")


class CSLFormatter:
    """Format citations using CSL styles."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize CSL formatter.

        Args:
            cache_dir: Directory to cache CSL style files (default: data/cache/csl_styles)
        """
        self.cache_dir = cache_dir or CSL_STYLES_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._available_styles = None

    def get_available_styles(self) -> List[str]:
        """
        Get list of available CSL styles.

        Returns:
            List of style names (e.g., ['ieee', 'apa', 'nature', 'plos'])
        """
        if self._available_styles is None:
            # Common CSL styles
            self._available_styles = [
                "ieee",
                "apa",
                "nature",
                "plos-one",
                "plos-computational-biology",
                "bmj",
                "ama",
                "vancouver",
                "harvard",
                "chicago",
                "mla",
            ]
        return self._available_styles

    def download_style(self, style_name: str) -> Path:
        """
        Download CSL style file from repository.

        Args:
            style_name: Name of the style (e.g., 'ieee', 'apa')

        Returns:
            Path to downloaded style file

        Raises:
            ValueError: If style download fails
        """
        style_file = self.cache_dir / f"{style_name}.csl"

        # Check if already cached
        if style_file.exists():
            logger.debug(f"Using cached CSL style: {style_file}")
            return style_file

        # Try different possible file names
        possible_names = [
            f"{style_name}.csl",
            f"{style_name}-no-et-al.csl",
            f"{style_name}-author-date.csl",
        ]

        for name in possible_names:
            url = f"{CSL_STYLES_REPO}/{name}"
            try:
                logger.info(f"Downloading CSL style from {url}")
                urllib.request.urlretrieve(url, style_file)
                logger.info(f"Downloaded CSL style: {style_file}")
                return style_file
            except urllib.error.HTTPError:
                continue

        raise ValueError(f"Could not download CSL style: {style_name}")

    def get_style_path(self, style_name: str) -> Path:
        """
        Get path to CSL style file, downloading if necessary.

        Args:
            style_name: Name of the style

        Returns:
            Path to style file
        """
        style_file = self.cache_dir / f"{style_name}.csl"
        if not style_file.exists():
            return self.download_style(style_name)
        return style_file

    def paper_to_csl(self, paper: Paper) -> Dict[str, Any]:
        """
        Convert Paper object to CSL JSON format.

        Args:
            paper: Paper object

        Returns:
            CSL JSON item as dictionary
        """
        csl_item = {
            "type": "article-journal",  # Default type
        }

        # Title
        if paper.title:
            csl_item["title"] = paper.title

        # Authors
        if paper.authors:
            authors = []
            for author_str in paper.authors:
                # Parse author string (format: "Last, First" or "First Last")
                if "," in author_str:
                    parts = author_str.split(",", 1)
                    authors.append({
                        "family": parts[0].strip(),
                        "given": parts[1].strip() if len(parts) > 1 else "",
                    })
                else:
                    # Try to split "First Last"
                    parts = author_str.strip().split()
                    if len(parts) >= 2:
                        authors.append({
                            "family": parts[-1],
                            "given": " ".join(parts[:-1]),
                        })
                    else:
                        authors.append({"literal": author_str})
            csl_item["author"] = authors

        # Year
        if paper.year:
            csl_item["issued"] = {"date-parts": [[paper.year]]}

        # Journal/Container
        if paper.journal:
            csl_item["container-title"] = paper.journal

        # DOI
        if paper.doi:
            csl_item["DOI"] = paper.doi

        # URL
        if paper.url:
            csl_item["URL"] = paper.url

        # Abstract
        if paper.abstract:
            csl_item["abstract"] = paper.abstract

        # Keywords
        if paper.keywords:
            if isinstance(paper.keywords, list):
                csl_item["keyword"] = paper.keywords
            else:
                csl_item["keyword"] = [paper.keywords]

        return csl_item

    def format_citations(
        self, papers: List[Paper], style: str = "ieee"
    ) -> List[Dict[str, Any]]:
        """
        Format papers using CSL style.

        Note: This converts papers to CSL JSON format. Actual rendering
        requires Pandoc with citeproc filter.

        Args:
            papers: List of Paper objects
            style: CSL style name (default: 'ieee')

        Returns:
            List of CSL JSON items
        """
        csl_items = []
        for paper in papers:
            csl_item = self.paper_to_csl(paper)
            csl_items.append(csl_item)

        return csl_items

    def export_csl_json(self, papers: List[Paper], output_path: Path) -> Path:
        """
        Export papers as CSL JSON file.

        Args:
            papers: List of Paper objects
            output_path: Path to output JSON file

        Returns:
            Path to generated JSON file
        """
        csl_items = self.format_citations(papers)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(csl_items, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(csl_items)} citations to CSL JSON: {output_path}")
        return output_path
