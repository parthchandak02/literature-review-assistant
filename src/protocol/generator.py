"""PROSPERO-format protocol generator."""

from __future__ import annotations

from pathlib import Path

from src.models import ProtocolDocument, ReviewConfig

# Mapping from review_type enum value to a PROSPERO-appropriate study design description.
# PROSPERO item 21 asks for the types of *primary* studies to be included, not the review type itself.
_STUDY_DESIGN_DESCRIPTIONS: dict[str, str] = {
    "systematic": (
        "Non-randomized studies, cohort studies, cross-sectional studies, "
        "quasi-experimental designs, observational studies, and usability evaluations"
    ),
    "scoping": (
        "Any study design including systematic reviews, randomized and non-randomized "
        "trials, observational studies, surveys, and grey literature"
    ),
    "meta_analysis": (
        "Randomized controlled trials and non-randomized studies with quantitative "
        "outcome data suitable for statistical pooling"
    ),
    "narrative": (
        "Any study design including experimental, observational, qualitative, "
        "and mixed-methods studies"
    ),
}


class ProtocolGenerator:
    def __init__(self, output_dir: str = "runs"):
        self.output_dir = Path(output_dir)

    def generate(self, workflow_id: str, config: ReviewConfig) -> ProtocolDocument:
        return ProtocolDocument(
            workflow_id=workflow_id,
            research_question=config.research_question,
            pico=config.pico,
            eligibility_criteria=config.inclusion_criteria + config.exclusion_criteria,
            planned_databases=config.target_databases,
            planned_screening_method="Dual AI reviewer with adjudication",
            planned_rob_tools=["rob2", "robins_i", "casp"],
            planned_synthesis_method="Meta-analysis when feasible; otherwise narrative synthesis",
            prospero_id=config.protocol.registration_number or None,
        )

    def render_markdown(self, protocol: ProtocolDocument, config: ReviewConfig) -> str:
        sections: list[tuple[str, str]] = [
            ("1. Review title", config.research_question),
            ("2. Original language title", config.research_question),
            ("3. Anticipated start date", "TBD"),
            ("4. Anticipated completion date", "TBD"),
            ("5. Stage of review at time of registration", "Started"),
            ("6. Named contact", "TBD"),
            ("7. Named contact email", "TBD"),
            ("8. Named contact address", "TBD"),
            ("9. Named contact phone", "TBD"),
            ("10. Organisational affiliation", "TBD"),
            ("11. Review team members and affiliations", "TBD"),
            ("12. Funding sources/sponsors", config.funding.source),
            ("13. Conflicts of interest", config.conflicts_of_interest),
            ("14. Review question", protocol.research_question),
            ("15. Searches", ", ".join(protocol.planned_databases)),
            ("16. URL to search strategy", "doc_search_strategies_appendix.md"),
            ("17. Condition/domain being studied", config.domain),
            ("18. Participants/population", config.pico.population),
            ("19. Intervention(s), exposure(s)", config.pico.intervention),
            ("20. Comparator(s)/control", config.pico.comparison),
            (
                "21. Types of study to be included",
                _STUDY_DESIGN_DESCRIPTIONS.get(
                    config.review_type.value,
                    f"Primary studies appropriate for a {config.review_type.value} review",
                ),
            ),
            ("22. Context", config.scope),
        ]
        lines = ["# PROSPERO Protocol Draft", ""]
        for header, body in sections:
            lines.append(f"## {header}")
            lines.append(body)
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def write_markdown(self, workflow_id: str, markdown_text: str) -> Path:
        _ = workflow_id  # Reserved for backward-compatible method signature.
        out_dir = self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / "doc_protocol.md"
        output_path.write_text(markdown_text, encoding="utf-8")
        return output_path
