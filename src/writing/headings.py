"""Shared heading normalization and inventory helpers."""

from __future__ import annotations

import re

SECTION_REQUIRED_SUBHEADINGS: dict[str, tuple[str, ...]] = {
    "methods": (
        "Eligibility Criteria",
        "Information Sources",
        "Selection Process",
        "Synthesis Methods",
    ),
    "results": (
        "Study Selection",
        "Study Characteristics",
        "Synthesis of Findings",
    ),
    "discussion": (
        "Principal Findings",
        "Comparison with Prior Work",
        "Strengths and Limitations",
        "Implications for Practice",
        "Implications for Research",
    ),
}

_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$")
_SENTENCE_START_RE = re.compile(
    r"^(The|This|These|We|Our|In|Across|To|A|An|Studies|Study|Data|Evidence|Findings|Overall|One|Demographic|Meta-analysis|Also)\b"
)
_TITLE_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z0-9()/:,\-']*$")
_CONNECTOR_TAIL = {"and", "or", "of", "for", "to", "with"}
_TERMINAL_CITATION_RE = re.compile(r"(?:\s*\[[^\]]+\])+\s*$")


def strip_terminal_citations(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    return _TERMINAL_CITATION_RE.sub("", value).rstrip()


def normalize_heading_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_terminal_citations(str(text or "")).strip().lower())


def normalize_heading_for_parity(raw: str) -> str:
    title = strip_terminal_citations(str(raw or "").strip())
    title = re.sub(r"\\[A-Za-z]+\{([^}]*)\}", r"\1", title)
    title = re.sub(r"[^A-Za-z0-9 ]+", " ", title)
    return re.sub(r"\s{2,}", " ", title).strip().lower()


