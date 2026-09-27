from src.models.writing import StructuredAbstractOutput


def _payload(**overrides):
    base = {
        "background": "Falls are a leading cause of injury in older adults worldwide.",
        "objectives": "To assess the effects of pickleball on balance and fall risk.",
        "methods": "We searched OpenAlex, Europe PMC, and Crossref for empirical studies.",
        "results": "Three studies met the inclusion criteria and reported balance outcomes.",
        "conclusions": "Evidence is limited but suggests possible balance benefits.",
        "keywords": ["pickleball", "balance", "falls"],
    }
    base.update(overrides)
    return base


def test_overlong_field_is_trimmed_at_sentence_boundary() -> None:
    sentence = "Databases were searched with predefined terms and screened in duplicate. "
    long_methods = sentence * 30
    out = StructuredAbstractOutput.model_validate(_payload(methods=long_methods))
    assert len(out.methods) <= 1200
    assert out.methods.endswith(".")
    assert out.methods.startswith("Databases were searched")


def test_extra_keywords_are_capped() -> None:
    out = StructuredAbstractOutput.model_validate(_payload(keywords=[f"k{i}" for i in range(12)]))
    assert len(out.keywords) == 8


def test_in_range_payload_is_unchanged() -> None:
    payload = _payload()
    out = StructuredAbstractOutput.model_validate(payload)
    assert out.methods == payload["methods"]
