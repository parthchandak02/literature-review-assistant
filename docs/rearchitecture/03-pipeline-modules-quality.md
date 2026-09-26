# 03 — Pipeline modules, quality contracts, and methodology risks

Scope: `src/{screening,extraction,quality,synthesis,writing,manuscript,citation,export,prisma,protocol,knowledge_graph,rag,fulltext,search,visualization}`.
Claimed contracts: `docs/ARCHITECTURE.md#pipeline`, `.cursor/rules/core/llm-output.mdc`.
Ground truth sample: latest completed run
`runs/2026-09-01/wf-0001-the-multi-dimensional-impacts-of-pickleball-participation-on-phy/run_01-28-22AM/`
(status `done`, 6 included studies, total cost $1.20). The two `2026-09-02` workflows (`wf-0002`, `wf-0003`) stopped after config/DB init and have no outputs.
Jev semantics used in section 4: `docs/rearchitecture/00-jev-reference.md` (typed `noul` / `choice` / `score` classifier; it cannot generate prose).

All line numbers are from the working tree as of 2026-09-26.

---

## 0. TL;DR

The sampled manuscript was marked `done` while its own audit returned **major_revisions (19 findings, 8 blocking)** and the contract layer **failed (3 violations)**. That happened because `gates.audit_gate_mode: "advisory"` (`config/settings.yaml:225`). Most defects trace to three structural causes:

1. **Facts reach the prose through several independent paths.** These are grounding-patch sentences, LLM prose, deterministic evidence-assembler templates, and export-time tables. Nothing reconciles them, so the manuscript contradicts itself on counts: 4 vs 6 studies in Table 1, 1 vs 4 full-text exclusion reasons, 209 vs 194 kappa N, and "three" vs "four" cross-sectional studies.
2. **Keyword-presence heuristics stand in for structure.** They run both at generation time (`grounding_patches.py` appends canned sentences when words are missing) and at gate time (`prisma_disclosure.py`, the `DOMAIN_SCOPE_DRIFT` check, and the count-regex checks). They pass text that is wrong and flag text that is fine.
3. **The methodology layer has correctness bugs that no gate checks**: PRISMA exclusion-reason tallies, automation-tool accounting, GRADE computed per study instead of per outcome, CASP-qualitative applied to quantitative designs, and vote counting that mixes benefit and harm.

---

## 1. Per-module map

Line counts are the sum of `*.py` files per package. D = deterministic, L = LLM.

