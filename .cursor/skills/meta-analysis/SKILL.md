---
name: meta-analysis
description: Implements meta-analysis using statsmodels. Use when building effect size calculations, forest plots, funnel plots, or synthesis pipeline.
---

# Meta-Analysis Implementation

Guide for implementing statistical synthesis using statsmodels.

## CRITICAL RULE
LLMs must NEVER compute statistics. All calculations use deterministic functions.

## Workflow

1. **Feasibility check** (deterministic): Evaluate structured outcome compatibility before pooling.
2. **Extract raw data** from `ExtractionRecord` (means, SDs, counts, events)
3. **Compute effect sizes** using statsmodels functions
4. **Assess heterogeneity** (I^2, Q, tau^2)
5. **Select model**: use `meta_analysis.heterogeneity_threshold` from `config/settings.yaml` (current default 50%) to pick fixed vs random-effects
6. **Pool effects** using `combine_effects()`
7. **Generate forest plot** using `.plot_forest()`
8. **Generate funnel plot** (matplotlib scatter) if >= 10 studies
9. **Store results** as `MetaAnalysisResult` in SQLite

## Effect Size Functions
See statsmodels meta_analysis docs. Use @Ref or search for current API.
- Continuous: `effectsize_smd(mean1, sd1, nobs1, mean2, sd2, nobs2)`
- Dichotomous: `effectsize_2proportions(count1, nobs1, count2, nobs2, statistic="rr"|"or"|"rd"|"as")`

## Known Limitations
- Mantel-Haenszel NOT available in statsmodels -- use DerSimonian-Laird
- statsmodels meta-analysis API is marked "experimental"
- Verify results against R metafor if possible
