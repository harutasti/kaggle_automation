import os
from typing import List, Optional
import datetime

from ..core.base_component import BaseComponent
from ..data_models import ExperimentResult, AnalysisResult
from ..utils.file_utils import write_markdown, ensure_dir

class PerformanceAnalyzer(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.analysis_dir = os.path.join(self.experiment_run_dir, "analysis")

        # Only ensure directory if not in dry-run mode
        if not config.get("dry_run", False):
            ensure_dir(self.analysis_dir)

    def analyze_results(self, iteration: int, results: List[ExperimentResult]) -> AnalysisResult:
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

        self._log_end(method_name, analysis)
        return analysis
