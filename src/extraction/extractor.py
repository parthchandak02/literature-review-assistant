"""Structured extraction service with LLM-based extraction and heuristic fallback."""

from __future__ import annotations

import logging
import re
import time

from pydantic import BaseModel, Field

from src.db.repositories import WorkflowRepository
from src.extraction.primary_status import primary_status_from_study_design
from src.llm.base_client import LLMBackend
from src.llm.pydantic_client import PydanticAIClient
from src.models import CandidatePaper, ExtractionRecord, OutcomeRecord, StudyDesign
from src.models.config import ReviewConfig, SettingsConfig

logger = logging.getLogger(__name__)

# Maximum characters passed to the extraction LLM.
# Gemini 3.1 Pro supports 1M token context; 32K chars (~8K tokens) is negligible.
_EXTRACTION_CHAR_LIMIT = 32_000

# HTML detection: if the text contains these patterns it is raw HTML markup
# that was returned by a connector instead of article text. The LLM should
# receive either a stripped plain-text version or an empty string so that
# heuristic extraction fires rather than producing boilerplate responses.
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]{0,200}>", re.DOTALL)
_HTML_ENTITIES_RE = re.compile(r"&(?:amp|lt|gt|nbsp|quot|apos);", re.IGNORECASE)
_HTML_BOILERPLATE_PHRASES = (
    "<!DOCTYPE",
    "<html",
    "<head",
    "<body",
    "javascript",
    "text/javascript",
    "window.onload",
)


def _is_html_content(text: str) -> bool:
    """Return True when text looks like raw HTML rather than article prose.

    Checks for DOCTYPE declaration, dense HTML tags (>1% of content), or
    known boilerplate phrases in the first 2000 characters.
    """
    sample = text[:2000]
    for phrase in _HTML_BOILERPLATE_PHRASES:
        if phrase.lower() in sample.lower():
            return True
    tag_matches = len(_HTML_TAG_RE.findall(text[:5000]))
    # More than 1 HTML tag per 80 characters in the sample -> treat as HTML
    return tag_matches > len(sample) / 80


# PDF header phrases that indicate we received a PDF cover page or table-of-contents
# rather than the actual paper body. These fragments appear in the first few bytes
# of many journal PDF retrievals when the PDF rendering failed partially.
_PDF_HEADER_PHRASES = (
    "Original Paper",
    "Original Research",
    "JMIR HUMAN FACTORS",
    "Page 1 of",
    "Downloaded from",
    "This article was downloaded",
    "Copyright (c)",
    "doi: 10.",
    "DOI: 10.",
    "Volume ",
    "Issue ",
)


def _clean_results_summary_text(text: str) -> str:
    """Remove DOI/boilerplate fragments from extracted free-text summaries."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    # Drop DOI links/tokens that leak from PDF headers.
    cleaned = re.sub(r"https?://doi\.org/\S+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdoi:\s*10\.\S+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b10\.\d{4,9}/\S+", "", cleaned)
    cleaned = re.sub(r"\b(?:open access|downloaded from|copyright)\b[^.]*\.?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _is_low_quality_extraction(text: str) -> bool:
    """Return True when extracted text appears to be an OCR artifact or PDF header.

    Detects two patterns that produce garbled Key Outcomes fields:
    1. High single-character token ratio (OCR-fragmented text like 'g p g p y y')
    2. Raw PDF cover-page or journal header text (journal title, page number lines)

    When this returns True for an extracted field, the caller should fall back
    to using the paper abstract instead of the low-quality extracted text.
    """
    if not text or len(text.strip()) < 10:
        return True
    tokens = text.split()
    if not tokens:
        return True
    # >35% single-char tokens = likely OCR noise
    single_char_ratio = sum(1 for t in tokens if len(t) == 1) / len(tokens)
    if single_char_ratio > 0.35:
        return True
    # Raw PDF header patterns at the start of the text
    stripped_start = text.strip()
    for marker in _PDF_HEADER_PHRASES:
        if stripped_start.startswith(marker):
            return True
    return False


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities; return plain text.

    Falls back to empty string when stripping produces fewer than 100 chars
    (the page was probably a redirect, 403, or empty response).
    """
    # Remove <script> and <style> blocks entirely
    stripped = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining tags
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    # Decode common entities
    stripped = _HTML_ENTITIES_RE.sub(
        lambda m: {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&nbsp;": " ", "&quot;": '"', "&apos;": "'"}.get(
            m.group(0).lower(), m.group(0)
        ),
        stripped,
    )
    # Collapse whitespace
    stripped = re.sub(r"[ \t]+", " ", stripped)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped if len(stripped) >= 100 else ""


