"""
Text Cleaner Utility

Removes conversational meta-commentary and unwanted preambles from LLM-generated
academic writing outputs using content-start detection.

Instead of pattern matching meta-commentary, this approach finds where actual
content starts (markdown headers, substantive paragraphs) and removes everything before it.
"""

import re
from typing import Tuple


def find_content_start(text: str) -> int:
    """
    Find the line index where actual content starts.
    
    Strategy:
    1. Look for markdown header that is NOT followed by conversational text
    2. If no valid header, find first substantive content (non-conversational, capitalized)
    3. Skip separator lines and conversational preambles
    
    Args:
        text: Text to analyze
        
    Returns:
        Index of first content line, or 0 if not found
    """
    lines = text.split('\n')
    
    conversational_patterns = [
        r'^(of course|certainly|here is|here\'s|below is)',
        r'^(as an expert|let me|i\'ll|allow me)',
        r'^(as requested|following your instructions)',
    ]
    
    def is_conversational_line(line: str) -> bool:
        """Check if a line starts with conversational phrase."""
        stripped = line.strip()
        return any(
            re.match(pattern, stripped, re.IGNORECASE)
            for pattern in conversational_patterns
        )
    
    def get_next_substantive_line(start_idx: int, max_lookahead: int = 10) -> Tuple[int, str]:
        """
        Find the next non-empty, non-separator line after start_idx.
        Returns (index, line) or (-1, '') if not found.
        """
        for i in range(start_idx + 1, min(start_idx + max_lookahead + 1, len(lines))):
            stripped = lines[i].strip()
            if stripped and not re.match(r'^[\*\-\_\=]{3,}$', stripped):
                return i, stripped
        return -1, ''
    
    # Priority 1: Find markdown header that is followed by actual content
    # Skip headers that are followed by conversational text
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Check for markdown header (# through ######)
        if re.match(r'^#{1,6}\s+', stripped):
            # Found a header - check what follows it
            next_idx, next_line = get_next_substantive_line(i, max_lookahead=5)
            
            if next_idx == -1:
                # No substantive line found after header, this might be content start
                return i
            
            # If next substantive line is conversational, skip this header
            if is_conversational_line(next_line):
                # This header is followed by meta-commentary, skip it
                # Continue looking for next header
                continue
            
            # Header is followed by non-conversational content - this is valid
            return i
    
    # Priority 2: Find first substantive content (non-conversational, capitalized)
    # This handles cases where there are no markdown headers
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip empty lines
        if not stripped:
            continue
        
        # Skip separator lines (***, ---, ===)
        if re.match(r'^[\*\-\_\=]{3,}$', stripped):
            continue
        
        # Skip if too short to be substantive
        if len(stripped) < 20:
            continue
        
        # Check if line starts with conversational phrase
        if is_conversational_line(stripped):
            continue
        
        # If starts with capital letter, this is likely content
        if stripped[0].isupper():
            return i
    
    return 0  # No clear content start found


def _conservative_clean(text: str) -> str:
    """
    Conservative cleaning: only remove obvious separators and known patterns.
    Used as fallback when content-start detection fails.
    
    Args:
        text: Text to clean
        
    Returns:
        Conservatively cleaned text
    """
    lines = text.split('\n')
    
    # Remove separator lines
    cleaned_lines = [
        line for line in lines
        if not re.match(r'^[\*\-\_\=]{3,}$', line.strip())
    ]
    
    # Remove lines starting with obvious conversational phrases
    conversational_starters = [
        'of course', 'here is', 'here\'s', 'below is', 'certainly',
        'as an expert', 'let me', 'i\'ll', 'allow me'
    ]
    
    final_lines = []
    skip_until_content = False
    
    for line in cleaned_lines:
        stripped = line.strip()
        
        if skip_until_content:
            # Check if this is actual content (has header or substantive)
            if re.match(r'^#{1,6}\s+', stripped) or (
                len(stripped) > 20 and stripped and stripped[0].isupper()
            ):
                skip_until_content = False
                final_lines.append(line)
        else:
            # Check if this starts a conversational preamble
            lower_stripped = stripped.lower()
            if any(lower_stripped.startswith(phrase) for phrase in conversational_starters):
                skip_until_content = True
                continue
            final_lines.append(line)
    
    cleaned = '\n'.join(final_lines)
    # Remove multiple consecutive empty lines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def clean_writing_output(text: str) -> str:
    """
    Remove meta-commentary by detecting where actual content starts.
    
    This approach is more robust than pattern matching because it:
    - Finds the first markdown header or substantive content
    - Removes everything before it
    - Works regardless of preamble variations
    
    Args:
        text: Raw LLM output text
        
    Returns:
        Cleaned text with meta-commentary removed
    """
    if not text or not isinstance(text, str):
        return text
    
    original_length = len(text)
    
    # Find where content actually starts
    content_start_idx = find_content_start(text)
    
    if content_start_idx > 0:
        lines = text.split('\n')
        cleaned = '\n'.join(lines[content_start_idx:]).strip()
        
        # Validation: don't remove too much (safety check)
        removal_ratio = 1 - (len(cleaned) / original_length) if original_length > 0 else 0
        if removal_ratio > 0.5:  # Removed more than 50%
            # Too aggressive, try more conservative approach
            return _conservative_clean(text)
        
        # Validation: ensure substantial content remains
        if len(cleaned) < 100:
            return _conservative_clean(text)
        
        # Additional cleanup: remove any remaining separator lines
        cleaned = re.sub(r'^[\*\-\_\=]{3,}\s*$', '', cleaned, flags=re.MULTILINE)
        # Remove multiple consecutive empty lines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        return cleaned.strip()
    
    # Fallback: conservative pattern-based removal if no clear content start found
    return _conservative_clean(text)
