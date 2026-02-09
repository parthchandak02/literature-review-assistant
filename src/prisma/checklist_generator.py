"""
PRISMA 2020 Checklist Generator

Generates PRISMA 2020 checklist file marking items as present/absent.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PRISMAChecklistGenerator:
    """Generates PRISMA 2020 checklist file."""

    def __init__(self):
        """Initialize checklist generator."""
        self.checklist_items = self._load_checklist_template()

    def _load_checklist_template(self) -> List[Dict[str, Any]]:
        """Load PRISMA 2020 checklist template."""
        return [
            {
                "item": 1,
                "section": "Title",
                "description": "Identify the report as a systematic review",
            },
            {
                "item": 2,
                "section": "Abstract",
                "description": "See PRISMA 2020 for Abstracts checklist",
            },
            {
                "item": 3,
                "section": "Introduction",
                "description": "Describe the rationale for the review",
            },
            {
                "item": 4,
                "section": "Introduction",
                "description": "Provide explicit statement of objectives",
            },
            {
                "item": 5,
                "section": "Methods",
                "description": "Specify inclusion and exclusion criteria",
            },
            {
                "item": 6,
                "section": "Methods",
                "description": "Specify all databases and sources searched",
            },
            {"item": 7, "section": "Methods", "description": "Present full search strategies"},
            {"item": 8, "section": "Methods", "description": "Specify methods for study selection"},
            {"item": 9, "section": "Methods", "description": "Specify methods for data collection"},
            {
                "item": 10,
                "section": "Methods",
                "description": "List and define outcomes and variables",
            },
            {
                "item": 11,
                "section": "Methods",
                "description": "Specify methods for risk of bias assessment",
            },
            {"item": 12, "section": "Methods", "description": "Specify effect measures"},
            {"item": 13, "section": "Methods", "description": "Describe synthesis methods"},
            {
                "item": 14,
                "section": "Methods",
                "description": "Describe methods for assessing reporting bias",
            },
            {
                "item": 15,
                "section": "Methods",
                "description": "Describe methods for assessing certainty",
            },
            {
                "item": 16,
                "section": "Results",
                "description": "Describe results of search and selection",
            },
            {
                "item": 17,
                "section": "Results",
                "description": "Cite each included study and present characteristics",
            },
            {"item": 18, "section": "Results", "description": "Present risk of bias assessments"},
            {"item": 19, "section": "Results", "description": "Present results for each study"},
            {"item": 20, "section": "Results", "description": "Present results of syntheses"},
            {
                "item": 21,
                "section": "Results",
                "description": "Present assessments of reporting biases",
            },
            {"item": 22, "section": "Results", "description": "Present assessments of certainty"},
            {"item": 23, "section": "Discussion", "description": "Provide general interpretation"},
            {"item": 24, "section": "Other", "description": "Provide registration information"},
            {"item": 25, "section": "Other", "description": "Describe sources of support"},
            {"item": 26, "section": "Other", "description": "Declare competing interests"},
            {"item": 27, "section": "Other", "description": "Report data availability"},
        ]

    def generate_checklist(self, report_content: str, output_path: str) -> str:
        """
        Generate PRISMA checklist file from report content.

        Args:
            report_content: Content of the generated report
            output_path: Path to save checklist file

        Returns:
            Path to generated checklist file
        """
        checklist = {
            "prisma_version": "2020",
            "report_title": self._extract_title(report_content),
            "items": [],
        }

        # Check each item
        for item_info in self.checklist_items:
            item_num = item_info["item"]
            description = item_info["description"]
            section = item_info["section"]

            is_present = self._check_item(report_content, item_num, description, section)
            page_number = self._find_page_number(report_content, section)

            checklist["items"].append(
                {
                    "item": item_num,
                    "section": section,
                    "description": description,
                    "reported": "Yes" if is_present else "No",
                    "page_number": page_number if page_number else "N/A",
                }
            )

        # Save checklist
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path_obj, "w") as f:
            json.dump(checklist, f, indent=2)

        logger.info(f"PRISMA checklist generated at {output_path_obj}")
        return str(output_path_obj)

    def _extract_title(self, content: str) -> str:
        """Extract title from report."""
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip()
        return "Systematic Review Report"

    def _check_item(self, content: str, item_num: int, description: str, section: str) -> bool:
        """Check if a PRISMA item is present in the report."""
        content_lower = content.lower()

        # Item-specific checks
        if item_num == 1:
            return bool(re.search(r"systematic\s+review", content_lower))
        elif item_num == 2:
            return bool(re.search(r"##\s+abstract", content_lower))
        elif item_num == 4:
            return bool(re.search(r"objectives?|objectives?\s+of\s+this\s+review", content_lower))
        elif item_num == 5:
            return bool(re.search(r"inclusion|exclusion|eligibility\s+criteria", content_lower))
        elif item_num == 6:
            return bool(re.search(r"database|PubMed|Scopus|search\s+sources?", content_lower))
        elif item_num == 7:
            return bool(re.search(r"search\s+strategy|search\s+query", content_lower))
        elif item_num == 11:
            return bool(re.search(r"risk\s+of\s+bias|quality\s+assessment", content_lower))
        elif item_num == 15:
            return bool(re.search(r"GRADE|certainty|confidence\s+in\s+evidence", content_lower))
        elif item_num == 17:
            return bool(
                re.search(
                    r"study\s+characteristics|characteristics\s+of\s+included\s+studies",
                    content_lower,
                )
            )
        elif item_num == 18:
            return bool(
                re.search(
                    r"risk\s+of\s+bias.*results?|quality\s+assessment.*results?", content_lower
                )
            )
        elif item_num == 22:
            return bool(re.search(r"GRADE.*results?|certainty.*results?", content_lower))
        elif item_num == 24:
            return bool(re.search(r"PROSPERO|registration|protocol\s+registered", content_lower))
        elif item_num == 25:
            return bool(re.search(r"funding|financial\s+support", content_lower))
        elif item_num == 26:
            return bool(
                re.search(r"conflicts?\s+of\s+interest|competing\s+interests", content_lower)
            )
        elif item_num == 27:
            return bool(re.search(r"data\s+availability|supplementary\s+materials", content_lower))

        # Generic section check
        section_patterns = {
            "Introduction": r"##\s+introduction",
            "Methods": r"##\s+methods",
            "Results": r"##\s+results",
            "Discussion": r"##\s+discussion",
            "Other": r"##\s+(funding|conflicts|data\s+availability)",
        }

        if section in section_patterns:
            return bool(re.search(section_patterns[section], content_lower, re.IGNORECASE))

        return False

    def _find_page_number(self, content: str, section: str) -> Optional[int]:
        """Find approximate page number for a section (markdown doesn't have pages, return None)."""
        # Markdown doesn't have page numbers, but we can estimate based on line numbers
        section_match = re.search(rf"##\s+{section}", content, re.IGNORECASE)
        if section_match:
            line_number = content[: section_match.start()].count("\n") + 1
            # Approximate: ~50 lines per page
            return (line_number // 50) + 1
        return None
