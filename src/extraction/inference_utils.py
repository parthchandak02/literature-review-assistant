from __future__ import annotations

import re

from src.models.enums import StudyDesign

_RESULT_NOT_EXTRACTABLE = "Result details were not extractable from the available text."

_COUNTRY_ALIASES: dict[str, str] = {
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "u.s.": "United States",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "south korea": "South Korea",
    "north korea": "North Korea",
    "ivory coast": "Cote d'Ivoire",
    "czech republic": "Czechia",
    "russia": "Russian Federation",
    "viet nam": "Vietnam",
}

_COUNTRY_NAMES = [
    "Afghanistan",
    "Albania",
    "Algeria",
    "Andorra",
    "Angola",
    "Antigua and Barbuda",
    "Argentina",
    "Armenia",
    "Australia",
    "Austria",
    "Azerbaijan",
    "Bahamas",
    "Bahrain",
    "Bangladesh",
    "Barbados",
    "Belarus",
    "Belgium",
    "Belize",
    "Benin",
    "Bhutan",
    "Bolivia",
    "Bosnia and Herzegovina",
    "Botswana",
    "Brazil",
    "Brunei",
    "Bulgaria",
    "Burkina Faso",
    "Burundi",
    "Cambodia",
    "Cameroon",
    "Canada",
    "Cape Verde",
    "Central African Republic",
    "Chad",
    "Chile",
    "China",
    "Colombia",
    "Comoros",
    "Congo",
    "Costa Rica",
    "Croatia",
    "Cuba",
    "Cyprus",
    "Czechia",
    "Denmark",
    "Djibouti",
    "Dominica",
    "Dominican Republic",
    "Ecuador",
    "Egypt",
    "El Salvador",
    "Equatorial Guinea",
    "Eritrea",
    "Estonia",
    "Eswatini",
    "Ethiopia",
    "Fiji",
    "Finland",
    "France",
    "Gabon",
    "Gambia",
    "Georgia",
    "Germany",
    "Ghana",
    "Greece",
    "Grenada",
    "Guatemala",
    "Guinea",
    "Guinea-Bissau",
    "Guyana",
    "Haiti",
    "Honduras",
    "Hungary",
    "Iceland",
    "India",
    "Indonesia",
    "Iran",
    "Iraq",
    "Ireland",
    "Israel",
    "Italy",
    "Jamaica",
    "Japan",
    "Jordan",
    "Kazakhstan",
    "Kenya",
    "Kiribati",
    "Kuwait",
    "Kyrgyzstan",
    "Laos",
    "Latvia",
    "Lebanon",
    "Lesotho",
    "Liberia",
    "Libya",
    "Liechtenstein",
    "Lithuania",
    "Luxembourg",
    "Madagascar",
    "Malawi",
    "Malaysia",
    "Maldives",
    "Mali",
    "Malta",
    "Marshall Islands",
    "Mauritania",
    "Mauritius",
    "Mexico",
    "Micronesia",
    "Moldova",
    "Monaco",
    "Mongolia",
    "Montenegro",
    "Morocco",
    "Mozambique",
    "Myanmar",
    "Namibia",
    "Nauru",
    "Nepal",
    "Netherlands",
    "New Zealand",
    "Nicaragua",
    "Niger",
    "Nigeria",
    "North Korea",
    "North Macedonia",
    "Norway",
    "Oman",
    "Pakistan",
    "Palau",
    "Panama",
    "Papua New Guinea",
    "Paraguay",
    "Peru",
    "Philippines",
    "Poland",
    "Portugal",
    "Qatar",
    "Romania",
    "Russian Federation",
    "Rwanda",
    "Saint Kitts and Nevis",
    "Saint Lucia",
    "Saint Vincent and the Grenadines",
    "Samoa",
    "San Marino",
    "Sao Tome and Principe",
    "Saudi Arabia",
    "Senegal",
    "Serbia",
    "Seychelles",
    "Sierra Leone",
    "Singapore",
    "Slovakia",
    "Slovenia",
    "Solomon Islands",
    "Somalia",
    "South Africa",
    "South Korea",
    "South Sudan",
    "Spain",
    "Sri Lanka",
    "Sudan",
    "Suriname",
    "Sweden",
    "Switzerland",
    "Syria",
    "Taiwan",
    "Tajikistan",
    "Tanzania",
    "Thailand",
    "Timor-Leste",
    "Togo",
    "Tonga",
    "Trinidad and Tobago",
    "Tunisia",
    "Turkey",
    "Turkmenistan",
    "Tuvalu",
    "Uganda",
    "Ukraine",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Uruguay",
    "Uzbekistan",
    "Vanuatu",
    "Vatican City",
    "Venezuela",
    "Vietnam",
    "Yemen",
    "Zambia",
    "Zimbabwe",
]

