#!/usr/bin/env python3
"""
Checkpoint Validation Script

Validates checkpoint files from workflow runs to ensure they can be loaded
and contain expected data structures.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.state_serialization import StateSerializer
from src.testing.stage_loader import StageLoader

console = Console()


class CheckpointValidator:
    """Validate checkpoint files."""

    def __init__(self):
        self.serializer = StateSerializer()
        self.loader = StageLoader()
        self.validation_results = []

    def list_checkpoints(self, workflow_dir: str) -> List[Path]:
        """List all checkpoint JSON files in workflow directory."""
        workflow_path = Path(workflow_dir)
        if not workflow_path.exists():
            return []
        
        checkpoints = list(workflow_path.glob("*_state.json"))
        return sorted(checkpoints)

    def validate_checkpoint_structure(self, checkpoint_path: Path) -> Dict[str, Any]:
        """Validate checkpoint JSON structure and required fields."""
        result = {
            "file": str(checkpoint_path),
            "valid_json": False,
            "has_required_fields": False,
            "errors": [],
            "warnings": [],
        }

        try:
            with open(checkpoint_path, "r") as f:
                data = json.load(f)
            result["valid_json"] = True
        except json.JSONDecodeError as e:
            result["errors"].append(f"Invalid JSON: {e}")
            return result
        except Exception as e:
            result["errors"].append(f"Failed to read file: {e}")
            return result

        # Check required fields
        required_fields = ["phase", "timestamp", "workflow_id", "data"]
        missing_fields = [field for field in required_fields if field not in data]
        
        if missing_fields:
            result["errors"].append(f"Missing required fields: {missing_fields}")
        else:
            result["has_required_fields"] = True

        # Check phase name matches filename
        phase_name = data.get("phase", "")
        expected_phase = checkpoint_path.stem.replace("_state", "")
        if phase_name != expected_phase:
            result["warnings"].append(
                f"Phase name mismatch: '{phase_name}' vs expected '{expected_phase}'"
            )

        return result

    def validate_checkpoint_data(self, checkpoint_path: Path, stage_name: str) -> Dict[str, Any]:
        """Validate checkpoint data can be deserialized."""
        result = {
            "file": str(checkpoint_path),
            "stage": stage_name,
            "deserialization_ok": False,
            "data_counts": {},
            "errors": [],
            "warnings": [],
        }

        try:
            data = self.loader._load_from_checkpoint(str(checkpoint_path), stage_name)
        except Exception as e:
            result["errors"].append(f"Failed to load checkpoint: {e}")
            return result

        phase_data = data.get("data", {})
        
        # Validate based on stage
        if stage_name == "search_databases":
            if "all_papers" in phase_data:
                try:
                    papers = self.serializer.deserialize_papers(phase_data["all_papers"])
                    result["data_counts"]["papers"] = len(papers)
                    result["deserialization_ok"] = True
                except Exception as e:
                    result["errors"].append(f"Failed to deserialize papers: {e}")
            else:
                result["errors"].append("Missing 'all_papers' field")

        elif stage_name == "deduplication":
            if "unique_papers" in phase_data:
                try:
                    papers = self.serializer.deserialize_papers(phase_data["unique_papers"])
                    result["data_counts"]["unique_papers"] = len(papers)
                    if "all_papers" in phase_data:
                        all_papers = self.serializer.deserialize_papers(phase_data["all_papers"])
                        result["data_counts"]["all_papers"] = len(all_papers)
                        if len(papers) > len(all_papers):
                            result["warnings"].append(
                                f"Unique papers ({len(papers)}) > all papers ({len(all_papers)})"
                            )
                    result["deserialization_ok"] = True
                except Exception as e:
                    result["errors"].append(f"Failed to deserialize papers: {e}")
            else:
                result["errors"].append("Missing 'unique_papers' field")

        elif stage_name == "title_abstract_screening":
            if "screened_papers" in phase_data:
                try:
                    papers = self.serializer.deserialize_papers(phase_data["screened_papers"])
                    result["data_counts"]["screened_papers"] = len(papers)
                    
                    if "title_abstract_results" in phase_data:
                        results = self.serializer.deserialize_screening_results(
                            phase_data["title_abstract_results"]
                        )
                        result["data_counts"]["results"] = len(results)
                        if len(papers) != len(results):
                            result["warnings"].append(
                                f"Paper count ({len(papers)}) != results count ({len(results)})"
                            )
                    
                    result["deserialization_ok"] = True
                except Exception as e:
                    result["errors"].append(f"Failed to deserialize: {e}")
            else:
                result["errors"].append("Missing 'screened_papers' field")

        elif stage_name == "fulltext_screening":
            if "eligible_papers" in phase_data:
                try:
                    papers = self.serializer.deserialize_papers(phase_data["eligible_papers"])
                    result["data_counts"]["eligible_papers"] = len(papers)
                    
                    if "screened_papers" in phase_data:
                        screened = self.serializer.deserialize_papers(phase_data["screened_papers"])
                        result["data_counts"]["screened_papers"] = len(screened)
                        if len(papers) > len(screened):
                            result["warnings"].append(
                                f"Eligible ({len(papers)}) > screened ({len(screened)})"
                            )
                    
                    if "fulltext_results" in phase_data:
                        results = self.serializer.deserialize_screening_results(
                            phase_data["fulltext_results"]
                        )
                        result["data_counts"]["results"] = len(results)
                    
                    # Check fulltext availability counts
                    if "fulltext_available_count" in phase_data:
                        result["data_counts"]["fulltext_available"] = phase_data["fulltext_available_count"]
                    if "fulltext_unavailable_count" in phase_data:
                        result["data_counts"]["fulltext_unavailable"] = phase_data["fulltext_unavailable_count"]
                    
                    result["deserialization_ok"] = True
                except Exception as e:
                    result["errors"].append(f"Failed to deserialize: {e}")
            else:
                result["errors"].append("Missing 'eligible_papers' field")

        elif stage_name == "data_extraction":
            if "extracted_data" in phase_data:
                try:
                    extracted = self.serializer.deserialize_extracted_data(phase_data["extracted_data"])
                    result["data_counts"]["extracted"] = len(extracted)
                    
                    if "final_papers" in phase_data:
                        papers = self.serializer.deserialize_papers(phase_data["final_papers"])
                        result["data_counts"]["final_papers"] = len(papers)
                        if len(extracted) != len(papers):
                            result["warnings"].append(
                                f"Extracted ({len(extracted)}) != final papers ({len(papers)})"
                            )
                    
                    result["deserialization_ok"] = True
                except Exception as e:
                    result["errors"].append(f"Failed to deserialize: {e}")
            else:
                result["errors"].append("Missing 'extracted_data' field")

        elif stage_name == "article_writing":
            if "article_sections" in phase_data:
                sections = phase_data["article_sections"]
                if isinstance(sections, dict):
                    result["data_counts"]["sections"] = len(sections)
                    expected_sections = ["introduction", "methods", "results", "discussion"]
                    missing_sections = [s for s in expected_sections if s not in sections]
                    if missing_sections:
                        result["warnings"].append(f"Missing sections: {missing_sections}")
                    result["deserialization_ok"] = True
                else:
                    result["errors"].append("'article_sections' should be a dictionary")
            else:
                result["errors"].append("Missing 'article_sections' field")

        return result

    def validate_stage_consistency(self, checkpoints: List[Path]) -> Dict[str, Any]:
        """Validate consistency between stages."""
        result = {
            "consistent": True,
            "errors": [],
            "warnings": [],
            "counts": {},
        }

        # Load all checkpoint data
        checkpoint_data = {}
        for checkpoint_path in checkpoints:
            stage_name = checkpoint_path.stem.replace("_state", "")
            try:
                data = self.loader._load_from_checkpoint(str(checkpoint_path), stage_name)
                checkpoint_data[stage_name] = data
            except Exception as e:
                result["errors"].append(f"Failed to load {stage_name}: {e}")
                continue

        # Extract counts for comparison
        serializer = StateSerializer()
        
        if "search_databases" in checkpoint_data:
            papers = serializer.deserialize_papers(
                checkpoint_data["search_databases"]["data"].get("all_papers", [])
            )
            result["counts"]["search"] = len(papers)

        if "deduplication" in checkpoint_data:
            unique = serializer.deserialize_papers(
                checkpoint_data["deduplication"]["data"].get("unique_papers", [])
            )
            result["counts"]["deduplication"] = len(unique)
            
            if "search_databases" in checkpoint_data:
                all_papers = serializer.deserialize_papers(
                    checkpoint_data["deduplication"]["data"].get("all_papers", [])
                )
                if len(unique) > len(all_papers):
                    result["errors"].append(
                        f"Deduplication: unique ({len(unique)}) > all ({len(all_papers)})"
                    )
                    result["consistent"] = False

        if "title_abstract_screening" in checkpoint_data:
            screened = serializer.deserialize_papers(
                checkpoint_data["title_abstract_screening"]["data"].get("screened_papers", [])
            )
            result["counts"]["title_screening"] = len(screened)
            
            if "deduplication" in checkpoint_data:
                unique = serializer.deserialize_papers(
                    checkpoint_data["deduplication"]["data"].get("unique_papers", [])
                )
                if len(screened) > len(unique):
                    result["warnings"].append(
                        f"Title screening: screened ({len(screened)}) > unique ({len(unique)})"
                    )

        if "fulltext_screening" in checkpoint_data:
            eligible = serializer.deserialize_papers(
                checkpoint_data["fulltext_screening"]["data"].get("eligible_papers", [])
            )
            result["counts"]["fulltext_screening"] = len(eligible)
            
            if "title_abstract_screening" in checkpoint_data:
                screened = serializer.deserialize_papers(
                    checkpoint_data["title_abstract_screening"]["data"].get("screened_papers", [])
                )
                if len(eligible) > len(screened):
                    result["errors"].append(
                        f"Fulltext: eligible ({len(eligible)}) > screened ({len(screened)})"
                    )
                    result["consistent"] = False

        if "data_extraction" in checkpoint_data:
            extracted = serializer.deserialize_extracted_data(
                checkpoint_data["data_extraction"]["data"].get("extracted_data", [])
            )
            result["counts"]["extraction"] = len(extracted)
            
            if "fulltext_screening" in checkpoint_data:
                eligible = serializer.deserialize_papers(
                    checkpoint_data["fulltext_screening"]["data"].get("eligible_papers", [])
                )
                if len(extracted) != len(eligible):
                    result["warnings"].append(
                        f"Extraction: extracted ({len(extracted)}) != eligible ({len(eligible)})"
                    )

        return result

    def validate_all(self, workflow_dir: str) -> Dict[str, Any]:
        """Validate all checkpoints in workflow directory."""
        checkpoints = self.list_checkpoints(workflow_dir)
        
        if not checkpoints:
            return {
                "valid": False,
                "errors": [f"No checkpoint files found in {workflow_dir}"],
            }

        results = {
            "workflow_dir": workflow_dir,
            "checkpoints_found": len(checkpoints),
            "checkpoints": [],
            "consistency": None,
            "all_valid": True,
        }

        # Validate each checkpoint
        for checkpoint_path in checkpoints:
            stage_name = checkpoint_path.stem.replace("_state", "")
            
            # Structure validation
            structure_result = self.validate_checkpoint_structure(checkpoint_path)
            
            # Data validation
            data_result = self.validate_checkpoint_data(checkpoint_path, stage_name)
            
            checkpoint_result = {
                "stage": stage_name,
                "file": str(checkpoint_path),
                "structure": structure_result,
                "data": data_result,
                "valid": (
                    structure_result["valid_json"]
                    and structure_result["has_required_fields"]
                    and data_result["deserialization_ok"]
                    and len(data_result["errors"]) == 0
                ),
            }
            
            results["checkpoints"].append(checkpoint_result)
            
            if not checkpoint_result["valid"]:
                results["all_valid"] = False

        # Validate consistency
        results["consistency"] = self.validate_stage_consistency(checkpoints)
        if not results["consistency"]["consistent"]:
            results["all_valid"] = False

        return results

    def generate_report(self, results: Dict[str, Any]) -> None:
        """Generate validation report."""
        console.print(f"\n[bold cyan]Checkpoint Validation Report[/bold cyan]")
        console.print(f"Workflow Directory: {results['workflow_dir']}")
        console.print(f"Checkpoints Found: {results['checkpoints_found']}\n")

        # Summary table
        table = Table(title="Checkpoint Summary")
        table.add_column("Stage", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Structure", style="yellow")
        table.add_column("Data", style="yellow")
        table.add_column("Counts", style="blue")

        for checkpoint in results["checkpoints"]:
            status = "[green]OK[/green]" if checkpoint["valid"] else "[red]FAIL[/red]"
            structure_status = (
                "[green]OK[/green]"
                if checkpoint["structure"]["valid_json"]
                and checkpoint["structure"]["has_required_fields"]
                else "[red]FAIL[/red]"
            )
            data_status = (
                "[green]OK[/green]"
                if checkpoint["data"]["deserialization_ok"]
                and len(checkpoint["data"]["errors"]) == 0
                else "[red]FAIL[/red]"
            )
            
            counts_str = ", ".join(
                [f"{k}={v}" for k, v in checkpoint["data"]["data_counts"].items()]
            ) or "N/A"

            table.add_row(
                checkpoint["stage"],
                status,
                structure_status,
                data_status,
                counts_str,
            )

        console.print(table)

        # Detailed errors and warnings
        has_issues = False
        for checkpoint in results["checkpoints"]:
            issues = []
            
            if checkpoint["structure"]["errors"]:
                issues.extend([f"Structure: {e}" for e in checkpoint["structure"]["errors"]])
            if checkpoint["structure"]["warnings"]:
                issues.extend([f"Structure warning: {w}" for w in checkpoint["structure"]["warnings"]])
            if checkpoint["data"]["errors"]:
                issues.extend([f"Data: {e}" for e in checkpoint["data"]["errors"]])
            if checkpoint["data"]["warnings"]:
                issues.extend([f"Data warning: {w}" for w in checkpoint["data"]["warnings"]])

            if issues:
                has_issues = True
                console.print(f"\n[bold yellow]{checkpoint['stage']}[/bold yellow]")
                for issue in issues:
                    if "warning" in issue.lower():
                        console.print(f"  [yellow]WARNING:[/yellow] {issue}")
                    else:
                        console.print(f"  [red]ERROR:[/red] {issue}")

        # Consistency check
        if results["consistency"]:
            consistency = results["consistency"]
            if consistency["errors"] or consistency["warnings"]:
                has_issues = True
                console.print("\n[bold yellow]Stage Consistency Check[/bold yellow]")
                for error in consistency["errors"]:
                    console.print(f"  [red]ERROR:[/red] {error}")
                for warning in consistency["warnings"]:
                    console.print(f"  [yellow]WARNING:[/yellow] {warning}")
                
                if consistency["counts"]:
                    console.print("\n  [cyan]Counts:[/cyan]")
                    for stage, count in consistency["counts"].items():
                        console.print(f"    {stage}: {count}")

        # Final status
        console.print("\n")
        if results["all_valid"]:
            console.print("[bold green]All checkpoints are valid![/bold green]")
        else:
            console.print("[bold red]Some checkpoints have validation errors![/bold red]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate workflow checkpoint files"
    )
    parser.add_argument(
        "--workflow-dir",
        type=str,
        required=True,
        help="Path to workflow checkpoint directory",
    )
    
    args = parser.parse_args()
    
    validator = CheckpointValidator()
    results = validator.validate_all(args.workflow_dir)
    validator.generate_report(results)
    
    # Exit with error code if validation failed
    sys.exit(0 if results["all_valid"] else 1)


if __name__ == "__main__":
    main()
