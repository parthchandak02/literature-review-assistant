"""Run context for CLI output and progress display."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from src.utils import structured_log
from rich.panel import Panel


def _decision_style(decision: str | None, other_reviewer_decision: Any) -> str:
    """Return Rich style for decision-based coloring."""
    if decision == "include":
        if other_reviewer_decision is not None:
            other_val = getattr(other_reviewer_decision, "value", str(other_reviewer_decision))
            if other_val == "include":
                return "[bold green]"  # both include
        return "[green]"  # include
    if decision == "exclude":
        return "[dim]"  # grey
    if decision == "uncertain":
        return "[yellow]"  # uncertain
    return "[bold]"  # fallback
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn
from rich.syntax import Syntax


@dataclass
class RunContext:
    """Context for workflow run: console, verbose/debug flags, progress, callbacks."""

    console: Console
    verbose: bool = False
    debug: bool = False
    offline: bool = False
    progress: Progress | None = None
    _phase_task_ids: dict[str, TaskID] = field(default_factory=dict, repr=False)
    proceed_with_partial_requested: list[bool] = field(default_factory=lambda: [False], repr=False)

    def should_proceed_with_partial(self) -> bool:
        """Return True if user requested to proceed with partial screening results (e.g. via Ctrl+C)."""
        return bool(self.proceed_with_partial_requested and self.proceed_with_partial_requested[0])

    def emit_phase_start(
        self, phase_name: str, description: str = "", total: int | None = None
    ) -> None:
        """Emit phase start status. Pass total when known so the progress bar renders properly."""
        structured_log.log_phase(phase=phase_name, action="start", description=description)
        if self.progress and phase_name not in self._phase_task_ids:
            task_id = self.progress.add_task(
                phase_name.replace("_", " ").title(),
                total=total if total is not None and total > 0 else None,
                start=True,
            )
            self._phase_task_ids[phase_name] = task_id
        if self.verbose and description:
            self.console.print(f"[bold]Phase: {phase_name}[/] {description}")

    def emit_phase_done(
        self,
        phase_name: str,
        summary: dict[str, Any] | None = None,
        total: int | None = None,
        completed: int | None = None,
    ) -> None:
        """Mark phase task complete and optionally print summary."""
        structured_log.log_phase(phase=phase_name, action="done", summary=summary, total=total, completed=completed)
        if self.progress and phase_name in self._phase_task_ids:
            task_id = self._phase_task_ids[phase_name]
            if total is not None and completed is not None:
                self.progress.update(task_id, total=total, completed=completed)
            else:
                self.progress.update(task_id, completed=1, total=1)
        if self.verbose and summary:
            parts = [f"[green]{phase_name} done[/]"]
            for k, v in summary.items():
                parts.append(f"{k}={v}")
            self.console.print(" ".join(parts))

    def _strip_markdown_json(self, raw: str) -> str:
        """Strip markdown code blocks from JSON string."""
        s = raw.strip()
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
        s = s.strip()
        first = s.find("{")
        last = s.rfind("}")
        if first >= 0 and last > first:
            s = s[first : last + 1]
        return s

    def log_api_call(
        self,
        source: str,
        status: str,
        details: str | None = None,
        records: int | None = None,
        *,
        call_type: str = "llm_screening",
        raw_response: str | None = None,
        latency_ms: int | None = None,
        model: str | None = None,
        paper_id: str | None = None,
        phase: str = "phase_unknown",
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
        other_reviewer_decision: Any = None,
        section_name: str | None = None,
        word_count: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an API call (LLM) when verbose. Use log_connector_result for connectors."""
        structured_log.log_api_call(
            source=source,
            status=status,
            phase=phase,
            paper_id=paper_id,
            model=model,
            latency_ms=latency_ms,
            records=records,
            error=details if status != "success" else None,
            raw_response=raw_response if status == "success" else None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            call_type=call_type,
        )
        if not self.verbose:
            return
        if status == "success":
            parts = [f"[cyan]{source}[/]"]
            if model:
                parts.append(f"[dim]{model.split(':')[-1]}[/]")
            if paper_id:
                parts.append(f"[dim]{paper_id[:12]}...[/]")
            if section_name:
                parts.append(f"[dim]{section_name}[/]")
            if details:
                decision_str = None
                if raw_response and call_type == "llm_screening":
                    stripped = self._strip_markdown_json(raw_response)
                    try:
                        obj = json.loads(stripped)
                        decision_str = obj.get("decision")
                    except Exception:
                        pass
                other = other_reviewer_decision
                style = _decision_style(decision_str, other)
                parts.append(f"{style}{details}[/]")
            if latency_ms is not None:
                parts.append(f"[dim]{latency_ms}ms[/]")
            if tokens_in is not None or tokens_out is not None:
                tok = f"{tokens_in or 0}in/{tokens_out or 0}out"
                parts.append(f"[dim]{tok}[/]")
            if cost_usd is not None and cost_usd > 0:
                parts.append(f"[dim]${cost_usd:.4f}[/]")
            if records is not None:
                parts.append(f"[dim]{records} records[/]")
            if word_count is not None:
                parts.append(f"[dim]{word_count} words[/]")
            self.console.print(" ".join(parts))
            if raw_response:
                if call_type == "llm_writing":
                    self._panel_llm_writing(
                        source, section_name, word_count, raw_response,
                        tokens_in, tokens_out, cost_usd, latency_ms,
                    )
                elif call_type == "llm_classification":
                    self._panel_llm_classification(
                        source, paper_id, raw_response,
                        tokens_in, tokens_out, cost_usd, latency_ms,
                    )
                else:
                    self._panel_llm_screening(
                        source, paper_id, raw_response,
                        latency_ms, cost_usd, other_reviewer_decision,
                    )
        else:
            msg = f"[red]{source}[/] failed"
            if details:
                msg += f": {details[:80]}"
            self.console.print(msg)

    def _panel_llm_screening(
        self,
        source: str,
        paper_id: str | None,
        raw_response: str,
        latency_ms: int | None,
        cost_usd: float | None,
        other_reviewer_decision: Any,
    ) -> None:
        stripped = self._strip_markdown_json(raw_response)
        try:
            obj = json.loads(stripped)
            decision = obj.get("decision", "?")
            conf = obj.get("confidence", 0)
            short_reason = (obj.get("short_reason") or "").strip()
            full_reason = obj.get("reasoning") or ""
            if not short_reason and full_reason:
                short_reason = (full_reason[:80] + ("..." if len(full_reason) > 80 else ""))
            title_parts = [source]
            if paper_id:
                title_parts.append(f"{paper_id[:12]}...")
            if latency_ms is not None:
                title_parts.append(f"{latency_ms}ms")
            if cost_usd is not None and cost_usd > 0:
                title_parts.append(f"${cost_usd:.4f}")
            title = " | ".join(title_parts)
            style = _decision_style(decision, other_reviewer_decision)
            body_lines = [f"{style}decision={decision} confidence={conf:.2f}[/]"]
            if short_reason:
                body_lines.append(f"short: {short_reason}")
            body_lines.append(f"reasoning: {full_reason}")
            body = "\n".join(body_lines)
            if self.debug:
                self.console.print(Panel(body, title=title, border_style="dim"))
                self.console.print(Syntax(json.dumps(obj, indent=2), "json"))
            else:
                self.console.print(Panel(body, title=title, border_style="dim"))
        except Exception:
            preview = stripped[:200] + ("..." if len(stripped) > 200 else "")
            self.console.print(Panel(preview, title="Raw (parse failed)", border_style="dim"))

    def _panel_llm_classification(
        self,
        source: str,
        paper_id: str | None,
        raw_response: str,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_usd: float | None,
        latency_ms: int | None,
    ) -> None:
        stripped = self._strip_markdown_json(raw_response)
        try:
            obj = json.loads(stripped)
            design = obj.get("study_design", "?")
            conf = obj.get("confidence", 0)
            reasoning = obj.get("reasoning") or ""
            title_parts = [source]
            if paper_id:
                title_parts.append(f"{paper_id[:12]}...")
            if latency_ms is not None:
                title_parts.append(f"{latency_ms}ms")
            if cost_usd is not None and cost_usd > 0:
                title_parts.append(f"${cost_usd:.4f}")
            title = " | ".join(title_parts)
            body_lines = [f"study_design={design} confidence={conf:.2f}"]
            if tokens_in is not None or tokens_out is not None:
                body_lines.append(f"tokens: {tokens_in or 0}in/{tokens_out or 0}out")
            body_lines.append(f"reasoning: {reasoning}")
            body = "\n".join(body_lines)
            self.console.print(Panel(body, title=title, border_style="dim"))
        except Exception:
            preview = stripped[:200] + ("..." if len(stripped) > 200 else "")
            self.console.print(Panel(preview, title="Raw (parse failed)", border_style="dim"))

    def _panel_llm_writing(
        self,
        source: str,
        section_name: str | None,
        word_count: int | None,
        content: str,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_usd: float | None,
        latency_ms: int | None,
    ) -> None:
        title_parts = [source]
        if section_name:
            title_parts.append(section_name)
        if word_count is not None:
            title_parts.append(f"{word_count} words")
        if latency_ms is not None:
            title_parts.append(f"{latency_ms}ms")
        if cost_usd is not None and cost_usd > 0:
            title_parts.append(f"${cost_usd:.4f}")
        title = " | ".join(title_parts)
        body_lines = []
        if tokens_in is not None or tokens_out is not None:
            body_lines.append(f"tokens: {tokens_in or 0}in/{tokens_out or 0}out")
        preview = (content or "").strip()[:200]
        if preview:
            body_lines.append(f"preview: {preview}{'...' if len(content) > 200 else ''}")
        body = "\n".join(body_lines) if body_lines else "(no content)"
        self.console.print(Panel(body, title=title, border_style="dim"))

    def log_connector_result(
        self,
        name: str,
        status: str,
        records: int,
        query: str = "",
        date_start: int | None = None,
        date_end: int | None = None,
        error: str | None = None,
    ) -> None:
        """Log connector (search API) result with full Rich panel when verbose."""
        structured_log.log_connector_result(
            connector=name,
            status=status,
            records=records if status == "success" else None,
            error=error if status != "success" else None,
        )
        if not self.verbose:
            return
        parts = [f"[cyan]{name}[/]"]
        if status == "success":
            parts.append(f"[dim]{records} records[/]")
        else:
            parts.append("[red]failed[/]")
            if error:
                parts.append(f"[dim]{error[:60]}...[/]" if len(error) > 60 else f"[dim]{error}[/]")
        self.console.print(" ".join(parts))
        date_range = ""
        if date_start is not None and date_end is not None:
            date_range = f"{date_start}-{date_end}"
        query_trunc = (query or "")[:200] + ("..." if len(query or "") > 200 else "")
        title_parts = [name, status]
        if date_range:
            title_parts.append(f"dates: {date_range}")
        title = " | ".join(title_parts)
        body_lines = [f"records: {records}" if status == "success" else f"error: {error or 'unknown'}"]
        if query_trunc:
            body_lines.append(f"query: {query_trunc}")
        if date_range:
            body_lines.append(f"date_range: {date_range}")
        body = "\n".join(body_lines)
        self.console.print(Panel(body, title=title, border_style="dim"))

    def log_extraction_paper(
        self,
        paper_id: str,
        design: str,
        extraction_summary: str,
        rob_judgment: str,
    ) -> None:
        """Log combined extraction + RoB panel per paper when verbose."""
        if not self.verbose:
            return
        summary_trunc = (extraction_summary or "")[:300] + ("..." if len(extraction_summary or "") > 300 else "")
        title = f"extraction_paper | {paper_id[:12]}..."
        body_lines = [
            f"design: {design}",
            f"rob_judgment: {rob_judgment}",
            f"extraction_summary: {summary_trunc}",
        ]
        body = "\n".join(body_lines)
        self.console.print(Panel(body, title=title, border_style="dim"))

    def log_synthesis(
        self,
        feasible: bool,
        groups: list[Any],
        rationale: str,
        n_studies: int,
        direction: str,
    ) -> None:
        """Log synthesis phase panel when verbose."""
        if not self.verbose:
            return
        title = "synthesis | phase_5"
        body_lines = [
            f"feasible: {feasible}",
            f"groups: {len(groups)}",
            f"rationale: {rationale}",
            f"n_studies: {n_studies}",
            f"direction: {direction}",
        ]
        body = "\n".join(body_lines)
        self.console.print(Panel(body, title=title, border_style="dim"))

    def log_prompt(self, agent_name: str, prompt: str, paper_id: str | None) -> None:
        """Log the prompt sent to an agent (debug only)."""
        if not self.debug:
            return
        truncated = prompt[:2000] + "... [truncated]" if len(prompt) > 2000 else prompt
        title = f"Prompt: {agent_name}"
        if paper_id:
            title += f" | {paper_id[:12]}..."
        self.console.print(Panel(truncated, title=title, border_style="dim"))

    def log_rate_limit_wait(self, tier: str, slots_used: int, limit: int) -> None:
        """Log when rate limiter is blocking (verbose only)."""
        structured_log.log_rate_limit_wait(tier=tier, slots_used=slots_used, limit=limit)
        if not self.verbose:
            return
        self.console.print(
            f"[yellow]Rate limit[/] ({tier}): {slots_used}/{limit} slots used, waiting..."
        )

    def log_screening_decision(
        self,
        paper_id: str,
        stage: str,
        decision: str,
        reason: str | None = None,
    ) -> None:
        """Log a screening decision when verbose."""
        structured_log.log_screening_decision(paper_id=paper_id, stage=stage, decision=decision, rationale=reason)
        if not self.verbose:
            return
        reason_snippet = (reason or "")[:60]
        self.console.print(
            f"  [dim]{paper_id[:12]}...[/] {stage} -> [bold]{decision}[/] {reason_snippet}"
        )

    def advance_screening(self, phase_name: str, current: int, total: int) -> None:
        """Advance screening progress bar."""
        if self.progress and phase_name in self._phase_task_ids:
            self.progress.update(
                self._phase_task_ids[phase_name],
                completed=current,
                total=total,
            )

    def emit_debug_state(self, phase_name: str, summary: dict[str, Any]) -> None:
        """Print minimal state summary at phase boundary when debug."""
        if not self.debug:
            return
        lines = [f"{k}: {v}" for k, v in summary.items()]
        self.console.print(
            Panel(
                "\n".join(lines),
                title=f"[debug] {phase_name}",
                border_style="dim",
            )
        )


def create_progress(console: Console) -> Progress:
    """Create a Rich Progress instance for workflow phases."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    )
