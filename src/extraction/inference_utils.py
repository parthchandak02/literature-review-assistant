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
    if any(token in lowered for token in _RESULT_SENTENCE_HINTS):
        return True
    if re.search(r"\b\d+(?:\.\d+)?%|\bp\s*[<=>]\s*0?\.\d+|\bn\s*=\s*\d+|\b\d+(?:\.\d+)?\s*(?:participants?|patients?|facilities|sites|records?)\b", lowered):
        return True
    return False


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
