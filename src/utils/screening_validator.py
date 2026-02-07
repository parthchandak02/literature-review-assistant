"""
Screening Validation Module

Validates screening decisions and provides statistics and calibration tools.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ScreeningStage(Enum):
    """Screening stages."""

    TITLE_ABSTRACT = "title_abstract"
    FULL_TEXT = "full_text"


@dataclass
class ScreeningStatistics:
    """Statistics for screening decisions."""

    total_papers: int
    included: int
    excluded: int
    uncertain: int
    inclusion_rate: float
    exclusion_rate: float
    exclusion_reasons: Dict[str, int]


class ScreeningValidator:
    """Validates screening decisions and provides statistics."""

    def __init__(self):
        """Initialize validator."""
        self.stats_by_stage: Dict[ScreeningStage, ScreeningStatistics] = {}
        self.exclusion_reasons_by_stage: Dict[ScreeningStage, Dict[str, int]] = {}

    def calculate_statistics(
        self,
        papers: List[Any],
        screening_results: List[Any],
        stage: ScreeningStage,
    ) -> ScreeningStatistics:
        """
        Calculate screening statistics.

        Args:
            papers: List of papers
            screening_results: List of screening results (with decision, exclusion_reason)
            stage: Screening stage

        Returns:
            ScreeningStatistics object
        """
        total = len(papers)
        included = sum(1 for r in screening_results if r.decision.value == "include")
        excluded = sum(1 for r in screening_results if r.decision.value == "exclude")
        uncertain = sum(1 for r in screening_results if r.decision.value == "uncertain")

        inclusion_rate = included / total if total > 0 else 0.0
        exclusion_rate = excluded / total if total > 0 else 0.0

        # Count exclusion reasons
        exclusion_reasons = {}
        for result in screening_results:
            if result.exclusion_reason:
                reason = result.exclusion_reason
                exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1

        stats = ScreeningStatistics(
            total_papers=total,
            included=included,
            excluded=excluded,
            uncertain=uncertain,
            inclusion_rate=inclusion_rate,
            exclusion_rate=exclusion_rate,
            exclusion_reasons=exclusion_reasons,
        )

        self.stats_by_stage[stage] = stats
        self.exclusion_reasons_by_stage[stage] = exclusion_reasons

        return stats

    def validate_exclusion_rate(
        self,
        stage: ScreeningStage,
        warning_threshold: float = 0.90,
        critical_threshold: float = 0.95,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate exclusion rate is reasonable.

        Args:
            stage: Screening stage
            warning_threshold: Warning threshold for exclusion rate (default: 90%)
            critical_threshold: Critical threshold for exclusion rate (default: 95%)

        Returns:
            Tuple of (is_valid, warning_message)
        """
        if stage not in self.stats_by_stage:
            return True, None

        stats = self.stats_by_stage[stage]
        exclusion_rate = stats.exclusion_rate

        if exclusion_rate >= critical_threshold:
            return False, (
                f"CRITICAL: Exclusion rate at {stage.value} stage is {exclusion_rate:.1%} "
                f"(>= {critical_threshold:.1%}). This suggests inclusion criteria may be too strict "
                f"or exclusion criteria too broad. Consider reviewing screening criteria."
            )
        elif exclusion_rate >= warning_threshold:
            return True, (
                f"WARNING: Exclusion rate at {stage.value} stage is {exclusion_rate:.1%} "
                f"(>= {warning_threshold:.1%}). This is unusually high. Consider reviewing "
                f"screening criteria if this is unexpected."
            )

        return True, None

    def validate_inclusion_rate(
        self,
        stage: ScreeningStage,
        warning_threshold: float = 0.10,
        critical_threshold: float = 0.05,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate inclusion rate is reasonable.

        Args:
            stage: Screening stage
            warning_threshold: Warning threshold for inclusion rate (default: 10%)
            critical_threshold: Critical threshold for inclusion rate (default: 5%)

        Returns:
            Tuple of (is_valid, warning_message)
        """
        if stage not in self.stats_by_stage:
            return True, None

        stats = self.stats_by_stage[stage]
        inclusion_rate = stats.inclusion_rate

        if inclusion_rate <= critical_threshold:
            return False, (
                f"CRITICAL: Inclusion rate at {stage.value} stage is {inclusion_rate:.1%} "
                f"(<= {critical_threshold:.1%}). This suggests inclusion criteria may be too strict. "
                f"Consider reviewing screening criteria."
            )
        elif inclusion_rate <= warning_threshold:
            return True, (
                f"WARNING: Inclusion rate at {stage.value} stage is {inclusion_rate:.1%} "
                f"(<= {warning_threshold:.1%}). This is unusually low. Consider reviewing "
                f"screening criteria if this is unexpected."
            )

        return True, None

    def get_summary_report(self) -> str:
        """
        Generate summary report of screening statistics.

        Returns:
            Formatted report string
        """
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("SCREENING STATISTICS SUMMARY")
        report_lines.append("=" * 60)

        for stage in ScreeningStage:
            if stage in self.stats_by_stage:
                stats = self.stats_by_stage[stage]
                report_lines.append(f"\n{stage.value.upper().replace('_', ' ')} STAGE:")
                report_lines.append(f"  Total papers: {stats.total_papers}")
                report_lines.append(f"  Included: {stats.included} ({stats.inclusion_rate:.1%})")
                report_lines.append(f"  Excluded: {stats.excluded} ({stats.exclusion_rate:.1%})")
                report_lines.append(f"  Uncertain: {stats.uncertain}")

                if stats.exclusion_reasons:
                    report_lines.append("\n  Exclusion Reasons:")
                    for reason, count in sorted(
                        stats.exclusion_reasons.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:5]:  # Top 5 reasons
                        report_lines.append(f"    - {reason}: {count}")

                # Validation warnings
                is_valid, warning = self.validate_exclusion_rate(stage)
                if warning:
                    report_lines.append(f"\n  VALIDATION: {warning}")

                _is_valid, warning = self.validate_inclusion_rate(stage)
                if warning:
                    report_lines.append(f"\n  VALIDATION: {warning}")

        report_lines.append("\n" + "=" * 60)
        return "\n".join(report_lines)

    def log_statistics(self, stage: ScreeningStage):
        """
        Log screening statistics.

        Args:
            stage: Screening stage
        """
        if stage not in self.stats_by_stage:
            return

        stats = self.stats_by_stage[stage]
        logger.info(f"Screening statistics for {stage.value}:")
        logger.info(f"  Total: {stats.total_papers}")
        logger.info(f"  Included: {stats.included} ({stats.inclusion_rate:.1%})")
        logger.info(f"  Excluded: {stats.excluded} ({stats.exclusion_rate:.1%})")
        logger.info(f"  Uncertain: {stats.uncertain}")

        # Validation warnings
        is_valid, warning = self.validate_exclusion_rate(stage)
        if warning:
            logger.warning(warning)

        _is_valid, warning = self.validate_inclusion_rate(stage)
        if warning:
            logger.warning(warning)