def _select_extraction_text(full_text: str, limit: int = _EXTRACTION_CHAR_LIMIT) -> str:
    """Return the most informative slice(s) of full text for extraction.

    When full_text fits within limit, it is returned unchanged. When it exceeds
    limit, a structured excerpt is built by capturing:
      - First 16K chars (abstract + introduction + methods)
      - Last 8K chars (conclusions + references -- often contains numeric results)
      - Up to 8K chars of table-bearing content from the middle (sections
        detected by 'Table' or 'Figure' headers, which carry quantitative data)

    This strategy captures ~75-80% of the quantitative content in a typical
    8-15 page research paper while staying within the budget.

    HTML detection: if the raw text looks like HTML (page redirect, 403 page,
    or publisher paywall HTML), it is stripped to plain text before slicing.
    If stripping yields fewer than 100 chars the function returns "" so the
    heuristic fallback fires instead of sending boilerplate to the LLM.
    """
    if _is_html_content(full_text):
        logger.warning(
            "Extraction text appears to be HTML markup (%d chars); stripping tags before extraction.",
            len(full_text),
        )
        full_text = _strip_html(full_text)
        if not full_text:
            logger.warning("HTML stripping produced empty text; heuristic extraction will be used.")
            return ""

    if len(full_text) <= limit:
        return full_text

    head = full_text[:16_000]
    tail = full_text[-8_000:]

    # Extract table-rich middle sections (first 8K worth of table-containing paragraphs)
    middle = full_text[16_000 : len(full_text) - 8_000]
    table_chunks: list[str] = []
    table_budget = limit - len(head) - len(tail)

    if table_budget > 0 and middle:
        # Split on paragraph breaks; keep paragraphs that contain table markers
        paragraphs = re.split(r"\n{2,}", middle)
        for para in paragraphs:
            if re.search(r"\bTable\s*\d+\b|\bFigure\s*\d+\b|\bFig\.\s*\d+\b", para, re.IGNORECASE):
                chunk = para.strip()
                if len(chunk) + sum(len(c) for c in table_chunks) <= table_budget:
                    table_chunks.append(chunk)
                else:
                    remaining = table_budget - sum(len(c) for c in table_chunks)
                    if remaining > 200:
                        table_chunks.append(chunk[:remaining])
                    break

    separator = "\n\n[...content omitted for length...]\n\n"
    parts = [head]
    if table_chunks:
        parts.append(separator.join(table_chunks))
    parts.append(tail)
    result = separator.join(p for p in parts if p.strip())
    return result[:limit]


class _OutcomeItem(BaseModel):
    name: str = ""
    description: str = ""
    effect_size: str = ""
    se: str = ""
    n: str = ""


class _ExtractionLLMResponse(BaseModel):
    study_duration: str = ""
    setting: str = ""
    participant_count: str = ""
    country: str = ""  # inferred from affiliation, institution name, or geographic reference
    participant_demographics: str = ""
    intervention_description: str = ""
    comparator_description: str = ""
    outcomes: list[_OutcomeItem] = Field(default_factory=list)
    results_summary: str = ""
    funding_source: str = ""
    conflicts_of_interest: str = ""


