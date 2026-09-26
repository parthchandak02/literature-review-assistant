"""Root test configuration.

Loads .env for non-secret settings, then blanks every provider / connector
credential and blocks outbound sockets to non-loopback hosts so no test can
reach a real third-party service. Tests that need a provider must use fakes.

Set ``LITREVIEW_ALLOW_NETWORK_TESTS=1`` to opt out (live-provider tests only).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import tempfile
from collections.abc import Iterator

import pytest
from dotenv import dotenv_values, load_dotenv

_ALLOW_NETWORK = os.getenv("LITREVIEW_ALLOW_NETWORK_TESTS", "").strip() == "1"

_SECRET_NAME_RE = re.compile(r"(API_KEY|_KEY|_TOKEN|_SECRET|_PASSWORD)$")

_KNOWN_SECRET_VARS: frozenset[str] = frozenset(
    {
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_API_KEY",
        "FIREWORKS_API_KEY",
        "TYPESAFE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "DEEPSEEK_API_KEY",
        "CO_API_KEY",
        "COHERE_API_KEY",
        "PERPLEXITY_SEARCH_API_KEY",
        "PERPLEXITY_API_KEY",
        "EXA_API_KEY",
        "TAVILY_API_KEY",
        "PUBMED_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
        "CORE_API_KEY",
        "SCOPUS_API_KEY",
        "WOS_API_KEY",
        "IEEE_API_KEY",
        "OPENALEX_API_KEY",
        "EMBASE_API_KEY",
        "EMBASE_EMAIL",
        "EMBASE_PASSWORD",
        "HF_TOKEN",
        "HUGGINGFACE_HUB_TOKEN",
    }
)


def _secret_env_names() -> set[str]:
    names = set(_KNOWN_SECRET_VARS)
    names.update(k for k in dotenv_values() if _SECRET_NAME_RE.search(k))
    names.update(k for k in os.environ if _SECRET_NAME_RE.search(k))
    return names


load_dotenv(override=True)

if not _ALLOW_NETWORK:
    # Empty (not deleted) so later load_dotenv() calls in src/config/loader.py
    # cannot re-populate them from .env.
    for _name in _secret_env_names():
        os.environ[_name] = ""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Web path guards only accept run roots under runs/ or LITREVIEW_RUNS_ROOTS; tests
# use pytest tmp_path (system temp dir) and /tmp for isolated run roots.
os.environ.setdefault("LITREVIEW_RUNS_ROOTS", os.pathsep.join([tempfile.gettempdir(), "/tmp"]))


_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "testserver", ""})


def _is_local_host(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    host_str = str(host).strip("[]").lower()
    if host_str in _LOOPBACK_NAMES:
        return True
    try:
        addr = ipaddress.ip_address(host_str.split("%", 1)[0])
    except ValueError:
        return False
    return addr.is_loopback or addr.is_unspecified


class ExternalNetworkBlockedError(RuntimeError):
    """Raised when a test attempts a real outbound network connection."""


def _blocked(target: object) -> ExternalNetworkBlockedError:
    return ExternalNetworkBlockedError(
        f"Test attempted external network access to {target!r}; use a fake/mock "
        "(set LITREVIEW_ALLOW_NETWORK_TESTS=1 only for deliberate live tests)."
    )


@pytest.fixture(scope="session", autouse=True)
def block_external_network() -> Iterator[None]:
    """Fail fast on any socket connect / DNS lookup to a non-loopback host."""
    if _ALLOW_NETWORK:
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection

    def _check_address(sock: socket.socket, address: object) -> None:
        if sock.family == getattr(socket, "AF_UNIX", object()):
            return
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_local_host(host):
            raise _blocked(address)

    def guarded_connect(self: socket.socket, address: object) -> None:
        _check_address(self, address)
        return real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: object) -> int:
        _check_address(self, address)
        return real_connect_ex(self, address)

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if not _is_local_host(host):
            raise _blocked(host)
        return real_getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]

    def guarded_create_connection(address: tuple, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if not _is_local_host(address[0]):
            raise _blocked(address)
        return real_create_connection(address, *args, **kwargs)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", guarded_connect)
        mp.setattr(socket.socket, "connect_ex", guarded_connect_ex)
        mp.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
        mp.setattr(socket, "create_connection", guarded_create_connection)
        yield


@pytest.fixture
def workflow_replay_id() -> str | None:
    """Optional workflow id for real-data replay tests (set WORKFLOW_REPLAY_ID)."""
    value = os.getenv("WORKFLOW_REPLAY_ID", "").strip()
    return value or None


@pytest.fixture
def workflow_replay_db_path() -> str | None:
    """Optional runtime.db path for real-data replay tests (set WORKFLOW_REPLAY_DB_PATH)."""
    value = os.getenv("WORKFLOW_REPLAY_DB_PATH", "").strip()
    return value or None
