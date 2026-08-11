from pydantic_ai.messages import BuiltinToolCallPart

from src.llm.factory import web_tool_progress_message


def test_web_tool_progress_message_search_query() -> None:
    part = BuiltinToolCallPart(
        tool_name="web_search",
        args={"query": "pickleball older adults residential care"},
    )
    assert web_tool_progress_message(part) == "Searching: pickleball older adults residential care"


def test_web_tool_progress_message_fetch_url() -> None:
    part = BuiltinToolCallPart(
        tool_name="web_fetch",
        args={"url": "https://www.ncbi.nlm.nih.gov/example"},
    )
    assert web_tool_progress_message(part) == "Reading www.ncbi.nlm.nih.gov"


def test_web_tool_progress_message_unknown_tool() -> None:
    part = BuiltinToolCallPart(tool_name="other_tool", args={})
    assert web_tool_progress_message(part) is None
