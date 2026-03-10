from src.main import _infer_terminal_registry_status


def test_infer_terminal_registry_status_maps_failed_and_error() -> None:
    assert _infer_terminal_registry_status({"status": "failed"}) == "failed"
    assert _infer_terminal_registry_status({"status": "error"}) == "failed"


def test_infer_terminal_registry_status_maps_cancelled_and_interrupted() -> None:
    assert _infer_terminal_registry_status({"status": "cancelled"}) == "interrupted"
    assert _infer_terminal_registry_status({"status": "interrupted"}) == "interrupted"


def test_infer_terminal_registry_status_defaults_to_completed() -> None:
    assert _infer_terminal_registry_status({"status": "completed"}) == "completed"
    assert _infer_terminal_registry_status({}) == "completed"
