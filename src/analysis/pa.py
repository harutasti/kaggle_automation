import os
from typing import List, Optional, Dict, Any
import datetime
import json

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

        # Codex configuration
        self.use_codex = config.get("pa_codex_enabled", False)
        self.dry_run = config.get("dry_run", False)
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
        if self.use_codex and not self.dry_run:
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
            prompt = self._prepare_pa_prompt(iteration, results, basic_analysis)

            if not prompt:
                self.logger.warning("Could not prepare PA prompt")
                return None

            # Execute Codex
            self.logger.info(f"Calling Codex for PA analysis (iteration {iteration})")

            # Get codex-responses directory for JSONL output
            codex_responses_dir = os.path.join(self.experiment_run_dir, "codex-responses")

            codex_result = execute_codex(
                mode=CodexMode.PA,
                results_data=prompt,  # PA expects results_data, not prompt
                output_dir=self.worktrees_dir,  # Run in worktrees/ for file access
                iteration=iteration,
                codex_responses_dir=codex_responses_dir,
                dry_run=self.dry_run,
                timeout=self.config.get("pa_codex_timeout", 180)
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
                          basic_analysis: AnalysisResult) -> Optional[str]:
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
            # Load PA prompt template
            prompt_path = os.path.join("prompts", "PA", "pa_analysis_prompt.md")
            if not os.path.exists(prompt_path):
                self.logger.error(f"PA prompt template not found: {prompt_path}")
                return None

            with open(prompt_path, 'r') as f:
                prompt_template = f.read()

            # Prepare experiment results table
            table_rows = []
            for r in results:
                key_params = json.dumps(r.parameters) if r.parameters else "{}"
                # Truncate long parameter strings
                if len(key_params) > 100:
                    key_params = key_params[:97] + "..."

                row = f"| {r.experiment_id} | {r.strategy_name} | "
                row += f"{r.score:.4f}" if r.score else "N/A"
                row += f" | {r.status} | {r.execution_time_seconds:.1f} | "
                row += "N/A | "  # Memory placeholder
                row += f"{key_params} |"
                table_rows.append(row)

            experiment_results_table = "\n".join(table_rows)

            # Calculate statistics
            successful_results = [r for r in results if r.status == "SUCCESS" and r.score is not None]
            failed_results = [r for r in results if r.status != "SUCCESS"]
            scores = [r.score for r in successful_results] if successful_results else []

            # Prepare detailed logs (simplified for now)
            detailed_logs = []
            for r in results[:5]:  # Show first 5 experiments in detail
                log_entry = f"### Experiment: {r.experiment_id}\n"
                log_entry += f"- Strategy: {r.strategy_name}\n"
                log_entry += f"- Score: {r.score:.4f}\n" if r.score else "- Score: N/A\n"
                log_entry += f"- Status: {r.status}\n"
                log_entry += f"- Runtime: {r.execution_time_seconds:.1f}s\n"
                if r.error_message:
                    log_entry += f"- Error: {r.error_message}\n"
                detailed_logs.append(log_entry)

            # Calculate time remaining (placeholder)
            time_remaining = "Unknown"  # Would need competition deadline

            # Fill the prompt template
            replacements = {
                "{num_experiments}": str(len(results)),
                "{iteration_number}": str(iteration),
                "{competition_name}": self.competition_name,
                "{evaluation_metric}": self.evaluation_metric,
                "{best_score}": f"{basic_analysis.best_score:.4f}" if basic_analysis.best_score else "N/A",
                "{max_iterations}": str(self.max_iterations),
                "{time_remaining}": time_remaining,
                "{experiment_results_table}": experiment_results_table,
                "{best_experiment_id}": basic_analysis.best_experiment_id or "N/A",
                "{avg_score}": f"{sum(scores)/len(scores):.4f}" if scores else "N/A",
                "{worst_score}": f"{min(scores):.4f}" if scores else "N/A",
                "{score_std}": f"{self._calculate_std(scores):.4f}" if scores else "N/A",
                "{success_rate}": f"{len(successful_results)/len(results)*100:.1f}" if results else "0",
                "{num_successful}": str(len(successful_results)),
                "{num_total}": str(len(results)),
                "{total_runtime}": f"{sum(r.execution_time_seconds for r in results)/60:.1f}",
                "{avg_runtime}": f"{sum(r.execution_time_seconds for r in results)/len(results)/60:.1f}" if results else "0",
                "{failed_experiments_list}": ", ".join([r.experiment_id for r in failed_results]) or "None",
                "{detailed_experiment_logs}": "\n\n".join(detailed_logs)
            }

            # Replace all placeholders
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
