CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    year INTEGER,
    source_database TEXT NOT NULL,
    doi TEXT,
    abstract TEXT,
    url TEXT,
    keywords TEXT,
    source_category TEXT NOT NULL DEFAULT 'database',
    openalex_id TEXT,
    country TEXT,
    display_label TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS search_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    database_name TEXT NOT NULL,
    source_category TEXT NOT NULL,
    search_date TEXT NOT NULL,
    search_query TEXT NOT NULL,
    limits_applied TEXT,
    records_retrieved INTEGER NOT NULL,
    workflow_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screening_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    stage TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    exclusion_reason TEXT,
    reviewer_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dual_screening_results (
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    stage TEXT NOT NULL,
    agreement INTEGER NOT NULL,
    final_decision TEXT NOT NULL,
    adjudication_needed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, paper_id, stage)
);

CREATE TABLE IF NOT EXISTS extraction_records (
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    study_design TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, paper_id)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    paper_id TEXT,
    claim_text TEXT NOT NULL,
    section TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citations (
    citation_id TEXT PRIMARY KEY,
    citekey TEXT UNIQUE NOT NULL,
    doi TEXT,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    year INTEGER,
    journal TEXT,
    bibtex TEXT,
    resolved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    citation_id TEXT NOT NULL REFERENCES citations(citation_id),
    evidence_span TEXT NOT NULL,
    evidence_score REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS rob_assessments (
    workflow_id TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id),
    tool_used TEXT NOT NULL,
    assessment_data TEXT NOT NULL,
    overall_judgment TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, paper_id)
);

CREATE TABLE IF NOT EXISTS grade_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    assessment_data TEXT NOT NULL,
    final_certainty TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS section_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    section TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    claims_used TEXT,
    citations_used TEXT,
    word_count INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(workflow_id, section, version)
);

CREATE TABLE IF NOT EXISTS gate_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL,
    threshold TEXT,
    actual_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_type TEXT NOT NULL,
    paper_id TEXT,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL,
    actor TEXT NOT NULL,
    phase TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cost_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    phase TEXT NOT NULL,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflows (
    workflow_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    dedup_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS synthesis_results (
    workflow_id TEXT NOT NULL,
    outcome_name TEXT NOT NULL,
    feasibility_data TEXT NOT NULL,
    narrative_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, outcome_name)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    workflow_id TEXT NOT NULL REFERENCES workflows(workflow_id),
    phase TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    papers_processed INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_id, phase)
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    ts TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi_unique ON papers(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_screening_paper ON screening_decisions(workflow_id, paper_id, stage);
CREATE INDEX IF NOT EXISTS idx_claims_section ON claims(section);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_citation ON evidence_links(citation_id);
CREATE INDEX IF NOT EXISTS idx_decision_log_phase ON decision_log(phase);
CREATE INDEX IF NOT EXISTS idx_gate_results_phase ON gate_results(phase);
CREATE INDEX IF NOT EXISTS idx_event_log_workflow ON event_log(workflow_id);

-- ============================================================
-- Idea 1: RAG - paper chunk storage (vector search via Python)
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_chunks_meta (
    chunk_id    TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    paper_id    TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);
CREATE INDEX IF NOT EXISTS idx_chunks_workflow ON paper_chunks_meta(workflow_id);
CREATE INDEX IF NOT EXISTS idx_chunks_paper ON paper_chunks_meta(paper_id);

-- ============================================================
-- Idea 2: Multimodal extraction (column added via migration)
-- extraction_source is added to extraction_records via ALTER TABLE
-- ============================================================

-- ============================================================
-- Idea 4: Active Learning - human screening corrections
-- ============================================================
CREATE TABLE IF NOT EXISTS screening_corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id     TEXT NOT NULL,
    paper_id        TEXT NOT NULL,
    ai_decision     TEXT NOT NULL,
    human_decision  TEXT NOT NULL,
    human_reason    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learned_criteria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id     TEXT NOT NULL,
    criterion_type  TEXT NOT NULL,
    criterion_text  TEXT NOT NULL,
    source_paper_ids TEXT,
    version         INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_corrections_workflow ON screening_corrections(workflow_id);
CREATE INDEX IF NOT EXISTS idx_criteria_workflow ON learned_criteria(workflow_id);

-- ============================================================
-- Idea 5: Knowledge Graph - paper relationships and communities
-- ============================================================
CREATE TABLE IF NOT EXISTS paper_relationships (
    workflow_id     TEXT NOT NULL,
    source_paper_id TEXT NOT NULL,
    target_paper_id TEXT NOT NULL,
    rel_type        TEXT NOT NULL,
    weight          REAL,
    PRIMARY KEY (workflow_id, source_paper_id, target_paper_id, rel_type),
    FOREIGN KEY (source_paper_id) REFERENCES papers(paper_id),
    FOREIGN KEY (target_paper_id) REFERENCES papers(paper_id)
);

CREATE TABLE IF NOT EXISTS graph_communities (
    workflow_id     TEXT NOT NULL,
    community_id    INTEGER NOT NULL,
    paper_ids       TEXT NOT NULL,
    label           TEXT,
    PRIMARY KEY (workflow_id, community_id)
);

CREATE TABLE IF NOT EXISTS research_gaps (
    gap_id          TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    description     TEXT NOT NULL,
    related_paper_ids TEXT,
    gap_type        TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gaps_workflow ON research_gaps(workflow_id);

-- ============================================================
-- Idea 3: Contradiction flags (stored as JSON in state; no new table needed)
-- ============================================================
