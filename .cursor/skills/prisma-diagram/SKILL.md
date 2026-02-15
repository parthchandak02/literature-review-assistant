---
name: prisma-diagram
description: Implements PRISMA 2020 flow diagram and visualizations. Use when building src/prisma/, timeline, or geographic distribution.
---

# PRISMA Diagram & Visualizations

Guide for implementing Phase 7 PRISMA diagram and related visualizations.

## PRISMA 2020 Two-Column Structure

- **Left column:** "Records identified from Databases and Registers" (per-database counts)
- **Right column:** "Records identified from Other Sources" (citation search, grey literature)

## Diagram Requirements

1. Per-database counts in identification box
2. Exclusion reasons categorized from `ExclusionReason` enum
3. Separate qualitative/quantitative synthesis counts
4. **Arithmetic validation:** records in = records out at every stage (`PRISMACounts.arithmetic_valid`)

## Data Source

Build from `PRISMACounts` model:
- `databases_records`, `other_sources_records`
- `duplicates_removed`, `records_screened`, `records_excluded_screening`
- `reports_sought`, `reports_not_retrieved`, `reports_assessed`
- `reports_excluded_with_reasons` (Dict[ExclusionReason, count])
- `studies_included_qualitative`, `studies_included_quantitative`

## Implementation

`src/prisma/prisma_generator.py` -- PRISMA diagram generation. Use matplotlib for custom diagrams. Verify arithmetic at each stage.

## Additional Visualizations

- **Charts** (`src/visualization/charts.py`): Existing visualization utilities
- **Timeline** (target): Publication timeline of included studies
- **Geographic** (target): Geographic distribution of studies
