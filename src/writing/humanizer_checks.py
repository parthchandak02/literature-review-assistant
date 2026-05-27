"""Deterministic checks for runtime humanizer quality gates."""

from __future__ import annotations

import math
import re
from collections import Counter
from statistics import mean, pstdev

from pydantic import BaseModel

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

_WORD_RE = re.compile(r"[A-Za-z']+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CONNECTIVE_RE = re.compile(
    r"\b(however|moreover|furthermore|additionally|consequently|nevertheless|therefore|thus|hence)\b",
    re.IGNORECASE,
)

_BLACKLIST_ENGLISH = {
    "delve",
    "tapestry",
    "pivotal",
    "crucial",
    "foster",
    "underscore",
    "showcase",
    "testament",
    "myriad",
    "nuanced",
    "holistic",
    "synergy",
    "leverage",
    "paradigm",
    "robust",
    "comprehensive",
    "innovative",
    "seamless",
    "streamline",
    "empower",
    "facilitate",
    "optimize",
    "beacon",
    "transformative",
    "resonate",
    "groundbreaking",
    "state-of-the-art",
    "cutting-edge",
    "unparalleled",
    "game-changer",
    "utilize",
    "commence",
    "endeavor",
    "ascertain",
    "ameliorate",
    "notwithstanding",
    "aforementioned",
    "henceforth",
    "thereby",
    "wherein",
    "herein",
}

_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("significance_inflation", HIGH, r"\b(stands as a testament|plays a (vital|crucial) role|pivotal moment)\b"),
    ("superficial_ing_clause", MEDIUM, r",\s*(highlighting|underscoring|emphasizing|fostering|showcasing)\b"),
    ("promotional_language", HIGH, r"\b(vibrant|must-visit|world-class|state-of-the-art|cutting-edge)\b"),
    ("vague_attribution", MEDIUM, r"\b(experts argue|widely regarded as|according to some analysts)\b"),
    ("challenges_prospects_template", MEDIUM, r"\b(despite these challenges|future outlook|looking ahead)\b"),
    ("ghost_citation_claim", HIGH, r"\b(studies show|research indicates|data suggests|experts agree)\b"),
    ("copula_avoidance", LOW, r"\b(serves as a|stands as a|functions as a|features a)\b"),
    ("negative_parallelism", MEDIUM, r"\b(it's not [^.]+\. ?it's [^.]+)\b"),
    ("rule_of_three_triplet", MEDIUM, r"\b\w+,\s+\w+,\s+and\s+\w+\b"),
    ("false_range_parallel", LOW, r"\bfrom [^,.;]+ to [^,.;]+,\s*from [^,.;]+ to [^,.;]+\b"),
    ("latinate_vocabulary", MEDIUM, r"\b(utilize|commence|endeavor|ascertain|ameliorate)\b"),
    ("personification", LOW, r"\b(the data tells us|the numbers speak|the market demands)\b"),
    ("em_dash_overuse", MEDIUM, r"[—–]"),
    ("sycophantic_tone", HIGH, r"\b(great question|you're absolutely right|that's an excellent point)\b"),
    ("cutoff_disclaimer", HIGH, r"\b(as of my last training|I don't have access to real-time data)\b"),
    ("chatbot_artifact", HIGH, r"\b(I'd be happy to help|as an AI|feel free to ask)\b"),
    ("both_sides_diplomacy", MEDIUM, r"\b(on the one hand|on the other|both perspectives have valid points)\b"),
    (
        "filler_phrase",
        MEDIUM,
        r"\b(in order to|due to the fact that|it is important to note that|at the end of the day)\b",
    ),
    ("excessive_hedging", MEDIUM, r"\b(could potentially|to some extent|one might argue|it seems that)\b"),
    ("generic_conclusion", MEDIUM, r"\b(the future looks bright|exciting times ahead|in conclusion)\b"),
    ("over_explanation", LOW, r"\b(in other words|simply put|to put it differently|basically)\b"),
    ("navigate_metaphor", MEDIUM, r"\bnavigate\b"),
    ("formulaic_opening", HIGH, r"^\s*(In an increasingly|In today's|In the current landscape|In an ever-changing)"),
    ("forced_plot_twist", MEDIUM, r"\b(But here's the thing|The real point is|But there's a catch)\b"),
)


class HumanizerFlag(BaseModel):
    """Single deterministic humanizer finding."""

    tier: str
    code: str
    message: str
    span_hint: str | None = None


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _sentences(text: str) -> list[str]:
    chunks = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    return chunks or ([text.strip()] if text.strip() else [])


def _window_ttr(words: list[str], window: int = 100) -> float:
    if not words:
        return 1.0
    if len(words) <= window:
        return len(set(words)) / max(len(words), 1)
    ratios: list[float] = []
    for i in range(0, len(words), window):
        chunk = words[i : i + window]
        if chunk:
            ratios.append(len(set(chunk)) / len(chunk))
    return mean(ratios) if ratios else 1.0


