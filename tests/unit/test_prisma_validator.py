"""
Unit tests for PRISMA validator.
"""

import pytest
import json
from pathlib import Path

from src.validation.prisma_validator import PRISMAValidator


@pytest.fixture
def validator():
    """Create PRISMA validator instance."""
    return PRISMAValidator()


@pytest.fixture
def complete_report_markdown():
    """Complete PRISMA-compliant report markdown."""
    return """# Systematic Review: Test Topic

## Abstract

**Background:** This is a systematic review of test topic. The context and rationale are provided here.

**Objectives:** The objectives of this review are to investigate test questions.

**Eligibility criteria:** Inclusion and exclusion criteria are specified.

**Information sources:** Databases searched include PubMed, Scopus, and others.

**Risk of bias:** Methods used to assess risk of bias are described.

**Synthesis methods:** Meta-analysis and synthesis methods are described.

**Results:** Results show findings from included studies.

**Limitations:** Limitations of the evidence are discussed.

**Interpretation:** Interpretation and conclusions are provided.

**Funding:** Funding sources are described.

**Registration:** This review is registered in PROSPERO (CRD123456).

## Introduction

### Rationale

The rationale for this review is described here.

### Objectives

The objectives of this systematic review are:
- Objective 1
- Objective 2

## Methods

### Eligibility Criteria

Inclusion and exclusion criteria are specified using PICOS framework.

### Information Sources

The following databases were searched: PubMed, Scopus, Web of Science.

### Search Strategy

Full search strategies are presented for each database.

### Study Selection

Methods for study selection are described.

### Data Collection

Methods for data collection are specified.

### Data Items

Outcomes and variables are listed and defined.

### Risk of Bias Assessment

Methods for risk of bias assessment using RoB 2 are described.

### Effect Measures

Effect measures are specified.

### Synthesis Methods

Synthesis methods including meta-analysis are described.

### Reporting Bias

Methods for assessing reporting bias are described.

### Certainty Assessment

Methods for assessing certainty using GRADE are described.

## Results

### Study Selection

Results of search and selection are described.

### Study Characteristics

Characteristics of included studies are presented in a table.

### Risk of Bias Results

Risk of bias assessments are presented.

### Results of Individual Studies

Results for each study are presented.

### Results of Syntheses

Results of syntheses are presented.

### Reporting Biases

Assessments of reporting biases are presented.

### Certainty of Evidence

GRADE assessments of certainty are presented.

## Discussion

### Summary

General interpretation of results is provided.

## Funding

Sources of support are described.

## Conflicts of Interest

Competing interests are declared.

## Data Availability

Data availability and supplementary materials are reported.
"""


@pytest.fixture
def incomplete_report_markdown():
    """Incomplete report missing some sections."""
    return """# Test Review

## Abstract

**Background:** Background is provided.

## Introduction

Rationale is described.

## Methods

Eligibility criteria are specified.

## Results

Some results are presented.

## Discussion

Discussion is provided.
"""


@pytest.fixture
def report_with_all_abstract_elements():
    """Report with all 12 abstract elements."""
    return """# Systematic Review

## Abstract

**Background:** Background context.

**Objectives:** Objectives are stated.

**Eligibility criteria:** Eligibility criteria are specified.

**Information sources:** Sources are listed.

**Risk of bias:** Risk of bias methods are described.

**Synthesis methods:** Synthesis methods are described.

**Results:** Results are presented.

**Limitations:** Limitations are discussed.

**Interpretation:** Interpretation is provided.

**Funding:** Funding is described.

**Registration:** Registration information is provided.

## Introduction

Rationale and objectives are described.

## Methods

Methods are described.

## Results

Results are presented.

## Discussion

Discussion is provided.
"""


def test_report_validation_complete(validator, complete_report_markdown, tmp_path):
    """Test validation of complete report."""
    report_path = tmp_path / "complete_report.md"
    report_path.write_text(complete_report_markdown)
    
    results = validator.validate_report(str(report_path))
    
    assert results["report_path"] == str(report_path)
    assert "prisma_items" in results
    assert "abstract_items" in results
    assert "compliance_score" in results
    assert results["compliance_score"] > 0.8  # Should be high for complete report
    assert len(results["missing_items"]) < 10  # Should have few missing items


def test_report_validation_incomplete(validator, incomplete_report_markdown, tmp_path):
    """Test validation of incomplete report."""
    report_path = tmp_path / "incomplete_report.md"
    report_path.write_text(incomplete_report_markdown)
    
    results = validator.validate_report(str(report_path))
    
    assert results["compliance_score"] < 0.5  # Should be low for incomplete report
    assert len(results["missing_items"]) > 10  # Should have many missing items


def test_report_validation_file_not_found(validator):
    """Test validation raises error for non-existent file."""
    with pytest.raises(FileNotFoundError):
        validator.validate_report("nonexistent_report.md")


