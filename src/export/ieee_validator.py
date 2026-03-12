"""IEEE manuscript validation: abstract length, cite resolution, reference count."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of IEEE validation."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _extract_abstract(tex_content: str) -> str | None:
    """Extract abstract text from LaTeX."""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex_content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _count_words(text: str) -> int:
    """Count words in text, normalizing common LaTeX markup to plain text."""
    # Replace LaTeX command forms like \textbf{foo} or \cite{A,B} with
    # their argument text so command names and braces are not counted.
    normalized = re.sub(r"\\[A-Za-z]+\{([^}]*)\}", r" \1 ", text)
    # Drop any remaining control sequences (e.g. \%, \&, \newline).
    normalized = re.sub(r"\\[A-Za-z]+|\\.", " ", normalized)
    normalized = normalized.replace("{", " ").replace("}", " ")
    words = re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?", normalized)
    return len(words)


def _extract_cite_keys(tex_content: str) -> set[str]:
    """Extract all \\cite{key} keys from LaTeX.

    A single cite command may carry a comma-separated list (for example
    ``\\cite{KeyA2020,KeyB2021}``). Validation must compare each key
    independently against BibTeX entries.
    """
    keys: set[str] = set()
    for raw_group in re.findall(r"\\cite\{([^}]+)\}", tex_content):
        for key in raw_group.split(","):
            stripped = key.strip()
            if stripped:
                keys.add(stripped)
    return keys


def _extract_bib_citekeys(bib_content: str) -> set[str]:
    """Extract all @entry{citekey, ...} keys from BibTeX."""
    return set(re.findall(r"@\w+\{([^,]+),", bib_content))


def validate_ieee(
    tex_content: str,
    bib_content: str,
    *,
    abstract_min: int = 150,
    abstract_max: int = 250,
    ref_min: int = 30,
    ref_max: int = 80,
) -> ValidationResult:
    """Validate IEEE manuscript.

    Checks:
    - Abstract 150-250 words
    - All \\cite{} resolve in .bib
    - Reference count warning if < 30 or > 80
    - No [?] or placeholder text
    """
    errors: list[str] = []
    warnings: list[str] = []

    abstract = _extract_abstract(tex_content)
    if abstract is None:
        errors.append("No abstract found")
    else:
        wc = _count_words(abstract)
        if wc < abstract_min:
            errors.append(f"Abstract too short: {wc} words (min {abstract_min})")
        elif wc > abstract_max:
            errors.append(f"Abstract too long: {wc} words (max {abstract_max})")

    cite_keys = _extract_cite_keys(tex_content)
    bib_keys = _extract_bib_citekeys(bib_content)
    unresolved = cite_keys - bib_keys
    if unresolved:
        errors.append(f"Unresolved citations: {sorted(unresolved)}")

    ref_count = len(bib_keys)
    if ref_count < ref_min:
        warnings.append(f"Reference count low: {ref_count} (typical min {ref_min})")
    elif ref_count > ref_max:
        warnings.append(f"Reference count high: {ref_count} (typical max {ref_max})")

    if "[?]" in tex_content or "[Number]" in tex_content or "[Year]" in tex_content:
        warnings.append("Placeholder text detected: [?], [Number], or [Year]")

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
