"""
PDF Retriever Module

Retrieves full-text PDFs from DOIs and extracts text content.
Supports multiple retrieval methods with fallback strategies.
"""

import os
import logging
from typing import Optional, Any
from pathlib import Path
import requests
import certifi

logger = logging.getLogger(__name__)


class PDFRetriever:
    """Retrieves PDFs and extracts text content."""

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Initialize PDF retriever.

        Args:
            cache_dir: Directory to cache retrieved PDFs (optional)
        """
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def retrieve_full_text(
        self, paper: Any, max_length: int = 50000
    ) -> Optional[str]:
        """
        Retrieve full text for a paper.

        Args:
            paper: Paper object with doi, url, title, etc.
            max_length: Maximum text length to return (for LLM context limits)

        Returns:
            Extracted text content or None if unavailable
        """
        # Try multiple retrieval methods
        text = None

        # Method 1: Try DOI-based retrieval
        if hasattr(paper, "doi") and paper.doi:
            text = self._retrieve_from_doi(paper.doi)
            if text:
                logger.debug(f"Retrieved full-text from DOI: {paper.doi}")
                return text[:max_length] if len(text) > max_length else text

        # Method 2: Try URL-based retrieval (if URL points to PDF)
        if hasattr(paper, "url") and paper.url:
            text = self._retrieve_from_url(paper.url)
            if text:
                logger.debug(f"Retrieved full-text from URL: {paper.url}")
                return text[:max_length] if len(text) > max_length else text

        # Method 3: Try arXiv PDF (if arXiv paper)
        if hasattr(paper, "database") and paper.database == "arXiv":
            if hasattr(paper, "url") and paper.url:
                text = self._retrieve_arxiv_pdf(paper.url)
                if text:
                    logger.debug(f"Retrieved full-text from arXiv: {paper.url}")
                    return text[:max_length] if len(text) > max_length else text

        logger.debug(f"Could not retrieve full-text for paper: {getattr(paper, 'title', 'Unknown')}")
        return None

    def _retrieve_from_doi(self, doi: str) -> Optional[str]:
        """
        Retrieve PDF from DOI using various services.

        Args:
            doi: DOI string

        Returns:
            Extracted text or None
        """
        # Try Sci-Hub (if available) - note: legal/ethical considerations apply
        # For production, use legitimate services like Crossref, Unpaywall, etc.

        # Try Unpaywall API (free, legal)
        try:
            unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email=research@example.com"
            response = requests.get(unpaywall_url, timeout=10, verify=certifi.where())
            if response.status_code == 200:
                data = response.json()
                pdf_url = data.get("best_oa_location", {}).get("url_for_pdf")
                if pdf_url:
                    return self._download_and_extract_pdf(pdf_url)
        except Exception as e:
            logger.debug(f"Unpaywall retrieval failed for {doi}: {e}")

        # Try direct DOI resolution
        try:
            doi_url = f"https://doi.org/{doi}"
            response = requests.get(doi_url, allow_redirects=True, timeout=10, verify=certifi.where())
            final_url = response.url
            if final_url.endswith(".pdf"):
                return self._download_and_extract_pdf(final_url)
        except Exception as e:
            logger.debug(f"DOI resolution failed for {doi}: {e}")

        return None

    def _retrieve_from_url(self, url: str) -> Optional[str]:
        """
        Retrieve PDF from URL if it points to a PDF.

        Args:
            url: URL string

        Returns:
            Extracted text or None
        """
        if not url:
            return None

        # Check if URL is a PDF
        if url.endswith(".pdf") or "pdf" in url.lower():
            return self._download_and_extract_pdf(url)

        # Try to find PDF link on the page (simple heuristic)
        try:
            response = requests.get(url, timeout=10, verify=certifi.where())
            if response.status_code == 200:
                content = response.text
                # Look for PDF links (simple pattern matching)
                import re
                pdf_links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', content, re.IGNORECASE)
                if pdf_links:
                    pdf_url = pdf_links[0]
                    # Make absolute URL if relative
                    if not pdf_url.startswith("http"):
                        from urllib.parse import urljoin
                        pdf_url = urljoin(url, pdf_url)
                    return self._download_and_extract_pdf(pdf_url)
        except Exception as e:
            logger.debug(f"URL retrieval failed for {url}: {e}")

        return None

    def _retrieve_arxiv_pdf(self, arxiv_url: str) -> Optional[str]:
        """
        Retrieve PDF from arXiv URL.

        Args:
            arxiv_url: arXiv URL or ID

        Returns:
            Extracted text or None
        """
        try:
            # Extract arXiv ID from URL
            arxiv_id = arxiv_url.split("/")[-1] if "/" in arxiv_url else arxiv_url
            # Remove .pdf extension if present
            arxiv_id = arxiv_id.replace(".pdf", "")
            
            # Construct PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            return self._download_and_extract_pdf(pdf_url)
        except Exception as e:
            logger.debug(f"arXiv PDF retrieval failed for {arxiv_url}: {e}")
            return None

    def _download_and_extract_pdf(self, pdf_url: str) -> Optional[str]:
        """
        Download PDF and extract text.

        Args:
            pdf_url: URL to PDF file

        Returns:
            Extracted text or None
        """
        try:
            # Check cache first
            if self.cache_dir:
                cache_key = self._get_cache_key(pdf_url)
                cache_path = self.cache_dir / f"{cache_key}.txt"
                if cache_path.exists():
                    logger.debug(f"Loading PDF text from cache: {cache_path}")
                    with open(cache_path, "r", encoding="utf-8") as f:
                        return f.read()

            # Download PDF
            response = requests.get(pdf_url, timeout=30, stream=True, verify=certifi.where())
            response.raise_for_status()

            # Check if it's actually a PDF
            content_type = response.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not pdf_url.endswith(".pdf"):
                logger.debug(f"URL does not appear to be a PDF: {pdf_url}")
                return None

            # Save to temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_path = tmp_file.name
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)

            # Extract text
            text = self._extract_text_from_pdf(tmp_path)

            # Cache extracted text
            if text and self.cache_dir:
                cache_key = self._get_cache_key(pdf_url)
                cache_path = self.cache_dir / f"{cache_key}.txt"
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.debug(f"Cached PDF text: {cache_path}")

            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            return text

        except Exception as e:
            logger.debug(f"PDF download/extraction failed for {pdf_url}: {e}")
            return None

    def _extract_text_from_pdf(self, pdf_path: str) -> Optional[str]:
        """
        Extract text from PDF file.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text or None
        """
        # Try multiple PDF extraction libraries
        text = None

        # Method 1: Try pypdf (lightweight)
        try:
            import pypdf
            with open(pdf_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                pages_text = []
                for page in reader.pages[:50]:  # Limit to first 50 pages
                    pages_text.append(page.extract_text())
                text = "\n\n".join(pages_text)
                if text and len(text.strip()) > 100:
                    logger.debug(f"Extracted {len(text)} chars using pypdf")
                    return text
        except ImportError:
            logger.debug("pypdf not available")
        except Exception as e:
            logger.debug(f"pypdf extraction failed: {e}")

        # Method 2: Try pdfplumber (better formatting)
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                pages_text = []
                for page in pdf.pages[:50]:  # Limit to first 50 pages
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(page_text)
                text = "\n\n".join(pages_text)
                if text and len(text.strip()) > 100:
                    logger.debug(f"Extracted {len(text)} chars using pdfplumber")
                    return text
        except ImportError:
            logger.debug("pdfplumber not available")
        except Exception as e:
            logger.debug(f"pdfplumber extraction failed: {e}")

        # Method 3: Try unstructured (if available)
        try:
            from unstructured.partition.pdf import partition_pdf
            elements = partition_pdf(pdf_path, strategy="hi_res", max_pages=50)
            text = "\n\n".join([str(el) for el in elements if hasattr(el, "text")])
            if text and len(text.strip()) > 100:
                logger.debug(f"Extracted {len(text)} chars using unstructured")
                return text
        except ImportError:
            logger.debug("unstructured not available")
        except Exception as e:
            logger.debug(f"unstructured extraction failed: {e}")

        return None

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()
