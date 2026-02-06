"""
Centralized Rich console utilities for consistent terminal output.

This module provides a singleton Console instance and helper functions
for common Rich operations, ensuring consistent formatting across the application.
"""

from rich.console import Console
from rich.panel import Panel
from typing import Optional, List, Tuple, Dict

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
        content = "[bold red]Failed to load checkpoints[/bold red]"
    
    console.print(
        Panel(
            content,
            title=f"[bold {color}]{title}[/bold {color}]",
            border_style=color,
            padding=padding,
        )
    )


def print_section_start_panel(
    section_name: str,
    section_number: int,
    total_sections: int,
    model: str,
    status: str = "Starting...",
    padding: Tuple[int, int] = (1, 2),
    add_spacing: bool = True,
) -> None:
    """
    Print a panel when an article section writing begins.
    
    Args:
        section_name: Name of the section (e.g., "Introduction", "Methods")
        section_number: Section number (1-5)
        total_sections: Total number of sections (5)
        model: LLM model being used
        status: Status message
        padding: Panel padding as (vertical, horizontal) tuple
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_section_start_panel(
            section_name="Introduction",
            section_number=1,
            total_sections=5,
            model="gemini-2.5-pro",
        )
    """
    if add_spacing:
        console.print()
    
    content = (
        f"[yellow]Model:[/yellow] {model}\n"
        f"[yellow]Status:[/yellow] {status}"
    )
    
    console.print(
        Panel(
            content,
            title=f"[bold cyan]Writing Section: {section_name} ({section_number}/{total_sections})[/bold cyan]",
            border_style="cyan",
            padding=padding,
        )
    )


def print_section_complete_panel(
    section_name: str,
    word_count: int,
    duration: float,
    humanized: bool = False,
    checkpoint_saved: bool = True,
    padding: Tuple[int, int] = (1, 2),
    add_spacing: bool = True,
) -> None:
    """
    Print a panel when an article section writing completes successfully.
    
    Args:
        section_name: Name of the section
        word_count: Number of words written
        duration: Time taken in seconds
        humanized: Whether humanization was applied
        checkpoint_saved: Whether checkpoint was saved successfully
        padding: Panel padding as (vertical, horizontal) tuple
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_section_complete_panel(
            section_name="Introduction",
            word_count=847,
            duration=36.2,
            humanized=True,
            checkpoint_saved=True,
        )
    """
    if add_spacing:
        console.print()
    
    humanized_text = " (humanized)" if humanized else ""
    checkpoint_text = "Checkpoint saved" if checkpoint_saved else "Checkpoint save failed"
    checkpoint_color = "green" if checkpoint_saved else "red"
    
    content = (
        f"[yellow]Status:[/yellow] [bold green]SUCCESS[/bold green]{humanized_text}\n"
        f"[yellow]Word count:[/yellow] {word_count:,} words\n"
        f"[yellow]Time taken:[/yellow] {duration:.1f}s\n"
        f"[yellow]Checkpoint:[/yellow] [{checkpoint_color}]{checkpoint_text}[/{checkpoint_color}]"
    )
    
    console.print(
        Panel(
            content,
            title=f"[bold green]Section Complete: {section_name}[/bold green]",
            border_style="green",
            padding=padding,
        )
    )


def print_section_retry_panel(
    section_name: str,
    attempt_number: int,
    max_attempts: int,
    reason: str = "Empty response or timeout",
    padding: Tuple[int, int] = (1, 2),
    add_spacing: bool = True,
) -> None:
    """
    Print a panel when a section writing retry is attempted.
    
    Args:
        section_name: Name of the section
        attempt_number: Current attempt number
        max_attempts: Total attempts allowed
        reason: Reason for retry
        padding: Panel padding as (vertical, horizontal) tuple
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_section_retry_panel(
            section_name="Results",
            attempt_number=2,
            max_attempts=2,
            reason="Empty response from LLM",
        )
    """
    if add_spacing:
        console.print()
    
    content = (
        f"[yellow]Attempt:[/yellow] {attempt_number}/{max_attempts}\n"
        f"[yellow]Reason:[/yellow] {reason}\n"
        f"[dim]Retrying immediately...[/dim]"
    )
    
    console.print(
        Panel(
            content,
            title=f"[bold yellow]Retry: {section_name}[/bold yellow]",
            border_style="yellow",
            padding=padding,
        )
    )


def print_naturalness_panel(
    section_name: str,
    status: str = "evaluating",
    scores: Optional[Dict[str, float]] = None,
    padding: Tuple[int, int] = (1, 2),
    add_spacing: bool = True,
) -> None:
    """
    Print a panel for naturalness scoring (distinct from main LLM writing).
    
    Args:
        section_name: Name of the section being scored
        status: "evaluating" or "complete"
        scores: Optional dict of naturalness scores (when complete)
        padding: Panel padding as (vertical, horizontal) tuple
        add_spacing: Whether to add blank line before panel
    
    Example:
        print_naturalness_panel(
            section_name="Introduction",
            status="complete",
            scores={
                "SENTENCE_STRUCTURE_DIVERSITY": 1.0,
                "VOCABULARY_RICHNESS": 1.0,
                "OVERALL_HUMAN_LIKE": 1.0,
            },
        )
    """
    if add_spacing:
        console.print()
    
    if status == "evaluating":
        color = "magenta"
        title = f"[bold {color}]Naturalness Scoring: {section_name}[/bold {color}]"
        content = "[dim]Evaluating text quality and human-like characteristics...[/dim]"
    else:  # complete
        color = "magenta"
        title = f"[bold {color}]Naturalness Scores: {section_name}[/bold {color}]"
        
        if scores:
            score_lines = []
            for key, value in scores.items():
                # Format score with color based on value
                if value >= 0.8:
                    score_color = "green"
                elif value >= 0.6:
                    score_color = "yellow"
                else:
                    score_color = "red"
                
                # Format key to be more readable
                readable_key = key.replace("_", " ").title()
                score_lines.append(f"[yellow]{readable_key}:[/yellow] [{score_color}]{value:.2f}[/{score_color}]")
            
            content = "\n".join(score_lines)
        else:
            content = "[dim]No scores available[/dim]"
    
    console.print(
        Panel(
            content,
            title=title,
            border_style=color,
            padding=padding,
        )
    )