| Module | Lines | Responsibility | Key files / functions | Inputs → outputs | D vs L |
|---|---|---|---|---|---|
| `search` | 5,117 | Multi-connector search, query strategy, dedup, CSV import, Scopus/WoS sessions, PDF retrieval helpers | `strategy.py` (551), `pdf_retrieval.py` (512), `scopus.py`, `deduplication.py`, `source_inference.py` | `ReviewConfig` → `CandidatePaper` rows, `search_results`, dedup count | D, except query generation, which uses the `search` agent |
| `screening` | 3,708 | Metadata/keyword prefilter, BM25 cap, batch LLM pre-rank, dual reviewer plus adjudicator, kappa, criteria refinement | `keyword_filter.py` (`_deterministic_prefilter_decision`, `bm25_rank_and_cap`), `batch_ranker.py`, `dual_screener.py` (1,693), `reliability.py`, `criteria_refinement.py` | papers → `screening_decisions`, `dual_screening_results`, `study_cohort_membership` | D prefilter (excluded **1,328 of 1,548** records in the sample); L for batch ranker, reviewers A/B, and adjudicator. Screening calls use a bespoke `complete_json*` path (`dual_screener.py:1021-1065`), not `complete_validated` |
| `fulltext` | 2,112 | Multi-tier OA PDF resolution (Unpaywall, S2, EPMC, CORE, PMC, landing pages), manual ingest | `retrieval.py` (1,875) | included T/A papers → PDFs / text, coverage report | D. **50 of 57 reports (87%) were not retrieved** in the sample |
| `extraction` | 1,936 | Study-design classification, structured extraction, table extraction, primary-status | `extractor.py` (`_extract_llm` around line 580: `complete_validated` plus a raw `complete()` fallback at `:626-628`), `study_classifier.py` (raw `complete_json`), `inference_utils.py`, `table_extraction.py` | paper + full text → `ExtractionRecord` (JSON blob in `extraction_records.data`) | L extraction with D heuristic fallbacks (`_heuristic_outcomes`, `_heuristic_summary`, `_infer_participant_count`) |
| `quality` | 1,480 | RoB 2, ROBINS-I, CASP, MMAT, study routing, GRADE | `study_router.py`, `runner.py` (`QualityLLMRunner.run_validated`), `rob2.py`, `robins_i.py`, `casp.py`, `mmat.py`, `grade.py` (`assess_from_rob`) | `ExtractionRecord` → `rob_assessments`, `casp_assessments`, `mmat_assessments`, `grade_assessments` | L per-item judgments (validated) with D "all-false" heuristic fallbacks (`mmat.py:140-155`). GRADE arithmetic is D |
| `synthesis` | 1,205 | Feasibility, effect sizes, pooling, sensitivity, narrative direction, contradictions | `feasibility.py`, `effect_size.py`, `meta_analysis.py` (`pool_effects`, statsmodels `combine_effects`), `sensitivity.py`, `narrative.py` (`_classify_direction_llm`, `_keyword_direction`), `contradiction_detector.py` | extraction records → `synthesis_results`, `data_narrative_synthesis.json` | D pooling (scipy/statsmodels). L per-study direction label (`narrative.py:126-181`) with keyword fallback (`:189-201`) |
| `rag` | 966 | Chunk, embed, HyDE, retrieve, LLM rerank | `chunker.py`, `embedder.py`, `hyde.py`, `retriever.py`, `reranker.py` | PDFs → `paper_chunks_meta`; section query → evidence chunks | D embed/retrieve; L HyDE and rerank (`complete_with_usage`, free-text, not validated) |
| `knowledge_graph` | 396 | Paper relationship graph, communities, gaps | `builder.py`, `community.py`, `gap_detector.py` | extraction → `paper_relationships`, `graph_communities`, `research_gaps` | D |
| `writing` | 7,693 | Grounding block, outline, section writer, validation, ratchet, fallbacks, grounding patches, humanizer, citation catalog, evidence assembler | `context_builder.py` (1,780), `orchestration.py` (`write_section_with_validation`, ratchet at `:638-720`), `section_writer.py`, `section_validation.py` (`compute_section_quality_score` `:483`), `grounding_patches.py` (661), `section_fallbacks.py`, `evidence_assembler.py`, `humanizer*.py`, `outline_generator.py`, `contradiction_resolver.py` | `WritingGroundingData` + RAG + catalog → `StructuredSectionDraft` → markdown → `section_drafts`, `writing_manifests` | L for outline, section IR (`complete_validated`), humanizer (free text), and contradiction resolver (free text). **Large D rewrite layer** after generation (see section 2.2) |
| `manuscript` | 2,501 | Contracts, readiness scorecard, violation policy, PRISMA disclosure, LLM audit, cohort | `contracts.py` (`run_manuscript_contracts` `:735`, ~40 codes), `readiness.py`, `violation_policy.py`, `prisma_disclosure.py`, `reviewer.py` (`run_manuscript_audit` `:433`) | assembled md/tex + DB → `ManuscriptContractResult`, `manuscript_audit_runs/findings`, `ReadinessScorecard` | D contracts and readiness; L reviewer (profile routing plus per-pass findings, validated) |
| `citation` | 86 | Claim → evidence ledger | `ledger.py` (`validate_manuscript`) | text + `citations`/`claims`/`evidence_links` → unresolved lists | D, syntactic only (see section 2.4) |
| `export` | 6,332 | Final assembly, numbered refs, tables, IEEE LaTeX, BibTeX, PRISMA checklist, submission zip | `markdown_refs.py` (2,103; `assemble_submission_manuscript` `:1789`, `build_compact_study_table` `:977`), `ieee_latex.py`, `bibtex_builder.py`, `prisma_checklist.py`, `submission_packager.py`, `prisma_flow_export.py` | drafts + DB → `doc_manuscript.md/.tex`, `references.bib`, `submission/` | D. It injects its own tables and appendices after writing, which is one of the independent fact paths |
| `prisma` | 668 | PRISMA counts and diagram | `diagram.py` (`build_prisma_counts` `:285-400`), `layout.py` | repos → `PRISMACounts` → `fig_prisma_flow.png` | D |
| `protocol` | 920 | PROSPERO-format protocol | `generator.py` | `ReviewConfig` → `doc_protocol.md`, PROSPERO docx | D (template) |
| `visualization` | 2,654 | RoB traffic light, timeline, geography, evidence network, concept and custom AI diagrams | `rob_figure.py`, `concept_diagrams.py`, `research_diagram_*` (preparer, placement, renderer use `complete_validated`; drawing uses Gemini image) | DB → PNG/SVG | D charts. L concept/custom diagrams. **Custom image diagrams were the largest single cost line ($0.41 of $1.20, 34%)** |

