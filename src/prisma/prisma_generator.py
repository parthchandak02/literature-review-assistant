"""
PRISMA Flow Diagram Generator

Wrapper around prisma-flow-diagram package that tracks study counts
through the workflow and generates PRISMA 2020-compliant diagrams.
"""

from typing import Dict, Optional, Any, List
from pathlib import Path
import logging
from ..utils.rich_utils import console
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)


class PRISMACounter:
    """Tracks study counts through the systematic review workflow."""

    def __init__(self):
        self.counts = {
            "found": 0,
            "found_other": 0,
            "no_dupes": 0,
            "screened": 0,
            "screen_exclusions": 0,
            "full_text_sought": 0,  # Papers that passed title/abstract screening (sought for full-text)
            "full_text_not_retrieved": 0,  # Papers where full-text was unavailable
            "full_text_assessed": 0,  # Papers that underwent full-text screening
            "full_text_exclusions": 0,
            "qualitative": 0,
            "quantitative": 0,
        }
        self.database_breakdown = {}  # e.g., {'Scopus': 133, 'WoS': 160, 'PubMed': 72}

    def set_found(self, count: int, database_breakdown: Optional[Dict[str, int]] = None):
        """Set total records identified through database searching."""
        self.counts["found"] = count
        if database_breakdown:
            self.database_breakdown = database_breakdown

    def set_found_other(self, count: int):
        """Set additional records from other sources."""
        self.counts["found_other"] = count

    def set_no_dupes(self, count: int):
        """Set records after duplicates removed."""
        self.counts["no_dupes"] = count

    def set_screened(self, count: int):
        """Set records screened."""
        self.counts["screened"] = count

    def set_screen_exclusions(self, count: int):
        """Set records excluded at title/abstract screening."""
        self.counts["screen_exclusions"] = count

    def set_full_text_sought(self, count: int):
        """Set full-text articles sought (papers that passed title/abstract screening)."""
        self.counts["full_text_sought"] = count

    def set_full_text_not_retrieved(self, count: int):
        """Set full-text articles not retrieved (unavailable)."""
        self.counts["full_text_not_retrieved"] = count

    def set_full_text_assessed(self, count: int):
        """Set full-text articles assessed (actually screened)."""
        self.counts["full_text_assessed"] = count

    def set_full_text_exclusions(self, count: int):
        """Set full-text articles excluded."""
        self.counts["full_text_exclusions"] = count
    
    # Backward compatibility
    def set_full_text(self, count: int):
        """Set full-text articles assessed (for backward compatibility)."""
        self.set_full_text_assessed(count)

    def set_qualitative(self, count: int):
        """Set studies included in qualitative synthesis."""
        self.counts["qualitative"] = count

    def set_quantitative(self, count: int):
        """Set studies included in quantitative synthesis."""
        self.counts["quantitative"] = count

    def get_counts(self) -> Dict[str, int]:
        """Get current counts dictionary."""
        return self.counts.copy()

    def get_database_breakdown(self) -> Dict[str, int]:
        """Get database breakdown."""
        return self.database_breakdown.copy()


