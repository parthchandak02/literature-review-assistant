"""Abstract LLM backend protocol for provider-agnostic LLM calls."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    """Structural protocol satisfied by any LLM client that can produce text or JSON.

    Callers pass json_schema to request structured JSON output.
    The returned string is either plain text or a JSON string matching the schema.
    Implementors must apply exponential-backoff retry on transient errors.
    """

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        json_schema: dict | None = None,
    ) -> str:
        """Return the LLM response as a string.

        If json_schema is supplied, the response MUST be a valid JSON string
        conforming to that schema. Callers use model_validate_json() on the result.
        """
        ...
