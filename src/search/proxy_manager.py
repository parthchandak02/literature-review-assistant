"""
Proxy Manager

Manages proxy configuration and rotation for database connectors.
Inspired by scholarly's ProxyGenerator but adapted for our use case.
"""

import logging
import os
from enum import Enum
from typing import Any, Callable, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class ProxyType(Enum):
    """Proxy type enumeration."""

    NONE = "none"
    HTTP = "http"
    SOCKS5 = "socks5"
    SCRAPERAPI = "scraperapi"
    FREE = "free"


class ProxyManager:
    """
    Manages proxy configuration and rotation for database searches.

    Supports:
    - HTTP/HTTPS proxies
    - SOCKS5 proxies
    - ScraperAPI integration
    - Free proxy rotation (with warnings)
    """

    def __init__(
        self,
        proxy_type: str = "none",
        http_proxy: Optional[str] = None,
        https_proxy: Optional[str] = None,
        scraperapi_key: Optional[str] = None,
        rotation_on_failure: bool = True,
        timeout: float = 5.0,
    ):
        """
        Initialize proxy manager.

        Args:
            proxy_type: Type of proxy ("none", "http", "socks5", "scraperapi", "free")
            http_proxy: HTTP proxy URL (e.g., "http://proxy.example.com:8080")
            https_proxy: HTTPS proxy URL (defaults to http_proxy if not specified)
            scraperapi_key: ScraperAPI API key (required for scraperapi type)
            rotation_on_failure: Whether to rotate proxies on failure
            timeout: Timeout for proxy health checks
        """
        self.proxy_type = ProxyType(proxy_type.lower())
        self.http_proxy = http_proxy or os.getenv("HTTP_PROXY")
        self.https_proxy = https_proxy or os.getenv("HTTPS_PROXY") or self.http_proxy
        self.scraperapi_key = scraperapi_key or os.getenv("SCRAPERAPI_KEY")
        self.rotation_on_failure = rotation_on_failure
        self.timeout = timeout

        self._proxy_works = False
        self._proxies: Dict[str, str] = {}
        self._proxy_gen: Optional[Callable] = None
        self._current_proxy: Optional[str] = None
        self._failed_proxies: set = set()

        # Initialize proxy based on type
        if self.proxy_type != ProxyType.NONE:
            self._setup_proxy()

    def _setup_proxy(self):
        """Setup proxy based on configured type."""
        if self.proxy_type == ProxyType.HTTP:
            self._setup_http_proxy()
        elif self.proxy_type == ProxyType.SOCKS5:
            self._setup_socks5_proxy()
        elif self.proxy_type == ProxyType.SCRAPERAPI:
            self._setup_scraperapi()
        elif self.proxy_type == ProxyType.FREE:
            logger.warning("Free proxy support is experimental and may be unreliable")
            self._setup_free_proxy()
        else:
            logger.warning(f"Unknown proxy type: {self.proxy_type}")

    def _setup_http_proxy(self):
        """Setup HTTP/HTTPS proxy."""
        if not self.http_proxy:
            logger.warning("HTTP proxy type selected but no proxy URL provided")
            return

        # Ensure proxy URL has protocol
        if not self.http_proxy.startswith(("http://", "https://")):
            self.http_proxy = f"http://{self.http_proxy}"

        if not self.https_proxy.startswith(("http://", "https://")):
            self.https_proxy = (
                f"https://{self.https_proxy}" if self.https_proxy else self.http_proxy
            )

        self._proxies = {
            "http": self.http_proxy,
            "https": self.https_proxy,
        }

        self._proxy_works = self._check_proxy(self._proxies)
        if self._proxy_works:
            logger.info(f"HTTP proxy configured: {self.http_proxy}")
        else:
            logger.warning("HTTP proxy configured but health check failed")

    def _setup_socks5_proxy(self):
        """Setup SOCKS5 proxy."""
        import importlib.util

        if importlib.util.find_spec("socks") is None:
            logger.error(
                "SOCKS5 proxy requires 'requests[socks]' or 'PySocks'. Install with: pip install requests[socks]"
            )
            return

        if not self.http_proxy:
            logger.warning("SOCKS5 proxy type selected but no proxy URL provided")
            return

        # Ensure proxy URL has protocol
        if not self.http_proxy.startswith("socks5://"):
            self.http_proxy = f"socks5://{self.http_proxy}"

        self._proxies = {
            "http": self.http_proxy,
            "https": self.http_proxy,
        }

        self._proxy_works = self._check_proxy(self._proxies)
        if self._proxy_works:
            logger.info(f"SOCKS5 proxy configured: {self.http_proxy}")
        else:
            logger.warning("SOCKS5 proxy configured but health check failed")

    def _setup_scraperapi(self):
        """Setup ScraperAPI proxy."""
        if not self.scraperapi_key:
            logger.error("ScraperAPI type selected but no API key provided")
            return

        # Check account status
        try:
            response = requests.get(
                "http://api.scraperapi.com/account",
                params={"api_key": self.scraperapi_key},
                timeout=self.timeout,
            )
            account_info = response.json()

            if "error" in account_info:
                logger.error(f"ScraperAPI error: {account_info['error']}")
                return

            request_count = account_info.get("requestCount", 0)
            request_limit = account_info.get("requestLimit", 0)
            logger.info(f"ScraperAPI account: {request_count}/{request_limit} requests used")

            if request_count >= request_limit:
                logger.warning("ScraperAPI account limit reached")
                return

        except Exception as e:
            logger.warning(f"Could not check ScraperAPI account status: {e}")

        # Setup ScraperAPI proxy
        prefix = "http://scraperapi.retry_404=true"
        proxy_url = f"{prefix}:{self.scraperapi_key}@proxy-server.scraperapi.com:8001"

        self._proxies = {
            "http": proxy_url,
            "https": proxy_url,
        }

        # ScraperAPI recommends 60s timeout
        self.timeout = 60.0

        self._proxy_works = self._check_proxy(self._proxies)
        if self._proxy_works:
            logger.info("ScraperAPI proxy configured successfully")
        else:
            logger.warning("ScraperAPI proxy configured but health check failed")

    def _setup_free_proxy(self):
        """Setup free proxy rotation (experimental)."""
        logger.warning("Free proxy support is experimental and unreliable")
        # Free proxy support would require additional dependencies
        # For now, just log a warning
        self._proxy_works = False

    def _check_proxy(self, proxies: Dict[str, str]) -> bool:
        """
        Check if proxy is working.

        Args:
            proxies: Dictionary with proxy URLs

        Returns:
            True if proxy works, False otherwise
        """
        try:
            with requests.Session() as session:
                session.proxies = proxies
                response = session.get(
                    "http://httpbin.org/ip",
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    ip_info = response.json()
                    logger.debug(f"Proxy works! IP address: {ip_info.get('origin', 'unknown')}")
                    return True
                elif response.status_code == 401:
                    logger.warning("Incorrect credentials for proxy")
                    return False
        except requests.Timeout:
            logger.debug(f"Proxy health check timed out after {self.timeout}s")
            return False
        except Exception as e:
            logger.debug(f"Proxy health check failed: {e}")
            return False

        return False

    def get_proxies(self) -> Optional[Dict[str, str]]:
        """
        Get proxy configuration for requests.

        Returns:
            Dictionary with proxy URLs or None if no proxy configured
        """
        if self.proxy_type == ProxyType.NONE or not self._proxy_works:
            return None

        return self._proxies.copy()

    def has_proxy(self) -> bool:
        """
        Check if proxy is configured and working.

        Returns:
            True if proxy is available, False otherwise
        """
        return self._proxy_works and self.proxy_type != ProxyType.NONE

    def rotate_proxy(self):
        """Rotate to next proxy (if rotation is enabled)."""
        if not self.rotation_on_failure:
            return

        if self.proxy_type == ProxyType.FREE:
            # Free proxy rotation would go here
            logger.debug("Free proxy rotation not yet implemented")
        else:
            logger.debug("Proxy rotation not available for this proxy type")

    def mark_proxy_failed(self, proxy_url: Optional[str] = None):
        """
        Mark a proxy as failed and rotate if enabled.

        Args:
            proxy_url: URL of failed proxy (optional)
        """
        if proxy_url:
            self._failed_proxies.add(proxy_url)

        if self.rotation_on_failure:
            self.rotate_proxy()

    def get_timeout(self) -> float:
        """
        Get recommended timeout for requests.

        Returns:
            Timeout in seconds
        """
        return self.timeout


def create_proxy_manager_from_config(config: Dict[str, Any]) -> ProxyManager:
    """
    Create ProxyManager from configuration dictionary.

    Args:
        config: Configuration dictionary with proxy settings

    Returns:
        ProxyManager instance
    """
    proxy_config = config.get("proxy", {})

    if not proxy_config.get("enabled", False):
        return ProxyManager(proxy_type="none")

    return ProxyManager(
        proxy_type=proxy_config.get("type", "none"),
        http_proxy=proxy_config.get("http_proxy"),
        https_proxy=proxy_config.get("https_proxy"),
        scraperapi_key=proxy_config.get("scraperapi_key"),
        rotation_on_failure=proxy_config.get("rotation_on_failure", True),
        timeout=proxy_config.get("timeout", 5.0),
    )
