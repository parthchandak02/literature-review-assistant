#!/usr/bin/env python3
"""
[Utility Script] IEEE Readiness Report Generator

Comprehensive status report checking all improvements and IEEE compliance.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel

console = Console()


def check_test_results() -> Dict[str, Any]:
    """Check latest test results."""
    test_outputs_dir = Path("data/test_outputs")
    latest_results = test_outputs_dir / "latest_results.json"
    
    if not latest_results.exists():
        # Try to find most recent test result
        test_files = list(test_outputs_dir.glob("test_results_*.json"))
        if test_files:
            latest_results = max(test_files, key=lambda p: p.stat().st_mtime)
        else:
            return {"status": "not_found", "message": "No test results found"}
    
    try:
        with open(latest_results, "r") as f:
            results = json.load(f)
        return {
            "status": "found",
            "total": results.get("summary", {}).get("total", 0),
            "passed": results.get("summary", {}).get("passed", 0),
            "failed": results.get("summary", {}).get("failed", 0),
            "timestamp": results.get("timestamp", "Unknown"),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_workflow_outputs() -> Dict[str, Any]:
    """Check for existing workflow outputs."""
    output_dir = Path("data/outputs")
    if not output_dir.exists():
        return {"status": "no_outputs", "message": "No outputs directory found"}
    
    # Find most recent workflow output
    workflow_dirs = []
    for item in output_dir.iterdir():
        if item.is_dir():
            if (item / "final_report.md").exists() or (item / "workflow_state.json").exists():
                workflow_dirs.append(item)
    
    if not workflow_dirs:
        return {"status": "no_workflows", "message": "No workflow outputs found"}
    
    latest_workflow = max(workflow_dirs, key=lambda p: p.stat().st_mtime)
    
    outputs = {
        "workflow_dir": str(latest_workflow),
        "files": {},
    }
    
    expected_files = {
        "final_report.md": "Final report",
        "prisma_diagram.png": "PRISMA diagram",
        "prisma_checklist.json": "PRISMA checklist",
        "search_strategies.md": "Search strategies",
        "extraction_form.md": "Extraction form",
        "final_report.tex": "LaTeX export",
        "final_report.docx": "Word export",
    }
    
    for filename, description in expected_files.items():
        filepath = latest_workflow / filename
        outputs["files"][filename] = {
            "exists": filepath.exists(),
            "size": filepath.stat().st_size if filepath.exists() else 0,
            "description": description,
        }
    
    # Check report content
    report_path = latest_workflow / "final_report.md"
    if report_path.exists():
        content = report_path.read_text()
        outputs["report_content"] = {
            "has_abstract": "## Abstract" in content or "abstract" in content.lower()[:1000],
            "has_keywords": "## Keywords" in content or "Keywords:" in content,
            "has_introduction": "## Introduction" in content,
            "has_methods": "## Methods" in content,
            "has_results": "## Results" in content,
            "has_discussion": "## Discussion" in content,
            "has_references": "## References" in content or "## Reference" in content,
            "has_funding": "## Funding" in content,
            "has_conflicts": "## Conflicts" in content or "## Competing" in content,
            "word_count": len(content.split()),
        }
    
    return outputs


def check_code_improvements() -> Dict[str, Any]:
    """Check if code improvements are in place."""
    improvements = {}
    
    # Check data extraction normalization
    extraction_file = Path("src/extraction/data_extractor_agent.py")
    if extraction_file.exists():
        content = extraction_file.read_text()
        improvements["normalization_function"] = "_normalize_extraction_response" in content
        improvements["enhanced_error_logging"] = "detailed_error" in content or "error_details" in content
    
    # Check keywords extraction
    workflow_file = Path("src/orchestration/workflow_manager.py")
    if workflow_file.exists():
        content = workflow_file.read_text()
        improvements["keywords_from_papers"] = "paper_keywords" in content and "paper.keywords" in content
        improvements["keywords_aggregation"] = "all_keywords" in content
    
    # Check abstract conversion for IEEE
    latex_file = Path("src/export/latex_exporter.py")
    if latex_file.exists():
        content = latex_file.read_text()
        improvements["abstract_conversion"] = "_convert_to_unstructured_abstract" in content
        improvements["ieee_citation_formatting"] = "IEEEFormatter" in content
    
    # Check table enhancements
    if latex_file.exists():
        content = latex_file.read_text()
        improvements["table_conversion"] = "_convert_markdown_table_to_latex" in content
        improvements["booktabs_support"] = "booktabs" in content.lower() or "\\toprule" in content
    
    # Check Pydantic validators
    schemas_file = Path("src/schemas/extraction_schemas.py")
    if schemas_file.exists():
        content = schemas_file.read_text()
        improvements["pydantic_validators"] = "@field_validator" in content
    
    return improvements


def check_ieee_compliance() -> Dict[str, Any]:
    """Check IEEE format compliance."""
    compliance = {
        "abstract_format": "unstructured",  # IEEE requires unstructured
        "abstract_word_count": "150-250",  # IEEE requirement
        "keywords_count": "5-10",  # IEEE requirement
        "citation_format": "IEEE style (square brackets)",
        "latex_template": "IEEEtran",
        "required_sections": [
            "Abstract",
            "Keywords (Index Terms)",
            "Introduction",
            "Methods",
            "Results",
            "Discussion",
            "References",
        ],
    }
    
    return compliance


def generate_report() -> str:
    """Generate comprehensive IEEE readiness report."""
    report_lines = []
    report_lines.append("# IEEE Readiness Report")
    report_lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Test Results
    report_lines.append("## 1. Test Results")
    report_lines.append("")
    test_results = check_test_results()
    if test_results.get("status") == "found":
        report_lines.append(f"- Total Tests: {test_results.get('total', 0)}")
        report_lines.append(f"- Passed: {test_results.get('passed', 0)}")
        report_lines.append(f"- Failed: {test_results.get('failed', 0)}")
        report_lines.append(f"- Last Run: {test_results.get('timestamp', 'Unknown')}")
    else:
        report_lines.append(f"- Status: {test_results.get('message', 'Unknown')}")
    report_lines.append("")
    
    # Code Improvements
    report_lines.append("## 2. Code Improvements Status")
    report_lines.append("")
    improvements = check_code_improvements()
    for improvement, status in improvements.items():
        status_str = "YES" if status else "NO"
        report_lines.append(f"- {improvement.replace('_', ' ').title()}: {status_str}")
    report_lines.append("")
    
    # Workflow Outputs
    report_lines.append("## 3. Workflow Outputs Status")
    report_lines.append("")
    outputs = check_workflow_outputs()
    if outputs.get("status") == "no_outputs" or outputs.get("status") == "no_workflows":
        report_lines.append(f"- Status: {outputs.get('message', 'Unknown')}")
        report_lines.append("- Recommendation: Run full workflow to generate outputs")
    else:
        report_lines.append(f"- Latest Workflow: {outputs.get('workflow_dir', 'Unknown')}")
        report_lines.append("")
        report_lines.append("### Output Files:")
        for filename, info in outputs.get("files", {}).items():
            status = "EXISTS" if info["exists"] else "MISSING"
            size_kb = info["size"] / 1024 if info["exists"] else 0
            report_lines.append(f"  - {filename}: {status} ({size_kb:.1f} KB)" if info["exists"] else f"  - {filename}: {status}")
        
        if "report_content" in outputs:
            report_lines.append("")
            report_lines.append("### Report Content Check:")
            content = outputs["report_content"]
            for key, value in content.items():
                if key != "word_count":
                    status = "YES" if value else "NO"
                    report_lines.append(f"  - {key.replace('_', ' ').title()}: {status}")
                else:
                    report_lines.append(f"  - Word Count: {value}")
    report_lines.append("")
    
    # IEEE Compliance
    report_lines.append("## 4. IEEE Format Compliance")
    report_lines.append("")
    compliance = check_ieee_compliance()
    report_lines.append("### Requirements:")
    for key, value in compliance.items():
        if isinstance(value, list):
            report_lines.append(f"- {key.replace('_', ' ').title()}:")
            for item in value:
                report_lines.append(f"  - {item}")
        else:
            report_lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    report_lines.append("")
    
    # Recommendations
    report_lines.append("## 5. Recommendations")
    report_lines.append("")
    
    recommendations = []
    
    if not improvements.get("normalization_function"):
        recommendations.append("Add response normalization function for data extraction")
    
    if not improvements.get("keywords_from_papers"):
        recommendations.append("Extract keywords from included papers, not just config")
    
    if not improvements.get("abstract_conversion"):
        recommendations.append("Add abstract conversion for IEEE unstructured format")
    
    if outputs.get("status") in ["no_outputs", "no_workflows"]:
        recommendations.append("Run full workflow to generate test outputs")
    
    if recommendations:
        for i, rec in enumerate(recommendations, 1):
            report_lines.append(f"{i}. {rec}")
    else:
        report_lines.append("All critical improvements appear to be implemented.")
    
    report_lines.append("")
    report_lines.append("## 6. Next Steps")
    report_lines.append("")
    report_lines.append("1. Run full workflow: `python main.py` or `make run`")
    report_lines.append("2. Verify outputs: `python scripts/validate_workflow_outputs.py`")
    report_lines.append("3. Check LaTeX export: Verify `final_report.tex` compiles")
    report_lines.append("4. Validate IEEE format: Check abstract word count, keywords, citations")
    report_lines.append("5. Test submission readiness: Ensure all required sections present")
    
    return "\n".join(report_lines)


def main():
    """Generate and display IEEE readiness report."""
    console.print(Panel.fit("[bold blue]IEEE Readiness Report Generator[/bold blue]", border_style="blue"))
    
    # Generate report
    report_content = generate_report()
    
    # Save to file (in .gitignore)
    output_file = Path("IEEE_READINESS_REPORT.md")
    with open(output_file, "w") as f:
        f.write(report_content)
    
    console.print(f"\n[green]Report generated:[/green] {output_file}")
    console.print("\n" + "=" * 80)
    console.print(report_content)
    console.print("=" * 80)


if __name__ == "__main__":
    main()
