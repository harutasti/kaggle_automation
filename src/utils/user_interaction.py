"""
User Interaction Utilities

Handles user confirmations and prompts for the AutoKaggle system.
"""

import sys
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text


class UserConfirmation:
    """Handles user confirmation prompts with rich formatting."""

    def __init__(self, skip_confirmations: bool = False, dry_run: bool = False):
        """
        Initialize the user confirmation handler.

        Args:
            skip_confirmations: If True, skip all confirmation prompts
            dry_run: If True, indicate dry-run mode in prompts
        """
        self.skip_confirmations = skip_confirmations
        self.dry_run = dry_run
        self.console = Console()

    def confirm_action(
        self,
        action_name: str,
        description: str,
        details: Optional[str] = None,
        warning: Optional[str] = None
    ) -> bool:
        """
        Ask user for confirmation before performing an action.

        Args:
            action_name: Name of the action (e.g., "Fetch Competition Data")
            description: Description of what will happen
            details: Optional additional details to display
            warning: Optional warning message to display

        Returns:
            True if user confirms or skip_confirmations is True, False otherwise
        """
        if self.skip_confirmations:
            self.console.print(f"[dim]Auto-confirming: {action_name}[/dim]")
            return True

        # Build the prompt message
        content = []

        # Add title
        content.append(Text(action_name, style="bold cyan"))
        content.append("")

        # Add description
        content.append(Text(description, style="white"))

        # Add details if provided
        if details:
            content.append("")
            content.append(Text("Details:", style="bold"))
            content.append(Text(details, style="dim"))

        # Add warning if provided
        if warning:
            content.append("")
            content.append(Text("⚠️  Warning:", style="bold yellow"))
            content.append(Text(warning, style="yellow"))

        # Add dry-run notice if applicable
        if self.dry_run:
            content.append("")
            content.append(Text("🔧 DRY-RUN MODE: No actual execution will occur", style="blue"))

        # Create panel
        panel = Panel(
            "\n".join(str(item) for item in content),
            title="[bold]Action Required[/bold]",
            border_style="cyan",
            padding=(1, 2)
        )

        # Display panel
        self.console.print()
        self.console.print(panel)

        # Get confirmation
        try:
            confirmed = Confirm.ask(
                "[bold cyan]Do you want to proceed?[/bold cyan]",
                default=True
            )

            if not confirmed:
                self.console.print("[red]Action cancelled by user[/red]")

            return confirmed

        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[red]Operation cancelled by user[/red]")
            return False

    def confirm_kaggle_fetch(self, competition_name: str) -> bool:
        """Confirm fetching Kaggle competition information."""
        return self.confirm_action(
            "Fetch Competition Data",
            f"Fetch information for competition: {competition_name}",
            "This will use crawl4ai to gather competition details, discussions, and benchmarks from Kaggle.",
            "This may take a few minutes depending on the competition size."
        )

    def confirm_kse_generation(self, iteration: int, num_hypotheses: int) -> bool:
        """Confirm KSE hypothesis generation."""
        iteration_type = "initial" if iteration == 0 else f"iteration {iteration}"
        return self.confirm_action(
            "Generate Hypotheses (KSE)",
            f"Generate {num_hypotheses} experiment hypotheses for {iteration_type}",
            "This will invoke Codex to create ML experiment strategies based on competition analysis.",
            "Codex API usage will be required (may incur costs)."
        )

    def confirm_waa_execution(self, experiment_ids: list) -> bool:
        """Confirm WAA experiment execution."""
        return self.confirm_action(
            "Execute Experiments (WAA)",
            f"Launch {len(experiment_ids)} experiments via Worker AI Agents",
            f"Experiment IDs: {', '.join(experiment_ids[:3])}{'...' if len(experiment_ids) > 3 else ''}",
            "Each experiment will run in its own git worktree and may take significant time."
        )

    def confirm_score_submission(self, score: float, experiment_id: str) -> bool:
        """Confirm score submission to Kaggle."""
        return self.confirm_action(
            "Submit to Kaggle",
            f"Submit predictions from experiment {experiment_id}",
            f"Best score achieved: {score:.4f}",
            "This will submit your predictions to the Kaggle leaderboard."
        )

    def confirm_pa_analysis(self, iteration: int, num_results: int) -> bool:
        """Confirm Performance Analyzer execution."""
        return self.confirm_action(
            "Analyze Performance (PA)",
            f"Analyze {num_results} experiment results from iteration {iteration}",
            "This will invoke Codex to analyze patterns, identify improvements, and generate recommendations.",
            "Codex API usage will be required (may incur costs)."
        )

    def confirm_iteration_submissions(self, iteration: int, experiment_ids: list) -> bool:
        """
        Confirm submitting iteration's successful experiments to Kaggle.

        Args:
            iteration: Current iteration number
            experiment_ids: List of successful experiment IDs to submit

        Returns:
            True if user confirms (or skip_confirmations is True)
        """
        return self.confirm_action(
            "Submit Iteration Results to Kaggle",
            f"Submit {len(experiment_ids)} successful experiment(s) from iteration {iteration} to Kaggle",
            f"Experiments: {', '.join(experiment_ids[:5])}{'...' if len(experiment_ids) > 5 else ''}",
            "This will submit predictions to the Kaggle leaderboard for official scoring."
        )

    def show_status(self, message: str, style: str = "dim"):
        """Display a status message without requiring confirmation."""
        self.console.print(f"[{style}]{message}[/{style}]")

    def show_success(self, message: str):
        """Display a success message."""
        self.console.print(f"[green]✓ {message}[/green]")

    def show_error(self, message: str):
        """Display an error message."""
        self.console.print(f"[red]✗ {message}[/red]")

    def show_warning(self, message: str):
        """Display a warning message."""
        self.console.print(f"[yellow]⚠ {message}[/yellow]")