_REGION_ALIASES: dict[str, str] = {
    "quebec": "Canada",
    "ontario": "Canada",
    "sindh": "Pakistan",
    "tando muhammad khan": "Pakistan",
    "penaranda": "Philippines",
    "nueva ecija": "Philippines",
    "lviv": "Ukraine",
    "rivne": "Ukraine",
    "intibuca": "Honduras",
    "intibuca, honduras": "Honduras",
}

_RESULT_SECTION_RE = re.compile(
    r"(?is)\b(?:results?|findings?|outcomes?)\s*[:.-]?\s*(.+?)(?=\b(?:discussion|conclusions?|interpretation|funding|trial registration)\b\s*[:.-]|\Z)"
)
_RESULT_SENTENCE_HINTS = (
    "result",
    "finding",
    "improv",
    "increase",
    "decrease",
    "reduction",
    "higher",
    "lower",
    "significant",
    "associated",
    "agreement",
    "coverage",
    "timeliness",
    "usability",
    "acceptability",
    "satisfaction",
    "integration",
    "efficiency",
    "operability",
)
_NON_RESULT_PREFIXES = (
    "background",
    "introduction",
    "objective",
    "objectives",
    "aim",
    "aims",
    "methods",
    "method",
)
_QUALITATIVE_SIGNALS = (
    "interview",
    "interviews",
    "focus group",
    "focus groups",
    "qualitative",
    "thematic analysis",
    "realist evaluation",
    "key informant",
    "key informants",
)
_QUANTITATIVE_SIGNALS = (
    "%",
    " p<",
    " p =",
    " p=",
    "odds ratio",
    "risk ratio",
    "hazard ratio",
    "confidence interval",
    "incidence rate",
    "coverage",
    "increase",
    "decrease",
    "improvement",
    "difference",
    "mean",
    "median",
)
_NEGATION_INABILITY_RE = re.compile(
    r"\b(?:cannot|could not|unable to|not possible to|insufficient(?:ly)?|did not)\b"
    r"[^.]{0,120}\b(?:extract|summari[sz]e|determine|identify|report|infer|conclude)\b",
    flags=re.IGNORECASE,
)
_HYPOTHETICAL_HEDGING_RE = re.compile(
    r"\b(?:would typically|would generally|might include|could potentially|may suggest|may indicate)\b",
    flags=re.IGNORECASE,
)
_META_REFERENTIAL_RE = re.compile(
    r"\b(?:this\s+(?:text|excerpt|abstract|article)|the provided\s+(?:text|excerpt|abstract)|in this excerpt)\b",
    flags=re.IGNORECASE,
)
_QUANTITATIVE_ANCHOR_RE = re.compile(
    r"\b\d+(?:\.\d+)?%|\bp\s*[<=>]\s*0?\.\d+|\bn\s*=\s*\d+|\b\d+(?:\.\d+)?\s*"
    r"(?:participants?|patients?|facilities|sites|records?|studies|trials?)\b",
    flags=re.IGNORECASE,
)
_COMPARISON_SIGNAL_RE = re.compile(
    r"\b(?:increase[sd]?|decrease[sd]?|improv(?:e|ed|ement)|reduc(?:e|ed|tion)|"
    r"higher|lower|greater|less|difference|associated|association|correlat(?:ed|ion)|"
    r"odds ratio|risk ratio|hazard ratio|confidence interval|significant(?:ly)?)\b",
    flags=re.IGNORECASE,
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "to",
        "was",
        "were",
        "with",
    }
)


def result_not_extractable_text() -> str:
    return _RESULT_NOT_EXTRACTABLE


def infer_country_from_text(*texts: str) -> str | None:
    haystack = " ".join(str(text or "") for text in texts)
    haystack = re.sub(r"\s+", " ", haystack).strip()
    if not haystack:
        return None
    lowered = haystack.lower()
    for alias, canonical in _REGION_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return canonical
    for alias, canonical in _COUNTRY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return canonical
    for country in sorted(_COUNTRY_NAMES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(country.lower())}\b", lowered):
            return country
    alpha2_tokens = re.findall(r"\b[A-Z]{2}\b", haystack)
    for token in alpha2_tokens:
        country = _country_name_from_alpha2(token)
        if country:
            return country
    return None