class PRISMAGenerator:
    """Generates PRISMA 2020-compliant flow diagrams."""

    def __init__(self, counter: Optional[PRISMACounter] = None):
        self.counter = counter or PRISMACounter()
        try:
            from prisma_flow_diagram.prisma import plot_prisma2020_new

            self.has_library = True
            self.plot_prisma2020_new = plot_prisma2020_new
        except ImportError as e:
            self.has_library = False
            print(
                f"Warning: prisma-flow-diagram not available ({e}). Using fallback matplotlib generator."
            )

    def generate(self, output_path: str, format: str = "png", interactive: bool = False) -> str:
        """
        Generate PRISMA flow diagram.

        Args:
            output_path: Path to save the diagram
            format: Output format ('png', 'svg', 'pdf')
            interactive: Whether to generate interactive HTML (if supported)

        Returns:
            Path to generated diagram
        """
        counts = self.counter.get_counts()

        if self.has_library:
            return self._generate_with_library(counts, output_path, format, interactive)
        else:
            return self._generate_fallback(counts, output_path, format)

    def _map_counts_to_library_format(self, counts: Dict[str, int]) -> tuple[Dict[str, Any], Dict[str, int]]:
        """
        Map PRISMACounter counts to the library's expected format.
        
        Returns:
            Tuple of (db_registers dict, included dict)
        """
        # Calculate duplicates removed
        duplicates_removed = counts.get("found", 0) - counts.get("no_dupes", 0)
        
        # Get database breakdown - can be dict or total count
        db_breakdown = self.counter.get_database_breakdown()
        if db_breakdown:
            databases_value = db_breakdown  # Library accepts dict for breakdown
        else:
            databases_value = counts.get("found", 0)  # Or total count
        
        # Map to library format
        db_registers = {
            "identification": {
                "databases": databases_value,
                # "registers": 0  # Optional, omit if not used
            },
            "removed_before_screening": {
                "duplicates": duplicates_removed,
                "automation": 0,  # Not currently tracked
                "other": 0,  # Not currently tracked
            },
            "records": {
                "screened": counts.get("screened", 0),
                "excluded": counts.get("screen_exclusions", 0),
            },
            "reports": {
                "sought": counts.get("full_text_sought", counts.get("full_text", 0)),
                "not_retrieved": counts.get("full_text_not_retrieved", 0),
                # Assessed should be all papers evaluated (with or without full-text)
                # Fallback: if not explicitly set, calculate from sought - not_retrieved
                "assessed": counts.get(
                    "full_text_assessed",
                    counts.get("full_text_sought", counts.get("full_text", 0))
                    - counts.get("full_text_not_retrieved", 0)
                ),
                "excluded_reasons": {
                    "Not eligible": counts.get("full_text_exclusions", 0),
                },
            },
        }
        
        # Included studies - use qualitative if available, otherwise quantitative
        included_studies = counts.get("qualitative", 0) or counts.get("quantitative", 0)
        included = {
            "studies": included_studies,
            "reports": included_studies,  # Assuming one report per study
        }
        
        return db_registers, included

    def _validate_prisma_counts(self, counts: Dict[str, int]) -> tuple[bool, List[str]]:
        """
        Validate PRISMA counts are consistent.
        
        Returns:
            Tuple of (is_valid, list of warnings/errors)
        """
        warnings = []
        
        # Get key counts
        sought = counts.get("full_text_sought", 0)
        not_retrieved = counts.get("full_text_not_retrieved", 0)
        assessed = counts.get("full_text_assessed", 0)
        counts.get("full_text_exclusions", 0)
        included = counts.get("qualitative", 0) or counts.get("quantitative", 0)
        
        # Validation rule 1: assessed should not exceed sought
        # (all papers that were sought for full-text assessment)
        if assessed > sought:
            warnings.append(
                f"Assessed ({assessed}) exceeds sought ({sought}). "
                f"This violates PRISMA rules: assessed <= sought."
            )
        
        # Validation rule 2: assessed should be at least sought - not_retrieved
        # (minimum: all papers with full-text available should be assessed)
        min_assessable = max(0, sought - not_retrieved)
        if assessed < min_assessable:
            warnings.append(
                f"Assessed ({assessed}) is less than minimum assessable ({min_assessable}). "
                f"At minimum, all papers with full-text ({sought} - {not_retrieved} = {min_assessable}) "
                f"should be assessed."
            )
        
        # Validation rule 3: included should not exceed assessed
        if included > assessed:
            warnings.append(
                f"Included ({included}) exceeds assessed ({assessed}). "
                f"This violates PRISMA rules: included <= assessed. "
                f"This may indicate a data consistency issue - all included papers must have been assessed."
            )
            # Auto-fix: set assessed to at least included if it's less
            # BUT: ensure this doesn't violate the relationship with sought and not_retrieved
            # If assessed would exceed sought, we need to adjust not_retrieved instead
            if assessed < included:
                # Check if we can safely increase assessed without violating sought relationship
                # If assessed = sought, then all papers were assessed (including those without full-text)
                # If assessed < sought, we can increase it up to sought
                max_assessed = sought  # Can't assess more than sought
                if included <= max_assessed:
                    # Log auto-correction (less critical, use dim style)
                    console.print(
                        f"[dim yellow]Auto-correcting PRISMA counts: assessed ({assessed}) < included ({included}). "
                        f"Setting assessed to {included}.[/dim yellow]"
                    )
                    assessed = included
                    counts["full_text_assessed"] = included
                else:
                    # If included > sought, there's a data consistency issue
                    warnings.append(
                        f"Cannot auto-correct: included ({included}) > sought ({sought}). "
                        f"This indicates a serious data consistency issue."
                    )
        
        # Validation rule 4: Check relationship between sought, assessed, and not_retrieved
        # According to PRISMA 2020:
        # - If all papers are assessed (including those without full-text): assessed = sought
        # - If only papers with full-text are assessed: assessed = sought - not_retrieved
        # - The relationship: sought >= assessed >= (sought - not_retrieved)
        
        # Check if assessed + not_retrieved exceeds sought (indicates double-counting)
        if assessed + not_retrieved > sought:
            warnings.append(
                f"Sought split mismatch: assessed ({assessed}) + not_retrieved ({not_retrieved}) = "
                f"{assessed + not_retrieved} > sought ({sought}). "
                f"This violates PRISMA rules. "
                f"Fix: Adjust one of: reports.sought, reports.assessed, reports.not_retrieved so they add up consistently. "
                f"Rule: Typically: db_registers.reports.sought = db_registers.reports.assessed + db_registers.reports.not_retrieved "
                f"(and likewise for other_methods.* if provided)."
            )
        
        # Check if assessed is within valid range
        min_assessable = max(0, sought - not_retrieved)  # Minimum: papers with full-text
        max_assessable = sought  # Maximum: all papers
        if assessed < min_assessable or assessed > max_assessable:
            warnings.append(
                f"Assessed count ({assessed}) is outside valid range [{min_assessable}, {max_assessable}]. "
                f"Sought: {sought}, Not retrieved: {not_retrieved}. "
                f"Note: Papers without full-text may still be assessed using title/abstract."
            )
        
        is_valid = len(warnings) == 0
        return is_valid, warnings

    def _generate_with_library(
        self, counts: Dict[str, int], output_path: str, format: str, interactive: bool
    ) -> str:
        """Generate using prisma-flow-diagram library."""
        try:
            # Validate PRISMA counts before generating
            is_valid, warnings = self._validate_prisma_counts(counts)
            if warnings:
                # Format warnings with Rich for better visibility
                warning_text = Text()
                warning_text.append("PRISMA Validation Warnings\n", style="bold yellow")
                warning_text.append("\n")
                for i, warning in enumerate(warnings, 1):
                    warning_text.append(f"{i}. ", style="yellow")
                    warning_text.append(warning, style="yellow")
                    if i < len(warnings):
                        warning_text.append("\n\n")
                
                console.print()
                console.print(
                    Panel(
                        warning_text,
                        title="[bold yellow]PRISMA Validation[/bold yellow]",
                        border_style="yellow",
                        padding=(1, 2),
                    )
                )
                console.print()
            
            db_registers, included = self._map_counts_to_library_format(counts)
            
            # Call the library function
            self.plot_prisma2020_new(
                db_registers=db_registers,
                included=included,
                other_methods=None,  # Not currently supported
                filename=str(output_path),
                show=False,
                figsize=(14, 10),
            )
            return output_path
        except Exception as e:
            print(f"Error generating with library: {e}")
            print("Falling back to matplotlib generator...")
            import traceback
            traceback.print_exc()
            return self._generate_fallback(counts, output_path, format)

    def _generate_fallback(self, counts: Dict[str, int], output_path: str, format: str) -> str:
        """Fallback matplotlib-based PRISMA diagram generator."""
        import matplotlib.pyplot as plt

        # Increased figure size for better quality
        fig, ax = plt.subplots(1, 1, figsize=(16, 20))
        ax.set_xlim(0, 12)
        ax.set_ylim(0, 20)
        ax.axis("off")

        # Better colors
        box_color = "#E8F4F8"
        arrow_color = "#2C3E50"

        # Larger box dimensions
        box_width = 3.5
        box_height = 1.0
        arrow_length = 0.4

        y_positions = {
            "identification": 18,
            "after_dupes": 15,
            "screening": 12,
            "eligible": 9,
            "full_text": 6,
            "included": 3,
        }

        x_left = 2
        x_right = 8

        # Identification box
        found_text = f"Records identified through database searching\n{counts['found']}"
        if self.counter.database_breakdown:
            db_list = ", ".join([f"{k}-{v}" for k, v in self.counter.database_breakdown.items()])
            found_text += f"\n({db_list})"

        self._draw_box(
            ax,
            x_left,
            y_positions["identification"],
            box_width,
            box_height * 1.8,
            found_text,
            box_color,
            fontsize=10,
        )

        # Other sources box (if any)
        if counts["found_other"] > 0:
            other_text = f"Additional records from other sources\n{counts['found_other']}"
            self._draw_box(
                ax,
                x_right,
                y_positions["identification"],
                box_width,
                box_height * 1.2,
                other_text,
                box_color,
                fontsize=10,
            )
            # Arrow from other sources
            ax.arrow(
                x_right + box_width / 2,
                y_positions["identification"] - box_height * 0.6,
                0,
                -arrow_length,
                head_width=0.15,
                head_length=0.15,
                fc=arrow_color,
                ec=arrow_color,
                lw=2,
            )

        # After duplicates
        dupes_text = f"Records after duplicates removed\n{counts['no_dupes']}"
        self._draw_box(
            ax,
            x_left,
            y_positions["after_dupes"],
            box_width,
            box_height * 1.2,
            dupes_text,
            box_color,
            fontsize=10,
        )
        ax.arrow(
            x_left + box_width / 2,
            y_positions["identification"] - box_height * 0.9,
            0,
            -arrow_length,
            head_width=0.15,
            head_length=0.15,
            fc=arrow_color,
            ec=arrow_color,
            lw=2,
        )

        # Exclusion box (right side)
        excl_text = f"Records excluded\n{counts['screen_exclusions']}"
        self._draw_box(
            ax,
            x_right,
            y_positions["after_dupes"],
            box_width,
            box_height * 1.2,
            excl_text,
            box_color,
            fontsize=10,
        )
        ax.arrow(
            x_left + box_width,
            y_positions["after_dupes"],
            x_right - x_left,
            0,
            head_width=0.15,
            head_length=0.15,
            fc=arrow_color,
            ec=arrow_color,
            lw=2,
        )

        # Screened
        screened_text = f"Records screened\n{counts['screened']}"
        self._draw_box(
            ax,
            x_left,
            y_positions["screening"],
            box_width,
            box_height * 1.2,
            screened_text,
            box_color,
            fontsize=10,
        )
        ax.arrow(
            x_left + box_width / 2,
            y_positions["after_dupes"] - box_height * 0.6,
            0,
            -arrow_length,
            head_width=0.15,
            head_length=0.15,
            fc=arrow_color,
            ec=arrow_color,
            lw=2,
        )

        # Eligible (papers that passed title/abstract screening)
        # This should be "screened" count minus "screen_exclusions"
        eligible_count = counts.get("screened", 0) - counts.get("screen_exclusions", 0)
        eligible_text = f"Relevant/eligible studies\n{eligible_count}"
        self._draw_box(
            ax,
            x_left,
            y_positions["eligible"],
            box_width,
            box_height * 1.2,
            eligible_text,
            box_color,
            fontsize=10,
        )
        ax.arrow(
            x_left + box_width / 2,
            y_positions["screening"] - box_height * 0.6,
            0,
            -arrow_length,
            head_width=0.15,
            head_length=0.15,
            fc=arrow_color,
            ec=arrow_color,
            lw=2,
        )

        # Full-text sought and not retrieved
        sought_count = counts.get("full_text_sought", counts.get("full_text", 0))
        not_retrieved_count = counts.get("full_text_not_retrieved", 0)
        assessed_count = counts.get("full_text_assessed", sought_count - not_retrieved_count)
        
        if not_retrieved_count > 0:
            ft_sought_text = f"Full-text articles sought\n{sought_count}\n(Not retrieved: {not_retrieved_count})"
            self._draw_box(
                ax,
                x_left,
                y_positions["full_text"],
                box_width,
                box_height * 1.4,
                ft_sought_text,
                box_color,
                fontsize=10,
            )
            # Arrow from eligible to sought
            ax.arrow(
                x_left + box_width / 2,
                y_positions["eligible"] - box_height * 0.6,
                0,
                -arrow_length,
                head_width=0.15,
                head_length=0.15,
                fc=arrow_color,
                ec=arrow_color,
                lw=2,
            )
            # Arrow from sought to not retrieved
            ax.arrow(
                x_left + box_width,
                y_positions["full_text"],
                x_right - x_left,
                0,
                head_width=0.15,
                head_length=0.15,
                fc=arrow_color,
                ec=arrow_color,
                lw=2,
            )
            # Not retrieved box
            not_retrieved_text = f"Full-text articles not retrieved\n{not_retrieved_count}"
            self._draw_box(
                ax,
                x_right,
                y_positions["full_text"],
                box_width,
                box_height * 1.2,
                not_retrieved_text,
                box_color,
                fontsize=10,
            )
            # Assessed box (below sought)
            assessed_text = f"Full-text articles assessed\n{assessed_count}"
            y_assessed = y_positions["full_text"] - 2.5
            self._draw_box(
                ax,
                x_left,
                y_assessed,
                box_width,
                box_height * 1.2,
                assessed_text,
                box_color,
                fontsize=10,
            )
            ax.arrow(
                x_left + box_width / 2,
                y_positions["full_text"] - box_height * 0.7,
                0,
                -arrow_length,
                head_width=0.15,
                head_length=0.15,
                fc=arrow_color,
                ec=arrow_color,
                lw=2,
            )
            y_exclusion = y_assessed
        else:
            # No not-retrieved, simpler flow
            ft_sought_text = f"Full-text articles assessed\n{assessed_count}"
            self._draw_box(
                ax,
                x_left,
                y_positions["full_text"],
                box_width,
                box_height * 1.2,
                ft_sought_text,
                box_color,
                fontsize=10,
            )
            ax.arrow(
                x_left + box_width / 2,
                y_positions["eligible"] - box_height * 0.6,
                0,
                -arrow_length,
                head_width=0.15,
                head_length=0.15,
                fc=arrow_color,
                ec=arrow_color,
                lw=2,
            )
            y_exclusion = y_positions["full_text"]

        # Full-text exclusion
        ft_excl_text = f"Full-text articles excluded\n{counts['full_text_exclusions']}"
        self._draw_box(
            ax,
            x_right,
            y_exclusion,
            box_width,
            box_height * 1.2,
            ft_excl_text,
            box_color,
            fontsize=10,
        )
        ax.arrow(
            x_left + box_width,
            y_exclusion,
            x_right - x_left,
            0,
            head_width=0.15,
            head_length=0.15,
            fc=arrow_color,
            ec=arrow_color,
            lw=2,
        )

        # Included
        included_text = f"Studies included in synthesis\nQualitative: {counts['qualitative']}\nQuantitative: {counts['quantitative']}"
        self._draw_box(
            ax,
            x_left,
            y_positions["included"],
            box_width,
            box_height * 1.5,
            included_text,
            box_color,
            fontsize=10,
        )
        # Arrow from assessed to included (or from eligible if no assessed box)
        arrow_start_y = y_exclusion if not_retrieved_count > 0 else y_positions["eligible"]
        ax.arrow(
            x_left + box_width / 2,
            arrow_start_y - box_height * 0.6,
            0,
            -arrow_length,
            head_width=0.15,
            head_length=0.15,
            fc=arrow_color,
            ec=arrow_color,
            lw=2,
        )

        plt.title("PRISMA 2020 Flow Diagram", fontsize=16, fontweight="bold", pad=25)
        plt.tight_layout()

        # Save with higher DPI
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, format=format, dpi=400, bbox_inches="tight", facecolor="white")
        plt.close()

        return str(output_path)

    def _draw_box(self, ax, x, y, width, height, text, color, fontsize=10):
        """Draw a rounded box with properly wrapped text."""
        import textwrap
        from matplotlib.patches import FancyBboxPatch

        # Wrap text to fit in box (approximately 30 chars per line)
        max_chars_per_line = int(width * 4)  # Approximate chars per unit width
        wrapped_lines = []
        for line in text.split("\n"):
            if len(line) > max_chars_per_line:
                wrapped_lines.extend(textwrap.wrap(line, width=max_chars_per_line))
            else:
                wrapped_lines.append(line)

        wrapped_text = "\n".join(wrapped_lines)

        # Draw box with better styling
        box = FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0.15",
            facecolor=color,
            edgecolor="#2C3E50",
            linewidth=2.0,
            zorder=1,
        )
        ax.add_patch(box)

        # Draw text with better formatting
        ax.text(
            x,
            y,
            wrapped_text,
            ha="center",
            va="center",
            fontsize=fontsize,
            fontweight="normal",
            color="#2C3E50",
            zorder=2,
            family="sans-serif",
        )


def create_prisma_diagram(
    counts: Dict[str, int],
    output_path: str,
    database_breakdown: Optional[Dict[str, int]] = None,
) -> str:
    """
    Convenience function to create a PRISMA diagram.

    Args:
        counts: Dictionary with PRISMA counts
        output_path: Where to save the diagram
        database_breakdown: Optional breakdown by database

    Returns:
        Path to generated diagram
    """
    counter = PRISMACounter()
    counter.counts.update(counts)
    if database_breakdown:
        counter.database_breakdown = database_breakdown

    generator = PRISMAGenerator(counter)
    return generator.generate(output_path)
