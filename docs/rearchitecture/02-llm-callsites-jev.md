# 02 — LLM layer, call-site inventory, and Jev offload plan

Scope: `src/llm/**`, `config/settings.yaml`, every LLM call site under `src/`.
Companion: `00-jev-reference.md` (Jev API facts and the off/shadow/on rules).
Method: `rg` over `complete_validated(`, `complete(`, `complete_with_usage(`,
`complete_validated_parts(`, `get_chat_client(`, `get_image_client(`, `run_text_with_web_tools(`,
`run_native_structured_json(`, `build_agent(`, `reserve_call_slot`, `log_cost`, plus real
`cost_records` from the only completed run (read with `sqlite3 file:...?immutable=1`).

---

## 0. TL;DR

- Jev-suitable work in the one completed run (wf-0001) cost about **$0.09 of $1.21 (about 7%)**.
  The expensive phases are prose (humanizer $0.27, section writing $0.24, outline $0.07) and
  Gemini image generation ($0.41), and Jev can't do any of those.
- The case for Jev is mainly **latency, recall and reviewer independence**, not dollars:
  - Screening currently takes about 6 s per batch call. The adjudicator runs per paper.
  - Screening is capped at `max_llm_screen: 200` purely for cost.
  - Reviewer A and reviewer B are the **same model at the same temperature**, so their errors
    are correlated.
- Top candidates: title/abstract screening, the batch pre-ranker, the RAG reranker (34 s average
  latency), per-domain RoB judgments, and study-design classification. Detail in section 3.
- Found while looking: plain-text calls to DeepSeek run with **thinking mode on**. For example,
  the reranker emits about 3.5K output tokens to return a list of 20 integers. Fixing this
  doesn't need Jev and probably saves more than Jev would on those surfaces.

---

## 1. LLM layer architecture

### 1.1 Modules

| File | Role |
|---|---|
| `src/llm/registry.py` | Maps model prefix to env key and genai-prices provider id. `build_agent()` builds a PydanticAI `Agent` with explicit API key. `rate_tier_for_model()` guesses the tier from substrings of the model string. |
| `src/llm/pydantic_client.py` | `PydanticAIClient`: `complete`, `complete_text`, `complete_with_usage`, `complete_validated`, `complete_validated_parts` (multimodal). Handles transient retry and structured-output strategy per provider. |
| `src/llm/factory.py` | Cached `get_chat_client(timeout)`, `get_embedder`, `PydanticAIImageClient` (ImageGenerationTool), `run_text_with_web_tools` (WebSearch/WebFetch, streaming progress), `run_native_structured_json`. |
| `src/llm/provider.py` | `LLMProvider`: agent config lookup (`settings.agents[name]`), `reserve_call_slot()` (rate limiter), `estimate_cost_usd()` (genai-prices, then `llm.price_fallback_per_mtok`, then 0.0), `log_cost()` writes a `CostRecord` to `cost_records`. Starts a genai-prices updater thread at import (hourly GitHub fetch). |
| `src/llm/rate_limiter.py`, `shared_rate_limiter.py` | Sliding-window RPM per tier (`flash`/`flash-lite`/`pro`), shared across the process and keyed by a hash of `GEMINI_API_KEY`. |
| `src/llm/model_fallback.py` | `get_fallback_model(tier)` maps a tier to an agent key in settings.yaml. |
| `src/llm/base_client.py` | `LLMBackend` protocol (`complete`). |

### 1.2 Providers and model tiers (`config/settings.yaml`)

All chat traffic goes to Fireworks except the diagram drawing and critic steps (Google).

| Model | Price in/out per MTok | Agents |
|---|---|---|
| `fireworks:.../deepseek-v4-flash-0731` | 0.14 / 0.28 | screening_reviewer_a, screening_reviewer_b, search, study_type_detection, abstract_generation, config_generation, batch_screener, concept_diagrams, research_diagram_preparer, research_diagram_placement, narrative, citation_matching, `rag.hyde_model`, `rag.reranker_model` |
| `fireworks:.../gpt-oss-120b` | 0.15 / 0.60 | screening_adjudicator |
| `fireworks:.../deepseek-v4-pro-0813` | 1.32 / 3.96 | extraction, quality_assessment, writing, humanizer, contradiction_resolver, criteria_refinement |
| `fireworks:.../minimax-m3` | 0.30 / 1.20 | table_extraction, `extraction.pdf_vision_model` |
| `google:gemini-3.1-flash-image-preview` | genai-prices | research_diagram_drawing |
| `google:gemini-2.5-flash` | genai-prices | research_diagram_critic |
| `sentence-transformers:lightonai/DenseOn` | local | `rag.embed_model` (logged at $0) |

