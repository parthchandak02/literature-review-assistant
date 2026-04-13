from src.orchestration.resume import _extract_screening_kappa_from_phase_done_payloads


def test_extract_screening_kappa_falls_back_to_phase_3_screening() -> None:
    payloads = [
        {"phase": "screening_calibration", "summary": {}},
        {"phase": "phase_3_screening", "summary": {"kappa": 0.7084693681582486}},
    ]

    kappa, stage, kappa_n = _extract_screening_kappa_from_phase_done_payloads(payloads)

    assert kappa == 0.7084693681582486
    assert stage == "title_abstract"
    assert kappa_n == 0


def test_extract_screening_kappa_prefers_calibration_payload_when_present() -> None:
    payloads = [
        {"phase": "screening_calibration", "summary": {"kappa": 0.81, "sample_size": 12}},
        {"phase": "phase_3_screening", "summary": {"kappa": 0.70}},
    ]

    kappa, stage, kappa_n = _extract_screening_kappa_from_phase_done_payloads(payloads)

    assert kappa == 0.81
    assert stage == "title_abstract"
    assert kappa_n == 12