Sample cost by phase (`cost_records`): custom diagram drawing $0.41, humanizer $0.27, writing $0.24, extraction $0.08, outline $0.07, audit $0.04, screening $0.05, quality $0.02. More than half of the spend goes to image generation and prose rewriting, not evidence work.

---

## 2. Quality-contract audit

### 2.1 Where structural contracts are enforced

| Layer | Location | What it enforces | Assessment |
|---|---|---|---|
| Section IR generation | `writing/orchestration.py:467-496` → `section_writer.write_section_structured_async` (`complete_validated`) → `_validate_structured_section_draft` (`section_validation.py:97`) | Block schema, citekeys limited to the catalog | Good. This is the only true generation-time structure |
| Section completeness plus retry | `orchestration.py:500-555` | Required subsections, citation coverage; one retry, then `_best_effort_accept` or deterministic fallback | Structural counts only. `_best_effort_accept` keeps failing drafts (the sample kept methods, results, and discussion with `missing_subheading:*`; see `writing_manifests.contract_status='warning'`) |
| Ratchet | `orchestration.py:638-720`, `SectionQualityScore` (`models/workflow.py:282-310`) | Lexicographic issue counts (hard, completeness, citation gap, outline, abstract floor, soft) | Counts only. No semantic signal such as fact correctness, overclaiming, or redundancy. Every section ran 2 iterations |
| Rendered integrity | `section_validation.py:200-256` `_grounding_integrity_issues` | Regex-extracted counts (for example `screened (\d+) records`) compared with grounding | Brittle: first match only, fixed phrasings. It missed "N=194" vs 209, "wrong outcome, n=3" vs 1 excluded, and "Three cross-sectional" vs 4 |
| Manuscript contracts | `manuscript/contracts.py:735-1349` | ~40 codes: included count vs table rows, placeholders, headings, figure numbering/assets, abstract fields and length, PRISMA statement, failed-DB disclosure, AI leakage, GRADE grounding, fallback use | Good breadth. Caught `INCLUDED_COUNT_MISMATCH` (6 vs 4) and `ABSTRACT_UNDER_MINIMUM` (77 words) in the sample. Many checks are substring or regex (below) |
| Violation policy | `manuscript/violation_policy.py:9-75` | Code → block/advisory per mode | Clean and central. `ABSTRACT_UNDER_MINIMUM`, `DOMAIN_SCOPE_DRIFT`, `EXTRACTION_YIELD_LOW`, `GRADE_UNGROUNDED`, and `QUALITY_ASSESSMENT_CORRUPTED_INPUT` are **absent from `SOFT_BLOCK_CODES`**, so they never block in soft mode |
| PRISMA disclosure | `manuscript/prisma_disclosure.py:10-105` | Numbers or phrases present | Presence, not correctness. `_int_word_boundary(md, 57)` passes if "57" appears anywhere. `_methodological_prisma_gaps` checks for literal substrings like `"registered"` and `"risk of bias"` (`:41-52`) |
| PRISMA arithmetic | `prisma/diagram.py:373-378` `arithmetic_valid` | screened = excluded + sought; sought = not_retrieved + assessed; assessed = excluded + included | **Does not check `sum(reports_excluded_with_reasons) == excluded_total`**, so the reason-tally bug (section 3.1) passes |
| Readiness scorecard | `manuscript/readiness.py:60-268` | finalize checkpoint, PRISMA arithmetic, audit, contracts, fallback events, lineage, PRISMA checklist, PDF | Correct AND-composition. It is not a gate on run status: the run still ends `done` |
| LLM reviewer audit | `manuscript/reviewer.py:385-560` | Profile-routed LLM findings (validated schema) | High yield: it caught most real defects in the sample. It also produced a false positive ("no dose-response study" when Owoeye is a dose-response analysis). With `audit_gate_mode: advisory` it cannot block (`orchestration/runners/audit_runner.py:78-79,191-202`) |
| Citation lineage | `citation/ledger.py:34-55`, `orchestration.py:374-424` | Citekeys exist; numeric refs in range; every claim has a link | Syntactic tautology (section 2.4) |

### 2.2 Post-hoc rewrites, keyword blocklists, and presence heuristics (anti-patterns per `llm-output.mdc`)

`llm-output.mdc` forbids keyword blocklists and prefers fail-fast validation over silent post-hoc rewriting. These locations violate that.

