"""Deterministic renderers for structured section/manuscript drafts."""

from __future__ import annotations

from src.models.writing import SectionBlock, StructuredManuscriptDraft, StructuredSectionDraft


def _render_block_markdown(block: SectionBlock) -> str:
    if block.block_type == "subheading":
        level = min(max(int(block.level or 3), 3), 4)
        return f"{'#' * level} {block.text.strip()}".strip()
    if block.block_type == "bullet_list":
        items = [item.strip(" -") for item in block.text.split("\n") if item.strip()]
        return "\n".join(f"- {item}" for item in items)
    return block.text.strip()


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
            if level == 3:
                lines.append(f"\\subsection{{{text}}}")
            else:
                lines.append(f"\\subsubsection{{{text}}}")
            continue
        if block.block_type == "bullet_list":
            items = [item.strip(" -") for item in text.split("\n") if item.strip()]
            if not items:
                continue
            lines.append("\\begin{itemize}")
            lines.extend(f"\\item {item}" for item in items)
            lines.append("\\end{itemize}")
            continue
        lines.append(text)
    return "\n\n".join(lines).strip()


def render_manuscript_markdown(manuscript: StructuredManuscriptDraft) -> dict[str, str]:
    """Render all section drafts to markdown by section key."""
    return {section.section_key: render_section_markdown(section) for section in manuscript.sections}


def render_manuscript_latex(manuscript: StructuredManuscriptDraft) -> dict[str, str]:
    """Render all section drafts to LaTeX body content by section key."""
    return {section.section_key: render_section_latex(section) for section in manuscript.sections}