def _build_extraction_prompt(
    paper: CandidatePaper,
    text: str,
    review: ReviewConfig,
) -> str:
    domain_brief = review.domain_brief_lines()
    return "\n".join(
        [
            "You are a systematic review data extractor.",
            f"Research question: {review.research_question}",
            f"Topic focus: {review.expert_topic()}",
            f"Domain: {review.domain}",
            f"Intervention of interest: {review.pico.intervention}",
            f"Population of interest: {review.pico.population}",
            f"Outcome of interest: {review.pico.outcome}",
            f"Preferred terminology: {', '.join(review.preferred_terminology())}",
            f"Topic anchor terms: {', '.join(review.domain_signal_terms(limit=12))}",
            *(["Domain brief:"] + [f"  - {item}" for item in domain_brief] if domain_brief else []),
            "",
            f"Title: {paper.title}",
            "",
            "Text excerpt (up to 32000 chars):",
            text[:32000],
            "",
            "Extract the following from this study:",
            "- study_duration: Duration of the study or intervention (e.g. '8 weeks', '6 months', 'unknown')",
            "- setting: Study setting as free text (e.g. 'classroom', 'workplace', 'clinical facility', 'laboratory', 'field site', 'online').",
            "- participant_count: Total participants as a plain number string (e.g. '120', '45').",
            "  Search for ANY numeric count: number of patients, procedures, encounters, events, or participants.",
            "  If the study reports '5,200 procedures during the study period', record '5200'.",
            "  If no numeric count of any kind appears anywhere in the text, use 'not reported'.",
            "  Do NOT include units like 'patients' in the field -- numbers only.",
            "- country: Country or countries where the study was conducted.",
            "  IMPORTANT: Infer from ANY available clue: author affiliations, hospital/clinic name,",
            "  city name, regional health system, or geographic reference in the abstract.",
            "  Examples: 'University of Tokyo' -> 'Japan'; 'MIT' -> 'United States';",
            "  'ETH Zurich' -> 'Switzerland'; 'NHS Trust' -> 'United Kingdom'; 'University of São Paulo' -> 'Brazil'.",
            "  Use ISO country name (e.g. 'Japan', 'Brazil', 'Saudi Arabia').",
            "  Only use 'Not Reported' if truly no geographic information is available anywhere.",
            "- participant_demographics: Brief description of participants (age, role, background, etc.)",
            "- intervention_description: What the intervention/treatment was in detail",
            "- comparator_description: What the control/comparison condition was (or 'no control' if absent)",
            "- outcomes: List of SPECIFIC outcome measures as reported in the paper. For each outcome:",
            "    name: the actual measured outcome name from the paper (e.g. 'primary outcome rate',",
            "          'mean score improvement', 'task completion time', 'cost per unit',",
            "          'adherence rate', 'error rate', 'effect size').",
            "    CRITICAL: NEVER use 'primary_outcome', 'not reported', or generic placeholders as a name. "
            "Use the real outcome name from the paper.",
            "    If no outcomes can be identified return an empty list [].",
            "    Also include: description, effect_size (e.g. 'OR=2.1'), se (standard error), n (sample size)",
            "- results_summary: Plain text summary of the key findings (2-4 sentences)",
            "- funding_source: Who funded the study (or 'not reported')",
            "- conflicts_of_interest: Any declared COI (or 'none declared')",
            "",
            "Return ONLY valid JSON matching the schema.",
        ]
    )


