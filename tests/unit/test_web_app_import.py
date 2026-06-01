from __future__ import annotations


def test_web_app_import_smoke() -> None:
    """Guard against module wiring regressions that crash API startup."""
    from src.web.app import app

    assert app is not None