Rate limits are `flash_rpm 60`, `flash_lite_rpm 120` and `pro_rpm 20`. The tier comes from
substring rules: `minimax` maps to pro, `gpt-oss` to flash, `deepseek-v4-pro` to pro.

### 1.3 Structured output, validation, and retries

- **Structured output strategy**:
  - Gemini uses `NativeOutput(StructuredDict(schema))`.
  - Everything else uses `StructuredDict` (tool calling).
  - DeepSeek on the `deepseek:` prefix, or Fireworks models with "deepseek" in the id, gets
    `extra_body={"thinking":{"type":"disabled"}}`, but **only when a JSON schema is passed**.
- **Three retry layers stack**:
  1. PydanticAI agent: `retries=3, output_retries=3`.
  2. `complete_validated` re-prompts with the validation error appended
     (`max_validation_retries=2`, so 3 attempts).
  3. `_run_with_retry`: 5 attempts with exponential backoff (2 s base, 90 s cap, jitter).
     It honours `Retry-After`. It only retries when the exception string matches
     `429/502/503/504` or `unavailable|resource_exhausted|rate|overloaded|gateway|quota`.
- **Cost logging**: call sites time the call themselves, then call
  `provider.estimate_cost()` and `provider.log_cost(...)`. Some sites (hyde, reranker,
  submission_packager) write a `CostRecord` directly through the repository. Nothing is logged
  centrally inside the client.

---

## 2. Real cost data (wf-0001, the only completed run)

Registry: `runs/workflows_registry.db`. It has three rows; wf-0002 and wf-0003 are config drafts
with no `cost_records`. wf-0001 is the pickleball review.

- Candidate pool: 1716 papers.
  - 1328 were removed by the keyword filter.
  - 209 went to dual review.
  - 21 title/abstract disagreements went to adjudication.
- 7 full-text dual reviews; 6 papers ended up `included_primary`.
- Totals: **145 calls, $1.205**.

| Phase | Model | Calls | Tokens in | Tokens out | USD | Avg latency |
|---|---|---:|---:|---:|---:|---:|
| phase_6f_custom_diagram_drawing | gemini-3.1-flash-image | 3 | 1,976 | 6,812 | 0.410 | 14.8 s |
| phase_6_humanizer | ds-v4-pro | 6 | 61,085 | 46,772 | 0.271 | 78.1 s |
| phase_6_writing | ds-v4-pro | 11 | 127,158 | 16,684 | 0.237 | 17.9 s |
| extraction | ds-v4-pro | 6 | 47,321 | 4,540 | 0.080 | 8.9 s |
| phase_6_writing_outline | ds-v4-pro | 6 | 41,003 | 4,123 | 0.071 | 8.8 s |
| phase_7_audit | ds-v4-pro | 3 | 16,243 | 4,220 | 0.038 | 17.0 s |
| phase_3_screening (A/B batched) | ds-v4-flash | 42 | 156,004 | 42,002 | 0.034 | 6.2 s |
| phase_3_screening (adjudicator) | gpt-oss-120b | 25 | 69,762 | 10,518 | 0.016 | — |
| quality_casp | ds-v4-pro | 4 | 5,266 | 1,027 | 0.011 | 3.7 s |
| phase_6_rerank | ds-v4-flash | 7 | 11,981 | 24,197 | 0.0085 | **34.2 s** |
| phase_6f_custom_diagram_critic | gemini-2.5-flash | 3 | 1,418 | 3,233 | 0.0085 | 8.3 s |
| screening_batch_ranker | ds-v4-flash | 4 | 26,596 | 9,934 | 0.0065 | 16.5 s |
| quality_rob2 | ds-v4-pro | 1 | 1,980 | 466 | 0.0045 | 5.6 s |
| quality_mmat | ds-v4-pro | 1 | 1,005 | 339 | 0.0027 | 4.8 s |
| phase_4_extraction_quality (study classifier) | ds-v4-flash | 6 | 15,505 | 1,220 | 0.0025 | 4.1 s |
| phase_6_hyde | ds-v4-flash | 5 | 2,332 | 5,629 | 0.0019 | 10.2 s |
| phase_6f_custom_diagram_preparer | ds-v4-flash | 1 | 2,924 | 1,730 | 0.0009 | 15.8 s |
| phase_6e_concept_diagram | ds-v4-flash | 3 | 1,323 | 2,149 | 0.0008 | 5.6 s |
| phase_5_narrative_direction | ds-v4-flash | 6 | 3,002 | 567 | 0.0006 | 1.7 s |
| phase_6f_custom_diagram_placement | ds-v4-flash | 1 | 2,260 | 321 | 0.0004 | 3.4 s |

