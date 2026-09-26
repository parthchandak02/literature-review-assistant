"""Root conftest blanks provider keys and blocks non-loopback sockets."""

from __future__ import annotations

import os
import socket

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("LITREVIEW_ALLOW_NETWORK_TESTS", "").strip() == "1",
    reason="network guard disabled by LITREVIEW_ALLOW_NETWORK_TESTS=1",
)


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "GOOGLE_API_KEY", "FIREWORKS_API_KEY", "OPENALEX_API_KEY"])
def test_provider_keys_blank(name: str) -> None:
    assert os.environ.get(name, "") == ""


def test_external_dns_and_connect_blocked() -> None:
    with pytest.raises(RuntimeError, match="external network access"):
        socket.getaddrinfo("generativelanguage.googleapis.com", 443)
    with pytest.raises(RuntimeError, match="external network access"):
        socket.create_connection(("8.8.8.8", 53), timeout=1)


@pytest.mark.asyncio
async def test_httpx_external_request_fails_fast() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(Exception, match="external network access"):
            await client.get("https://generativelanguage.googleapis.com/")


def test_loopback_allowed() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        client = socket.create_connection(server.getsockname(), timeout=1)
        client.close()
    finally:
        server.close()
