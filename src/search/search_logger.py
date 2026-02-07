"""
PRISMA-compliant search logging and documentation generation.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database_connectors import Paper
from .search_strategy import SearchStrategyBuilder

logger = logging.getLogger(__name__)


class SearchLogger:
    """
    Logs search activities for PRISMA compliance.

    Implements PRISMA-S (PRISMA-Search) extension for documenting
    literature searches in systematic reviews.
    """

    def __init__(self, output_dir: Optional[str] = None):
        """
        Initialize search logger.

        Args:
            output_dir: Directory for search logs (default: data/outputs/search_logs)
        """
        if output_dir is None:
            output_dir = Path(__file__).parent.parent.parent / "data" / "outputs" / "search_logs"

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.search_history: List[Dict[str, Any]] = []
        self.current_search: Optional[Dict[str, Any]] = None

    def start_search(
        self,
        query: str,
        database: str,
        search_strategy: Optional[SearchStrategyBuilder] = None,
        max_results: int = 100,
    ):
        """
        Start logging a new search.

        Args:
            query: Search query string
            database: Database name
            search_strategy: Search strategy builder (optional)
            max_results: Maximum results requested
        """
        self.current_search = {
            "query": query,
            "database": database,
            "search_strategy": search_strategy.get_strategy_description()
            if search_strategy
            else None,
            "max_results": max_results,
            "start_time": datetime.now().isoformat(),
            "results": [],
            "total_found": 0,
            "errors": [],
        }

    def log_result(self, papers: List[Paper], error: Optional[Exception] = None):
        """
        Log search results.

        Args:
            papers: List of Paper objects found
            error: Exception if search failed (optional)
        """
        if not self.current_search:
            logger.warning("No active search to log results for")
            return

        if error:
            self.current_search["errors"].append(
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        else:
            self.current_search["results"] = [
                {
                    "title": p.title,
                    "doi": p.doi,
                    "year": p.year,
                    "authors": p.authors,
                    "database": p.database,
                }
                for p in papers
            ]
            self.current_search["total_found"] = len(papers)

        self.current_search["end_time"] = datetime.now().isoformat()

    def finish_search(self):
        """Finish current search and add to history."""
        if self.current_search:
            self.search_history.append(self.current_search.copy())
            self.current_search = None

    def log_deduplication(
        self,
        total_before: int,
        total_after: int,
        duplicates_removed: int,
        method: str = "fuzzy_matching",
    ):
        """
        Log deduplication results.

        Args:
            total_before: Total papers before deduplication
            total_after: Total papers after deduplication
            duplicates_removed: Number of duplicates removed
            method: Deduplication method used
        """
        if not self.current_search:
            logger.warning("No active search to log deduplication for")
            return

        self.current_search["deduplication"] = {
            "total_before": total_before,
            "total_after": total_after,
            "duplicates_removed": duplicates_removed,
            "method": method,
            "timestamp": datetime.now().isoformat(),
        }

    def generate_prisma_report(self, filename: Optional[str] = None) -> Path:
        """
        Generate PRISMA-compliant search report.

        Args:
            filename: Output filename (default: prisma_search_report_YYYYMMDD.json)

        Returns:
            Path to generated report file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prisma_search_report_{timestamp}.json"

        report_path = self.output_dir / filename

        # PRISMA-S compliant report structure
        report = {
            "report_type": "PRISMA-S Search Report",
            "generated_at": datetime.now().isoformat(),
            "information_sources": self._generate_sources_section(),
            "search_strategies": self._generate_strategies_section(),
            "peer_review": {
                "peer_reviewed": False,  # Should be set by user
                "reviewer": None,
                "review_date": None,
            },
            "managing_records": self._generate_records_section(),
            "search_history": self.search_history,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"PRISMA report generated: {report_path}")
        return report_path

    def generate_search_summary_csv(self, filename: Optional[str] = None) -> Path:
        """
        Generate CSV summary of all searches.

        Args:
            filename: Output filename (default: search_summary_YYYYMMDD.csv)

        Returns:
            Path to generated CSV file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"search_summary_{timestamp}.csv"

        csv_path = self.output_dir / filename

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "database",
                "query",
                "start_time",
                "end_time",
                "total_found",
                "errors",
                "deduplication_before",
                "deduplication_after",
                "duplicates_removed",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for search in self.search_history:
                row = {
                    "database": search["database"],
                    "query": search["query"][:100],  # Truncate long queries
                    "start_time": search["start_time"],
                    "end_time": search.get("end_time", ""),
                    "total_found": search["total_found"],
                    "errors": len(search.get("errors", [])),
                    "deduplication_before": search.get("deduplication", {}).get("total_before", ""),
                    "deduplication_after": search.get("deduplication", {}).get("total_after", ""),
                    "duplicates_removed": search.get("deduplication", {}).get(
                        "duplicates_removed", ""
                    ),
                }
                writer.writerow(row)

        logger.info(f"Search summary CSV generated: {csv_path}")
        return csv_path

    def export_search_strategies(self, output_path: Optional[str] = None) -> Path:
        """
        Export all search strategies to a markdown file.

        Args:
            output_path: Optional output path (default: auto-generated)

        Returns:
            Path to exported search strategies file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"search_strategies_{timestamp}.md"
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Search Strategies\n\n")
            f.write(
                "This document contains the complete search strategies used for all databases.\n\n"
            )
            f.write("---\n\n")

            strategies = self._generate_strategies_section()

            for db_name, strategy_data in strategies.items():
                f.write(f"## {db_name}\n\n")
                f.write(f"**Search Date:** {strategy_data.get('search_date', 'Not specified')}\n\n")
                f.write(f"**Query:** {strategy_data.get('query', 'Not specified')}\n\n")

                full_strategy = strategy_data.get("full_search_strategy", "")
                if full_strategy:
                    f.write("**Full Search Strategy:**\n\n")
                    f.write("```\n")
                    f.write(full_strategy)
                    f.write("\n```\n\n")
                else:
                    f.write("**Full Search Strategy:** Not available\n\n")

                limits = strategy_data.get("limits", {})
                if limits.get("date_range") or limits.get("language"):
                    f.write("**Limits:**\n")
                    if limits.get("date_range"):
                        f.write(f"- Date range: {limits['date_range']}\n")
                    if limits.get("language"):
                        f.write(f"- Language: {limits['language']}\n")
                    f.write("\n")

                f.write("---\n\n")

        logger.info(f"Search strategies exported to {output_path}")
        return output_path

    def _generate_sources_section(self) -> Dict[str, Any]:
        """Generate PRISMA-S information sources section."""
        databases_searched = set()
        for search in self.search_history:
            databases_searched.add(search["database"])

        return {
            "databases_searched": sorted(databases_searched),
            "study_registries": [],  # Can be added if used
            "online_resources": [],  # Can be added if used
            "citation_searching": False,  # Can be enabled if used
            "contacts": False,  # Can be enabled if used
        }

    def _generate_strategies_section(self) -> Dict[str, Any]:
        """Generate PRISMA-S search strategies section."""
        strategies = {}

        for search in self.search_history:
            db = search["database"]
            if db not in strategies:
                strategies[db] = {
                    "full_search_strategy": search.get("search_strategy", ""),
                    "query": search["query"],
                    "limits": {
                        "date_range": None,  # Extract from search strategy if available
                        "language": None,
                        "other": None,
                    },
                    "search_filters": [],
                    "search_date": search["start_time"],
                }

        return strategies

    def _generate_records_section(self) -> Dict[str, Any]:
        """Generate PRISMA-S managing records section."""
        total_by_database = {}
        total_all = 0

        for search in self.search_history:
            db = search["database"]
            count = search["total_found"]
            total_by_database[db] = total_by_database.get(db, 0) + count
            total_all += count

        dedup_info = {}
        for search in self.search_history:
            if "deduplication" in search:
                dedup_info[search["database"]] = search["deduplication"]

        return {
            "total_records_by_database": total_by_database,
            "total_records_before_deduplication": total_all,
            "deduplication_method": "fuzzy_matching",  # Default, can be customized
            "deduplication_details": dedup_info,
            "total_records_after_deduplication": sum(
                d.get("total_after", 0) for d in dedup_info.values()
            ),
        }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get search statistics.

        Returns:
            Dictionary with search statistics
        """
        total_searches = len(self.search_history)
        total_results = sum(s["total_found"] for s in self.search_history)
        databases_used = {s["database"] for s in self.search_history}
        total_errors = sum(len(s.get("errors", [])) for s in self.search_history)

        return {
            "total_searches": total_searches,
            "total_results": total_results,
            "databases_used": sorted(databases_used),
            "total_errors": total_errors,
            "average_results_per_search": total_results / total_searches
            if total_searches > 0
            else 0,
        }
