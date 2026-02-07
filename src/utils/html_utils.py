"""
HTML Utilities

Utilities for HTML unescaping and text cleaning.
Inspired by pybliometrics' HTML unescaping functionality.
"""

import html
import re
from typing import Optional


def html_unescape(text: Optional[str], unescape: bool = True) -> Optional[str]:
    """
    Unescape HTML entities in text.

    Args:
        text: Text that may contain HTML entities
        unescape: Whether to perform unescaping (default: True)

    Returns:
        Unescaped text or original text if unescape is False
    """
    if not text:
        return text

    if not unescape:
        return text

    try:
        # Decode HTML entities (e.g., &amp; -> &, &lt; -> <)
        return html.unescape(text)
    except Exception:
        # If unescaping fails, return original text
        return text


def remove_html_tags(text: Optional[str]) -> Optional[str]:
    """
    Remove HTML tags from text.

    Args:
        text: Text that may contain HTML tags

    Returns:
        Text with HTML tags removed
    """
    if not text:
        return text

    try:
        # Remove HTML tags using regex
        # This is a simple approach - for more complex HTML, use BeautifulSoup
        clean_text = re.sub(r"<[^>]+>", "", text)
        # Clean up multiple spaces
        clean_text = re.sub(r"\s+", " ", clean_text)
        return clean_text.strip()
    except Exception:
        return text


def normalize_text(text: Optional[str]) -> Optional[str]:
    """
    Normalize text by unescaping HTML and removing tags.

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    if not text:
        return text

    # First unescape HTML entities
    text = html_unescape(text, unescape=True)

    # Then remove HTML tags
    text = remove_html_tags(text)

    return text


def clean_abstract(abstract: Optional[str]) -> Optional[str]:
    """
    Clean abstract text by removing HTML and normalizing.

    Args:
        abstract: Abstract text that may contain HTML

    Returns:
        Cleaned abstract text
    """
    if not abstract:
        return abstract

    # Normalize the text
    cleaned = normalize_text(abstract)

    # Remove common artifacts
    if cleaned:
        # Remove excessive whitespace
        cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
        cleaned = cleaned.strip()

    return cleaned
