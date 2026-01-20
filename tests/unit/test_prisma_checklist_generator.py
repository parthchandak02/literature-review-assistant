"""
Unit tests for PRISMA checklist generator.
"""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.prisma.checklist_generator import PRISMAChecklistGenerator


@pytest.fixture
def generator():
    """Create PRISMA checklist generator instance."""
    return PRISMAChecklistGenerator()


@pytest.fixture
def complete_report_content():
    """Complete report content for checklist generation."""
    return """# Systematic Review: Test Topic

## Abstract

Abstract content with all elements.

## Introduction

Rationale and objectives are described.

## Methods

Eligibility criteria, information sources, search strategy, and other methods are described.
Risk of bias assessment methods are specified.
GRADE methods for assessing certainty are described.

## Results

Study selection results are described.
Study characteristics are presented in a table.
Risk of bias results are presented.
GRADE certainty results are presented.

## Discussion

Discussion is provided.

## Funding

Funding sources are described.

## Conflicts of Interest

Competing interests are declared.

## Data Availability

Data availability is reported.

## Registration

This review is registered in PROSPERO (CRD123456).
"""


@pytest.fixture
def incomplete_report_content():
    """Incomplete report content."""
    return """# Test Review

## Introduction

Some content.

## Methods

Some methods.

## Results

Some results.
"""


def test_checklist_generation(generator, complete_report_content, tmp_path):
    """Test checklist generation with complete report."""
    output_path = tmp_path / "checklist.json"
    
    result_path = generator.generate_checklist(complete_report_content, str(output_path))
    
    assert Path(result_path).exists()
    assert result_path == str(output_path)
    
    with open(result_path, "r") as f:
        checklist = json.load(f)
    
    assert checklist["prisma_version"] == "2020"
    assert "report_title" in checklist
    assert "items" in checklist
    assert len(checklist["items"]) == 27  # Should have 27 PRISMA items


def test_checklist_item_detection(generator, complete_report_content, tmp_path):
    """Test that checklist correctly detects items."""
    output_path = tmp_path / "checklist.json"
    generator.generate_checklist(complete_report_content, str(output_path))
    
    with open(output_path, "r") as f:
        checklist = json.load(f)
    
    items = {item["item"]: item for item in checklist["items"]}
    
    # Check that key items are detected
    assert items[1]["reported"] == "Yes"  # Title
    assert items[4]["reported"] == "Yes"  # Objectives
    assert items[5]["reported"] == "Yes"  # Eligibility criteria
    assert items[7]["reported"] == "Yes"  # Search strategy
    assert items[11]["reported"] == "Yes"  # Risk of bias methods
    assert items[15]["reported"] == "Yes"  # Certainty assessment
    assert items[17]["reported"] == "Yes"  # Study characteristics
    assert items[18]["reported"] == "Yes"  # Risk of bias results
    assert items[22]["reported"] == "Yes"  # Certainty results
    assert items[24]["reported"] == "Yes"  # Registration
    assert items[25]["reported"] == "Yes"  # Funding
    assert items[26]["reported"] == "Yes"  # Conflicts of interest
    assert items[27]["reported"] == "Yes"  # Data availability


def test_checklist_missing_items(generator, incomplete_report_content, tmp_path):
    """Test checklist with missing items."""
    output_path = tmp_path / "checklist.json"
    generator.generate_checklist(incomplete_report_content, str(output_path))
    
    with open(output_path, "r") as f:
        checklist = json.load(f)
    
    items = checklist["items"]
    
    # Should have many "No" items
    no_items = [item for item in items if item["reported"] == "No"]
    assert len(no_items) > 10


def test_checklist_json_output(generator, complete_report_content, tmp_path):
    """Test JSON output format."""
    output_path = tmp_path / "checklist.json"
    generator.generate_checklist(complete_report_content, str(output_path))
    
    with open(output_path, "r") as f:
        checklist = json.load(f)
    
    # Verify structure
    assert isinstance(checklist, dict)
    assert "prisma_version" in checklist
    assert "report_title" in checklist
    assert "items" in checklist
    assert isinstance(checklist["items"], list)
    
    # Verify item structure
    for item in checklist["items"]:
        assert "item" in item
        assert "section" in item
        assert "description" in item
        assert "reported" in item
        assert "page_number" in item
        assert item["reported"] in ["Yes", "No"]


def test_title_extraction(generator):
    """Test title extraction from report."""
    content = "# Systematic Review: Test Topic\n\nContent here."
    title = generator._extract_title(content)
    assert title == "Systematic Review: Test Topic"
    
    # Test with no title
    content_no_title = "Content without title."
    title = generator._extract_title(content_no_title)
    assert title == "Systematic Review Report"  # Default


def test_item_checking(generator):
    """Test individual item checking."""
    content = "# Systematic Review\n\n## Methods\n\nSearch strategy is presented."
    
    # Test item 1 (title)
    assert generator._check_item(content, 1, "Identify the report as a systematic review", "Title")
    
    # Test item 7 (search strategy)
    assert generator._check_item(content, 7, "Present full search strategies", "Methods")
    
    # Test item that doesn't exist
    assert not generator._check_item(content, 24, "Provide registration information", "Other")


def test_page_number_estimation(generator):
    """Test page number estimation."""
    # Create content with sections at different line positions
    content = "\n".join([f"Line {i}" for i in range(200)]) + "\n## Methods\n\nContent"
    
    page_num = generator._find_page_number(content, "Methods")
    
    # Should estimate based on line number (approximately)
    assert page_num is not None
    assert isinstance(page_num, int)
    assert page_num > 0


def test_page_number_not_found(generator):
    """Test page number when section not found."""
    content = "Some content without Methods section."
    page_num = generator._find_page_number(content, "Methods")
    assert page_num is None


def test_checklist_all_items_present(generator):
    """Test that all 27 items are included in checklist."""
    assert len(generator.checklist_items) == 27
    
    # Verify item numbers are sequential
    item_numbers = [item["item"] for item in generator.checklist_items]
    assert item_numbers == list(range(1, 28))


def test_checklist_section_mapping(generator):
    """Test that items are mapped to correct sections."""
    sections = {}
    for item in generator.checklist_items:
        section = item["section"]
        if section not in sections:
            sections[section] = []
        sections[section].append(item["item"])
    
    # Verify expected sections exist
    assert "Title" in sections
    assert "Abstract" in sections
    assert "Introduction" in sections
    assert "Methods" in sections
    assert "Results" in sections
    assert "Discussion" in sections
    assert "Other" in sections
    
    # Verify item 1 is in Title
    assert 1 in sections["Title"]
    # Verify item 2 is in Abstract
    assert 2 in sections["Abstract"]
