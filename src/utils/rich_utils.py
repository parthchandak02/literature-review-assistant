"""
Centralized Rich console utilities for consistent terminal output.

This module provides a singleton Console instance and helper functions
for common Rich operations, ensuring consistent formatting across the application.
"""

from rich.console import Console
from rich.panel import Panel
from typing import Optional

# Singleton console instance - used throughout the application
console = Console()


def print_panel(
    content: str,
    title: Optional[str] = None,
    border_style: str = "blue",
    add_spacing: bool = True,
) -> None:
    """
    Print a Rich panel with consistent spacing.
    
    This function automatically adds spacing before panels to prevent
    overlap with spinner characters when used inside console.status() contexts.
    
    Args:
        content: The content to display in the panel
        title: Optional title for the panel
        border_style: Color/style for the panel border
        add_spacing: Whether to add a blank line before the panel (default: True)
    
    Example:
        print_panel(
            "Processing data...",
            title="Status",
            border_style="cyan"
        )
    """
    if add_spacing:
        console.print()
    
    console.print(
        Panel(
            content,
            title=title,
            border_style=border_style,
        )
    )


def print_llm_request_panel(
    model: str,
    provider: str,
    agent: str,
    temperature: float,
    prompt_length: int,
    prompt_preview: str,
) -> None:
    """
    Print a standardized LLM request panel.
    
    Args:
        model: Model name
        provider: LLM provider (openai, anthropic, etc.)
        agent: Agent name/role
        temperature: Temperature setting
        prompt_length: Length of the prompt in characters
        prompt_preview: Preview of the prompt (truncated)
    """
    content = (
        f"[bold cyan]LLM Call[/bold cyan]\n"
        f"[yellow]Model:[/yellow] {model} ({provider})\n"
        f"[yellow]Agent:[/yellow] {agent}\n"
        f"[yellow]Temperature:[/yellow] {temperature}\n"
        f"[yellow]Prompt length:[/yellow] {prompt_length} chars\n"
        f"[yellow]Prompt preview:[/yellow]\n{prompt_preview}"
    )
    
    print_panel(
        content=content,
        title="[bold]-> LLM Request[/bold]",
        border_style="cyan",
    )


def print_llm_response_panel(
    duration: float,
    response_preview: str,
    tokens: Optional[int] = None,
    cost: Optional[float] = None,
) -> None:
    """
    Print a standardized LLM response panel.
    
    Args:
        duration: Response time in seconds
        response_preview: Preview of the response (truncated)
        tokens: Optional token count
        cost: Optional cost in dollars
    """
    token_info = f"\n[yellow]Tokens:[/yellow] {tokens}" if tokens else ""
    cost_info = f"\n[yellow]Cost:[/yellow] ${cost:.6f}" if cost and cost > 0 else ""
    
    content = (
        f"[bold green]LLM Response[/bold green]\n"
        f"[yellow]Duration:[/yellow] {duration:.2f}s{token_info}{cost_info}\n"
        f"[yellow]Response preview:[/yellow]\n{response_preview}"
    )
    
    print_panel(
        content=content,
        title="[bold]<- LLM Response[/bold]",
        border_style="green",
    )