**A. Keyword-presence → append canned prose (`writing/grounding_patches.py`)**
- `_patch_introduction_grounding` `:132-141`: if `"gap"` is absent, append a rationale sentence; if `"question"` is absent, append the research question verbatim.
- `_patch_methods_grounding` `:144-323`: 12 separate `if "<word>" not in lower:` branches, each appending boilerplate. Examples: `:299` outcome definitions, `:301` effect measure, `:303` data prep, `:305` heterogeneity, `:307` reporting bias, `:309` software ("statsmodels or scipy was not used"). `_replace_or_append_subsection` (`:47-65`) **replaces the whole LLM-written body** of "Selection Process" and "Data Collection" with templated text.
- `_patch_results_grounding` `:326-428`: **phrase-variant blocklist** that rewrites "predominantly positive" into "directionally favorable but uncertain evidence pattern" (`:332-340`). It then appends heterogeneity and reporting-bias sentences asserting results that were never computed ("Heterogeneity results did not identify a consistent interaction or effect modifier…", `:416-426`). That is a **fabricated finding**.
- `_patch_discussion_grounding` `:431-506` and `_patch_conclusion_grounding` `:509-547`: the same pattern, including the fixed claim "low to very low certainty across outcomes" regardless of the actual GRADE rows.
- Evidence that it is fragile: the final manuscript still says "predominantly positive" four times (Results and Discussion), so the rewrite either did not run on the final text or was undone downstream (humanizer or assembly). Either way the contract is not deterministic.

**B. Lexical blocklists (`writing/humanizer_guardrails.py`, `writing/humanizer_checks.py`)**
- `_FILLER_REPLACEMENTS` `:22-31`, `_AI_LEXICON_REPLACEMENTS` `:34-52` ("moreover" → "and", "comprehensive" → "detailed", "crucial" → "important"), `_BLACKLIST_SUBSTITUTIONS` `:54-65`. These are applied to every section in `_render_and_sanitize` (`orchestration.py:309`) and again in `section_loop.py:329,396`. "Moreover, X" → "and, X" is ungrammatical.
- **Content-deleting regex** at `humanizer_guardrails.py:134-140`: `\b(W1 W2[ W3])\b(?:\s+[\w,.-]+){0,4}\s+\1\b` → `\1` deletes up to 4 words between two occurrences of a repeated bigram. The only safety net reverts if numeric tokens or citations change (`:173-177`). Word-only deletions ("hip-knee coordination *during cognitive dual-task and* hip-knee coordination…") pass silently.
- `_BLACKLIST_ENGLISH` word set in `humanizer_checks.py:23+` drives `scan_humanizer_flags` → LLM repair.

**C. Keyword gates at contract time (`manuscript/contracts.py`)**
- `DOMAIN_SCOPE_DRIFT` via `_discouraged_term_hits` `:193-195` is a substring hit on the whole body before References. In the sample it fired on "tennis, badminton, squash…", which appear **only in the PICOS exclusion-criteria appendix**. That is a false positive by construction.
- `_AI_LEAKAGE_PATTERNS` `:287-295`: literal phrase list.
- `_find_quality_assessment_corruption` `:678-695`: `unreadable|corrupted|binary|garbled`.
- `_extract_disclosed_included_counts` `:249-270`: five fixed phrasings. "Six studies were included" (a spelled-out number) is invisible to it.

**D. Keyword fallbacks for LLM judgments**
- `synthesis/narrative.py:189-201` `_keyword_direction`: "increase" → positive. An "increase in injuries" is classified positive whenever the LLM path fails.
- `extraction/extractor.py:644-656` heuristic outcomes and summaries.
- `quality/mmat.py:140-155` heuristic "all criteria false" on LLM failure. It is flagged `assessment_source="heuristic"` but still flows into tables and figures.

**E. Silent deterministic placeholders that bypass manifests**
- `orchestration/runners/writing/section_loop.py:578-586`: when the abstract is empty, this writes "This review synthesizes the available evidence for the topic… Objectives: This review evaluated What are…?." That is **exactly the abstract shipped in the sample**. `writing_manifests` for the abstract says `contract_status='passed', fallback_used=0, meta_json={}`, and `fallback_events` is empty, so `SECTION_DETERMINISTIC_FALLBACK` (`contracts.py:1316-1339`) cannot fire. The fallback is invisible to the control plane.
- `section_fallbacks.py:97-165` `_build_minimum_compliant_abstract` contains domain-specific leftovers from another review: "digital record adoption alone will produce durable coverage gains" (`:163`), "implementation and usability outcomes" (`:147`).