def test_abstract_elements_detection(validator, report_with_all_abstract_elements, tmp_path):
    """Test detection of all 12 abstract elements."""
    report_path = tmp_path / "abstract_report.md"
    report_path.write_text(report_with_all_abstract_elements)
    
    results = validator.validate_report(str(report_path))
    
    abstract_items = results["abstract_items"]
    assert len(abstract_items) == 12
    
    # Check that key elements are detected
    assert abstract_items.get("background", {}).get("present", False)
    assert abstract_items.get("objectives", {}).get("present", False)
    assert abstract_items.get("eligibility", {}).get("present", False)
    assert abstract_items.get("sources", {}).get("present", False)
    assert abstract_items.get("risk_of_bias", {}).get("present", False)
    assert abstract_items.get("synthesis", {}).get("present", False)
    assert abstract_items.get("results", {}).get("present", False)
    assert abstract_items.get("limitations", {}).get("present", False)
    assert abstract_items.get("interpretation", {}).get("present", False)
    assert abstract_items.get("funding", {}).get("present", False)
    assert abstract_items.get("registration", {}).get("present", False)


def test_compliance_scoring(validator, complete_report_markdown, tmp_path):
    """Test compliance score calculation."""
    report_path = tmp_path / "scoring_report.md"
    report_path.write_text(complete_report_markdown)
    
    results = validator.validate_report(str(report_path))
    
    # Score should be between 0 and 1
    assert 0 <= results["compliance_score"] <= 1
    
    # For complete report, score should be high
    assert results["compliance_score"] > 0.7
    
    # Verify score calculation: present_items / total_items
    total_items = len(validator.prisma_2020_items) + len(validator.abstract_items)
    present_items = sum(
        1 for item in results["prisma_items"].values() if item["present"]
    ) + sum(1 for item in results["abstract_items"].values() if item["present"])
    
    expected_score = present_items / total_items if total_items > 0 else 0.0
    assert abs(results["compliance_score"] - expected_score) < 0.01


def test_edge_cases_empty_report(validator, tmp_path):
    """Test validation with empty report."""
    report_path = tmp_path / "empty_report.md"
    report_path.write_text("")
    
    results = validator.validate_report(str(report_path))
    
    assert results["compliance_score"] == 0.0
    assert len(results["missing_items"]) > 0


def test_edge_cases_malformed_markdown(validator, tmp_path):
    """Test validation with malformed markdown."""
    report_path = tmp_path / "malformed_report.md"
    report_path.write_text("### Invalid\n\n# Missing sections\n\nRandom text")
    
    results = validator.validate_report(str(report_path))
    
    # Should still return results without crashing
    assert "compliance_score" in results
    assert "missing_items" in results


def test_validation_report_generation(validator, complete_report_markdown, tmp_path):
    """Test generation of validation report JSON."""
    report_path = tmp_path / "validation_report.md"
    report_path.write_text(complete_report_markdown)
    
    results = validator.validate_report(str(report_path))
    output_path = tmp_path / "validation_output.json"
    
    saved_path = validator.generate_validation_report(results, str(output_path))
    
    assert Path(saved_path).exists()
    
    with open(saved_path, "r") as f:
        saved_data = json.load(f)
    
    assert saved_data["report_path"] == str(report_path)
    assert "prisma_items" in saved_data
    assert "abstract_items" in saved_data
    assert "compliance_score" in saved_data


def test_validation_report_default_path(validator, complete_report_markdown, tmp_path):
    """Test validation report generation with default path."""
    report_path = tmp_path / "default_report.md"
    report_path.write_text(complete_report_markdown)
    
    results = validator.validate_report(str(report_path))
    
    saved_path = validator.generate_validation_report(results)
    
    assert Path(saved_path).exists()
    assert saved_path.endswith("prisma_validation_report.json")
    
    # Should be in same directory as report
    assert Path(saved_path).parent == Path(report_path).parent


def test_item_detection_title(validator):
    """Test detection of title item."""
    content = "# Systematic Review of Test Topic"
    assert validator._check_item_presence(content, "title", "Identify the report as a systematic review", "Title")


def test_item_detection_objectives(validator):
    """Test detection of objectives item."""
    content = "## Introduction\n\nThe objectives of this review are to investigate."
    assert validator._check_item_presence(content, "objectives", "Provide explicit statement of objectives", "Introduction")


def test_item_detection_eligibility(validator):
    """Test detection of eligibility criteria."""
    content = "## Methods\n\nInclusion and exclusion criteria are specified using PICOS."
    assert validator._check_item_presence(content, "eligibility_criteria", "Specify inclusion and exclusion criteria", "Methods")


def test_item_detection_search_strategy(validator):
    """Test detection of search strategy."""
    content = "## Methods\n\nThe search strategy for PubMed is presented."
    assert validator._check_item_presence(content, "search_strategy", "Present full search strategies", "Methods")


def test_abstract_extraction(validator):
    """Test abstract section extraction."""
    content = """# Title

## Abstract

This is the abstract content with background and objectives.

## Introduction

This is introduction content.
"""
    abstract = validator._extract_abstract(content)
    assert abstract is not None
    assert "abstract content" in abstract.lower()
    assert "introduction content" not in abstract.lower()


def test_abstract_element_checking(validator):
    """Test checking individual abstract elements."""
    abstract = "Background: Context. Objectives: Aims. Eligibility: Criteria."
    
    assert validator._check_abstract_element(abstract, "background", "Background")
    assert validator._check_abstract_element(abstract, "objectives", "Objectives")
    assert validator._check_abstract_element(abstract, "eligibility", "Eligibility criteria")
    assert not validator._check_abstract_element(abstract, "funding", "Funding")  # Not present
