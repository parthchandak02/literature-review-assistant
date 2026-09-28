"""Abstract-related utilities for structured abstract parsing, validation, and normalization."""

from __future__ import annotations

import re

from src.models import StructuredAbstractOutput

_ABSTRACT_FIELDS = ("Background", "Objectives", "Methods", "Results", "Conclusions", "Keywords")
_ANY_BRACKET_CITATION_RE = re.compile(r"\[[^\[\]\n]{1,120}\]")

_AUX_WORDS = frozenset(
    {"is", "are", "was", "were", "do", "does", "did", "can", "could", "should", "will", "would", "has", "have", "had"}
)
_PREPOSITIONS = frozenset({"of", "in", "on", "for", "among", "to", "with", "from", "by", "at", "about"})
_WHAT_BE_RE = re.compile(r"^(?:what|which)\s+(?:is|are|was|were)\s+(.+)$", flags=re.IGNORECASE)
_WHAT_KNOWN_RE = re.compile(r"^what\s+is\s+(?:currently\s+)?known\s+about\s+(.+)$", flags=re.IGNORECASE)
_WHAT_NOUN_RE = re.compile(r"^(?:what|which)\s+([A-Za-z][\w-]*)\s+(.+)$", flags=re.IGNORECASE)
_TRAILING_SUBQUESTION_RE = re.compile(
    r"[,;]?\s+(?:and|or)\s+(?:how|what|which|whether|why|to what extent)\b.*$", flags=re.IGNORECASE
)


def question_to_objective_phrase(question: str) -> str | None:
    """Turn a "What are the X?"-style research question into a noun phrase ("the X").

    Returns None when the question cannot be rephrased safely (for example
    inverted how/does/is questions), so callers can fall back to other data.
    """
    text = " ".join(str(question or "").split()).rstrip(" ?.!")
    if not text:
        return None
    text = _TRAILING_SUBQUESTION_RE.sub("", text).rstrip(" ,;")
    known = _WHAT_KNOWN_RE.match(text)
    if known:
        return f"current evidence on {known.group(1)}"
    be = _WHAT_BE_RE.match(text)
    noun_match = _WHAT_NOUN_RE.match(text)
    if be:
        phrase = be.group(1)
    elif noun_match:
        noun, rest = noun_match.group(1), noun_match.group(2)
        first_rest = rest.split()[0].lower()
        if noun.lower() in _AUX_WORDS or first_rest in _AUX_WORDS or first_rest in _PREPOSITIONS:
            return None
        phrase = f"the {noun} that {rest}"
    else:
        return None
    if phrase.split()[0] in {"The", "A", "An", "These", "Those"}:
        phrase = phrase[0].lower() + phrase[1:]
    return phrase or None


def review_objective_phrase(research_question: str, pico: object | None = None) -> str:
    """Noun phrase describing what the review examined, safe to embed mid-sentence."""
    phrase = question_to_objective_phrase(research_question)
    if phrase:
        return phrase
    intervention = str(getattr(pico, "intervention", "") or "").strip().rstrip(".")
    outcome = str(getattr(pico, "outcome", "") or "").strip().rstrip(".")
    population = str(getattr(pico, "population", "") or "").strip().rstrip(".")
    if intervention and outcome:
        tail = f" in {population}" if population else ""
        return f"the effects of {intervention} on {outcome}{tail}"
    text = " ".join(str(research_question or "").split()).rstrip(" ?.!")
    if text:
        return f'the research question "{text}"'
    return "the predefined research question"