def sanitize_heading_title(raw_title: str) -> str:
    """Normalize heading titles for consistent markdown/LaTeX rendering."""
    title = re.sub(r"\s{2,}", " ", str(raw_title or "").strip())
    title = strip_terminal_citations(title)

    spill_markers = (
        " due to ",
        " because ",
        " although ",
        " while ",
        " since ",
        " where ",
        " when ",
        " after ",
        " before ",
        " during ",
    )
    lower = title.lower()
    for marker in spill_markers:
        idx = lower.find(marker)
        if idx > 0:
            title = title[:idx].strip()
            break

    title = re.sub(
        r"\s+(Due|Because|Although|While|Since|Where|When|After|Before|During)$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()

    connectors = {"and", "or", "of", "for", "to", "with", "in", "on", "by"}
    words = title.split()
    if len(words) > 6:
        keep: list[str] = []
        for idx, word in enumerate(words):
            clean = word.strip(".,;:!?")
            if idx > 0 and clean[:1].islower() and clean.lower() not in connectors:
                break
            keep.append(clean)
        title = " ".join(keep).strip()

    return title


def normalize_subsection_heading_layout(text: str) -> str:
    """Split inline heading+body patterns into canonical multiline markdown."""
    text = re.sub(r"\s+(#{2,6}\s+)", r"\n\n\1", text)
    out_lines: list[str] = []
    lines = text.splitlines()
    i = 0

    def _looks_title_fragment(s: str) -> bool:
        words = s.strip().split()
        if not words or len(words) > 5:
            return False
        return all(_TITLE_TOKEN_RE.match(w) or w.lower() in _CONNECTOR_TAIL for w in words)

    while i < len(lines):
        line = lines[i]
        m = _HEADING_RE.match(line.strip())
        if m:
            level = m.group(1)
            tail = strip_terminal_citations(m.group(2).strip())
            known_prefix_map = {
                "data items": "Data Items",
                "comparison with prior work": "Comparison with Prior Work",
                "search strategy": "Search Strategy",
                "risk of bias and critical appraisal": "Risk of Bias and Critical Appraisal",
            }
            tail_low = tail.lower()
            matched_known = False
            for raw_prefix, canonical in known_prefix_map.items():
                needle = raw_prefix + " "
                if tail_low.startswith(needle):
                    body = tail[len(raw_prefix) :].strip()
                    out_lines.extend([f"{level} {canonical}", ""])
                    if body:
                        out_lines.append(body)
                    matched_known = True
                    break
            if matched_known:
                i += 1
                continue
            if len(level) >= 4:
                spill = re.search(
                    r"\b(The|This|These|We|Our|In|Across|To|A|An|Evidence|Findings|Overall|One|Demographic|Meta-analysis|Also)\b",
                    tail,
                )
                if spill and spill.start() > 10:
                    left = tail[: spill.start()].strip(" -:")
                    right = tail[spill.start() :].strip()
                    if left and right:
                        out_lines.extend([f"{level} {left}", "", right])
                        i += 1
                        continue
            if " such as " in tail.lower():
                idx = tail.lower().find(" such as ")
                left = tail[:idx].strip()
                right = tail[idx + 1 :].strip()
                if left and right:
                    out_lines.extend([f"{level} {left}", "", right])
                    i += 1
                    continue
            nxt_idx = i + 1
            while nxt_idx < len(lines) and not lines[nxt_idx].strip():
                nxt_idx += 1
            nxt = lines[nxt_idx].strip() if nxt_idx < len(lines) else ""
            tail_words = tail.split()
            if nxt and not nxt.startswith("#"):
                if tail_words and tail_words[-1].lower() in _CONNECTOR_TAIL:
                    nxt_words = nxt.split()
                    if nxt_words:
                        first = nxt_words[0]
                        first_clean = first.rstrip(".,;:!?")
                        if first_clean and first_clean[:1].isupper():
                            if first != first_clean:
                                new_heading = f"{level} {tail} {first_clean}".strip()
                                new_body = " ".join(nxt_words[1:]).strip()
                                if new_body:
                                    out_lines.extend([new_heading, "", new_body])
                                    i = nxt_idx + 1
                                    continue
                    consumed = 0
                    for j, word in enumerate(nxt_words):
                        if (
                            j > 0
                            and word.lower() in {"the", "this", "these", "we", "our", "in", "across", "to", "a", "an"}
                            and j + 1 < len(nxt_words)
                            and nxt_words[j + 1][:1].islower()
                        ):
                            break
                        if _TITLE_TOKEN_RE.match(word):
                            consumed = j + 1
                            if consumed >= 4:
                                break
                            continue
                        break
                    if consumed > 0:
                        title_join = " ".join(nxt_words[:consumed]).strip()
                        body_rest = " ".join(nxt_words[consumed:]).strip()
                        line = f"{level} {tail} {title_join}".strip()
                        if body_rest:
                            out_lines.extend([line, "", body_rest])
                            i = nxt_idx + 1
                            continue
                        out_lines.append(line)
                        i = nxt_idx + 1
                        continue
                if (
                    nxt[:1].islower()
                    and len(tail_words) >= 3
                    and tail_words[-1][:1].isupper()
                    and tail_words[-1].isalpha()
                ):
                    spill = tail_words[-1]
                    heading_tail = " ".join(tail_words[:-1]).strip()
                    if heading_tail:
                        out_lines.extend([f"{level} {heading_tail}", "", f"{spill} {nxt}".strip()])
                        i = nxt_idx + 1
                        continue
                if _SENTENCE_START_RE.match(nxt) and not _looks_title_fragment(nxt):
                    out_lines.extend([f"{level} {tail}", "", nxt])
                    i = nxt_idx + 1
                    continue
            words = tail.split()
            if len(words) >= 4:
                for idx in range(2, min(len(words), 12)):
                    left_words = words[:idx]
                    right_words = words[idx:]
                    left_ok = all(_TITLE_TOKEN_RE.match(w) or w.lower() in _CONNECTOR_TAIL for w in left_words)
                    if not left_ok:
                        continue
                    right = " ".join(right_words).strip()
                    if (
                        left_words
                        and left_words[-1].lower() in _CONNECTOR_TAIL
                        and right_words
                        and not _SENTENCE_START_RE.match(right)
                    ):
                        if _looks_title_fragment(right):
                            continue
                        consumed = 0
                        for pos, word in enumerate(right_words):
                            if (
                                pos > 0
                                and word.lower() in {"the", "this", "these", "we", "our", "in", "across", "to", "a", "an"}
                                and pos + 1 < len(right_words)
                                and right_words[pos + 1][:1].islower()
                            ):
                                break
                            if _TITLE_TOKEN_RE.match(word):
                                consumed += 1
                                if consumed >= 3:
                                    break
                                continue
                            break
                        if 0 < consumed < len(right_words):
                            merged_left = left_words + right_words[:consumed]
                            merged_right = " ".join(right_words[consumed:]).strip()
                            if merged_right:
                                out_lines.extend([f"{level} {' '.join(merged_left)}", "", merged_right])
                                i += 1
                                break
                    if (
                        right_words
                        and right_words[0].lower() in _CONNECTOR_TAIL
                        and len(left_words) >= 2
                        and len(right_words) >= 2
                        and right_words[1][:1].islower()
                    ):
                        heading_title = " ".join(left_words).strip()
                        body = " ".join(right_words).strip()
                        if heading_title and body:
                            out_lines.extend([f"{level} {heading_title}", "", body])
                            i += 1
                            break
                    if (_SENTENCE_START_RE.match(right) or (right and right[0].isupper() and any(c in right for c in ".,"))) and (
                        not _looks_title_fragment(right)
                    ):
                        out_lines.extend([f"{level} {' '.join(left_words)}", "", right])
                        i += 1
                        break
                else:
                    out_lines.append(line)
                    i += 1
                    continue
                continue
        out_lines.append(line)
        i += 1
    return "\n".join(out_lines)


def split_markdown_paragraphs(lines: list[str]) -> list[str]:
    paragraph_buf: list[str] = []
    paragraphs: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph_buf:
                paragraphs.append(" ".join(paragraph_buf).strip())
                paragraph_buf.clear()
            continue
        if stripped.startswith("#"):
            if paragraph_buf:
                paragraphs.append(" ".join(paragraph_buf).strip())
                paragraph_buf.clear()
            continue
        paragraph_buf.append(stripped)
    if paragraph_buf:
        paragraphs.append(" ".join(paragraph_buf).strip())
    return paragraphs


def markdown_subheading_paragraphs(lines: list[str], *, min_level: int = 3, max_level: int = 4) -> dict[str, list[str]]:
    subheading_blocks: dict[str, list[str]] = {}
    current_heading: str | None = None
    paragraph_buf: list[str] = []

    def _flush_paragraph() -> None:
        nonlocal paragraph_buf
        if current_heading is None or not paragraph_buf:
            paragraph_buf = []
            return
        subheading_blocks.setdefault(current_heading, []).append(" ".join(paragraph_buf).strip())
        paragraph_buf = []

    for line in lines:
        stripped = line.strip()
        match = _HEADING_RE.match(stripped)
        if match:
            _flush_paragraph()
            level = len(match.group(1))
            if min_level <= level <= max_level:
                current_heading = normalize_heading_text(match.group(2))
            else:
                current_heading = None
            continue
        if not stripped:
            _flush_paragraph()
            continue
        if current_heading is not None:
            paragraph_buf.append(stripped)
    _flush_paragraph()
    return subheading_blocks


def extract_markdown_heading_inventory(md_text: str, *, min_level: int = 2, max_level: int = 4) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    normalized_md = normalize_subsection_heading_layout(md_text)
    for line in normalized_md.splitlines():
        match = _HEADING_RE.match(line.strip())
        if not match:
            continue
        level = len(match.group(1))
        if min_level <= level <= max_level:
            out.append((level, normalize_heading_for_parity(sanitize_heading_title(match.group(2)))))
    return out
