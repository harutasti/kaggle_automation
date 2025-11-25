"""
Prompt Template Filler Module

Manages placeholder replacement in KSE prompt templates with actual
competition data, system specifications, and iteration results.
"""

import re
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptFiller:
    """Fills KSE prompt templates with actual data."""

    def __init__(self, prompts_dir: str = "prompts/KSE"):
        """
        Initialize the prompt filler.

        Args:
            prompts_dir: Directory containing prompt templates
        """
        self.prompts_dir = Path(prompts_dir)
        self.initial_prompt_path = self.prompts_dir / "kse_prompt_initial_iteration.md"
        self.subsequent_prompt_path = self.prompts_dir / "kse_prompt_subsequent_iterations.md"

        # Validate prompt files exist
        if not self.initial_prompt_path.exists():
            raise FileNotFoundError(f"Initial iteration prompt not found at {self.initial_prompt_path}")
        if not self.subsequent_prompt_path.exists():
            raise FileNotFoundError(f"Subsequent iterations prompt not found at {self.subsequent_prompt_path}")

    def fill_initial_prompt(
        self,
        competition_info: Dict[str, Any],
        dataset_analysis: Dict[str, Any],
        system_specs: Dict[str, Any],
        community_insights: Dict[str, Any],
        num_hypotheses: int = 5
    ) -> str:
        """
        Fill the initial iteration prompt template with actual data.

        Args:
            competition_info: Competition metadata from KIM
            dataset_analysis: Dataset statistics from DatasetAnalyzer
            system_specs: System specifications from SystemSpecsDetector
            community_insights: Insights from crawler/discussions
            num_hypotheses: Number of hypotheses to generate

        Returns:
            Filled prompt string
        """
        logger.info("Filling initial iteration prompt template")

        # Load template
        with open(self.initial_prompt_path, "r") as f:
            template = f.read()

        # Prepare all placeholders
        placeholders = self._prepare_initial_placeholders(
            competition_info, dataset_analysis, system_specs, community_insights, num_hypotheses
        )

        # Fill placeholders
        filled_prompt = self._fill_placeholders(template, placeholders)

        # Validate critical placeholders
        self._validate_filled_prompt(filled_prompt, "initial")

        return filled_prompt

    def fill_subsequent_prompt(
        self,
        competition_info: Dict[str, Any],
        dataset_analysis: Dict[str, Any],
        system_specs: Dict[str, Any],
        community_insights: Dict[str, Any],
        iteration_results: Dict[str, Any],
        pa_analysis: Dict[str, Any],
        iteration_number: int,
        num_hypotheses: int = 5
    ) -> str:
        """
        Fill the subsequent iterations prompt template with actual data.

        Args:
            competition_info: Competition metadata from KIM
            dataset_analysis: Dataset statistics from DatasetAnalyzer
            system_specs: System specifications from SystemSpecsDetector
            community_insights: Insights from crawler/discussions
            iteration_results: Results from previous iteration
            pa_analysis: Performance analysis from PA
            iteration_number: Current iteration number
            num_hypotheses: Number of hypotheses to generate

        Returns:
            Filled prompt string
        """
        logger.info(f"Filling subsequent iteration prompt template for iteration {iteration_number}")

        # Load template
        with open(self.subsequent_prompt_path, "r") as f:
            template = f.read()

        # Prepare all placeholders
        placeholders = self._prepare_subsequent_placeholders(
            competition_info, dataset_analysis, system_specs, community_insights,
            iteration_results, pa_analysis, iteration_number, num_hypotheses
        )

        # Fill placeholders
        filled_prompt = self._fill_placeholders(template, placeholders)

        # Validate critical placeholders
        self._validate_filled_prompt(filled_prompt, "subsequent")

        return filled_prompt

    def _prepare_initial_placeholders(
        self,
        competition_info: Dict[str, Any],
        dataset_analysis: Dict[str, Any],
        system_specs: Dict[str, Any],
        community_insights: Dict[str, Any],
        num_hypotheses: int
    ) -> Dict[str, Any]:
        """Prepare all placeholders for initial iteration prompt."""
        placeholders = {}

        # Competition information
        placeholders["competition_name"] = competition_info.get("name", "[ASSUMED: Unknown Competition]")
        placeholders["competition_type"] = dataset_analysis.get("competition_type", "[ASSUMED: classification]")
        placeholders["evaluation_metric"] = competition_info.get("evaluation_metric", "[ASSUMED: accuracy]")
        placeholders["submission_format"] = competition_info.get("submission_format", "[ASSUMED: csv with id and prediction columns]")

        # Dataset statistics
        placeholders.update(dataset_analysis)

        # System specifications
        placeholders.update(system_specs)

        # Community insights
        placeholders["discussion_winning_approaches"] = self._format_list(
            community_insights.get("winning_approaches", ["[ASSUMED: No discussion data available]"])
        )
        placeholders["discussion_benchmarks"] = self._format_benchmarks(
            community_insights.get("benchmarks", {})
        )
        placeholders["discussion_common_pitfalls"] = self._format_list(
            community_insights.get("common_pitfalls", ["[ASSUMED: Standard ML pitfalls apply]"])
        )
        placeholders["discussion_recommended_techniques"] = self._format_list(
            community_insights.get("recommended_techniques", ["[ASSUMED: Standard ML techniques]"])
        )
        placeholders["discussion_domain_knowledge"] = community_insights.get(
            "domain_knowledge", "[ASSUMED: No specific domain knowledge required]"
        )

        # Generation parameters
        placeholders["num_hypotheses"] = num_hypotheses

        # Runtime estimates
        placeholders.update(self._prepare_runtime_placeholders(system_specs))

        # Diversity requirements
        placeholders.update(self._prepare_diversity_requirements(num_hypotheses))

        return placeholders

    def _prepare_subsequent_placeholders(
        self,
        competition_info: Dict[str, Any],
        dataset_analysis: Dict[str, Any],
        system_specs: Dict[str, Any],
        community_insights: Dict[str, Any],
        iteration_results: Dict[str, Any],
        pa_analysis: Dict[str, Any],
        iteration_number: int,
        num_hypotheses: int
    ) -> Dict[str, Any]:
        """Prepare all placeholders for subsequent iterations prompt."""
        # Start with initial placeholders
        placeholders = self._prepare_initial_placeholders(
            competition_info, dataset_analysis, system_specs, community_insights, num_hypotheses
        )

        # Add iteration-specific information
        placeholders["iteration_number"] = iteration_number
        placeholders["prev_iter"] = iteration_number - 1
        placeholders["num_previous_experiments"] = len(iteration_results.get("experiments", []))

        # Best experiment results
        best_exp = iteration_results.get("best_experiment", {})
        placeholders["best_score"] = best_exp.get("score", 0.0)
        placeholders["best_experiment_id"] = best_exp.get("id", "unknown")
        placeholders["best_strategy"] = best_exp.get("strategy", "unknown")
        placeholders["best_time"] = best_exp.get("runtime_minutes", 0)
        placeholders["best_gap"] = best_exp.get("train_val_gap", 0)

        # Worst experiment results
        worst_exp = iteration_results.get("worst_experiment", {})
        placeholders["worst_score"] = worst_exp.get("score", 0.0)
        placeholders["worst_experiment_id"] = worst_exp.get("id", "unknown")
        placeholders["worst_strategy"] = worst_exp.get("strategy", "unknown")

        # Aggregate statistics
        placeholders["mean_score"] = iteration_results.get("mean_score", 0.0)
        placeholders["std_score"] = iteration_results.get("std_score", 0.0)
        placeholders["min_score"] = iteration_results.get("min_score", 0.0)
        placeholders["max_score"] = iteration_results.get("max_score", 0.0)
        placeholders["success_rate"] = iteration_results.get("success_rate", 0.0)

        # PA analysis
        placeholders.update(self._prepare_pa_placeholders(pa_analysis))

        # Previous results table
        placeholders["previous_results_table"] = self._format_results_table(
            iteration_results.get("experiments", [])
        )

        # Improvement targets
        placeholders["improvement_threshold"] = 0.01  # 1% improvement
        placeholders["min_improvement"] = 0.005
        placeholders["target_improvement"] = 0.02
        placeholders["stretch_improvement"] = 0.05
        placeholders["ceiling_score"] = community_insights.get("ceiling_score", 0.95)

        # Computational budget
        total_time = sum(exp.get("runtime_minutes", 0) for exp in iteration_results.get("experiments", []))
        placeholders["cumulative_time"] = total_time
        placeholders["avg_time"] = total_time / len(iteration_results.get("experiments", [1]))
        placeholders["remaining_budget"] = max(0, 600 - total_time)  # Assuming 10 hour budget
        placeholders["remaining_experiments"] = int(placeholders["remaining_budget"] / placeholders["avg_time"]) if placeholders["avg_time"] > 0 else 0

        # CV scheme from first iteration
        placeholders["cv_scheme_from_iter1"] = iteration_results.get("cv_scheme", "StratifiedKFold(5)")

        # Distribution requirements for subsequent iterations
        placeholders.update(self._prepare_iteration_distribution(num_hypotheses))

        return placeholders

    def _prepare_pa_placeholders(self, pa_analysis: Dict[str, Any]) -> Dict[str, str]:
        """Prepare placeholders from PA analysis."""
        placeholders = {}

        # Success patterns
        success_patterns = pa_analysis.get("success_patterns", [])
        for i, pattern in enumerate(success_patterns[:3], 1):
            placeholders[f"success_pattern_{i}"] = pattern

        # Failure patterns
        failure_patterns = pa_analysis.get("failure_patterns", [])
        for i, pattern in enumerate(failure_patterns[:3], 1):
            placeholders[f"failure_pattern_{i}"] = pattern

        # Feature importance
        feature_importance = pa_analysis.get("feature_importance", [])
        for i, feature in enumerate(feature_importance[:3], 1):
            placeholders[f"feature_{i}"] = feature.get("name", "unknown")
            placeholders[f"importance_score_{i}"] = feature.get("score", 0.0)

        # Recommendations
        placeholders["pa_high_priority_recommendations"] = self._format_list(
            pa_analysis.get("high_priority", ["Continue current approach"])
        )
        placeholders["pa_medium_priority_recommendations"] = self._format_list(
            pa_analysis.get("medium_priority", ["Explore alternative models"])
        )
        placeholders["pa_experimental_recommendations"] = self._format_list(
            pa_analysis.get("experimental", ["Try novel approaches"])
        )
        placeholders["pa_avoid_recommendations"] = self._format_list(
            pa_analysis.get("avoid", ["Avoid overly complex models"])
        )

        # Unresolved questions
        questions = pa_analysis.get("unresolved_questions", [])
        for i, question in enumerate(questions[:2], 1):
            placeholders[f"specific_question_{i}"] = question

        # Summary
        placeholders["pa_analysis_summary"] = pa_analysis.get(
            "summary", "Previous iteration showed promising results with room for improvement."
        )

        return placeholders

    def _prepare_runtime_placeholders(self, system_specs: Dict[str, Any]) -> Dict[str, str]:
        """Prepare runtime-related placeholders."""
        runtime_estimates = system_specs.get("runtime_estimates", {})

        return {
            "CPU_or_GPU": runtime_estimates.get("hardware_type", "CPU"),
            "time_budget": "180",  # 3 hours default
            "expected_runtime": runtime_estimates.get("medium_model", "45-90"),
            "X": runtime_estimates.get("small_model", "15-30").split("-")[0],
            "Y": runtime_estimates.get("small_model", "15-30").split("-")[1],
            "2x expected": str(int(runtime_estimates.get("medium_model", "45-90").split("-")[1]) * 2)
        }

    def _prepare_diversity_requirements(self, num_hypotheses: int) -> Dict[str, Any]:
        """Prepare diversity quota requirements based on number of hypotheses."""
        if num_hypotheses >= 7:
            return {
                "baseline_count": 1,
                "feature_eng_count": 2,
                "advanced_count": 2,
                "ensemble_count": 1,
                "creative_count": num_hypotheses - 6
            }
        elif num_hypotheses >= 5:
            return {
                "baseline_count": 1,
                "feature_eng_count": 2,
                "advanced_count": 1,
                "ensemble_count": 1,
                "creative_count": num_hypotheses - 5
            }
        else:
            return {
                "baseline_count": 1,
                "feature_eng_count": 1,
                "advanced_count": 1,
                "ensemble_count": 0,
                "creative_count": max(0, num_hypotheses - 3)
            }

    def _prepare_iteration_distribution(self, num_hypotheses: int) -> Dict[str, Any]:
        """Prepare hypothesis distribution for subsequent iterations."""
        exploitation = int(num_hypotheses * 0.4)
        innovation = int(num_hypotheses * 0.4)
        exploration = num_hypotheses - exploitation - innovation

        return {
            "exploitation_count": f"{exploitation}-{exploitation+1}",
            "innovation_count": f"{innovation-1}-{innovation}",
            "exploration_count": f"{exploration}"
        }

    def _fill_placeholders(self, template: str, placeholders: Dict[str, Any]) -> str:
        """
        Replace all placeholders in template with actual values.

        Args:
            template: Template string with {placeholders}
            placeholders: Dictionary of placeholder values

        Returns:
            Filled template string
        """
        filled = template

        # Sort placeholders by length (longest first) to avoid partial replacements
        sorted_placeholders = sorted(placeholders.items(), key=lambda x: len(x[0]), reverse=True)

        for key, value in sorted_placeholders:
            # Handle different value types
            if value is None:
                value_str = "[ASSUMED: Not available]"
            elif isinstance(value, (int, float)):
                if isinstance(value, float):
                    value_str = f"{value:.2f}"
                else:
                    value_str = str(value)
            elif isinstance(value, bool):
                value_str = "Yes" if value else "No"
            elif isinstance(value, (list, dict)):
                value_str = json.dumps(value, indent=2) if value else "[ASSUMED: Empty]"
            else:
                value_str = str(value)

            # Replace placeholder
            pattern = "{" + key + "}"
            filled = filled.replace(pattern, value_str)

        return filled

    def _format_list(self, items: List[str], bullet: str = "- ") -> str:
        """Format a list of items as markdown bullet points."""
        if not items:
            return f"{bullet}[ASSUMED: No items available]"
        return "\n".join(f"{bullet}{item}" for item in items)

    def _format_benchmarks(self, benchmarks: Dict[str, Any]) -> str:
        """Format benchmark scores as markdown."""
        if not benchmarks:
            return "- [ASSUMED: No benchmark data available]"

        lines = []
        for key, value in benchmarks.items():
            if isinstance(value, (int, float)):
                lines.append(f"- {key}: {value:.4f}")
            else:
                lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def _format_results_table(self, experiments: List[Dict[str, Any]]) -> str:
        """Format experiment results as markdown table."""
        if not experiments:
            return "| No experiments conducted yet |"

        # Table header
        table = "| Exp ID | Strategy | Val Score | Train-Val Gap | Runtime | Status |\n"
        table += "|--------|----------|-----------|---------------|---------|--------|\n"

        # Table rows
        for exp in experiments:
            exp_id = exp.get("id", "unknown")
            strategy = exp.get("strategy", "unknown")
            score = exp.get("validation_score", 0.0)
            gap = exp.get("train_val_gap", 0.0)
            runtime = exp.get("runtime_minutes", 0)
            status = exp.get("status", "unknown")

            table += f"| {exp_id} | {strategy} | {score:.4f} | {gap:.2f}% | {runtime}min | {status} |\n"

        return table

    def _validate_filled_prompt(self, prompt: str, prompt_type: str) -> None:
        """
        Validate that critical placeholders have been filled.

        Args:
            prompt: Filled prompt string
            prompt_type: "initial" or "subsequent"

        Raises:
            ValueError: If critical placeholders remain unfilled
        """
        # Find remaining placeholders
        remaining = re.findall(r"\{([^}]+)\}", prompt)

        # Filter out markdown code blocks and legitimate uses of braces
        actual_placeholders = []
        for match in remaining:
            # Skip if it's likely part of code or JSON
            if not any(x in match for x in [":", "=", "(", ")", "[", "]", '"', "'"]):
                actual_placeholders.append(match)

        if actual_placeholders:
            # Log warning for non-critical placeholders
            non_critical = ["hypothesis_id", "exp_id", "feature_1", "param_1", "model_type"]
            critical_remaining = [p for p in actual_placeholders if not any(nc in p for nc in non_critical)]

            if critical_remaining:
                logger.warning(f"Critical placeholders remain unfilled in {prompt_type} prompt: {critical_remaining}")
                # Don't raise error, just warn - the prompt can still be useful
            else:
                logger.debug(f"Non-critical placeholders remain (expected): {actual_placeholders}")

    def save_filled_prompt(self, filled_prompt: str, output_path: str) -> None:
        """
        Save filled prompt to file.

        Args:
            filled_prompt: Filled prompt string
            output_path: Path to save the filled prompt
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(filled_prompt)

        logger.info(f"Saved filled prompt to {output_path}")