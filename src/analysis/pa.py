import os
from typing import List, Optional, Dict, Any
import datetime
import json
from pathlib import Path

from ..core.base_component import BaseComponent
from ..data_models import ExperimentResult, AnalysisResult, ExperimentDecision, ExperimentDecisionType
from ..utils.file_utils import write_markdown, ensure_dir
from ..utils.codex_executor import CodexMode, execute_codex
from ..utils.pa_parser import (
    parse_pa_codex_output, extract_best_score_info, extract_improvement_trend,
    parse_evolution_decisions, validate_evolution_decisions, generate_decision_retry_prompt
)
from ..utils.prompt_filler import PromptFiller

class PerformanceAnalyzer(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.analysis_dir = os.path.join(self.experiment_run_dir, "analysis")
        # Worktrees directory for PA Codex execution (gives access to experiment files)
        self.worktrees_dir = os.path.join(self.experiment_run_dir, "worktrees")

        ensure_dir(self.analysis_dir)

        # Codex configuration driven by simulation_mode
        self.use_codex = not config.get("simulation_mode", False)
        self.max_iterations = config.get("max_iterations", 3)
        self.prompt_filler = PromptFiller(config)
        self.competition_name = config.get("kaggle_competition_name", "unknown")
        self.evaluation_metric = config.get("evaluation_metric", "unknown")

    def analyze_results(self, iteration: int, results: List[ExperimentResult],
                       official_scores: Optional[Dict[str, float]] = None) -> AnalysisResult:
        """Analyze the current iteration's results (and optionally prior ones)."""
        method_name = "analyze_results"
        self._log_start(method_name, iteration=iteration, num_results=len(results))

        if not results:
            self.logger.warning("No results provided for analysis.")
            summary = f"# Analysis Report - Iteration {iteration}\n\nNo results available for this iteration."
            analysis = AnalysisResult(
                iteration=iteration,
                summary_markdown=summary,
                best_score=None,
                best_experiment_id=None,
                improvement_trend="N/A",
                recommended_strategies=[]
            )
            write_markdown(summary, os.path.join(self.analysis_dir, f"analysis_iter_{iteration}.md"))
            self._log_end(method_name, analysis)
            return analysis

        # --- Simple analysis logic ---
        successful_results = [r for r in results if r.status == "SUCCESS" and r.score is not None]
        failed_results = [r for r in results if r.status != "SUCCESS"]

        best_score_current_iter = None
        best_exp_id_current_iter = None
        scores = []
        if successful_results:
            successful_results.sort(key=lambda r: r.score, reverse=True)  # Sort by score (desc)
            best_exp_current_iter = successful_results[0]
            best_score_current_iter = best_exp_current_iter.score
            best_exp_id_current_iter = best_exp_current_iter.experiment_id
            scores = [r.score for r in successful_results]
            self.logger.info(f"Best score in iteration {iteration}: {best_score_current_iter:.4f} (Exp ID: {best_exp_id_current_iter})")

        # Improvement trend (placeholder: would need full history from RAD)
        # all_results = rad.get_all_results()  # RAD instance required
        improvement_trend = "N/A"  # TODO: implement

        # Recommend next strategies: prioritize successes and those not yet failing
        successful_strategies = set(r.strategy_name for r in successful_results)
        failed_strategies = set(r.strategy_name for r in failed_results)
        recommended_strategies = list(successful_strategies) + [s for s in list(set(r.strategy_name for r in results)) if s not in failed_strategies and s not in successful_strategies]
        # Could add: weight by score, try new strategies, etc.

        # --- Build analysis markdown ---
        summary_md = f"# Analysis Report - Iteration {iteration}\n\n"
        summary_md += f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        summary_md += f"## Overview\n"
        summary_md += f"- Experiments Processed: {len(results)}\n"
        summary_md += f"- Successful Runs: {len(successful_results)}\n"
        summary_md += f"- Failed Runs: {len(failed_results)}\n\n"

        if best_score_current_iter is not None:
            summary_md += f"## Performance\n"
            summary_md += f"- **Best Score:** {best_score_current_iter:.4f}\n"
            summary_md += f"- Best Experiment ID: {best_exp_id_current_iter}\n"
            summary_md += f"- Score Distribution (Successful Runs): Avg={sum(scores)/len(scores):.4f}, Min={min(scores):.4f}, Max={max(scores):.4f}\n"
            summary_md += f"- Improvement Trend: {improvement_trend}\n\n" # TODO
        else:
            summary_md += "## Performance\nNo successful runs with scores in this iteration.\n\n"

        if failed_results:
            summary_md += f"## Failures\n"
            for fr in failed_results[:5]:  # Show top 5 failures
                summary_md += f"- {fr.experiment_id} ({fr.strategy_name}): Status={fr.status}\n"  # Could include error messages
            if len(failed_results) > 5:
                summary_md += "- ... (and more)\n"
            summary_md += "\n"

        summary_md += f"## Recommendations for Next Iteration\n"
        if recommended_strategies:
            summary_md += "- Prioritize strategies: " + ", ".join(recommended_strategies) + "\n"
        else:
            summary_md += "- No specific strategy recommendations based on this iteration.\n"
        summary_md += "- Consider exploring hyperparameter tuning for top performers.\n" # 例
        summary_md += "- Consider investigating failures.\n" # 例

        analysis_file_path = os.path.join(self.analysis_dir, f"analysis_iter_{iteration}.md")
        write_markdown(summary_md, analysis_file_path)
        self.logger.info(f"Analysis report saved to: {analysis_file_path}")

        analysis = AnalysisResult(
            iteration=iteration,
            summary_markdown=summary_md,  # Could store as file path instead
            best_score=best_score_current_iter,
            best_experiment_id=best_exp_id_current_iter,
            improvement_trend=improvement_trend,
            recommended_strategies=recommended_strategies
        )

        # If Codex is enabled, perform deep analysis
        if self.use_codex:
            try:
                self.logger.info("Performing deep analysis with Codex...")
                codex_insights = self._analyze_with_codex(iteration, results, analysis, official_scores)

                # Update analysis with Codex insights
                if codex_insights:
                    analysis.success_patterns = codex_insights.get("success_patterns", [])
                    analysis.failure_patterns = codex_insights.get("failure_patterns", [])
                    analysis.feature_importance = codex_insights.get("feature_importance", [])
                    analysis.hyperparameter_insights = codex_insights.get("hyperparameter_insights", [])
                    analysis.high_priority_recommendations = codex_insights.get("high_priority_recommendations", [])
                    analysis.medium_priority_recommendations = codex_insights.get("medium_priority_recommendations", [])
                    analysis.experimental_recommendations = codex_insights.get("experimental_recommendations", [])
                    analysis.avoid_recommendations = codex_insights.get("avoid_recommendations", [])
                    analysis.unresolved_questions = codex_insights.get("unresolved_questions", [])
                    analysis.overfitting_analysis = codex_insights.get("overfitting_analysis")
                    analysis.convergence_status = codex_insights.get("convergence_status", improvement_trend)
                    analysis.improvement_rate = codex_insights.get("improvement_rate")
                    analysis.computational_efficiency = codex_insights.get("computational_efficiency", [])
                    analysis.top_discoveries = codex_insights.get("top_discoveries", [])
                    analysis.critical_decisions = codex_insights.get("critical_decisions", [])

                    # Update summary with deeper insights
                    if codex_insights.get("summary"):
                        analysis.summary_markdown += f"\n\n## Deep Analysis Summary\n\n{codex_insights['summary']}"

                    # Save updated analysis
                    write_markdown(analysis.summary_markdown, analysis_file_path)
                    self.logger.info("Deep analysis with Codex completed successfully")

            except Exception as e:
                self.logger.error(f"Error performing Codex analysis: {e}")
                # Continue with basic analysis if Codex fails

        self._log_end(method_name, analysis)
        return analysis

    def _analyze_with_codex(self, iteration: int, results: List[ExperimentResult],
                          basic_analysis: AnalysisResult,
                          official_scores: Optional[Dict[str, float]] = None) -> Optional[Dict[str, Any]]:
        """
        Use Codex to perform deep analysis of experiment results.

        Args:
            iteration: Current iteration number
            results: List of experiment results
            basic_analysis: Basic analysis already performed

        Returns:
            Dictionary with structured insights from Codex
        """
        try:
            # Prepare the prompt
            prompt = self._prepare_pa_prompt(iteration, results, basic_analysis, official_scores or {})

            if not prompt:
                self.logger.warning("Could not prepare PA prompt")
                return None

            # Execute Codex
            self.logger.info(f"Calling Codex for PA analysis (iteration {iteration})")

            # Get codex-responses directory for JSONL output
            codex_responses_dir = os.path.join(self.experiment_run_dir, "codex-responses")

            use_resume = iteration > 0
            run_label = "initial" if iteration == 0 else "resume"
            resume_prompt = prompt if use_resume else None

            codex_result = execute_codex(
                mode=CodexMode.PA,
                results_data=prompt,  # PA expects results_data, not prompt
                output_dir=self.worktrees_dir,  # Run in worktrees/ for file access
                iteration=iteration,
                codex_responses_dir=codex_responses_dir,
                timeout=self.config.get("pa_codex_timeout", 180),
                resume_prompt=resume_prompt,
                run_label=run_label
            )

            if not codex_result.success:
                self.logger.error(f"Codex PA execution failed: {codex_result.error}")
                return None

            # Parse Codex output
            if codex_result.analysis:
                # If already parsed by executor
                return codex_result.analysis

            # Otherwise parse the raw output
            if codex_result.output_file:
                output_path = os.path.join(self.worktrees_dir, codex_result.output_file)
                if os.path.exists(output_path):
                    with open(output_path, 'r') as f:
                        codex_output = f.read()
                    return parse_pa_codex_output(codex_output)

            return None

        except Exception as e:
            self.logger.error(f"Error in _analyze_with_codex: {e}")
            return None

    def _prepare_pa_prompt(self, iteration: int, results: List[ExperimentResult],
                          basic_analysis: AnalysisResult,
                          official_scores: Optional[Dict[str, float]]) -> Optional[str]:
        """
        Prepare the PA prompt for Codex analysis.

        Args:
            iteration: Current iteration number
            results: List of experiment results
            basic_analysis: Basic analysis already performed

        Returns:
            Filled prompt string or None if preparation fails
        """
        try:
            prompts_dir = Path("prompts") / "PA"
            if iteration == 0:
                prompt_path = prompts_dir / "pa_prompt_first_run.md"
            else:
                prompt_path = prompts_dir / "pa_prompt_resume.md"

            if not prompt_path.exists():
                prompt_path = Path("prompts") / "PA" / "pa_analysis_prompt.md"
                if not prompt_path.exists():
                    self.logger.error(f"PA prompt template not found: {prompt_path}")
                    return None

            prompt_template = prompt_path.read_text(encoding="utf-8")

            waa_results_block = self._build_waa_results_block(results, official_scores)

            # Calculate statistics
            successful_results = [r for r in results if r.status == "SUCCESS" and r.score is not None]
            failed_results = [r for r in results if r.status != "SUCCESS"]
            scores = [r.score for r in successful_results] if successful_results else []

            summary_lines = [
                f"- Iteration: {iteration}",
                f"- Best CV score: {basic_analysis.best_score:.4f}" if basic_analysis.best_score else "- Best CV score: N/A",
                f"- Best experiment: {basic_analysis.best_experiment_id or 'N/A'}",
                f"- Avg CV score: {sum(scores)/len(scores):.4f}" if scores else "- Avg CV score: N/A",
                f"- Success rate: {len(successful_results)/len(results)*100:.1f}%" if results else "- Success rate: 0%"
            ]
            summary_block = "\n".join(summary_lines)

            replacements = {
                "<<WAA_RESULTS>>": waa_results_block,
                "<<SUMMARY_BLOCK>>": summary_block
            }

            filled_prompt = prompt_template
            for key, value in replacements.items():
                filled_prompt = filled_prompt.replace(key, str(value))

            return filled_prompt

        except Exception as e:
            self.logger.error(f"Error preparing PA prompt: {e}")
            return None

    def _calculate_std(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def _build_waa_results_block(self, results: List[ExperimentResult],
                                 official_scores: Optional[Dict[str, float]]) -> str:
        """Render WAA results (including official scores) as markdown bullets."""
        if not results:
            return "No experiments were run in this iteration."

        lines = []
        for r in results:
            official = None
            if official_scores:
                official = official_scores.get(r.experiment_id)
            official_str = f"{official:.4f}" if official is not None else "N/A"
            cv_str = f"{r.score:.4f}" if r.score is not None else "N/A"
            lines.append(
                f"- {r.experiment_id} | strategy={r.strategy_name} | cv_score={cv_str} | official_score={official_str} | status={r.status} | params={json.dumps(r.parameters) if r.parameters else '{}'}"
            )
        return "\n".join(lines)

    def analyze_with_evolution_decisions(
        self,
        iteration: int,
        results: List[ExperimentResult],
        official_scores: Optional[Dict[str, float]] = None
    ) -> AnalysisResult:
        """
        Analyze results AND generate evolution decisions for each experiment.

        This is the main entry point for persistent evolution mode. It:
        1. Performs standard analysis
        2. Generates CONTINUE/TERMINATE decisions for each experiment
        3. Retries until valid decisions are obtained

        Args:
            iteration: Current iteration number
            results: List of experiment results
            official_scores: Optional dict mapping experiment_id to official Kaggle score

        Returns:
            AnalysisResult with experiment_decisions populated
        """
        # First, perform standard analysis
        analysis = self.analyze_results(iteration, results, official_scores)

        # If Codex is not enabled, skip evolution decisions
        if not self.use_codex:
            self.logger.warning("Codex not enabled, skipping evolution decisions")
            return analysis

        # Get evolution decisions with retry logic
        try:
            experiment_ids = [r.experiment_id for r in results]
            decisions = self._get_evolution_decisions_with_retry(
                iteration, results, analysis, official_scores, experiment_ids
            )

            # Populate analysis with decisions
            analysis.experiment_decisions = decisions
            analysis.experiments_to_continue = sum(
                1 for d in decisions if d.decision == ExperimentDecisionType.CONTINUE
            )
            analysis.experiments_to_terminate = sum(
                1 for d in decisions if d.decision == ExperimentDecisionType.TERMINATE
            )
            analysis.new_slots_available = analysis.experiments_to_terminate

            self.logger.info(
                f"Evolution decisions: {analysis.experiments_to_continue} CONTINUE, "
                f"{analysis.experiments_to_terminate} TERMINATE"
            )

            # Save decisions to file for debugging
            self._save_evolution_decisions(iteration, decisions)

        except Exception as e:
            self.logger.error(f"Failed to get evolution decisions: {e}")
            # Leave experiment_decisions empty, caller will need to handle

        return analysis

    def _get_evolution_decisions_with_retry(
        self,
        iteration: int,
        results: List[ExperimentResult],
        analysis: AnalysisResult,
        official_scores: Optional[Dict[str, float]],
        expected_experiment_ids: List[str]
    ) -> List[ExperimentDecision]:
        """
        Get evolution decisions from PA, retrying until valid output is obtained.

        Args:
            iteration: Current iteration number
            results: List of experiment results
            analysis: Basic analysis result
            official_scores: Optional official scores
            expected_experiment_ids: List of experiment IDs that need decisions

        Returns:
            List of ExperimentDecision objects

        Raises:
            RuntimeError: If unable to get valid decisions after many retries
        """
        max_retries = 100  # Keep retrying as per user preference
        retry_count = 0

        # Get initial PA output with evolution decisions prompt
        codex_output = self._get_pa_output_with_decisions(iteration, results, analysis, official_scores)

        while retry_count < max_retries:
            try:
                # Try to parse evolution decisions
                decisions, summary = parse_evolution_decisions(codex_output)

                # Validate decisions
                is_valid, issues = validate_evolution_decisions(decisions, expected_experiment_ids)

                if is_valid:
                    self.logger.info(f"Successfully parsed evolution decisions after {retry_count} retries")
                    return decisions

                # Invalid - generate retry prompt and continue
                self.logger.warning(f"Evolution decisions validation failed: {issues}")
                retry_prompt = generate_decision_retry_prompt(issues, codex_output)

                # Resume PA with retry prompt
                codex_output = self._resume_pa_for_decisions(iteration, retry_prompt)
                retry_count += 1

            except ValueError as e:
                # Parsing failed completely
                self.logger.warning(f"Failed to parse evolution decisions: {e}")
                retry_prompt = generate_decision_retry_prompt([str(e)], codex_output)
                codex_output = self._resume_pa_for_decisions(iteration, retry_prompt)
                retry_count += 1

        # Should not reach here with max_retries=100, but just in case
        raise RuntimeError(f"Failed to get valid evolution decisions after {max_retries} retries")

    def _get_pa_output_with_decisions(
        self,
        iteration: int,
        results: List[ExperimentResult],
        analysis: AnalysisResult,
        official_scores: Optional[Dict[str, float]]
    ) -> str:
        """
        Get PA Codex output that includes evolution decisions.

        Returns the raw Codex output text.
        """
        # Prepare prompt with evolution decisions requirement
        prompt = self._prepare_pa_prompt_with_decisions(iteration, results, analysis, official_scores)

        codex_responses_dir = os.path.join(self.experiment_run_dir, "codex-responses")

        codex_result = execute_codex(
            mode=CodexMode.PA,
            results_data=prompt,
            output_dir=self.worktrees_dir,
            iteration=iteration,
            codex_responses_dir=codex_responses_dir,
            timeout=self.config.get("pa_codex_timeout", 300),  # Longer timeout for decisions
            resume_prompt=prompt if iteration > 0 else None,
            run_label="evolution"
        )

        if not codex_result.success:
            raise RuntimeError(f"Codex PA execution failed: {codex_result.error}")

        # Read the output
        if codex_result.output_file:
            output_path = os.path.join(self.worktrees_dir, codex_result.output_file)
            if os.path.exists(output_path):
                with open(output_path, 'r') as f:
                    return f.read()

        # Try to get from JSONL
        return codex_result.raw_output or ""

    def _resume_pa_for_decisions(self, iteration: int, retry_prompt: str) -> str:
        """
        Resume PA session with a retry prompt to fix decision format.

        Returns the new Codex output text.
        """
        codex_responses_dir = os.path.join(self.experiment_run_dir, "codex-responses")

        codex_result = execute_codex(
            mode=CodexMode.PA,
            results_data=retry_prompt,
            output_dir=self.worktrees_dir,
            iteration=iteration,
            codex_responses_dir=codex_responses_dir,
            timeout=self.config.get("pa_codex_timeout", 180),
            resume_prompt=retry_prompt,
            run_label="decision_retry"
        )

        if not codex_result.success:
            raise RuntimeError(f"Codex PA resume failed: {codex_result.error}")

        if codex_result.output_file:
            output_path = os.path.join(self.worktrees_dir, codex_result.output_file)
            if os.path.exists(output_path):
                with open(output_path, 'r') as f:
                    return f.read()

        return codex_result.raw_output or ""

    def _prepare_pa_prompt_with_decisions(
        self,
        iteration: int,
        results: List[ExperimentResult],
        analysis: AnalysisResult,
        official_scores: Optional[Dict[str, float]]
    ) -> str:
        """
        Prepare PA prompt that includes evolution decision requirements.
        """
        # Get base prompt
        base_prompt = self._prepare_pa_prompt(iteration, results, analysis, official_scores)
        if not base_prompt:
            raise RuntimeError("Failed to prepare base PA prompt")

        # Load evolution decisions template
        evolution_prompt_path = Path("prompts") / "PA" / "pa_evolution_decisions.md"
        if evolution_prompt_path.exists():
            evolution_template = evolution_prompt_path.read_text(encoding="utf-8")

            # Build experiment list for the template
            experiment_list = "\n".join(f"- {r.experiment_id}" for r in results)
            evolution_template = evolution_template.replace("<<EXPERIMENT_IDS>>", experiment_list)

            # Append to base prompt
            return base_prompt + "\n\n" + evolution_template
        else:
            # Inline evolution decision requirements if template not found
            experiment_list = "\n".join(f"- {r.experiment_id}" for r in results)
            inline_requirements = f"""

---

## CRITICAL: Evolution Decisions Required

You MUST provide explicit CONTINUE or TERMINATE decisions for each experiment.

### Experiments requiring decisions:
{experiment_list}

### Output Format (REQUIRED):

```yaml
decisions:
  - experiment_id: "<exact experiment ID from list above>"
    decision: CONTINUE  # or TERMINATE
    confidence: 0.85  # 0.0-1.0
    reasoning: "Why this decision was made"
    improvement_instructions: |  # REQUIRED for CONTINUE
      1. First specific improvement
      2. Second specific improvement
    potential_ceiling: 0.82  # Optional: estimated max score
    priority_rank: 1  # 1=highest priority

summary:
  continue_count: <number>
  terminate_count: <number>
  new_slots: <same as terminate_count>
```

### Decision Criteria:

**CONTINUE if:**
- Score is competitive (within 5% of best)
- Clear improvement path exists
- Approach provides diversity value

**TERMINATE if:**
- Score is significantly worse (>10% below best) with no clear fix
- Approach has fundamental limitations
- Similar/better approach already exists
"""
            return base_prompt + inline_requirements

    def _save_evolution_decisions(self, iteration: int, decisions: List[ExperimentDecision]) -> None:
        """Save evolution decisions to a JSON file for debugging/auditing."""
        decisions_file = os.path.join(self.analysis_dir, f"evolution_decisions_iter_{iteration}.json")

        decisions_data = {
            "iteration": iteration,
            "timestamp": datetime.datetime.now().isoformat(),
            "decisions": [
                {
                    "experiment_id": d.experiment_id,
                    "decision": d.decision.value,
                    "reasoning": d.reasoning,
                    "confidence": d.confidence,
                    "improvement_instructions": d.improvement_instructions,
                    "termination_reason": d.termination_reason,
                    "potential_ceiling": d.potential_ceiling,
                    "priority_rank": d.priority_rank
                }
                for d in decisions
            ],
            "summary": {
                "continue_count": sum(1 for d in decisions if d.decision == ExperimentDecisionType.CONTINUE),
                "terminate_count": sum(1 for d in decisions if d.decision == ExperimentDecisionType.TERMINATE)
            }
        }

        with open(decisions_file, 'w') as f:
            json.dump(decisions_data, f, indent=2)

        self.logger.info(f"Evolution decisions saved to: {decisions_file}")
