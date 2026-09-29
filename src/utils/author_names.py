"""Family-name extraction for short author labels ("Roth et al.")."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

_INITIALS_RE = re.compile(r"^(?:[A-Z]\.?-?){1,3}$")
_PARTICLES = frozenset(
    {
        "van",
        "von",
        "der",
        "den",
        "de",
        "del",
        "della",
        "di",
        "da",
        "dos",
        "du",
        "la",
        "le",
        "ten",
        "ter",
        "bin",
        "al",
        "el",
    }
)
_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "phd", "md"})
_TITLES = frozenset({"dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms."})
_VIETNAMESE_FAMILIES = frozenset(
    {
        "nguyen",
        "tran",
        "le",
        "pham",
        "hoang",
        "huynh",
        "phan",
        "vu",
        "vo",
        "dang",
        "bui",
        "do",
        "ho",
        "ngo",
        "duong",
        "ly",
        "trinh",
        "dinh",
        "truong",
    }
)
_VIETNAMESE_MIDDLES = frozenset({"van", "thi", "duc", "minh", "thanh", "ngoc", "quoc", "huu", "thu", "hong"})
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def _fold(token: str) -> str:
    return (
        "".join(c for c in unicodedata.normalize("NFKD", token) if not unicodedata.combining(c))
        .lower()
        .replace("đ", "d")
    )


def _is_initials(token: str) -> bool:
    return bool(_INITIALS_RE.match(token))


def _strip_affixes(tokens: list[str]) -> list[str]:
    while tokens and tokens[0].lower() in _TITLES:
        tokens = tokens[1:]
    while tokens and tokens[-1].lower().rstrip(",") in _SUFFIXES:
        tokens = tokens[:-1]
    return tokens


def family_name(author: Any) -> str:
    """Return the family name of one author entry, or "" when unknown.

    Handles dicts ({"family"|"last": ...}), "Family, Given", "Given M. Family",
    "Family G." / "Family GK" (PubMed style), CJK script and Vietnamese
    family-first order ("Nguyen Van An").
    """
    if isinstance(author, dict):
        return str(author.get("family") or author.get("last") or "").strip()
    text = re.sub(r"\s+", " ", str(author or "")).strip()
    if not text:
        return ""
    if "," in text:
        head, _, tail = text.partition(",")
        if head.strip() and tail.strip().lower() not in _SUFFIXES:
            text = head
            head_tokens = _strip_affixes(head.split())
            if len(head_tokens) > 1 and not all(_is_initials(t) for t in head_tokens[1:]):
                return " ".join(head_tokens)
        else:
            text = head
    tokens = _strip_affixes(text.split())
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    if _CJK_RE.search(text):
        return tokens[0]
    if not _is_initials(tokens[0]) and all(_is_initials(t) for t in tokens[1:]):
        return tokens[0]
    if len(tokens) >= 3 and _fold(tokens[0]) in _VIETNAMESE_FAMILIES and _fold(tokens[1]) in _VIETNAMESE_MIDDLES:
        return tokens[0]
    family = [tokens[-1]]
    for tok in reversed(tokens[1:-1]):
        if tok.lower() in _PARTICLES:
            family.insert(0, tok)
        else:
            break
    return " ".join(family)


def parse_author_list(authors_raw: Any) -> list[Any]:
    """Normalise authors stored as a list, JSON array string, or delimited string."""
    if isinstance(authors_raw, list):
        return [a for a in authors_raw if a]
    text = str(authors_raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            return [a for a in parsed if a]
    if ";" in text:
        return [p.strip() for p in text.split(";") if p.strip()]
    if " and " in text:
        return [p.strip() for p in text.split(" and ") if p.strip()]
    return [text]


def first_author_family(authors_raw: Any) -> tuple[str, bool]:
    """Return (first author's family name, has more than one author)."""
    authors = parse_author_list(authors_raw)
    if not authors:
        return "", False
    return family_name(authors[0]), len(authors) > 1