def _sentence_burstiness(sentences: list[str]) -> float:
    lengths = [len(_words(s)) for s in sentences if s]
    if len(lengths) < 2:
        return 1.0
    avg = mean(lengths)
    if avg <= 0:
        return 1.0
    return pstdev(lengths) / avg


def _bigram_repetition(words: list[str]) -> int:
    if len(words) < 2:
        return 0
    bigrams = [f"{a} {b}" for a, b in zip(words, words[1:])]
    counts = Counter(bigrams)
    return sum(1 for n in counts.values() if n >= 3)


def _opener_diversity(sentences: list[str]) -> float:
    openers = []
    for sent in sentences:
        tokens = _words(sent)
        if len(tokens) >= 2:
            openers.append(f"{tokens[0]} {tokens[1]}")
        elif tokens:
            openers.append(tokens[0])
    if not openers:
        return 1.0
    return len(set(openers)) / len(openers)


def _punctuation_entropy(text: str) -> float:
    punct = [ch for ch in text if ch in ".,;:?!-()"]
    if not punct:
        return 0.0
    counts = Counter(punct)
    total = len(punct)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def _compressibility_ratio(text: str) -> float:
    if not text:
        return 1.0
    chunks = [text[i : i + 4] for i in range(max(0, len(text) - 3))]
    return len(set(chunks)) / max(len(chunks), 1)


def _metric_flags(text: str) -> list[HumanizerFlag]:
    flags: list[HumanizerFlag] = []
    words = _words(text)
    sents = _sentences(text)
    ttr = _window_ttr(words)
    burst = _sentence_burstiness(sents)
    repeats = _bigram_repetition(words)
    connective_density = len(_CONNECTIVE_RE.findall(text)) / max(len(words), 1) * 100.0
    opener_diversity = _opener_diversity(sents)
    compressibility = _compressibility_ratio(text.lower())
    punctuation_entropy = _punctuation_entropy(text)

    if ttr < 0.35:
        flags.append(HumanizerFlag(tier=MEDIUM, code="metric_ttr_low", message=f"TTR low ({ttr:.2f})"))
    if burst < 0.35:
        flags.append(HumanizerFlag(tier=MEDIUM, code="metric_burstiness_low", message=f"Burstiness low ({burst:.2f})"))
    if repeats > 0:
        flags.append(HumanizerFlag(tier=MEDIUM, code="metric_bigram_repeat", message=f"Repeated bigrams ({repeats})"))
    if connective_density > 0.7:
        flags.append(
            HumanizerFlag(
                tier=MEDIUM,
                code="metric_connective_density_high",
                message=f"Connective density high ({connective_density:.2f}/100 words)",
            )
        )
    if opener_diversity < 0.70:
        flags.append(
            HumanizerFlag(
                tier=MEDIUM,
                code="metric_opener_diversity_low",
                message=f"Sentence opener diversity low ({opener_diversity:.2f})",
            )
        )
    if compressibility < 0.60:
        flags.append(
            HumanizerFlag(
                tier=LOW,
                code="metric_compressibility_high",
                message=f"Text appears formulaic ({compressibility:.2f})",
            )
        )
    if punctuation_entropy < 1.25:
        flags.append(
            HumanizerFlag(
                tier=LOW,
                code="metric_punctuation_entropy_low",
                message=f"Punctuation entropy low ({punctuation_entropy:.2f})",
            )
        )
    return flags


def scan_humanizer_flags(text: str) -> list[HumanizerFlag]:
    """Return deterministic severity-tiered flags for the humanizer skill."""
    out: list[HumanizerFlag] = []
    lowered = text.lower()
    for term in sorted(_BLACKLIST_ENGLISH):
        if re.search(rf"\b{re.escape(term)}\b", lowered, flags=re.IGNORECASE):
            out.append(HumanizerFlag(tier=HIGH, code="blacklist_term", message=f"Blacklisted term: {term}"))

    for code, tier, pattern in _PATTERNS:
        matches = list(re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE))
        for match in matches[:3]:
            out.append(
                HumanizerFlag(
                    tier=tier,
                    code=code,
                    message=f"Detected {code.replace('_', ' ')}",
                    span_hint=match.group(0)[:120],
                )
            )

    out.extend(_metric_flags(text))
    return out


def has_high_severity(flags: list[HumanizerFlag]) -> bool:
    """Return True when any high-severity finding is present."""
    return any(flag.tier == HIGH for flag in flags)


def format_flags_for_repair(flags: list[HumanizerFlag], limit: int = 12) -> str:
    """Render high-severity findings as compact bullet lines."""
    high = [f for f in flags if f.tier == HIGH][:limit]
    if not high:
        return ""
    return "\n".join(f"- {item.code}: {item.message}" for item in high)