**F. Deterministic templated Results prose** (`writing/evidence_assembler.py:106-133, 317, 399`)
- Produces "<truncated title> reported the following key finding: <raw extraction text>" and "Rct studies contributed to the evidence base summarized in this review." In the sample these sentences carry **raw HTML** (`</b>`, `<i>F</i>`) and titles cut mid-word ("…in pre-frail old reported…").

### 2.3 Where LLM calls bypass `complete_validated` (contract says it is required for structured output)

| Call site | Path | Issue |
|---|---|---|
| `screening/dual_screener.py:1021-1065, 1585-1612` | `complete_json*` via `gemini_client.py` / local wrappers | Custom JSON parse path, not Pydantic-validated retries |
| `extraction/study_classifier.py:269-280` | `complete_json_with_usage` / `complete_json` | Same |
| `extraction/extractor.py:626-628`, `quality/runner.py:85-87` | Raw `complete()` + `model_validate_json` when `provider is None` | **No cost record** (violates the invariant that every LLM call logs cost) and no retry |
| `synthesis/narrative.py:158-164` | `complete_with_usage` + `model_validate_json` | No validated retry; failures fall to the keyword heuristic |
| `rag/hyde.py:125`, `rag/reranker.py:106`, `writing/contradiction_resolver.py:109` | free text / hand-parsed | Reranker output is parsed by hand |
| `writing/humanizer.py:97, 181` | Free-text rewrite of the **rendered markdown** after IR validation | Bypasses the structured IR entirely; only numeric/citation integrity is re-checked |

### 2.4 Citation grounding is syntactic

- `orchestration.py:374-403` registers every cited sentence as a `ClaimRecord(confidence=1.0)` and links it with `evidence_span=citekey, evidence_score=1.0`. There is no check that the cited paper supports the claim.
- `ledger.validate_manuscript` (`citation/ledger.py:34-55`) only checks that citekeys exist and that numeric refs are in `[1, N]`. `run_summary.json` therefore reports `citation_lineage_valid: true` for a manuscript that cites a GRADE methods paper ([11]) as support for a substantive practice claim (last sentence of the Conclusion), and bundles `[1], [2]` at paragraph ends instead of attaching them to claims.

---

## 3. Methodology correctness risks

### 3.1 PRISMA 2020 counts

1. **Full-text exclusion reasons tally individual reviewer votes, not final decisions.** `db/repos/screening.py:136-171` ranks `screening_decisions` rows with `decision='exclude'` per paper but never joins to the final outcome. In the sample, reviewer B voted "wrong_outcome" on 3 papers that were **ultimately included** (`dual_screening_results.final_decision='include'`: `ff1cc1d4`, `a02dc0d4`, `b62cf0c8`). Result: manuscript and flow diagram say "1 excluded (wrong intervention n=1; wrong outcome n=3)". `arithmetic_valid` (`prisma/diagram.py:373-378`) does not check the reason sum.
2. **Automation-tool exclusions are misfiled as title/abstract screening.** `automation_excluded` is taken from the `batch_screen_done` event only (11 records, `diagram.py:367-372`). The keyword/metadata prefilter excluded **1,328** records (`reviewer_type='keyword_filter'`) that are reported inside "1,480 excluded at title/abstract screening". PRISMA 2020 requires "records removed before screening: marked ineligible by automation tools" as a separate box. The Methods text ("routing 220 records to a priority scoring stage") and Results ("1,537 proceeded to title and abstract screening") therefore disagree, and kappa is reported on N=194 while 209 were dual-screened.
3. **Not-retrieved is stored as a full-text "exclude" by the adjudicator** (`exclusion_reason='no_full_text'`, 50 rows). The count path special-cases it, but any consumer that reads `screening_decisions` directly will double-count.
4. **An 87% non-retrieval rate is a validity threat that only produces disclosure text.** There is no gate threshold, and the review proceeds to "predominantly positive" conclusions from 6 of 57 eligible reports.
5. **Figure cross-references are wrong in prose.** "PRISMA flow is presented in Figure 1" but it is Fig. 3; "timeline Figure 4, geographic Figure 5" are actually Fig. 6 and 7. Fig. 7 is "by source database; country not available", contradicting "geographic distribution". `FIGURE_NUMBERING_INVALID` checks sequence only, not that referenced numbers match captions.

### 3.2 Risk of bias

