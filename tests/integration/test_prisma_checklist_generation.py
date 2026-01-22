"""
Integration tests for PRISMA checklist generation.
"""

import json
from pathlib import Path

from src.prisma.checklist_generator import PRISMAChecklistGenerator
from tests.fixtures.mock_report_sections import get_sample_report_markdown


def test_checklist_file_creation(tmp_path):
    """Test that PRISMA checklist file is created correctly."""
    generator = PRISMAChecklistGenerator()
    
    report_content = get_sample_report_markdown()
    output_path = tmp_path / "prisma_checklist.json"
    
    result_path = generator.generate_checklist(report_content, str(output_path))
    
    assert Path(result_path).exists()
    assert result_path == str(output_path)
    
    with open(result_path, "r") as f:
        checklist = json.load(f)
    
    assert checklist["prisma_version"] == "2020"
    assert "report_title" in checklist
    assert "items" in checklist
    assert len(checklist["items"]) == 27


def test_item_marking(tmp_path):
    """Test that checklist correctly marks items as present/absent."""
    generator = PRISMAChecklistGenerator()
    
    # Complete report should have most items marked as "Yes"
    complete_report = get_sample_report_markdown()
    output_path = tmp_path / "checklist_complete.json"
    generator.generate_checklist(complete_report, str(output_path))
    
    with open(output_path, "r") as f:
        checklist = json.load(f)
    
    yes_items = [item for item in checklist["items"] if item["reported"] == "Yes"]
    # Complete report should have many items present
    assert len(yes_items) > 15
    
    # Incomplete report should have fewer items
    incomplete_report = "# Test Review\n\n## Introduction\n\nSome content."
    output_path_incomplete = tmp_path / "checklist_incomplete.json"
    generator.generate_checklist(incomplete_report, str(output_path_incomplete))
    
    with open(output_path_incomplete, "r") as f:
        checklist_incomplete = json.load(f)
    
    yes_items_incomplete = [item for item in checklist_incomplete["items"] if item["reported"] == "Yes"]
    assert len(yes_items_incomplete) < len(yes_items)
