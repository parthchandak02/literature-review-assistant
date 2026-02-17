from __future__ import annotations

import pytest

from src.main import build_parser


def test_phase2_live_command_removed() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["phase2-live"])
    parsed = parser.parse_args(["run"])
    assert parsed.command == "run"
