"""
Recorded LLM responses for regression testing.
These were actual responses that caused crashes - now used as fixtures.

This file contains real problematic LLM responses encountered in production,
recorded for regression testing at zero API cost.
"""

# The actual response that crashed the system (Paper 4)
# Date: 2026-02-07
# Context: Full-text screening of "Conversational AI as an Intelligent Tutor"
# Issue: LLM returned plain text instead of JSON, causing response.parsed to return None
PLAIN_TEXT_RESPONSE_PAPER4 = """DECISION: EXCLUDE
CONFIDENCE: 0.9
REASONING: The paper discusses conversational AI as intelligent tutors, but the domain is general education and not specific to health sciences as required by the inclusion criteria.
EXCLUSION_REASON: Non-health science domains"""

# Malformed JSON response (missing closing brace)
MALFORMED_JSON_RESPONSE = """{
  "decision": "include",
  "confidence": 0.85,
  "reasoning": "Meets criteria"
  # Missing closing brace"""

# Response with extra text before JSON
TEXT_BEFORE_JSON = """Here's my analysis of the paper:

{
  "decision": "include",
  "confidence": 0.9,
  "reasoning": "Paper meets inclusion criteria for health science education"
}

Hope this helps with your systematic review!"""

# Response with extra text after JSON
TEXT_AFTER_JSON = """{
  "decision": "exclude",
  "confidence": 0.85,
  "reasoning": "Not relevant to health sciences",
  "exclusion_reason": "Wrong domain"
}
Please note that this is just my initial assessment and full-text review may reveal more details."""

# Valid JSON but wrong schema (missing required fields)
WRONG_SCHEMA_RESPONSE = """{
  "verdict": "include",
  "score": 0.85
}"""

# Valid JSON but wrong field types
WRONG_TYPE_RESPONSE = """{
  "decision": "include",
  "confidence": "high",
  "reasoning": "Good paper"
}"""

# Response that returns None when parsed
NULL_PARSED_RESPONSE = {
    "content": "I think this paper should be included in your review",
    "parsed": None
}

# Incomplete JSON
INCOMPLETE_JSON = """{
  "decision": "include",
  "confidence": 0.9,
  "reasoning": "This paper meets"""

# JSON with unexpected extra fields
EXTRA_FIELDS_JSON = """{
  "decision": "include",
  "confidence": 0.9,
  "reasoning": "Meets all criteria",
  "exclusion_reason": null,
  "extra_field1": "unexpected",
  "extra_field2": 123,
  "metadata": {"source": "test"}
}"""

# Multiple JSON objects in response
MULTIPLE_JSON_OBJECTS = """{
  "decision": "include",
  "confidence": 0.8,
  "reasoning": "First attempt"
}
{
  "decision": "exclude",
  "confidence": 0.9,
  "reasoning": "Actually, on second thought..."
}"""

# Empty response
EMPTY_RESPONSE = ""

# Response with only whitespace
WHITESPACE_ONLY_RESPONSE = """


   

"""

# Response with markdown code block
MARKDOWN_WRAPPED_JSON = """```json
{
  "decision": "include",
  "confidence": 0.9,
  "reasoning": "Paper meets criteria"
}
```"""

# Response with HTML tags
HTML_WRAPPED_JSON = """<div>
{
  "decision": "include",
  "confidence": 0.9,
  "reasoning": "Meets criteria"
}
</div>"""

# Int enum instead of string (Gemini-specific bug)
INT_ENUM_RESPONSE = """{
  "decision": 1,
  "confidence": 0.9,
  "reasoning": "Using int enum"
}"""

# Valid structured response examples (for positive testing)
VALID_INCLUDE_RESPONSE = """{
  "decision": "include",
  "confidence": 0.95,
  "reasoning": "Paper discusses AI tutors for medical education, meeting all inclusion criteria including health science domain and educational focus.",
  "exclusion_reason": null
}"""

VALID_EXCLUDE_RESPONSE = """{
  "decision": "exclude",
  "confidence": 0.9,
  "reasoning": "Paper focuses on general software engineering education, not health sciences.",
  "exclusion_reason": "Non-health science domains"
}"""

VALID_UNCERTAIN_RESPONSE = """{
  "decision": "uncertain",
  "confidence": 0.5,
  "reasoning": "Abstract mentions both health and non-health applications, needs full-text review to determine relevance."
}"""

# Response causing ValidationError (confidence out of range)
CONFIDENCE_OUT_OF_RANGE = """{
  "decision": "include",
  "confidence": 1.5,
  "reasoning": "Very confident"
}"""

# Response with null reasoning (should fail validation)
NULL_REASONING = """{
  "decision": "include",
  "confidence": 0.9,
  "reasoning": null
}"""