**Scaling.** wf-0001 is a small review. For a typical 30-study review:

- Per-included-study phases scale roughly 5×. That covers extraction (about $0.40), quality
  (about $0.09) and the study classifier (about $0.013).
- Title/abstract screening is bounded by `max_llm_screen: 200` plus up to 50 overflow papers,
  so it stays near $0.05 to $0.08.
- Full-text screening scales with the number of full-text candidates.
- Writing is roughly fixed per run.

**Signs that DeepSeek thinking mode is on.** The reranker averages 3,457 output tokens to
return a JSON list of 20 indices. HyDE produces 1,126 tokens for a 100 to 200 word passage.
Both are plain-text calls (`json_schema=None`), so `_model_settings` never disables thinking.
The humanizer (7.8K output tokens per call, $0.27) goes through the same path. This needs
verifying with a single probe, but it is the cheapest optimisation available.

---

## 3. Call-site inventory

Legend:
- **Task type**: C = classification, S = scoring/ranking, E = extraction, G = generation,
  J = judge/critique.
- **Volume**: per-paper, per-batch, per-section, or per-run.
- **Jev** rating: HIGH means a direct fit with a typed answer. MED means the decision part fits
  but a prose field must be templated or kept on the LLM. LOW means prose, long context, or
  multimodal.

