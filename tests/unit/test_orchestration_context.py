from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from src.orchestration.context import (
    RunContext,
    WebRunContext,
    _decision_style,
    _reason_label_from_code,
    _screening_reason_code,
    create_progress,
)

# ---------------------------------------------------------------------------
# _reason_label_from_code
# ---------------------------------------------------------------------------


class TestReasonLabelFromCode:
    def test_known_codes_return_labels(self) -> None:
        assert _reason_label_from_code("timeout") == "Full text retrieval timed out"
        assert _reason_label_from_code("oa_recovered") == "Full text successfully retrieved"
        assert _reason_label_from_code("publisher_403") == "Full text blocked by publisher"

    def test_unknown_code_returns_humanised_fallback(self) -> None:
        assert _reason_label_from_code("some_new_code") == "some new code"

    def test_empty_string_returns_itself(self) -> None:
        assert _reason_label_from_code("") == ""


# ---------------------------------------------------------------------------
# _screening_reason_code
# ---------------------------------------------------------------------------


class TestScreeningReasonCode:
    def test_extracts_first_pipe_token(self) -> None:
        assert _screening_reason_code("low_relevance_score|details here") == "low_relevance_score"

    def test_no_pipe_returns_lowered_string(self) -> None:
        assert _screening_reason_code("TIMEOUT") == "timeout"

    def test_none_returns_none(self) -> None:
        assert _screening_reason_code(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _screening_reason_code("") is None

    def test_pipe_only_returns_none(self) -> None:
        assert _screening_reason_code("|rest") is None


# ---------------------------------------------------------------------------
# _decision_style
# ---------------------------------------------------------------------------


class TestDecisionStyle:
    def test_include_with_matching_other(self) -> None:
        other = MagicMock(value="include")
        assert _decision_style("include", other) == "[bold green]"

    def test_include_with_mismatched_other(self) -> None:
        other = MagicMock(value="exclude")
        assert _decision_style("include", other) == "[green]"

    def test_include_with_no_other(self) -> None:
        assert _decision_style("include", None) == "[green]"

    def test_exclude(self) -> None:
        assert _decision_style("exclude", None) == "[dim]"

    def test_uncertain(self) -> None:
        assert _decision_style("uncertain", None) == "[yellow]"

    def test_unknown_decision(self) -> None:
        assert _decision_style("something_else", None) == "[bold]"

    def test_none_decision(self) -> None:
        assert _decision_style(None, None) == "[bold]"

    def test_include_other_is_plain_string(self) -> None:
        assert _decision_style("include", "include") == "[bold green]"


# ---------------------------------------------------------------------------
# RunContext -- initialisation and defaults
# ---------------------------------------------------------------------------


class TestRunContextInit:
    def test_defaults(self) -> None:
        console = Console(file=MagicMock())
        ctx = RunContext(console=console)
        assert ctx.verbose is False
        assert ctx.debug is False
        assert ctx.offline is False
        assert ctx.progress is None
        assert ctx.should_proceed_with_partial() is False

    def test_custom_flags(self) -> None:
        ctx = RunContext(console=Console(file=MagicMock()), verbose=True, debug=True, offline=True)
        assert ctx.verbose is True
        assert ctx.debug is True
        assert ctx.offline is True


# ---------------------------------------------------------------------------
# RunContext.should_proceed_with_partial
# ---------------------------------------------------------------------------


class TestShouldProceedWithPartial:
    def test_default_is_false(self) -> None:
        ctx = RunContext(console=Console(file=MagicMock()))
        assert ctx.should_proceed_with_partial() is False

    def test_true_when_flag_set(self) -> None:
        ctx = RunContext(console=Console(file=MagicMock()), proceed_with_partial_requested=[True])
        assert ctx.should_proceed_with_partial() is True

    def test_empty_list_returns_false(self) -> None:
        ctx = RunContext(console=Console(file=MagicMock()), proceed_with_partial_requested=[])
        assert ctx.should_proceed_with_partial() is False


# ---------------------------------------------------------------------------
# RunContext._strip_markdown_json
# ---------------------------------------------------------------------------


class TestStripMarkdownJson:
    @pytest.fixture()
    def ctx(self) -> RunContext:
        return RunContext(console=Console(file=MagicMock()))

    def test_plain_json_unchanged(self, ctx: RunContext) -> None:
        raw = '{"decision": "include"}'
        assert ctx._strip_markdown_json(raw) == raw

    def test_strips_code_fence(self, ctx: RunContext) -> None:
        raw = '```json\n{"decision": "include"}\n```'
        assert json.loads(ctx._strip_markdown_json(raw)) == {"decision": "include"}

    def test_strips_bare_fence(self, ctx: RunContext) -> None:
        raw = '```\n{"key": "val"}\n```'
        assert json.loads(ctx._strip_markdown_json(raw)) == {"key": "val"}

    def test_extracts_json_from_surrounding_text(self, ctx: RunContext) -> None:
        raw = 'Here is the result: {"a": 1} -- done'
        assert json.loads(ctx._strip_markdown_json(raw)) == {"a": 1}

    def test_empty_string(self, ctx: RunContext) -> None:
        assert ctx._strip_markdown_json("") == ""

    def test_no_braces(self, ctx: RunContext) -> None:
        assert ctx._strip_markdown_json("no json here") == "no json here"


# ---------------------------------------------------------------------------
# RunContext.emit_phase_start / emit_phase_done
# ---------------------------------------------------------------------------


class TestEmitPhase:
    @pytest.fixture()
    def verbose_ctx(self) -> RunContext:
        console = Console(file=MagicMock())
        progress = MagicMock()
        progress.add_task.return_value = 42
        return RunContext(console=console, verbose=True, progress=progress)

    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_start_adds_task(self, mock_log: MagicMock, verbose_ctx: RunContext) -> None:
        verbose_ctx.emit_phase_start("phase_1", description="desc", total=10)
        verbose_ctx.progress.add_task.assert_called_once()  # type: ignore[union-attr]
        assert "phase_1" in verbose_ctx._phase_task_ids

    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_start_deduplicates(self, mock_log: MagicMock, verbose_ctx: RunContext) -> None:
        verbose_ctx.emit_phase_start("phase_1", total=5)
        verbose_ctx.emit_phase_start("phase_1", total=5)
        assert verbose_ctx.progress.add_task.call_count == 1  # type: ignore[union-attr]

    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_done_updates_progress(self, mock_log: MagicMock, verbose_ctx: RunContext) -> None:
        verbose_ctx.emit_phase_start("phase_2", total=10)
        verbose_ctx.emit_phase_done("phase_2", total=10, completed=10)
        verbose_ctx.progress.update.assert_called()  # type: ignore[union-attr]

    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_done_without_totals(self, mock_log: MagicMock, verbose_ctx: RunContext) -> None:
        verbose_ctx.emit_phase_start("phase_x")
        verbose_ctx.emit_phase_done("phase_x")
        verbose_ctx.progress.update.assert_called_once_with(  # type: ignore[union-attr]
            verbose_ctx._phase_task_ids["phase_x"],
            completed=1,
            total=1,
        )

    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_done_unknown_phase_no_error(self, mock_log: MagicMock) -> None:
        ctx = RunContext(console=Console(file=MagicMock()), progress=MagicMock())
        ctx.emit_phase_done("nonexistent")


# ---------------------------------------------------------------------------
# RunContext.log_status
# ---------------------------------------------------------------------------


class TestLogStatus:
    def test_prints_message(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console)
        ctx.log_status("hello")
        console.print.assert_called_once()
        assert "hello" in console.print.call_args[0][0]


# ---------------------------------------------------------------------------
# RunContext.log_prompt
# ---------------------------------------------------------------------------


class TestLogPrompt:
    def test_debug_prints_panel(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, debug=True)
        ctx.log_prompt("agent_a", "some prompt", "paper123")
        console.print.assert_called_once()

    def test_non_debug_silent(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, debug=False)
        ctx.log_prompt("agent_a", "some prompt", "paper123")
        console.print.assert_not_called()

    def test_long_prompt_truncated(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, debug=True)
        ctx.log_prompt("agent_a", "x" * 3000, None)
        console.print.assert_called_once()


# ---------------------------------------------------------------------------
# RunContext.log_api_call (verbose paths)
# ---------------------------------------------------------------------------


class TestLogApiCall:
    @patch("src.orchestration.context.structured_log")
    def test_success_verbose_prints(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_api_call(
            "src",
            "success",
            details="det",
            model="gpt-4",
            paper_id="p1",
            latency_ms=100,
            tokens_in=50,
            tokens_out=60,
            cost_usd=0.01,
        )
        assert console.print.called

    @patch("src.orchestration.context.structured_log")
    def test_failure_verbose_prints_red(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_api_call("src", "error", details="bad thing")
        call_arg = console.print.call_args[0][0]
        assert "failed" in call_arg

    @patch("src.orchestration.context.structured_log")
    def test_non_verbose_silent(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_api_call("src", "success")
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# RunContext.log_connector_result
# ---------------------------------------------------------------------------


class TestLogConnectorResult:
    @patch("src.orchestration.context.structured_log")
    def test_success_verbose(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_connector_result("pubmed", "success", 42, query="cancer")
        assert console.print.call_count >= 1

    @patch("src.orchestration.context.structured_log")
    def test_failure_verbose(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_connector_result("pubmed", "error", 0, error="429 rate limited")
        assert console.print.call_count >= 1

    @patch("src.orchestration.context.structured_log")
    def test_non_verbose_silent(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_connector_result("pubmed", "success", 10)
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# RunContext.log_pdf_result
# ---------------------------------------------------------------------------


class TestLogPdfResult:
    @patch("src.orchestration.context.structured_log")
    def test_success_verbose(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_pdf_result("p1", "Title", "unpaywall", True)
        assert console.print.called

    @patch("src.orchestration.context.structured_log")
    def test_failure_with_reason(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_pdf_result("p1", "Title", "unpaywall", False, reason_code="publisher_403")
        call_arg = console.print.call_args[0][0]
        assert "Full text blocked by publisher" in call_arg

    @patch("src.orchestration.context.structured_log")
    def test_non_verbose_silent(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_pdf_result("p1", "Title", "src", True)
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# RunContext.log_screening_decision
# ---------------------------------------------------------------------------


class TestLogScreeningDecision:
    @patch("src.orchestration.context.structured_log")
    def test_verbose_prints(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_screening_decision("p1", "title_abstract", "include", confidence=0.9)
        assert console.print.called

    @patch("src.orchestration.context.structured_log")
    def test_non_verbose_silent(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_screening_decision("p1", "title_abstract", "exclude")
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# RunContext.advance_screening
# ---------------------------------------------------------------------------


class TestAdvanceScreening:
    def test_updates_progress_bar(self) -> None:
        progress = MagicMock()
        ctx = RunContext(console=Console(file=MagicMock()), progress=progress)
        ctx._phase_task_ids["phase_3"] = 99
        ctx.advance_screening("phase_3", 5, 10)
        progress.update.assert_called_once_with(99, completed=5, total=10)

    def test_no_progress_no_error(self) -> None:
        ctx = RunContext(console=Console(file=MagicMock()))
        ctx.advance_screening("phase_3", 5, 10)

    def test_unknown_phase_no_error(self) -> None:
        ctx = RunContext(console=Console(file=MagicMock()), progress=MagicMock())
        ctx.advance_screening("unknown", 1, 1)


# ---------------------------------------------------------------------------
# RunContext.emit_debug_state
# ---------------------------------------------------------------------------


class TestEmitDebugState:
    def test_debug_prints_panel(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, debug=True)
        ctx.emit_debug_state("phase_1", {"papers": 5})
        console.print.assert_called_once()

    def test_non_debug_silent(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, debug=False)
        ctx.emit_debug_state("phase_1", {"papers": 5})
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# RunContext.log_rate_limit_wait / resolved
# ---------------------------------------------------------------------------


class TestLogRateLimit:
    @patch("src.orchestration.context.structured_log")
    def test_wait_verbose(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_rate_limit_wait("tier1", 5, 10, waited_seconds=1.5)
        console.print.assert_called_once()

    @patch("src.orchestration.context.structured_log")
    def test_wait_non_verbose(self, mock_log: MagicMock) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_rate_limit_wait("tier1", 5, 10)
        console.print.assert_not_called()

    def test_resolved_verbose(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_rate_limit_resolved("tier1", 2.0)
        console.print.assert_called_once()

    def test_resolved_non_verbose(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_rate_limit_resolved("tier1", 2.0)
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# RunContext.log_extraction_paper / log_synthesis
# ---------------------------------------------------------------------------


class TestLogExtractionAndSynthesis:
    def test_extraction_verbose(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_extraction_paper("p1", "RCT", "summary text", "low")
        console.print.assert_called_once()

    def test_extraction_non_verbose(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_extraction_paper("p1", "RCT", "summary", "low")
        console.print.assert_not_called()

    def test_synthesis_verbose(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=True)
        ctx.log_synthesis(True, [{"g": 1}], "good", 5, "positive")
        console.print.assert_called_once()

    def test_synthesis_non_verbose(self) -> None:
        console = MagicMock(spec=Console)
        ctx = RunContext(console=console, verbose=False)
        ctx.log_synthesis(False, [], "na", 0, "none")
        console.print.assert_not_called()


# ---------------------------------------------------------------------------
# create_progress
# ---------------------------------------------------------------------------


class TestCreateProgress:
    def test_returns_progress_instance(self) -> None:
        from rich.progress import Progress

        console = Console(file=MagicMock())
        p = create_progress(console)
        assert isinstance(p, Progress)


# ---------------------------------------------------------------------------
# WebRunContext -- initialisation
# ---------------------------------------------------------------------------


class TestWebRunContextInit:
    def test_defaults(self) -> None:
        ctx = WebRunContext()
        assert ctx.web_mode is True
        assert ctx.verbose is False
        assert ctx.debug is False
        assert ctx.offline is False
        assert ctx.progress is None
        assert ctx.should_proceed_with_partial() is False

    def test_partial_flag(self) -> None:
        ctx = WebRunContext(proceed_with_partial_requested=[True])
        assert ctx.should_proceed_with_partial() is True


# ---------------------------------------------------------------------------
# WebRunContext._emit
# ---------------------------------------------------------------------------


class TestWebRunContextEmit:
    def test_emit_calls_on_event(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx._emit({"type": "test"})
        on_event.assert_called_once()
        event = on_event.call_args[0][0]
        assert event["type"] == "test"
        assert "id" in event
        assert "ts" in event

    def test_emit_enqueues_to_queue(self) -> None:
        queue = MagicMock()
        ctx = WebRunContext(queue=queue)
        ctx._emit({"type": "test"})
        queue.put_nowait.assert_called_once()

    def test_emit_swallows_callback_errors(self) -> None:
        on_event = MagicMock(side_effect=RuntimeError("boom"))
        ctx = WebRunContext(on_event=on_event)
        ctx._emit({"type": "test"})

    def test_emit_preserves_existing_id(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx._emit({"type": "test", "id": "custom-id"})
        event = on_event.call_args[0][0]
        assert event["id"] == "custom-id"


# ---------------------------------------------------------------------------
# WebRunContext.set_db_path / notify_workflow_id
# ---------------------------------------------------------------------------


class TestWebRunContextCallbacks:
    def test_set_db_path_fires_on_db_ready(self) -> None:
        on_db_ready = MagicMock()
        on_event = MagicMock()
        ctx = WebRunContext(on_db_ready=on_db_ready, on_event=on_event)
        ctx.set_db_path("/tmp/runtime.db")
        on_db_ready.assert_called_once_with("/tmp/runtime.db")
        event = on_event.call_args[0][0]
        assert event["type"] == "db_ready"

    def test_set_db_path_swallows_callback_error(self) -> None:
        on_db_ready = MagicMock(side_effect=RuntimeError("boom"))
        ctx = WebRunContext(on_db_ready=on_db_ready)
        ctx.set_db_path("/tmp/runtime.db")

    def test_notify_workflow_id_fires_callback(self) -> None:
        on_wf_ready = MagicMock()
        ctx = WebRunContext(on_workflow_id_ready=on_wf_ready)
        ctx.notify_workflow_id("wf-001", "/runs/wf-001")
        on_wf_ready.assert_called_once_with("wf-001", "/runs/wf-001")

    def test_notify_workflow_id_swallows_error(self) -> None:
        on_wf_ready = MagicMock(side_effect=RuntimeError("boom"))
        ctx = WebRunContext(on_workflow_id_ready=on_wf_ready)
        ctx.notify_workflow_id("wf-001", "/runs/wf-001")

    def test_notify_workflow_id_noop_when_no_callback(self) -> None:
        ctx = WebRunContext()
        ctx.notify_workflow_id("wf-001", "/runs/wf-001")


# ---------------------------------------------------------------------------
# WebRunContext -- phase and logging methods emit events
# ---------------------------------------------------------------------------


class TestWebRunContextLogging:
    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_start(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.emit_phase_start("phase_1", description="desc", total=5)
        event = on_event.call_args[0][0]
        assert event["type"] == "phase_start"
        assert event["phase"] == "phase_1"

    @patch("src.orchestration.context.structured_log")
    def test_emit_phase_done(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.emit_phase_done("phase_1", summary={"n": 3}, total=3, completed=3)
        event = on_event.call_args[0][0]
        assert event["type"] == "phase_done"

    @patch("src.orchestration.context.structured_log")
    def test_log_api_call(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_api_call("src", "success", model="gpt-4", paper_id="p1")
        event = on_event.call_args[0][0]
        assert event["type"] == "api_call"
        assert event["status"] == "success"

    @patch("src.orchestration.context.structured_log")
    def test_log_connector_result(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_connector_result("openalex", "success", 100, query="test")
        event = on_event.call_args[0][0]
        assert event["type"] == "connector_result"

    @patch("src.orchestration.context.structured_log")
    def test_log_pdf_result(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_pdf_result("p1", "Title", "unpaywall", True)
        event = on_event.call_args[0][0]
        assert event["type"] == "pdf_result"
        assert event["success"] is True

    def test_log_extraction_paper(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_extraction_paper("p1", "RCT", "summary", "low")
        event = on_event.call_args[0][0]
        assert event["type"] == "extraction_paper"

    def test_log_synthesis(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_synthesis(True, [{"g": 1}], "ok", 5, "positive")
        event = on_event.call_args[0][0]
        assert event["type"] == "synthesis"

    @patch("src.orchestration.context.structured_log")
    def test_log_rate_limit_wait(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_rate_limit_wait("tier1", 3, 10, waited_seconds=1.2)
        event = on_event.call_args[0][0]
        assert event["type"] == "rate_limit_wait"

    def test_log_rate_limit_resolved(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_rate_limit_resolved("tier1", 2.3)
        event = on_event.call_args[0][0]
        assert event["type"] == "rate_limit_resolved"

    @patch("src.orchestration.context.structured_log")
    def test_log_screening_decision(self, mock_log: MagicMock) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_screening_decision("p1", "title_abstract", "include", confidence=0.8, title="Paper")
        event = on_event.call_args[0][0]
        assert event["type"] == "screening_decision"
        assert event["decision"] == "include"

    def test_log_status(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.log_status("busy")
        event = on_event.call_args[0][0]
        assert event["type"] == "status"
        assert event["message"] == "busy"

    def test_advance_screening(self) -> None:
        on_event = MagicMock()
        ctx = WebRunContext(on_event=on_event)
        ctx.advance_screening("phase_3", 7, 20)
        event = on_event.call_args[0][0]
        assert event["type"] == "progress"
        assert event["current"] == 7

    def test_log_prompt_is_noop(self) -> None:
        ctx = WebRunContext()
        ctx.log_prompt("agent", "prompt text", "paper_id")

    def test_emit_debug_state_is_noop(self) -> None:
        ctx = WebRunContext()
        ctx.emit_debug_state("phase_1", {"a": 1})
