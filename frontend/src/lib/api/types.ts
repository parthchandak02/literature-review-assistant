type ReviewEventIdentity = { id?: string }

/** Present on SSE events when the backend labels durability for replay contracts. */
export type EventDurability = "durable" | "eventual"

export type ReviewEvent = (
  | ({ type: "phase_start"; phase: string; description: string; total: number | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "phase_done"; phase: string; summary: Record<string, unknown>; total: number | null; completed: number | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "progress"; phase: string; current: number; total: number; ts: string } & ReviewEventIdentity)
  | ({ type: "api_call"; source: string; status: string; phase: string; call_type: string; model: string | null; paper_id: string | null; latency_ms: number | null; tokens_in: number | null; tokens_out: number | null; cost_usd: number | null; records: number | null; details: string | null; section_name: string | null; word_count: number | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "connector_result"; name: string; status: string; records: number; query?: string; error: string | null; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "screening_decision"; paper_id: string; stage: string; decision: string; confidence?: number; title?: string; reason?: string; method?: "llm" | "heuristic"; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "extraction_paper"; paper_id: string; design: string; rob_judgment: string; ts: string } & ReviewEventIdentity)
  | ({ type: "synthesis"; feasible: boolean; groups: number; n_studies: number; direction: string; ts: string } & ReviewEventIdentity)
  | ({ type: "rate_limit_wait"; tier: string; slots_used: number; limit: number; waited_seconds?: number; ts: string } & ReviewEventIdentity)
  | ({ type: "rate_limit_resolved"; tier: string; waited_seconds: number; ts: string } & ReviewEventIdentity)
  | ({ type: "search_override_status"; database: string; status: "applied" | "miss" | "absent"; detail: string; ts: string } & ReviewEventIdentity)
  | ({ type: "status"; message: string; ts: string } & ReviewEventIdentity)
  | ({ type: "screening_prefilter_done"; deduped: number; metadata_rejected: number; after_metadata: number; automation_excluded: number; to_llm: number; dual_review_cap?: number | null; bm25_validation_forwarded?: number; empty_abstract_pool?: number; empty_abstract_excluded?: number; empty_abstract_rescued?: number; reason_breakdown?: Record<string, number>; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "deterministic_exclusion_qa_sample"; sample_size: number; pool_size: number; items: Array<{ paper_id: string; reason_code: string; title: string }>; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "batch_screen_done"; scored: number; forwarded: number; excluded: number; skipped_resume: number; threshold: number; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "screening_cap_overflow"; trigger: string; validation_tail_n: number; validation_tail_forwarded: number; validation_tail_forward_rate: number; trigger_threshold: number; overflow_candidates: number; overflow_evaluated: number; overflow_forwarded: number; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "screening_calibration"; include_threshold: number; exclude_threshold: number; kappa: number; iterations: number; sample_size: number; ts: string } & ReviewEventIdentity)
  | ({ type: "pdf_result"; paper_id: string; title: string; source: string; success: boolean; ts: string; reason_code?: string | null; reason_label?: string | null; action?: string | null; entity_type?: string | null; entity_id?: string | null } & ReviewEventIdentity)
  | ({ type: "db_ready"; ts: string } & ReviewEventIdentity)
  | ({ type: "workflow_id_ready"; workflow_id: string } & ReviewEventIdentity)
  | ({ type: "done"; outputs: Record<string, unknown>; ts?: string } & ReviewEventIdentity)
  | ({ type: "error"; msg: string; traceback?: string; ts?: string } & ReviewEventIdentity)
  | ({ type: "cancelled"; ts?: string } & ReviewEventIdentity)
) & { durability?: EventDurability }

export interface RunRequest {
  review_yaml: string
  deepseek_api_key: string
  gemini_api_key?: string
  openrouter_api_key?: string
  openai_api_key?: string
  anthropic_api_key?: string
  groq_api_key?: string
  mistral_api_key?: string
  cohere_api_key?: string
  openalex_api_key?: string
  ieee_api_key?: string
  pubmed_email?: string
  pubmed_api_key?: string
  perplexity_api_key?: string
  semantic_scholar_api_key?: string
  crossref_email?: string
  wos_api_key?: string
  scopus_api_key?: string
  run_root?: string
}

export interface RunResponse {
  run_id: string
  topic: string
}

export interface HistoryEntry {
  workflow_id: string
  topic: string
  status: string
  db_path: string
  created_at: string
  updated_at?: string | null
  papers_found?: number | null
  papers_included?: number | null
  total_cost?: number | null
  artifacts_count?: number | null
  stats_ok?: boolean | null
  stats_error?: string | null
  live_run_id?: string | null
  notes?: string | null
  is_archived?: boolean
  archived_at?: string | null
  is_completed_hidden?: boolean
  completed_hidden_at?: string | null
}