| # | File:function | Phase (cost tag) | Type | Output schema | Agent / model | Volume per run | Jev | Rationale |
|---|---|---|---|---|---|---|---|---|
| 1 | `screening/dual_screener.py` `_run_reviewer` / batch path (via `gemini_client.PydanticAIScreeningClient.complete_batch_screening_with_usage`) — title/abstract | phase_3_screening | C | `BatchScreeningResponsePayload` → items like `ScreeningResponsePayload` (decision include/exclude/uncertain, confidence, reasoning, exclusion_reason) | screening_reviewer_a, screening_reviewer_b / ds-v4-flash | Per paper, batched 10 per call. At most 200+50 papers × 2 reviewers. wf-0001: 42 calls | **HIGH** | `choice` INCLUDE/EXCLUDE/UNCERTAIN with inclusion and exclusion criteria as named criteria. Jev's live probe got 3 of 3 correct. `exclusion_reason` can be a second `choice` over the `ExclusionReason` enum. The prose `reasoning` field is audit-trail only and can be templated or dropped. |
| 2 | same — full-text stage | phase_3_screening | C | same | same | Per full-text candidate (7 in wf-0001; typically 30 to 100) | **MED** | Full text exceeds Jev's roughly 32K effective context. Would need section-chunked questions (methods, population). Cochrane MECIR C39 requires dual review here. Use Jev as a triage signal only. |
| 3 | `screening/dual_screener.py` `_run_adjudicator` | phase_3_screening | J/C | `ScreeningResponsePayload` | screening_adjudicator / gpt-oss-120b | Per disagreement (25 in wf-0001, about 10% of dual-reviewed papers) | LOW–MED | These are the hardest cases by construction. Keep the LLM. At most, a Jev vote could be added as a feature. |
| 4 | `screening/batch_ranker.py` `BatchLLMRanker._rank_batch` | screening_batch_ranker | S | `BatchRankerResponsePayload` (id, score 0 to 1, reason) | batch_screener / ds-v4-flash | Per batch of 80 papers (4 calls in wf-0001) | **HIGH** | Relevance score is a direct fit: a `score` rubric per paper or a `choice` HIGH/MED/LOW. Split into fan-outs of about 20 to 25 papers because of Jev latency at 48 or more questions. |
| 5 | `screening/dual_screener.py` `screen_batch_for_calibration` (runner phase `screening_calibration`) | phase_3_screening | C | same as #1 | reviewers A/B | 15 papers × 1 iteration | HIGH | Same task as #1. This is also where Jev's threshold could be calibrated per run. |
| 6 | `screening/criteria_refinement.py` `refine_criteria` | criteria_refinement | G | `_RefinementLLMResponse` (list of criteria text) | criteria_refinement / ds-v4-pro | Per human-correction batch (rare; HITL) | LOW | Generates new criterion text. |
| 7 | `extraction/study_classifier.py` `StudyClassifier.classify` | phase_4_extraction_quality | C | `StudyClassificationResult` (StudyDesign enum, confidence, reasoning) | study_type_detection / ds-v4-flash | Per included paper (6) | **HIGH** | `choice` over the StudyDesign enum. The existing low-confidence fallback maps directly onto Jev confidence. Heuristic pre-checks (DOI, title) already exist. |
| 8 | `extraction/extractor.py` `_llm_extract` (line about 601) | extraction | E | `_ExtractionLLMResponse` (free-text fields plus a list of outcomes) | extraction / ds-v4-pro | Per included paper; long full text | LOW | Span and number extraction with free text; context above 32K. Small typed sub-fields (country, setting type, funding type) could move to Jev later. |
| 9 | `extraction/table_extraction.py` | phase_4_pdf_vision_table_extraction | E (multimodal) | `_TableOutcomePayloadEnvelope` | table_extraction / minimax-m3 | Per paper with a PDF | LOW | Vision input. |
| 10 | `quality/rob2.py` → `quality/runner.py` `run_validated` | quality_rob2 | J/C | `_Rob2LLMResponse` (5 domains × low/some_concerns/high, plus rationales and overall) | quality_assessment / ds-v4-pro | Per RCT | **MED** | Each domain is a `choice` with the signalling questions as criteria. The overall judgment is deterministic by the RoB 2 algorithm and shouldn't come from an LLM at all. Rationales are prose, so template them from Jev's winning criterion or keep the LLM for non-"low" domains. |
| 11 | `quality/robins_i.py` | quality_robins_i | J/C | `_RobinsILLMResponse` (7 domains × low/moderate/serious/critical/no_information) | quality_assessment | Per non-randomized study | **MED** | Same pattern as #10. |
| 12 | `quality/casp.py` | quality_casp | J/C | `_CaspLLMResponse` (8 booleans plus summary) | quality_assessment | Per qualitative study | **HIGH** | 8 yes/no questions map to `noul` fan-out over one state. The summary can be templated. |
| 13 | `quality/mmat.py` | quality_mmat | J/C | `_MmatLLMResponse` (7 booleans plus summary) | quality_assessment | Per mixed or other study | **HIGH** | Same as #12. |
| — | `quality/grade.py` | — | — | — | none | — | n/a | Already deterministic. |
| 14 | `synthesis/narrative.py` `_classify_direction_llm` | phase_5_narrative_direction | C | `_DirectionLLMResponse` (positive/negative/mixed/null) | narrative / ds-v4-flash | Per study × outcome | **HIGH** | Textbook `choice`. The current fallback is a keyword heuristic. |
| 15 | `rag/hyde.py` `generate_hyde` | phase_6_hyde | G | plain text | `rag.hyde_model` (ds-v4-flash, temperature hardcoded 0.7) | Per section (about 5) | LOW | Generates a hypothetical passage. |
| 16 | `rag/reranker.py` `rerank_chunks` | phase_6_rerank | S | plain text, parsed with `find('[')` | `rag.reranker_model` (ds-v4-flash) | Per section (7) | **HIGH** | 20 chunks × `score` relevance to the section query is one fan-out over a shared state. Expect about 0.3 to 1 s instead of 34 s. |
| 17 | `writing/outline_generator.py` | phase_6_writing_outline | G | `SectionOutline` | writing / ds-v4-pro | Per section | LOW | Structured plan whose content is prose. |
| 18 | `writing/section_writer.py` (sections, `StructuredSectionDraft`; abstract, `StructuredAbstractOutput`) | phase_6_writing | G | as named | writing, abstract_generation | Per section × ratchet iteration (at most 2) | LOW | Prose. The ratchet score (`section_validation.py`) is already deterministic. |
| 19 | `writing/humanizer.py` `humanize_async`, `humanize_repair_async` | phase_6_humanizer | G | plain text | humanizer / ds-v4-pro | Per section × `humanization_iterations: 2` | LOW | Prose rewrite. Biggest text cost; see the thinking-mode note in section 2. |
| 20 | `writing/contradiction_resolver.py` `generate_contradiction_paragraph` | writing_contradiction_resolver | G | plain text | contradiction_resolver / ds-v4-pro | Per run (0 or 1) | LOW | Prose. |
| 21 | `manuscript/reviewer.py` profile selection (line about 402) | phase_7_audit | C | `ManuscriptAuditProfileSelection` (list of profile enum) | writing (reserve) / temperature hardcoded 0.0 | Per run (1) | **HIGH** | Multi-label pick from a fixed enum; could be one `noul` per profile. Tiny cost. |
| 22 | `manuscript/reviewer.py` profile review (line about 512) | phase_7_audit | J | `_ReviewerResponse` (verdict plus findings with evidence text) | per-profile agent | Per profile (at most 2) | LOW | Findings require quoted evidence and recommendations. The manuscript is above 32K. Only the verdict fits Jev, and it isn't used for gating. |
| 23 | `visualization/concept_diagrams.py` | phase_6e_concept_diagram | G | plain text (diagram spec) | concept_diagrams | Per run (3) | LOW | Generation. |
| 24 | `visualization/research_diagram_preparer.py` | phase_6f_custom_diagram_preparer | G | `DiagramBriefPack` | research_diagram_preparer | Per run (1) | LOW | Generation. |
| 25 | `visualization/research_diagram_placement.py` | phase_6f_custom_diagram_placement | C + E | `_PlacementEnvelope` (target_section enum plus anchor_text) | research_diagram_placement | Per run (1) | MED | Section choice fits Jev; `anchor_text` must be copied from the draft. |
| 26 | `visualization/research_diagram_renderer.py` drawing (`get_image_client().generate`) | phase_6f_custom_diagram_drawing | G (image) | bytes | gemini-3.1-flash-image | Per diagram × rounds | LOW | Image generation. Largest single cost ($0.41). |
| 27 | `visualization/research_diagram_renderer.py` critic (`complete_validated_parts`) | phase_6f_custom_diagram_critic | J (multimodal) | `_CritiqueEnvelope` (3 scores plus issues) | gemini-2.5-flash | Per diagram round | LOW | Needs image input. Jev is text-only as far as we know. |
| 28 | `export/submission_packager.py` LLM citation resolver (line about 501) | not tagged (logged only if db_path) | C | untyped `{num: citekey}` dict, parsed with `ast.literal_eval` fallback | citation_matching / ds-v4-flash | Per run, only on unresolved citations | MED | Per unresolved number, a `choice` among candidate citekeys fits well. Current code is untyped and doesn't follow the contract. |
| 29 | `web/config_generator.py` `generate_config_yaml` (web research, then `run_native_structured_json` / `complete`) | none (no cost logging; pre-run) | G | `_GeneratedConfig` / `_GeneratedScopingConfig` | config_generation / ds-v4-flash | Per draft | LOW | Generates PICO, keywords and queries. `evaluate_config_quality_yaml` rubric checks could later use Jev `score`. |
| 30 | `rag/embedder.py` (`get_embedder`) | phase_4b_embedding | embedding | vectors | local sentence-transformers | Per chunk batch | n/a | Not an LLM decision. |
| — | `protocol/generator.py`, `search/strategy.py`, `knowledge_graph/*`, `citation/ledger.py` | — | — | — | none | — | n/a | Deterministic; no LLM calls found. Search queries are produced once by config_generator (#29). |

### 3.1 Jev candidates ranked by cost savings

Based on wf-0001 dollars, with the 30-study extrapolation in brackets. Jev's own price is unknown:
it returns no `usage.cost`, so compute it from tokens once a price is confirmed. Savings are shown
as incumbent spend removed.

| Rank | Surface | Incumbent $ per run | Other gains |
|---|---|---|---|
| 1 | Title/abstract dual screening A/B (#1, #5) | $0.034 [about $0.05–0.08, capped] | 6 s → about 0.2 s per decision; could remove the `max_llm_screen` cap (recall); independent model family |
| 2 | Quality: CASP/MMAT booleans, RoB2/ROBINS-I domains (#10–13) | $0.018 [about $0.09] | Deterministic overall judgment; removes the RoB 2 schema-default bias (section 5) |
| 3 | RAG rerank (#16) | $0.0085 [same] | 34 s → under 1 s per section, which is about 4 minutes off writing wall time |
| 4 | Batch pre-ranker (#4) | $0.0065 [about $0.01] | 16.5 s per batch |
| 5 | Study-design classifier (#7) | $0.0025 [about $0.013] | Typed, calibratable confidence |
| 6 | Narrative direction (#14), audit profile selection (#21), citation matching (#28), diagram placement section (#25) | under $0.002 combined | Removes keyword or `ast.literal_eval` fallbacks |

The Jev-addressable total is about $0.07 to $0.09 per small run, or about $0.25 for a 30-study
run. For comparison, turning off thinking on plain-text DeepSeek calls (humanizer, rerank, HyDE)
could remove a large share of the $0.28 those three spend, with no quality risk. Do that first.

---

## 4. Quality risks and shadow-mode designs

### 4.1 Where offloading could hurt

1. **Screening recall.** A false exclude at title/abstract is permanent, because the PRISMA flow
   never revisits it. Jev's confidence is normalized max-probability, not calibrated. Its bias
   direction depends on the task. Any exclude-acting path needs calibration per surface and a
   recall target of at least 0.95 on includes.
2. **Full text over 32K.** Truncating to fit loses methods and results detail. Keep Jev to
   title/abstract or to section-chunked questions.
3. **Audit trail.** `screening_decisions.reasoning` and RoB rationales appear in exports and
   the manuscript. Replacing them with templates weakens reviewer-facing justification. Keep an
   LLM rationale wherever the judgment is non-trivial (exclude with low confidence, any
   "high"/"serious" domain).
4. **Methodology optics.** MECIR and PRISMA describe the reviewers. If Jev becomes a reviewer,
   the Methods section and protocol must disclose it. Tie this into the `src/manuscript/
   prisma_disclosure.py` and `manuscript_ir` disclosures.
5. **Fan-out collapse.** Without the "For paper #N" anchor, answers converge. Batched prompts
   must follow the anchoring rule in `00-jev-reference.md`.
6. **Silver labels.** Calibration data today is LLM-versus-LLM. `screening_corrections` (human)
   has 0 rows in wf-0001, so agreement with the incumbent isn't proof of correctness.

### 4.2 Calibration data already in the DB

- `dual_screening_results`: 1,605 rows in wf-0001.
  - 1,527 title/abstract agreements, but most are keyword-filter auto-excludes.
  - The LLM-reviewed subset is 209 papers, with 21 disagreements plus 4 at full text.
- `screening_decisions`: per-reviewer decision and confidence (reviewer_a, reviewer_b,
  adjudicator, batch_ranker, keyword_filter).
- `study_cohort_membership.synthesis_eligibility`: final truth for included and excluded.
- `decision_log` (actor `study_classifier_agent`): predicted design plus confidence.
- `rob_assessments`, `casp_assessments`, `mmat_assessments`: per-domain judgments with
  `assessment_source` and `fallback_used`.

Only one completed run exists. Replay more runs (`run --config <snapshot> --fresh`) with shadow
mode on to build at least 500 labeled title/abstract pairs before any flip.

### 4.3 Designs

**A. Screening, three-stage rollout.**
1. *Shadow*: for every paper sent to reviewer A, also send a Jev `choice` (anchored fan-out
   of 10 to 20 papers per state, criteria from the review config). Persist to a new typed table
   `jev_shadow_decisions(workflow_id, surface, item_id, stage, answer, confidence, probabilities_json,
   incumbent_answer, incumbent_confidence, latency_ms, tokens_in, tokens_out, model)`. Also log
   to `cost_records` with phase `jev_shadow_screening`.
   Report:
   - Cohen's kappa of Jev against A, against B, and against the final decision.
   - Recall on final includes.
   - A reliability curve (confidence bucket against agreement).
   - Coverage-versus-error at thresholds from 0.80 to 0.99.
2. *Jev as reviewer B (independent second reviewer)*: reviewer A (DeepSeek) plus Jev.
   - Agreement: accept the decision.
   - Disagreement, or Jev confidence below τ: run the incumbent reviewer B, then the
     adjudicator as today.
   - This fixes the same-model correlation between A and B and cuts about half of the A/B calls.
   - Keep `exclude_fast_path_requires_dual: true`. Jev now counts as the second reviewer.
3. *Pre-ranker replacement*: swap the batch ranker (#4) for Jev `score`. The existing
   `batch_screen_validation_*` sample becomes a free recall audit.
   - Once recall holds, raise `max_llm_screen`. It exists only for cost, and Jev makes the tail
     cheap.

Promotion gate:
- Recall on includes at or above 0.97 against final decisions.
- Kappa against the final decision at or above the current A-versus-B kappa.
- No regression in included-study count on replay.

**B. Quality instruments.**
- Shadow Jev domain `choice` or `noul` answers against the DeepSeek-Pro judgments already in
  `*_assessments`.
- In `on` mode:
  - Jev answers each domain.
  - The overall judgment is computed deterministically (RoB 2 and ROBINS-I algorithms).
  - The LLM is called only for domains where Jev confidence is below τ or the judgment is not
    low risk, and it supplies the rationale for those.
- Track the per-domain confusion matrix. Pay particular attention to low-versus-some_concerns,
  where LLM defaults currently bias the result (section 5).

**C. Rerank.**
- Shadow: record the Jev order next to the LLM order.
- Compare NDCG@8 between them, and check which chunks were actually cited in
  `section_drafts`/`evidence_links`.
- Promote once citation-hit parity holds. Fail open to the original hybrid order, as now.

**D. Small classifiers (study design, narrative direction, audit profiles).**
- Shadow with a direct agreement rate.
- Flip once agreement is at or above 0.9 on 50 or more items and the disagreements are reviewed
  by hand.
- The keyword fallbacks stay as the final fallback.

All surfaces follow the rules in `00-jev-reference.md`:
- `off|shadow|on` per surface in `settings.yaml`.
- Fail open to the incumbent.
- Model id in config.
- Every call logged to `cost_records`.

A clean seam: add a `JevClient` in `src/llm/jev_client.py` behind a small
`DecisionBackend` protocol (`decide(state, questions) -> typed answers`), next to
`PydanticAIClient` rather than inside it. Jev isn't a PydanticAI model.

---

## 5. Weaknesses in the LLM layer

1. **`_is_retryable` matches substrings loosely.** `"rate"` matches "moderate", "generate",
   "separate" and "accurate". `"quota"` also matches a hard billing exhaustion. Non-transient
   errors (for example a validation message quoting a ROBINS-I "moderate" judgment) can be retried
   5 times with backoff up to 90 s. Match on the exception type or HTTP status instead.
2. **Retry layers multiply.** PydanticAI `retries=3/output_retries=3`, times
   `complete_validated` (3 attempts), times transient retry (5), gives a worst case of dozens of
   provider calls behind one logical call. There is no global budget per call, and latency is
   unbounded in practice.
3. **Thinking mode is only disabled for structured calls.** `_model_settings(structured=False)`
   leaves DeepSeek V4 thinking on for HyDE, the reranker, the humanizer, the contradiction
   resolver and concept diagrams. Evidence: rerank averages 3,457 output tokens and 34 s.
4. **Missing `workflow_id` in cost records.** 112 of 145 rows in wf-0001 have
   `workflow_id=''`. `provider.log_cost(...)` is called without `workflow_id` in these places:
   - `dual_screener.py`
   - `study_classifier.py`
   - `quality/runner.py`
   - `extractor.py`
   - `batch_ranker.py`
   - humanizer, section writing and outline paths
   - `contradiction_resolver.py`

   Per-DB queries still work, but anything that keys on `workflow_id` (global history
   aggregation, exports) under-attributes cost.
5. **Gaps in cost logging.**
   - `web/config_generator.py` logs nothing (pre-run, no DB).
   - `submission_packager.py` logs only when `db_path` is set, and its phase isn't
     standardized.
   - Failed calls are never logged, although their tokens were spent. This includes validation
     failures after all retries, and the batch reviewer failure that falls back to per-paper
     calls, so the retry spend there goes unlogged too.
   - Legacy `complete_json` paths estimate tokens by word count.
6. **Rate limiting is incomplete and mis-keyed.**
   - The shared limiter is keyed by `GEMINI_API_KEY`, while almost all traffic goes to
     Fireworks.
   - Tiers come from substring guesses.
   - HyDE, the reranker, the humanizer, table extraction, the citation resolver and
     config_generator never call `reserve_call_slot`.
   - Two concurrent runs (`max_concurrent_runs: 2`) share one process-wide bucket, which is
     correct, but the uncovered sites bypass it.
7. **Settings are read from disk instead of the run's snapshot.**
   - `model_fallback.get_fallback_model`, `provider._load_price_fallback_per_mtok`,
     `contradiction_resolver`, `submission_packager` and `humanizer`/`criteria_refinement`
     model getters call `load_configs("config/settings.yaml")`. That path depends on the
     current working directory and ignores the run's `config_snapshot.yaml`.
   - `get_fallback_model` has confusing tier names: `"flash"` maps to the `writing` agent,
     which is the pro model, and `"lite"` maps to `screening_reviewer_a`.
8. **Temperatures are hardcoded in 7 places**, bypassing settings: hyde 0.7, reranker 0.0,
   contradiction 0.1, criteria_refinement 0.1, audit profile 0.0, citation resolver 0.0,
   table extraction 0.1. `narrative` also forces 0.0. Classification agents in settings run at
   0.1 to 0.2 with no seed, so screening isn't reproducible run to run.
9. **Output parsing breaks the project's LLM output contract**
   (`.cursor/rules/core/llm-output.mdc`, which requires schema-validated output such as
   `complete_validated`).
   - The reranker scans free text with `find('[')`.
   - The citation resolver uses an untyped `additionalProperties` schema plus
     `ast.literal_eval`.
   - `contradiction_resolver` accepts any string of 50 or more characters.
   - None of these use `complete_validated`.
10. **Silent heuristic fallbacks.**
    - RoB2, ROBINS-I, CASP and MMAT fall back to a heuristic on any exception.
    - Narrative falls back to keywords.
    - The contradiction resolver falls back to a canned paragraph.
    - The reranker falls back to the original order.
    - `fallback_events` is written only by `rag_retrieval.py` (0 rows in wf-0001), so these
      fallbacks are invisible in `/api/run/{id}/diagnostics`.
11. **RoB 2 schema defaults bias toward low risk.** `_Rob2LLMResponse` defaults
    `domain_3_missing_data` and `domain_5_selection` to `"low"`, so omitted fields silently
    become low risk. ROBINS-I correctly defaults to `no_information`. The overall judgment is
    LLM-provided rather than computed by the RoB 2 algorithm.
12. **Reviewer independence.** Reviewers A and B use the same model (`deepseek-v4-flash-0731`)
    at the same temperature (0.1). Their "dual review" kappa overstates independence.
13. **Minor issues.**
    - An `Agent` is rebuilt on every call.
    - No prompt caching is used, although screening prompts repeat long criteria blocks.
    - The genai-prices updater thread starts at import time and makes a network call in tests
      and the CLI.
    - `complete()` and `complete_with_usage()` duplicate the structured-output branch.
