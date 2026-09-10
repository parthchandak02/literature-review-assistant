from src.web.config_generator import (
    _build_yaml,
    _GeneratedScopingConfig,
    _Pcc,
)


def _scoping_defaults() -> dict:
    return {
        "target_databases": ["openalex", "pubmed", "semantic_scholar"],
        "target_sections": ["abstract", "methods", "results", "discussion", "conclusion"],
        "date_range_start": 2010,
        "date_range_end": 2026,
        "living_review": False,
        "last_search_date": None,
        "protocol": {
            "registered": False,
            "registry": "PROSPERO",
            "registration_number": "",
            "registration_date": "",
            "url": "",
        },
        "funding": {"source": "No funding received", "grant_number": "", "funder": ""},
        "conflicts_of_interest": "None declared",
        "search_overrides": None,
        "domain_expert": None,
    }


def _make_scoping_config() -> _GeneratedScopingConfig:
    return _GeneratedScopingConfig(
        research_question="What evidence exists on digital health literacy for older adults?",
        review_type="scoping",
        pcc=_Pcc(
            population="Older adults in community settings",
            concept="Digital health literacy interventions",
            context="Community and primary-care settings, 2010-present",
        ),
        keywords=[
            "digital health literacy",
            "older adults",
            "health literacy",
            "digital literacy",
            "community health",
            "patient education",
            "telehealth literacy",
            "eHealth literacy",
            "mobile health literacy",
            "community settings",
            "primary care",
            "aging population",
            "health information",
            "technology adoption",
            "digital skills training",
        ],
        domain="Digital health literacy for older adults",
        scope="Maps intervention types and outcomes for digital health literacy in community settings.",
        inclusion_criteria=[
            "Peer-reviewed empirical studies on digital health literacy.",
            "Studies in community or outpatient settings.",
            "English-language publications since 2010.",
            "Studies reporting intervention or outcome information.",
        ],
        exclusion_criteria=[
            "Editorials without empirical data.",
            "Hospital-only studies without community relevance.",
            "Studies unrelated to digital health literacy.",
        ],
        search_overrides=None,
    )


def test_build_yaml_emits_pcc_question_framework_and_osf_registry() -> None:
    yaml_text = _build_yaml(
        _make_scoping_config(),
        defaults=_scoping_defaults(),
        question_framework="pcc",
    )
    assert 'review_type: "scoping"' in yaml_text
    assert 'question_framework: "pcc"' in yaml_text
    assert "pcc:" in yaml_text
    assert 'concept: "Digital health literacy interventions"' in yaml_text
    assert 'registry: "OSF"' in yaml_text


def test_build_yaml_maps_pcc_to_backward_compatible_pico_block() -> None:
    yaml_text = _build_yaml(_make_scoping_config(), defaults=_scoping_defaults())
    assert 'intervention: "Digital health literacy interventions"' in yaml_text
    assert 'comparison: "Community and primary-care settings, 2010-present"' in yaml_text
    assert 'outcome: "evidence characteristics and gaps"' in yaml_text