1. **CASP qualitative checklist applied to quantitative cross-sectional and epidemiology designs.** `quality/study_router.py:53-58` routes `CROSS_SECTIONAL` → `casp`, and `quality/casp.py:21,54` uses the qualitative items (reflexivity, recruitment strategy for qualitative research). Two NEISS surveillance studies scored 1/8 and the others 0/8, and the LLM's own summaries say "not a qualitative study". Appropriate tools here are JBI analytical cross-sectional, AXIS, or MMAT category 4.
2. **Pre-post studies are routed to MMAT** (`study_router.py:50-52`), but the manuscript narrates "the mixed-methods study was appraised with the MMAT". The prose derives a "mixed-methods" label from the tool, not the design (see `grounding_patches.py:218-228`, which contains the heuristic "if mmat_count > mixed_methods_design_n and pre_post_design_n > 0").
3. **Heuristic all-false fallbacks** (`mmat.py:140-155`, CASP similar) look identical to real "not met" judgments in tables. The single MMAT row in the sample is 0/5 with LLM prose saying information was absent.

### 3.3 GRADE

1. **Graded per study, not per outcome across studies.** `extraction_runner.py:451, 889` pick `outcomes[0]` of each study as its GRADE outcome, and `:975-1003` groups by exact outcome string. Every sample row therefore has `n_studies=1`, and GRADE rated "Cadence (motoric dual-task walking)", a null secondary outcome, instead of the review's pre-specified outcome domains. The pre-post study got no GRADE row, so there were 4 rows for 6 studies.
2. **CASP/MMAT never influence the RoB downgrade.** `grade.py:134-178` accepts only `RoB2Assessment | RobinsIAssessment`. Cross-sectional studies meeting 0/8 CASP criteria are "risk of bias: not serious" in the Summary of Findings table.
3. **Inconsistency, indirectness, and publication bias are hardcoded to 0** (`grade.py:190-193`). Imprecision uses a pooled-N < 300 rule across heterogeneous studies (`:181-182`), and `study_design=_gp_recs[0].study_design` takes the first record's design for mixed groups (`extraction_runner.py:994`).

### 3.4 Synthesis

1. **Meta-analysis maths is deterministic** (statsmodels `combine_effects`, `synthesis/meta_analysis.py:50`). The model choice is **data-driven**, though: fixed-effect if I² < threshold, else random-effects (`:55-68`). Cochrane guidance is to pre-specify the model. Random-effects CIs use z (`_pooled_stats` `:22-33`) even with few studies. HKSJ variance appears only as a zero-variance fallback (`:65-66`), not as the Knapp-Hartung CI the settings rule implies (`use_t=True`).
2. **Vote counting across benefit and harm outcomes.** `narrative.py:209-295` classifies one direction per study under a single `outcome_name="primary_outcome"`, then derives `predominantly_positive` from 3 positive (gait, wellbeing, vitality), 2 negative (injury incidence), and 1 null. SWiM requires vote counting within outcome domains with a defined direction of benefit. Injury incidence is not "negative evidence" for a wellbeing question; it is a separate harm domain. The label propagates into the Abstract, Results, Discussion, and Conclusion.
3. The **RCT is labelled "positive"** although its primary gait outcomes were null (p=0.57/0.90/0.62). The direction came from the authors' interpretive sentence.

### 3.5 Extraction and data integrity

- Raw HTML from abstracts reaches tables and prose: `results_summary` contains `</b>`, `<i>F</i>`. `_strip_html` (`extractor.py:330`) is applied only when the full text looks like an HTML page (`:371-376`), not to summary fields.
- `participant_ratio=1.00` in the extraction-completeness gate, while the manuscript states that 2 of 6 studies lacked N (`orchestration/helpers/extraction_metrics.py:56`). The gate and the writer read different fields or inference paths.
- Table 1 and Appendix B list 4 of 6 studies. `build_compact_study_table` (`export/markdown_refs.py:977-1072`) iterates the `papers` list passed in, and 2 included NEISS studies were missing from it or filtered. The caption then says "Summary of 4 included studies", so the table self-describes its truncation instead of failing. Design labels are title-cased raw enums ("Rct", "Pre Post"): `_DESIGN_SHORT` keys (`:1036-1041`) don't match enum values.
- `run_summary.json`: `rag_sections_success: 7` > `rag_sections_total: 6`.
- `writing_manifests.grounding_hash == citation_catalog_hash` for every row (`f8dbfc926a362b64`), and `evidence_source_ids=[]`. Either one hash is written to both fields or the catalog hash is derived from grounding. Either way the manifest cannot distinguish the two inputs.

---

## 4. Scoring/grading steps that a cheap typed decision model (Jev) could handle

Jev fits bounded label and score decisions over a provided state (≤ ~32K tokens), with calibrated probabilities. It cannot write prose. Candidates, in order of value and risk:

