import os
from typing import List, Optional, Dict, Any
import datetime
import json
from pathlib import Path

from ..core.base_component import BaseComponent
from ..data_models import ExperimentResult, AnalysisResult
from ..utils.file_utils import write_markdown, ensure_dir
from ..utils.codex_executor import CodexMode, execute_codex
from ..utils.pa_parser import parse_pa_codex_output, extract_best_score_info, extract_improvement_trend
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
