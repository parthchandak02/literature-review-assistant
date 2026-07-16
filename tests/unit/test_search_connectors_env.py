from __future__ import annotations

import os

import pytest

from src.config.env_context import env_override_context
from src.search.openalex import OpenAlexConnector


def test_openalex_connector_reads_task_local_override() -> None:
    saved = os.environ.pop("OPENALEX_API_KEY", None)
    try:
        with env_override_context({"OPENALEX_API_KEY": "ctx-openalex-override"}):
            connector = OpenAlexConnector("wf-test")
            assert connector._api_key == "ctx-openalex-override"
    finally:
        if saved is not None:
            os.environ["OPENALEX_API_KEY"] = saved


def test_openalex_connector_requires_key_when_no_override() -> None:
    saved = os.environ.pop("OPENALEX_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="OPENALEX_API_KEY"):
            OpenAlexConnector("wf-test")
    finally:
        if saved is not None:
            os.environ["OPENALEX_API_KEY"] = saved