| Step | Today | Jev question shape | Why it fits / caveats |
|---|---|---|---|
| Per-study effect direction per outcome domain (`synthesis/narrative.py:126-181`) | Flash LLM + keyword fallback, one label per study | `choice` per (study, domain): `BENEFIT / HARM / NULL / MIXED / NOT_REPORTED` with the domain's direction of benefit in criteria | Direct replacement. Removes the keyword fallback and forces domain-scoped votes (fixes section 3.4 item 2) |
| CASP / MMAT / JBI item judgments (`quality/casp.py`, `mmat.py`) | Pro-model LLM per study, bool fields | Fan-out of `choice` (`YES / NO / CANT_TELL`) per checklist item, anchored "For item C3:" | Adds the missing "can't tell" state (all-NO today). Keep the Pro model only for the free-text overall summary, or render it deterministically |
| RoB 2 / ROBINS-I signalling questions (`rob2.py`, `robins_i.py`) | Pro LLM → domain judgments | `choice` per signalling question (Y/PY/PN/N/NI) → **deterministic** RoB 2 algorithm maps answers to domain and overall judgments | Moves judgment arithmetic into code (Cochrane algorithm) and leaves only the reading-comprehension step to Jev. Escalate on confidence < 0.85 |
| GRADE inconsistency / indirectness domains (`grade.py:190-193`, currently hardcoded 0) | none | `choice` `NOT_SERIOUS / SERIOUS / VERY_SERIOUS` per outcome domain with PICO and study PICO as state | Fills domains that are silently zero today. Final certainty stays deterministic |
| Study design classification (`extraction/study_classifier.py`) | Flash LLM raw JSON | `choice` over the `StudyDesign` enum | Classic classifier task, and it drives RoB routing |
| Full-text exclusion reason (`dual_screener` adjudicator) | LLM free label | `choice` over the `ExclusionReason` enum, final decision only | Also forces one canonical reason per paper (fixes section 3.1 item 1 at the source) |
| Batch pre-rank relevance (`screening/batch_ranker.py`) | Flash LLM score | `score` rubric 0–4 per paper, fan-out ≤ 13 per call | Already probed in `00-jev-reference.md` (3/3 correct). Keep the recall-first threshold |
| Section ratchet semantic sub-scores (`section_validation.compute_section_quality_score`) | Counts only | `noul` per section: "contains a claim contradicted by the FACTUAL DATA BLOCK", "overclaims beyond GRADE certainty", "introduces a study not in catalog" | Adds the missing semantic axis to the lexicographic key. Use it as an extra tier, never to accept a draft |
| Reviewer-audit finding verification (`manuscript/reviewer.py`) | Pro LLM generates findings | Keep generation on the main LLM. Use Jev `noul` to **verify** each finding against DB facts ("Is finding #k supported by the canonical counts?") before it is blocking | Cuts false positives (the "no dose-response study" finding in the sample) and turns advisory findings into trustworthy blockers |
| Claim ↔ citation support (`orchestration.py:374-403`, ledger) | `evidence_score=1.0` constant | `choice` `SUPPORTS / PARTIAL / UNRELATED` for (claim sentence, cited study key finding / chunk) | Converts lineage from syntactic to semantic. Store the probability as `evidence_score` |
| Humanizer flag scan (`humanizer_checks.py`) | word blocklists | `score` "AI-boilerplate density" per paragraph | Replaces blocklists with a category judgment, consistent with `llm-output.mdc` |

Not suitable for Jev: section prose, outline, humanizer rewrite, contradiction resolution text, diagrams, and any statistic (those stay in scipy/statsmodels).

---

## 5. Re-architecture recommendations (ranked by impact on robustness and output quality)

1. **Make gates block by default and make the run status honest.**
   - Set `audit_gate_mode` to block for `methods_to_results_coherence` findings. Add `ABSTRACT_UNDER_MINIMUM`, `EXTRACTION_YIELD_LOW`, `GRADE_UNGROUNDED`, and `QUALITY_ASSESSMENT_CORRUPTED_INPUT` to `SOFT_BLOCK_CODES`.
   - Add a terminal status such as `done_with_blockers` so a manuscript with 8 blocking findings is never labelled `done`.
   - Make `ReadinessScorecard.ready` the value surfaced in `run_summary.json` and the UI.
   - *Impact: highest; zero generation cost.*