def has_specific_result_summary(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(lowered.startswith(prefix + ":") or lowered.startswith(prefix + " ") for prefix in _NON_RESULT_PREFIXES):
        section_match = _RESULT_SECTION_RE.search(cleaned)
        if section_match:
            lowered = section_match.group(1).strip().lower()
        else:
            return False
    if _is_substantive_finding(lowered):
        return True
    return bool(_QUANTITATIVE_ANCHOR_RE.search(lowered))


def derive_concise_result_summary(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return _RESULT_NOT_EXTRACTABLE

    section_match = _RESULT_SECTION_RE.search(cleaned)
    if section_match:
        candidate = section_match.group(1).strip(" .;")
        if has_specific_result_summary(candidate):
            return _ensure_terminal_punctuation(candidate)

    sentences = [
        sentence.strip(" ;")
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
        if sentence.strip()
    ]
    result_sentences: list[str] = []
    for sentence in sentences:
        sentence_low = sentence.lower().lstrip()
        if any(sentence_low.startswith(prefix + ":") or sentence_low.startswith(prefix + " ") for prefix in _NON_RESULT_PREFIXES):
            continue
        if has_specific_result_summary(sentence):
            result_sentences.append(_ensure_terminal_punctuation(sentence))
        if len(result_sentences) >= 2:
            break
    if result_sentences:
        return " ".join(result_sentences)
    return _RESULT_NOT_EXTRACTABLE


def _country_name_from_alpha2(code: str) -> str | None:
    try:
        import pycountry
    except Exception:
        return None
    country = pycountry.countries.get(alpha_2=str(code or "").upper())
    if not country:
        return None
    name = str(getattr(country, "name", "") or "").strip()
    if not name:
        return None
    return _COUNTRY_ALIASES.get(name.lower(), name)


def _content_words(text: str) -> list[str]:
    tokens = re.findall(r"[a-z][a-z'-]{2,}", text.lower())
    return [token for token in tokens if token not in _STOP_WORDS]


def _has_quantitative_anchor(text: str) -> bool:
    lowered = text.lower()
    return bool(_QUANTITATIVE_ANCHOR_RE.search(text)) or any(signal in lowered for signal in _QUANTITATIVE_SIGNALS)


def _has_comparison_anchor(text: str) -> bool:
    return bool(_COMPARISON_SIGNAL_RE.search(text))


def _is_substantive_finding(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if _NEGATION_INABILITY_RE.search(cleaned):
        return False
    if _HYPOTHETICAL_HEDGING_RE.search(cleaned):
        return False
    if _META_REFERENTIAL_RE.search(cleaned):
        return False

    content_words = _content_words(cleaned)
    unique_ratio = (len(set(content_words)) / len(content_words)) if content_words else 0.0
    has_quantitative_anchor = _has_quantitative_anchor(cleaned)
    has_comparison_anchor = _has_comparison_anchor(cleaned)
    has_qualitative_anchor = any(signal in lowered for signal in _QUALITATIVE_SIGNALS)

    if len(content_words) >= 6 and unique_ratio < 0.3:
        return False
    if len(cleaned) < 80 and not (has_quantitative_anchor or has_comparison_anchor or has_qualitative_anchor):
        return False
    if len(content_words) < 3 and not (has_quantitative_anchor or has_comparison_anchor):
        return False
    return True


def should_promote_to_mixed_methods(
    study_design: StudyDesign,
    *,
    summary_text: str,
    raw_text: str,
    outcome_names: list[str] | None = None,
) -> bool:
    if study_design not in {StudyDesign.QUALITATIVE, StudyDesign.USABILITY_STUDY}:
        return False
    haystack = " ".join(
        [
            str(summary_text or ""),
            str(raw_text or ""),
            " ".join(str(name or "") for name in (outcome_names or [])),
        ]
    ).lower()
    has_qualitative = any(token in haystack for token in _QUALITATIVE_SIGNALS)
    has_quantitative = any(token in haystack for token in _QUANTITATIVE_SIGNALS) or bool(
        re.search(r"\b\d+(?:\.\d+)?%|\bp\s*[<=>]\s*0?\.\d+|\bn\s*=\s*\d+\b", haystack)
    )
    return has_qualitative and has_quantitative


def _ensure_terminal_punctuation(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return value
    if value[-1] in ".!?":
        return value
    return value + "."
