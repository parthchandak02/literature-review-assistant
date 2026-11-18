"""Unit tests for reason-specific database path validation errors."""

from __future__ import annotations

import pathlib

import pytest
from fastapi import HTTPException

from src.web.shared import _validate_db_path


def test_validate_db_path_accepts_existing_db(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "runtime.db"
    db.write_text("")
    assert _validate_db_path(str(db)) == db.resolve()


def test_validate_db_path_rejects_path_outside_run_root(tmp_path: pathlib.Path) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir()
    outside = tmp_path / "elsewhere" / "runtime.db"
    outside.parent.mkdir()
    outside.write_text("")
    with pytest.raises(HTTPException) as exc:
        _validate_db_path(str(outside), str(run_root))
    assert exc.value.status_code == 400
    detail = str(exc.value.detail)
    assert "Invalid database path" in detail
    assert "outside run root" in detail
    assert str(outside.resolve()) in detail
    assert str(run_root.resolve()) in detail


def test_validate_db_path_rejects_non_db_suffix(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("x")
    with pytest.raises(HTTPException) as exc:
        _validate_db_path(str(path))
    assert exc.value.status_code == 400
    detail = str(exc.value.detail)
    assert "Invalid database path" in detail
    assert "must end with .db" in detail
    assert "'.txt'" in detail


def test_validate_db_path_rejects_missing_file(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "missing.db"
    with pytest.raises(HTTPException) as exc:
        _validate_db_path(str(missing))
    assert exc.value.status_code == 400
    detail = str(exc.value.detail)
    assert "Invalid database path" in detail
    assert "does not exist or is not a file" in detail
    assert str(missing.resolve()) in detail
