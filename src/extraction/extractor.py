"""Structured extraction service with LLM-based extraction and heuristic fallback."""

from __future__ import annotations

import logging
import re
import time

from pydantic import BaseModel, Field

from src.db.repositories import WorkflowRepository
from src.extraction.inference_utils import (
    _is_substantive_finding,
    derive_concise_result_summary,
    infer_country_from_text,
    result_not_extractable_text,
    should_promote_to_mixed_methods,
)
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

_SCOPE_NEGATION_PATTERNS = (
    re.compile(r"\bdoes\s+not\s+describe\b", flags=re.IGNORECASE),
    re.compile(r"\bnot\s+aligned\s+with\b", flags=re.IGNORECASE),
    re.compile(r"\boutside\s+the\s+scope\b", flags=re.IGNORECASE),
    re.compile(r"\bwrong\s+intervention\b", flags=re.IGNORECASE),
    re.compile(r"\bnot\s+an?\s+(?:example|evaluation|assessment|study)\s+of\b", flags=re.IGNORECASE),
)
_SCOPE_GENERIC_TOKENS = frozenset(
    {
        "study",
        "studies",
        "review",
        "reviews",
        "system",
        "systems",
        "intervention",
        "interventions",
        "program",
        "programme",
        "approach",
        "service",
        "services",
        "implementation",
        "outcome",
        "outcomes",
        "health",
        "clinical",
        "public",
        "effect",
        "effects",
        "impact",
        "using",
        "based",
    }
)

_COUNT_CONTEXT_PATTERNS = (
    re.compile(r"\bn\s*[:=]\s*(\d[\d,]{0,8})\b", flags=re.IGNORECASE),
    re.compile(
        r"\b(\d[\d,]{0,8})\s+"
        r"(?:participants?|patients?|children|caregivers?|parents?|students?|workers?|"
        r"health care workers|healthcare workers|vaccinators?|informants?|users?|"
        r"subjects?|respondents?|records?|encounters?|procedures?|visits?|facilities|"
        r"cent(?:er|re)s?|clinics?|sites?)\b",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\((\d[\d,]{0,8})/(\d[\d,]{0,8})\)\s+of\s+"
        r"(?:participants?|patients?|children|students?|workers?|vaccinators?|users?|"
        r"records?|facilities|cent(?:er|re)s?|clinics?|sites?)\b",
        flags=re.IGNORECASE,
    ),
)

