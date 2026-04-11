"""Deterministic renderers for structured section/manuscript drafts."""

from __future__ import annotations

from src.models.writing import SectionBlock, StructuredManuscriptDraft, StructuredSectionDraft
from src.writing.headings import normalize_heading_for_parity, sanitize_heading_title


def _dedupe_citations(citations: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for citation in citations:
        key = str(citation or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def collect_section_citations(section: StructuredSectionDraft) -> list[str]:
    """Collect citekeys from structured section fields in stable order."""
    ordered: list[str] = []
    seen: set[str] = set()
    for key in _dedupe_citations(section.cited_keys or []):
        seen.add(key)
        ordered.append(key)
    for block in section.blocks:
        for key in _dedupe_citations(block.citations or []):
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)
    return ordered


def _append_citations(text: str, citations: list[str], *, bullet_list: bool = False) -> str:
    body = text.strip()
    ordered = _dedupe_citations(citations)
    if not ordered:
        return body
    suffix = f" [{', '.join(ordered)}]"
    if bullet_list:
        lines = [line.rstrip() for line in body.splitlines() if line.strip()]
        if not lines:
            return ""
        lines[-1] = f"{lines[-1]}{suffix}"
        return "\n".join(lines)
    return f"{body}{suffix}".strip()


def _render_block_markdown(block: SectionBlock) -> str:
    if block.block_type == "subheading":
        level = min(max(int(block.level or 3), 3), 4)
        title = sanitize_heading_title(block.text)
        return f"{'#' * level} {title}".strip()
    if block.block_type == "bullet_list":
        items = [item.strip(" -") for item in block.text.split("\n") if item.strip()]
        rendered = "\n".join(f"- {item}" for item in items)
        return _append_citations(rendered, block.citations or [], bullet_list=True)
    return _append_citations(block.text, block.citations or [])


def render_section_markdown(section: StructuredSectionDraft) -> str:
    """Render one structured section to markdown deterministically."""
    lines: list[str] = []
    for block in section.blocks:
        rendered = _render_block_markdown(block)
        if rendered:
            lines.append(rendered)
    return "\n\n".join(lines).strip()


def render_section_latex(section: StructuredSectionDraft) -> str:
    """Render one structured section to LaTeX body content deterministically."""
    lines: list[str] = []
    for block in section.blocks:
        text = block.text.strip()
        if not text:
            continue
        if block.block_type == "subheading":
            level = min(max(int(block.level or 3), 3), 4)
            title = sanitize_heading_title(text)
            if level == 3:
                lines.append(f"\\subsection{{{title}}}")
            else:
                lines.append(f"\\subsubsection{{{title}}}")
            continue
        if block.block_type == "bullet_list":
            items = [item.strip(" -") for item in text.split("\n") if item.strip()]
            if not items:
                continue
            lines.append("\\begin{itemize}")
            rendered_items = [f"\\item {item}" for item in items]
            ordered = _dedupe_citations(block.citations or [])
            if ordered:
                rendered_items[-1] = f"{rendered_items[-1]} [{', '.join(ordered)}]"
            lines.extend(rendered_items)
            lines.append("\\end{itemize}")
            continue
        lines.append(_append_citations(text, block.citations or []))
    return "\n\n".join(lines).strip()


def render_manuscript_markdown(manuscript: StructuredManuscriptDraft) -> dict[str, str]:
    """Render all section drafts to markdown by section key."""
    return {section.section_key: render_section_markdown(section) for section in manuscript.sections}


def render_manuscript_latex(manuscript: StructuredManuscriptDraft) -> dict[str, str]:
    """Render all section drafts to LaTeX body content by section key."""
    return {section.section_key: render_section_latex(section) for section in manuscript.sections}


def collect_section_heading_inventory(section: StructuredSectionDraft) -> list[tuple[int, str]]:
    """Return canonical heading inventory for one structured section."""
    headings: list[tuple[int, str]] = []
    for block in section.blocks:
        if block.block_type != "subheading":
            continue
        level = min(max(int(block.level or 3), 3), 4)
        headings.append((level, normalize_heading_for_parity(sanitize_heading_title(block.text))))
    return headings


def collect_manuscript_heading_inventory(manuscript: StructuredManuscriptDraft) -> dict[str, list[tuple[int, str]]]:
    """Return canonical heading inventory for each structured manuscript section."""
    return {section.section_key: collect_section_heading_inventory(section) for section in manuscript.sections}

