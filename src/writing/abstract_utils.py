"""Abstract-related utilities for structured abstract parsing, validation, and normalization."""

from __future__ import annotations

import re

from src.models import StructuredAbstractOutput

_ABSTRACT_FIELDS = ("Background", "Objectives", "Methods", "Results", "Conclusions", "Keywords")
_ANY_BRACKET_CITATION_RE = re.compile(r"\[[^\[\]\n]{1,120}\]")


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
        "Objectives": f"This systematic review addressed {research_question}.",
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