2. **Single canonical `ManuscriptFacts` IR, rendered deterministically, never re-derived.**
   - Build one typed object after synthesis containing PRISMA counts (with automation boxes and per-paper final reasons), the cohort list with display labels, design counts, N totals, RoB per study, GRADE per outcome domain, figure/table registry with numbers, and database status.
   - Every fact-bearing sentence (Selection Process, Study Selection, Study Characteristics table, abstract Methods/Results numbers, figure refs) is rendered from this IR by templates. The LLM writes only interpretive prose, referencing facts by slot IDs (`{fact:included_n}`, `{fig:prisma}`) that are resolved at render time.
   - Delete `grounding_patches.py` keyword branches, the export-time table rebuilds that disagree, and the `_extract_count` regex checks: numbers can no longer drift.
   - This is the extension of `src/models/manuscript_ir.py` ("canonical disclosures IR") that the codebase already started.
   - *Fixes: 4-vs-6 table, reason tally text, 194 vs 209, figure numbering, "three vs four".*

3. **Fix the PRISMA and screening data model at the source.**
   - Full-text reasons: one row per paper from the final decision (join `dual_screening_results`, or persist `final_exclusion_reason`).
   - Report keyword/metadata prefilter exclusions as `automation_excluded`.
   - Store not-retrieved as a status, not as an exclusion.
   - Extend `arithmetic_valid` with `sum(reasons) == excluded_total` and `automation_excluded == count(reviewer_type IN ('keyword_filter','batch_ranker','metadata'))`.
   - Add a unit test built from this sample's DB shape.

4. **Correct the methodology layer.**
   - Route cross-sectional designs to JBI or AXIS (quantitative), keep CASP for qualitative, and add "can't tell".
   - GRADE per pre-specified outcome domain across studies, with CASP/MMAT/JBI mapped to RoB downgrades and inconsistency/indirectness judged (Jev) instead of hardcoded to 0.
   - Pre-specify the fixed or random-effects model in config and use HKSJ CIs for k < 10.
   - Vote-count per outcome domain with a declared direction of benefit, and keep harms as a separate domain.

5. **Replace post-hoc rewriting with fail-fast IR repair.**
   - Remove `humanizer_guardrails` lexical substitutions and the n-gram deletion regex.
   - Move the humanizer (or drop it) **before** IR validation, operating on `StructuredSectionDraft.blocks` with `complete_validated`, so the rendered text is always the validated text.
   - Replace `_keyword_direction`, the `DOMAIN_SCOPE_DRIFT` substring scan, and the phrase lists with structural or Jev category checks. Scope the domain-drift check to prose sections, excluding appendices and tables.

6. **Every fallback must be observable.**
   - Route `section_loop.py:578-590` placeholders and `_build_minimum_compliant_abstract` through `fallback_events`, and set `writing_manifests.fallback_used=1`, so `SECTION_DETERMINISTIC_FALLBACK` fires.
   - Strip foreign-domain leftovers from fallback templates.
   - Fix the manifest hash fields and populate `evidence_source_ids`.
   - Heuristic RoB rows should render as "not assessed", not "NO".

7. **Semantic citation lineage.**
   - Replace `evidence_score=1.0` with a Jev (or cheap LLM) SUPPORTS/PARTIAL/UNRELATED verdict per claim–citation pair, using the study's key finding or RAG chunk as state.
   - Gate on the rate of UNRELATED and PARTIAL verdicts. Require citations at claim level: IR blocks already carry `citations`, so stop appending bundled `[1], [2]` to paragraph ends.

8. **Unify the LLM call path.**
   - Move screening, study classifier, narrative direction, reranker, and contradiction resolver onto `complete_validated`.
   - Delete the raw `complete()` fallbacks in `extractor.py:626-628` and `quality/runner.py:85-87`, which skip cost logging. Fail closed if `provider` is missing.

9. **Full-text retrieval as a first-class quality gate.**
   - Add a configurable ceiling (for example, block or require HITL when non-retrieval exceeds 40% of sought).
   - Surface per-tier retrieval diagnostics. With 87% non-retrieval the synthesis is not credible regardless of prose quality.
   - Sanitize HTML in all extraction text fields (not only full-text pages), and fix design-label rendering.

10. **Rebalance spend toward evidence.**
    - Make custom AI image diagrams opt-in (34% of run cost, and low methodological value).
    - Cap humanizer passes (22%).
    - Redirect budget to a Pro-model second extraction pass or dual RoB appraisal, which directly improves the evidence tables.

### Suggested order

Items 1, 3, and 6 first (small, deterministic, and they make the pipeline honest). Then item 2, the structural fix that eliminates the largest defect class. Then item 4 (methodology) and item 5 (remove anti-patterns once item 2 makes them unnecessary). Items 7–10 follow, with Jev surfaces from section 4 introduced in shadow mode per `00-jev-reference.md` rules.