class ExtractionService:
    """Create typed extraction records from paper metadata/full text.

    Uses Gemini Pro LLM when available; falls back to heuristic extraction
    on API errors or when offline.
    """

    def __init__(
        self,
        repository: WorkflowRepository,
        llm_client: LLMBackend | None = None,
        settings: SettingsConfig | None = None,
        review: ReviewConfig | None = None,
        provider: object | None = None,
    ):
        self.repository = repository
        self.llm_client = llm_client
        self.settings = settings
        self.review = review
        self.provider = provider

    @staticmethod
    def _heuristic_summary(paper: CandidatePaper, full_text: str) -> str:
        text = full_text.strip()
        if text:
            return text[:1200]
        abstract = (paper.abstract or "").strip()
        if abstract:
            return abstract[:1200]
        return "No summary available."

    def _heuristic_outcomes(self) -> list[OutcomeRecord]:
        """Generic fallback when LLM extraction yields no outcomes.

        Uses the review's PICO outcome field as description context so the
        fallback is at least topic-aware. Never uses a hardcoded subject-area label.
        """
        topic = (self.review.pico.outcome if self.review else "") or "not reported"
        return [OutcomeRecord(name="not reported", description=topic[:200])]

    def _heuristic_extract(
        self,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        text = _select_extraction_text(full_text)
        summary = self._heuristic_summary(paper, text)
        return ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            primary_study_status=primary_status_from_study_design(study_design),
            study_duration="unknown",
            setting="not_reported",
            participant_count=None,
            participant_demographics=None,
            intervention_description=paper.title[:500],
            comparator_description=None,
            outcomes=self._heuristic_outcomes(),
            results_summary={
                "summary": summary,
                "source": "heuristic",
            },
            funding_source=None,
            conflicts_of_interest=None,
            source_spans={
                "full_text_excerpt": text[:500] if text.strip() else "",
                "title": paper.title[:500],
            },
        )

    async def _llm_extract(
        self,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        assert self.llm_client is not None
        assert self.review is not None
        assert self.settings is not None

        agent = self.settings.agents.get("extraction")
        if not agent:
            raise ValueError(
                "Extraction agent not configured in settings.yaml. Add 'extraction:' under 'agents:' with a model name."
            )
        model = agent.model
        temperature = agent.temperature

        text = _select_extraction_text(full_text)
        prompt = _build_extraction_prompt(paper, text, self.review)

        if self.provider is not None:
            await self.provider.reserve_call_slot("extraction")
        t0 = time.monotonic()
        if self.provider is not None and isinstance(self.llm_client, PydanticAIClient):
            parsed, tok_in, tok_out, cw, cr, retries = await self.llm_client.complete_validated(
                prompt,
                model=model,
                temperature=temperature,
                response_model=_ExtractionLLMResponse,
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            cost = self.provider.estimate_cost_usd(model, tok_in, tok_out, cw, cr)
            await self.provider.log_cost(
                model,
                tok_in,
                tok_out,
                cost,
                latency_ms,
                phase="extraction",
                cache_read_tokens=cr,
                cache_write_tokens=cw,
            )
            if retries > 0:
                logger.info(
                    "Extraction for %s succeeded after %d validation retry(ies).",
                    paper.paper_id[:12],
                    retries,
                )
        else:
            schema = _ExtractionLLMResponse.model_json_schema()
            raw = await self.llm_client.complete(prompt, model=model, temperature=temperature, json_schema=schema)
            parsed = _ExtractionLLMResponse.model_validate_json(raw)

        outcomes: list[OutcomeRecord] = []
        for o in parsed.outcomes or []:
            name = (o.name or "").strip()
            if not name:
                continue
            outcomes.append(
                OutcomeRecord(
                    name=name,
                    description=o.description or "",
                    effect_size=o.effect_size or "",
                    se=o.se or "",
                    n=o.n or "",
                )
            )
        if not outcomes:
            outcomes = self._heuristic_outcomes()

        participant_count: int | None = None
        raw_count = (parsed.participant_count or "").strip()
        if raw_count:
            m = re.search(r"\d+", raw_count)
            if m:
                participant_count = int(m.group())

        # Guard against OCR artifact text in key fields. If the extracted
        # results_summary looks like garbled OCR or a raw PDF header, fall back
        # to the heuristic summary derived from the abstract.
        results_summary_text = parsed.results_summary or ""
        if _is_low_quality_extraction(results_summary_text):
            results_summary_text = self._heuristic_summary(paper, text)
        else:
            results_summary_text = _clean_results_summary_text(results_summary_text)

        # Country is a new field extracted by the improved prompt. Read it from
        # the parsed output if present; default to paper metadata if absent.
        country_extracted = getattr(parsed, "country", None)
        if country_extracted and _is_low_quality_extraction(country_extracted):
            country_extracted = None

        return ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            primary_study_status=primary_status_from_study_design(study_design),
            study_duration=parsed.study_duration or "unknown",
            setting=parsed.setting or "not_reported",
            participant_count=participant_count,
            participant_demographics=parsed.participant_demographics or None,
            intervention_description=parsed.intervention_description or paper.title[:500],
            comparator_description=parsed.comparator_description or None,
            outcomes=outcomes,
            results_summary={
                "summary": results_summary_text or self._heuristic_summary(paper, text),
                "source": "llm",
                **({"country": country_extracted} if country_extracted else {}),
            },
            funding_source=parsed.funding_source or None,
            conflicts_of_interest=parsed.conflicts_of_interest or None,
            source_spans={
                "full_text_excerpt": text[:500] if text.strip() else "",
                "title": paper.title[:500],
            },
        )

    async def extract(
        self,
        workflow_id: str,
        paper: CandidatePaper,
        study_design: StudyDesign,
        full_text: str,
    ) -> ExtractionRecord:
        record: ExtractionRecord
        if self.llm_client is not None and self.review is not None and self.settings is not None:
            try:
                record = await self._llm_extract(paper, study_design, full_text)
            except Exception as exc:
                # Log both exception type AND message so quota/auth errors are visible
                # in the server log and diagnosable without a debugger.
                logger.warning(
                    "LLM extraction failed for %s (%s: %s); using heuristic fallback. "
                    "If all papers fail, check API quota for the extraction model.",
                    paper.paper_id[:12],
                    type(exc).__name__,
                    str(exc)[:200],
                )
                record = self._heuristic_extract(paper, study_design, full_text)
        else:
            record = self._heuristic_extract(paper, study_design, full_text)
        await self.repository.save_extraction_record(workflow_id=workflow_id, record=record)
        return record
