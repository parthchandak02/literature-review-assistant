"""Operator-provided PDF drop folder for papers that resist automated retrieval."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.config.env_context import get_env
from src.search.pdf_parse import is_pdf_bytes

logger = logging.getLogger(__name__)

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_FILENAME_DOI_RE = re.compile(r"10\.\d{4,9}[-_][-._;()/:A-Z0-9]+", re.IGNORECASE)


def _doi_candidates_from_text(text: str) -> list[str]:
    """Extract DOI strings from filename text, including underscore variants."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _DOI_RE.finditer(text):
        normalized = _normalize_doi(match.group(0))
        if normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    for match in _FILENAME_DOI_RE.finditer(text):
        normalized = _normalize_doi(re.sub(r"^(10\.\d{4,9})[-_]", r"\1/", match.group(0), count=1))
        if normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found

_index_mtime: float | None = None
_index: dict[str, Path] = {}


def manual_pdf_directory() -> Path | None:
    """Return configured manual PDF directory, if any."""
    raw = (
        (get_env("FULLTEXT_MANUAL_PDF_DIR") or "").strip()
        or (get_env("MANUAL_PDF_DIR") or "").strip()
    )
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _normalize_doi(doi: str) -> str:
    bare = doi.strip()
    if "doi.org/" in bare.lower():
        bare = bare.split("doi.org/", 1)[-1]
    return bare.lower().rstrip(".")


def _rebuild_index(directory: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for pdf in directory.rglob("*.pdf"):
        if not pdf.is_file():
            continue
        haystack = f"{pdf.name} {pdf.stem}"
        for normalized in _doi_candidates_from_text(haystack):
            mapping[normalized] = pdf
    logger.info("manual_ingest: indexed %d PDFs under %s", len(mapping), directory)
    return mapping


def _doi_index(directory: Path) -> dict[str, Path]:
    global _index_mtime, _index
    mtime = directory.stat().st_mtime
    if _index_mtime != mtime or not _index:
        _index = _rebuild_index(directory)
        _index_mtime = mtime
    return _index


def find_manual_pdf_path(doi: str) -> Path | None:
    """Locate a manually dropped PDF whose filename contains the DOI."""
    directory = manual_pdf_directory()
    if not directory or not doi:
        return None
    normalized = _normalize_doi(doi)
    return _doi_index(directory).get(normalized)


def load_manual_pdf_bytes(doi: str) -> bytes | None:
    """Load PDF bytes from the operator drop folder when DOI matches filename."""
    path = find_manual_pdf_path(doi)
    if not path:
        return None
    body = path.read_bytes()
    if not is_pdf_bytes(body):
        logger.warning("manual_ingest: %s is not a valid PDF", path)
        return None
    return body


def reset_manual_index_cache() -> None:
    """Clear cached index (for tests)."""
    global _index_mtime, _index
    _index_mtime = None
    _index = {}
