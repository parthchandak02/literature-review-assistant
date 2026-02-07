"""
Test fixtures for report sections.
"""

from typing import Dict


def get_complete_article_sections() -> Dict[str, str]:
    """Get complete article sections with PRISMA 2020 format."""
    return {
        "title": "Systematic Review: Test Topic",
        "abstract": """Background: This systematic review addresses an important research question.

Objectives: The objectives of this review are to investigate test questions.

Eligibility criteria: Inclusion and exclusion criteria are specified.

Information sources: Databases searched include PubMed, Scopus, and others.

Risk of bias: Methods used to assess risk of bias are described.

Synthesis methods: Meta-analysis and synthesis methods are described.

Results: Results show findings from included studies.

Limitations: Limitations of the evidence are discussed.

Interpretation: Interpretation and conclusions are provided.

Funding: Funding sources are described.

Registration: This review is registered in PROSPERO (CRD123456).""",
        "introduction": """## Introduction

### Rationale

The rationale for this review is described here.

### Objectives

The objectives of this systematic review are:
- Objective 1
- Objective 2""",
        "methods": """## Methods

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

### Risk of Bias Assessment

Methods for risk of bias assessment using RoB 2 are described.

### Certainty Assessment

Methods for assessing certainty using GRADE are described.""",
        "results": """## Results

### Study Selection

Results of search and selection are described.

### Study Characteristics

Characteristics of included studies are presented in a table.

### Risk of Bias Results

Risk of bias assessments are presented.

### Certainty of Evidence

GRADE assessments of certainty are presented.""",
        "discussion": """## Discussion

### Summary

General interpretation of results is provided.

### Limitations

Limitations of the evidence and review process are discussed.

### Implications

Implications for practice, policy, and research are provided.""",
        "keywords": "systematic review, test topic, research",
        "funding": "Sources of support are described.",
        "conflicts_of_interest": "Competing interests are declared.",
        "data_availability": "Data availability and supplementary materials are reported.",
    }


def get_sample_report_markdown() -> str:
    """Get sample complete report markdown."""
    sections = get_complete_article_sections()

    return f"""# {sections["title"]}

## Abstract

{sections["abstract"]}

## Keywords

{sections["keywords"]}

{sections["introduction"]}

{sections["methods"]}

{sections["results"]}

{sections["discussion"]}

## Funding

{sections["funding"]}

## Conflicts of Interest

{sections["conflicts_of_interest"]}

## Data Availability

{sections["data_availability"]}
"""