_PLACEHOLDER_SUMMARY_PATTERNS = (
    re.compile(r"^\s*not reported(?:\s+in\s+the\s+provided\s+text)?\.?\s*$", flags=re.IGNORECASE),
    re.compile(r"^\s*no summary available\.?\s*$", flags=re.IGNORECASE),
    re.compile(
        r"^\s*the provided text excerpt does not contain a summary of the study'?s results or findings\.?\s*$",
        flags=re.IGNORECASE,
    ),
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


def _finalize_results_summary_text(text: str) -> str:
    cleaned = _clean_results_summary_text(text)
    if _is_placeholder_summary_text(cleaned) or _is_filler_summary_text(cleaned):
        return ""
    concise = derive_concise_result_summary(cleaned)
    if concise.startswith("Result details were not extractable"):
        return concise
    return concise or cleaned


def _is_placeholder_summary_text(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    return any(pattern.match(cleaned) for pattern in _PLACEHOLDER_SUMMARY_PATTERNS)


def _is_filler_summary_text(text: str) -> bool:
    cleaned = _clean_results_summary_text(text)
    if not cleaned:
        return True
    return not _is_substantive_finding(cleaned)


def _synthesize_summary_from_outcomes(outcomes: list["_OutcomeItem"]) -> str:
    parts: list[str] = []
    for outcome in outcomes:
        name = str(outcome.name or "").strip()
        if not name or name.lower() in {"not reported", "primary_outcome", "secondary_outcome"}:
            continue
        detail_bits: list[str] = []
        effect_size = str(outcome.effect_size or "").strip()
        sample_size = str(outcome.n or "").strip()
        if effect_size:
            detail_bits.append(f"effect size {effect_size}")
        if sample_size:
            detail_bits.append(f"n={sample_size}")
        if not detail_bits:
            continue
        if detail_bits:
            parts.append(f"{name} ({'; '.join(detail_bits)})")
        else:
            parts.append(name)
        if len(parts) >= 3:
            break
    if not parts:
        return ""
    return "Reported outcomes: " + "; ".join(parts) + "."


def _scope_anchor_terms(review: ReviewConfig | None) -> tuple[list[str], list[str]]:
    if review is None:
        return [], []
    phrases: list[str] = []
    seen_phrases: set[str] = set()
    seen_tokens: set[str] = set()
    tokens: list[str] = []
    candidates = [
        review.pico.intervention,
        *review.preferred_terminology(limit=16),
        *review.domain_signal_terms(limit=20),
    ]
    for raw in candidates:
        phrase = re.sub(r"[^a-z0-9+/ -]+", " ", str(raw or "").lower())
        phrase = re.sub(r"\s+", " ", phrase).strip(" -")
        if len(phrase) >= 4 and phrase not in seen_phrases:
            seen_phrases.add(phrase)
            phrases.append(phrase)
        for token in re.findall(r"[a-z0-9][a-z0-9+/.-]{2,}", phrase):
            if len(token) < 4 or token in _SCOPE_GENERIC_TOKENS or token in seen_tokens:
                continue
            seen_tokens.add(token)
            tokens.append(token)
    return phrases, tokens


def detect_scope_mismatch(record: ExtractionRecord, review: ReviewConfig | None) -> tuple[bool, str | None]:
    """Return True only for explicit intervention-scope contradictions."""
    text_parts = [
        record.intervention_description or "",
        str(record.results_summary.get("summary") or ""),
        str(record.source_spans.get("title") or ""),
    ]
    evidence_text = re.sub(r"\s+", " ", " ".join(part for part in text_parts if part).strip()).lower()
    if not evidence_text:
        return False, None
    if not any(pattern.search(evidence_text) for pattern in _SCOPE_NEGATION_PATTERNS):
        return False, None
    anchor_phrases, anchor_tokens = _scope_anchor_terms(review)
    matched_phrases = [phrase for phrase in anchor_phrases if phrase in evidence_text]
    matched_tokens = [
        token for token in anchor_tokens if re.search(rf"\b{re.escape(token)}\b", evidence_text, flags=re.IGNORECASE)
    ]
    if not matched_phrases and len(matched_tokens) < 2:
        return False, None
    matched = matched_phrases[:2] or matched_tokens[:3]
    return True, ", ".join(matched)


def _coerce_int_token(token: str) -> int | None:
    cleaned = (token or "").strip().replace(",", "")
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    if value <= 0:
        return None
    return value


def _infer_participant_count(
    raw_count: str,
    participant_demographics: str,
    results_summary: str,
    paper: CandidatePaper,
    text: str,
) -> int | None:
    direct = _coerce_int_token(raw_count)
    if direct is not None:
        return direct

    candidate_blocks = [
        participant_demographics,
        results_summary,
        paper.abstract or "",
        text,
    ]
    for block in candidate_blocks:
        sample = re.sub(r"\s+", " ", str(block or "")).strip()
        if not sample:
            continue
        for pattern in _COUNT_CONTEXT_PATTERNS:
            match = pattern.search(sample)
            if not match:
                continue
            if len(match.groups()) == 1:
                value = _coerce_int_token(match.group(1))
            else:
                value = _coerce_int_token(match.group(2))
            if value is not None:
                return value
    return None


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
        abstract = (paper.abstract or "").strip()
        if abstract:
            return abstract[:1200]
        text = full_text.strip()
        if text:
            return text[:1200]
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
        summary = _finalize_results_summary_text(self._heuristic_summary(paper, text))
        if not summary:
            summary = _clean_results_summary_text(self._heuristic_summary(paper, text))
        country = (
            str(getattr(paper, "country", None) or "").strip()
            or infer_country_from_text(paper.title, paper.abstract or "", text)
            or None
        )
        return ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            primary_study_status=primary_status_from_study_design(study_design),
            study_duration="unknown",
            setting="not_reported",
            country=country,
            participant_count=None,
            participant_demographics=None,
            intervention_description=paper.title[:500],
            comparator_description=None,
            outcomes=self._heuristic_outcomes(),
            results_summary={
                "summary": summary,
                "source": "heuristic",
                **({"country": country} if country else {}),
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

        # Guard against OCR artifacts and non-substantive LLM filler before
        # allowing free-text summaries to pass downstream.
        results_summary_text = _clean_results_summary_text(parsed.results_summary or "")
        results_summary_text = _finalize_results_summary_text(results_summary_text)
        if _is_low_quality_extraction(results_summary_text):
            results_summary_text = ""
        if not results_summary_text or results_summary_text == result_not_extractable_text():
            results_summary_text = _synthesize_summary_from_outcomes(parsed.outcomes or [])
        if not results_summary_text or results_summary_text == result_not_extractable_text():
            results_summary_text = _finalize_results_summary_text(self._heuristic_summary(paper, text))

        participant_count = _infer_participant_count(
            raw_count=(parsed.participant_count or "").strip(),
            participant_demographics=parsed.participant_demographics or "",
            results_summary=results_summary_text,
            paper=paper,
            text=text,
        )

        # Country is a new field extracted by the improved prompt. Read it from
        # the parsed output if present; default to paper metadata if absent.
        country_extracted = getattr(parsed, "country", None)
        if country_extracted and _is_low_quality_extraction(country_extracted):
            country_extracted = None
        country_extracted = (
            str(country_extracted or "").strip()
            or str(getattr(paper, "country", None) or "").strip()
            or infer_country_from_text(
                paper.title,
                paper.abstract or "",
                parsed.setting or "",
                parsed.participant_demographics or "",
                parsed.intervention_description or "",
                results_summary_text,
                text,
            )
            or None
        )
        if should_promote_to_mixed_methods(
            study_design,
            summary_text=results_summary_text,
            raw_text=text,
            outcome_names=[o.name for o in outcomes],
        ):
            study_design = StudyDesign.MIXED_METHODS

        return ExtractionRecord(
            paper_id=paper.paper_id,
            study_design=study_design,
            primary_study_status=primary_status_from_study_design(study_design),
            study_duration=parsed.study_duration or "unknown",
            setting=parsed.setting or "not_reported",
            country=country_extracted,
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