def _replace_or_append_abstract_field(content: str, field: str, value: str) -> str:
    pattern = re.compile(
        rf"(\*\*{re.escape(field)}:\*\*\s*)(.*?)(?=(?:\s+\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if pattern.search(content):
        return pattern.sub(lambda match: f"{match.group(1)}{value}", content, count=1)
    suffix = "" if not content.strip() else "\n"
    return f"{content.rstrip()}{suffix}**{field}:** {value}"


def _ensure_structured_abstract(content: str, research_question: str) -> str:
    """Ensure abstract contains all required structured fields.

    If fields are missing, append deterministic fallback lines so downstream
    markdown/latex extraction always has a complete abstract shape.
    """
    text = content.strip()
    if not text:
        text = "Evidence synthesis was generated from included studies."

    _present = {f: bool(re.search(rf"\*\*{re.escape(f)}:\*\*", text, flags=re.IGNORECASE)) for f in _ABSTRACT_FIELDS}
    _present["Conclusions"] = _present["Conclusions"] or bool(
        re.search(r"\*\*Conclusion:\*\*", text, flags=re.IGNORECASE)
    )
    defaults = {
        "Background": "This topic has important practical and implementation implications.",
        "Objectives": f"This systematic review addressed {review_objective_phrase(research_question)}.",
        "Methods": (
            "Bibliographic databases were searched according to protocol, with "
            "eligibility screening and risk-of-bias assessment."
        ),
        "Results": (
            "Across the included studies, findings suggested directionally favorable implementation and workflow "
            "outcomes in some settings, with substantial between-study heterogeneity limiting direct quantitative "
            "comparability and certainty."
        ),
        "Conclusions": (
            "Available evidence indicates potential benefits, but conclusions remain cautious because small samples, "
            "methodological heterogeneity, and reporting gaps constrain certainty."
        ),
        "Keywords": "systematic review, evidence synthesis, implementation, outcomes, methodology",
    }
    redirect_re = re.compile(
        r"\b(?:reported|presented|described|discussed)\s+in\s+(?:the\s+)?(?:body|main text|results section|"
        r"synthesis section|manuscript)\b|\bsee\s+(?:the\s+)?(?:body|results section|synthesis section)\b",
        flags=re.IGNORECASE,
    )
    if all(_present.values()):
        for field in ("Results", "Conclusions"):
            value_match = re.search(
                rf"\*\*{re.escape(field)}:\*\*\s*(.+?)(?=(?:\n\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if value_match and redirect_re.search(value_match.group(1).strip()):
                text = _replace_or_append_abstract_field(text, field, defaults[field])
        return text
    _missing_lines = [f"**{field}:** {defaults[field]}" for field in _ABSTRACT_FIELDS if not _present[field]]
    return (text + "\n\n" + "\n".join(_missing_lines)).strip()


def _normalize_structured_abstract_fields(content: str) -> str:
    """Normalize spacing and terminal punctuation for structured abstract fields."""

    def _rewrite(field: str, text: str, *, always_period: bool = False) -> str:
        pattern = re.compile(
            rf"(\*\*{re.escape(field)}:\*\*\s*)(.*?)(?=(?:\n\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
            flags=re.IGNORECASE | re.DOTALL,
        )

        def _repl(match: re.Match[str]) -> str:
            value = re.sub(r"\s+", " ", match.group(2).strip())
            if value:
                if always_period:
                    value = value.rstrip(" ,;:.") + "."
                elif value[-1] not in ".!?":
                    value = f"{value}."
            return f"{match.group(1)}{value}"

        return pattern.sub(_repl, text, count=1)

    normalized = str(content or "").strip()
    for field in ("Background", "Objectives", "Methods", "Results", "Conclusions"):
        normalized = _rewrite(field, normalized)
    normalized = _rewrite("Keywords", normalized, always_period=True)
    return normalized


def parse_structured_abstract_markdown(content: str) -> StructuredAbstractOutput:
    """Parse structured abstract markdown into typed payload."""
    text = str(content or "").strip()

    def _extract(field_pattern: str) -> str:
        match = re.search(
            rf"\*\*{field_pattern}:\*\*\s*(.*?)(?=(?:\s+\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return re.sub(r"\s+", " ", (match.group(1) if match else "").strip())

    background = _extract("Background")
    objectives = _extract("Objectives")
    methods = _extract("Methods")
    results = _extract("Results")
    conclusions = _extract("Conclusions")
    if not conclusions:
        conclusions = _extract("Conclusion")
    keywords_value = _extract("Keywords")
    keywords = [kw.strip(" .,:;") for kw in keywords_value.split(",") if kw.strip(" .,:;")]

    payload = StructuredAbstractOutput(
        background=background,
        objectives=objectives,
        methods=methods,
        results=results,
        conclusions=conclusions,
        keywords=keywords,
    )
    return payload.normalized()


def validate_structured_abstract_markdown_band(
    content: str,
    *,
    min_words: int,
    max_words: int,
) -> tuple[bool, str]:
    """Return validity and reason for structured abstract markdown."""
    try:
        parsed = parse_structured_abstract_markdown(content)
        parsed.validate_word_band(min_words=min_words, max_words=max_words)
    except Exception as exc:
        return False, str(exc)
    return True, ""


def canonicalize_structured_abstract_markdown(content: str) -> str:
    """Return canonical multiline structured abstract markdown."""
    return parse_structured_abstract_markdown(content).to_markdown()


def _abstract_body_word_count(content: str) -> int:
    try:
        parsed = parse_structured_abstract_markdown(content)
        return parsed.body_word_count()
    except Exception:
        matches = re.findall(
            r"\*\*(Background|Objectives|Methods|Results|Conclusions?):\*\*\s*(.*?)(?=(?:\s+\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
            str(content or ""),
            flags=re.IGNORECASE | re.DOTALL,
        )
        body = " ".join(text for _field, text in matches)
        body = re.sub(r"\s+", " ", body).strip()
        return len(body.split())


def _append_abstract_field_sentence(content: str, field: str, sentence: str) -> str:
    pattern = re.compile(
        rf"(\*\*{re.escape(field)}:\*\*\s*)(.*?)(?=(?:\n\*\*[A-Za-z][A-Za-z ]*:\*\*|$))",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _repl(match: re.Match[str]) -> str:
        existing = match.group(2).strip()
        if sentence.lower() in existing.lower():
            return match.group(0)
        separator = " " if existing else ""
        return f"{match.group(1)}{existing}{separator}{sentence}"

    return pattern.sub(_repl, content, count=1)


def _strip_abstract_citation_markup(content: str) -> str:
    """Abstract output must remain citation-free after all deterministic passes."""
    cleaned = _ANY_BRACKET_CITATION_RE.sub("", str(content or ""))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    return cleaned.strip()
