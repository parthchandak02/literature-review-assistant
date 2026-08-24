"""Institutional full-text access for paywalled publishers (Elsevier/ScienceDirect).

Uses browser-exported session cookies or library institutional tokens. Email/password
login is not supported here; operators authenticate in a browser and export cookies.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import aiohttp

from src.config.env_context import get_env
from src.search.pdf_parse import is_pdf_bytes
from src.search.scopus_session import load_scopus_session_cookie
from src.utils.ssl_context import tcp_connector_with_certifi

logger = logging.getLogger(__name__)

_SD_ARTICLE_API = "https://api.elsevier.com/content/article/doi"
_SD_PDFFT = "https://www.sciencedirect.com/science/article/pii/{pii}/pdfft"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def resolve_sciencedirect_pii(
    session: aiohttp.ClientSession,
    doi: str,
    api_key: str,
) -> str | None:
    """Resolve ScienceDirect PII from DOI via Elsevier metadata API."""
    url = f"{_SD_ARTICLE_API}/{quote(doi, safe='')}"
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=45)) as resp:
        if resp.status != 200:
            return None
        payload = await resp.json(content_type=None)
    core = (payload.get("full-text-retrieval-response") or {}).get("coredata") or {}
    pii = (core.get("pii") or "").strip()
    if pii:
        return pii
    identifier = (core.get("dc:identifier") or "").strip()
    if identifier.upper().startswith("PII:"):
        return identifier.split(":", 1)[1].strip()
    return None


async def fetch_sciencedirect_pdf_via_session(
    doi: str,
    cookie_header: str | None = None,
    *,
    api_key: str | None = None,
) -> bytes | None:
    """Download Elsevier PDF using an institutional browser session cookie."""
    cookie = (cookie_header or load_scopus_session_cookie() or "").strip()
    key = (api_key or get_env("SCOPUS_API_KEY") or get_env("EMBASE_API_KEY") or "").strip()
    if not cookie or not doi or not key:
        return None

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(connector=tcp_connector_with_certifi()) as session:
        pii = await resolve_sciencedirect_pii(session, doi, key)
        if not pii:
            logger.debug("institutional: no PII for doi=%s", doi)
            return None
        pdf_url = _SD_PDFFT.format(pii=pii)
        headers = {
            "Cookie": cookie,
            "User-Agent": _USER_AGENT,
            "Accept": "application/pdf,*/*",
            "Referer": f"https://www.sciencedirect.com/science/article/pii/{pii}",
        }
        async with session.get(pdf_url, headers=headers, allow_redirects=True, timeout=timeout) as resp:
            if resp.status != 200:
                logger.debug("institutional: ScienceDirect pdfft HTTP %s for doi=%s", resp.status, doi)
                return None
            body = await resp.read()
    if not is_pdf_bytes(body):
        return None
    return body
