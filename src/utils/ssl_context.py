"""Shared SSL context using certifi CA bundle for aiohttp connectors."""

from __future__ import annotations

import os
import ssl

import aiohttp
import certifi


def default_ssl_context() -> ssl.SSLContext:
    """Return SSL context using certifi CA bundle (fixes cert verify on macOS/python.org)."""
    return ssl.create_default_context(cafile=certifi.where())


def _ssl_context() -> ssl.SSLContext | bool:
    """Return SSL context; use False to skip verification when RESEARCH_AGENT_SSL_SKIP_VERIFY=1."""
    if os.getenv("RESEARCH_AGENT_SSL_SKIP_VERIFY", "").lower() in ("1", "true", "yes"):
        return False
    return default_ssl_context()


def tcp_connector_with_certifi() -> aiohttp.TCPConnector:
    """Return aiohttp TCPConnector using certifi CA bundle (or skip verify if env set)."""
    return aiohttp.TCPConnector(ssl=_ssl_context())
