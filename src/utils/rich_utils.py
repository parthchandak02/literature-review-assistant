"""
Centralized Rich console utilities for consistent terminal output.

This module provides a singleton Console instance and helper functions
for common Rich operations, ensuring consistent formatting across the application.
"""

from rich.console import Console
from rich.panel import Panel
from typing import Optional, List, Tuple

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


def print_workflow_status_panel(
    title: str,
    message: str,
    status_color: str = "cyan",
    padding: Tuple[int, int] = (1, 2),
    add_spacing: bool = True,
) -> None:
    """
    Print workflow status panels (checkpoints, resume info, etc.)
    
    Args:
        title: Panel title
        message: Main message content
        status_color: Border color (cyan, green, yellow, red)
        padding: Panel padding as (vertical, horizontal) tuple
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_workflow_status_panel(
            title="Checkpoint Detected",
            message="Found existing checkpoint!",
            status_color="green",
        )
    """
    if add_spacing:
        console.print()
    
    console.print(
        Panel(
            message,
            title=f"[bold {status_color}]{title}[/bold {status_color}]",
            border_style=status_color,
            padding=padding,
        )
    )


def print_phase_panel(
    phase_name: str,
    phase_number: int,
    description: str,
    status: str = "executing",
    padding: Tuple[int, int] = (1, 2),
    expand: bool = True,
    add_spacing: bool = True,
) -> None:
    """
    Print phase execution status panels.
    
    Args:
        phase_name: Name of the phase
        phase_number: Phase number
        description: Phase description
        status: Phase status (executing, completed, skipped_checkpoint, skipped_disabled)
        padding: Panel padding as (vertical, horizontal) tuple
        expand: Whether panel should expand to full width
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_phase_panel(
            phase_name="search_databases",
            phase_number=1,
            description="Search multiple databases",
            status="executing",
        )
    """
    if add_spacing:
        console.print()
    
    # Determine color and message based on status
    if status == "executing":
        color = "cyan"
        status_text = ""
        content = f"{description}\n\n[dim]Phase {phase_number}[/dim]"
    elif status == "completed":
        color = "green"
        status_text = ""
        content = f"[bold green]Phase completed successfully[/bold green]\n\n{description}"
    elif status == "skipped_checkpoint":
        color = "yellow"
        status_text = "[bold yellow]SKIPPED[/bold yellow] - Already completed\n\n"
        content = f"{status_text}{description}\n\n[dim]Phase {phase_number} - Completed in checkpoint[/dim]"
    elif status == "skipped_disabled":
        color = "cyan"
        status_text = "[bold cyan]SKIPPED[/bold cyan] - Disabled in configuration\n\n"
        content = f"{status_text}{description}\n\n[dim]Phase {phase_number} - Optional phase disabled[/dim]"
    else:
        color = "blue"
        content = f"{description}\n\n[dim]Phase {phase_number}[/dim]"
    
    title_prefix = "Executing Phase" if status == "executing" else f"Phase {phase_number}"
    
    console.print(
        Panel(
            content,
            title=f"[bold {color}]{title_prefix}: {phase_name}[/bold {color}]",
            border_style=color,
            padding=padding,
            expand=expand,
        )
    )


def print_checkpoint_panel(
    phases_loaded: List[str],
    phases_attempted: int,
    status: str = "loading",
    padding: Tuple[int, int] = (1, 2),
    add_spacing: bool = True,
) -> None:
    """
    Print checkpoint loading status panels.
    
    Args:
        phases_loaded: List of phase names that were successfully loaded
        phases_attempted: Total number of phases attempted to load
        status: Loading status (loading, loaded, error)
        padding: Panel padding as (vertical, horizontal) tuple
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_checkpoint_panel(
            phases_loaded=["search_databases", "deduplication"],
            phases_attempted=3,
            status="loaded",
        )
    """
    if add_spacing:
        console.print()
    
    num_loaded = len(phases_loaded)
    
    if status == "loading":
        color = "cyan"
        title = "Loading Checkpoints"
        content = f"[bold cyan]Loading {phases_attempted} checkpoint(s)...[/bold cyan]"
    elif status == "loaded":
        color = "green"
        title = "Checkpoints Loaded"
        content = (
            f"[bold green]Successfully loaded {num_loaded} checkpoint(s)[/bold green]\n\n"
            f"[dim]{', '.join(phases_loaded)}[/dim]"
        )
    else:  # error
        color = "red"
        title = "Checkpoint Error"
        content = f"[bold red]Failed to load checkpoints[/bold red]"
    
    console.print(
        Panel(
            content,
            title=f"[bold {color}]{title}[/bold {color}]",
            border_style=color,
            padding=padding,
        )
    )
