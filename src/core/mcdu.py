import os
import shutil
import time
import json
import sys
from typing import Dict, List, Optional

from .base_component import BaseComponent
from .kim import KaggleInterfaceManager
from .kse import KnowledgeStrategyEngine
from ..execution.eo import ExperimentOrchestrator
from ..analysis.rad import ResultAggregatorDatabase
from ..analysis.pa import PerformanceAnalyzer
from ..utils.user_interaction import UserConfirmation
from ..data_models import CompetitionInfo, ExperimentHypothesis, ExperimentResult, AnalysisResult

class MasterControllerDecisionUnit(BaseComponent):
    def __init__(self, config: dict):
        """
        Initialize the Master Controller Decision Unit.

        Args:
            config: Configuration dictionary (already loaded and enriched by main.py)
        """
        self.config = config
        super().__init__(self.config)  # Initialize BaseComponent

        # Initialize user confirmation handler
        self.user_confirm = UserConfirmation(
            skip_confirmations=self.config.get("skip_confirmations", False),
            dry_run=self.config.get("dry_run", False)
        )

        # Initialize components
        self.kim = KaggleInterfaceManager(self.config)
        self.kse = KnowledgeStrategyEngine(self.config)
        self.eo = ExperimentOrchestrator(self.config)
        self.rad = ResultAggregatorDatabase(self.config)
        self.pa = PerformanceAnalyzer(self.config)

        # State variables
        self.current_iteration = 0
        self.max_iterations = self.config.get("max_iterations", 5)
        self.wca_per_iteration = self.config.get("wca_per_iteration", 3)
        self.competition_info: Optional[CompetitionInfo] = None
        self.all_results: Dict[int, List[ExperimentResult]] = {}  # {iteration: [results]}
        self.all_hypotheses: Dict[str, ExperimentHypothesis] = {}  # {exp_id: hypothesis} - persists across iterations
        self.best_score_overall: Optional[float] = None
        self.best_experiment_id_overall: Optional[str] = None
        self.iterations_without_improvement = 0
        self.stop_reason: Optional[str] = None
        self.pending_cleanup: Dict[str, str] = {}  # {exp_id: worktree_path} for delayed cleanup

        # Load stop conditions
        stop_config = self.config.get("stop_condition", {})
        self.score_threshold = stop_config.get("score_threshold")
        self.no_improvement_threshold = stop_config.get("no_improvement_iterations", 3)


    def run_main_loop(self):
        """Main execution loop."""
        self._log_start("run_main_loop")

        # 1. Initialization: fetch competition info & download data
        competition_name = self.config.get("kaggle_competition_name", "unknown")

        # Confirm fetching competition info
        if not self.user_confirm.confirm_kaggle_fetch(competition_name):
            self.logger.info("User cancelled competition fetch. Exiting.")
            self.stop_reason = "User cancelled operation"
            return

        self.competition_info = self.kim.get_competition_info()
        if not self.competition_info:
            self.logger.critical("Failed to get competition info. Exiting.")
            self.user_confirm.show_error("Failed to fetch competition information")
            return

        self.user_confirm.show_success(f"Successfully fetched competition info for {competition_name}")

        if not self.kim.download_data_files(self.competition_info):
             self.logger.warning("Failed to download/verify data files. Continuing, but WAA might fail.")
             self.user_confirm.show_warning("Failed to download/verify some data files")
             # Could decide to stop here

        # Pass dataset analysis from KIM to KSE (avoids duplicate analysis)
        dataset_placeholders = self.kim.get_dataset_analysis_placeholders()
        if dataset_placeholders:
            self.kse.set_dataset_analysis(dataset_placeholders)
            self.logger.info("Passed dataset analysis from KIM to KSE")

        # Copy kaggle_data to hypotheses/ for KSE access
        experiment_run_dir = self.config.get("experiment_run_dir", "./experiments")
        kaggle_data_src = os.path.join(experiment_run_dir, "kaggle_data")
        hypotheses_kaggle_data = os.path.join(experiment_run_dir, "hypotheses", "kaggle_data")
        if os.path.exists(kaggle_data_src) and not os.path.exists(hypotheses_kaggle_data):
            try:
                shutil.copytree(kaggle_data_src, hypotheses_kaggle_data)
                self.logger.info(f"Copied kaggle_data to hypotheses/ for KSE access")
            except Exception as copy_error:
                self.logger.warning(f"Failed to copy kaggle_data to hypotheses: {copy_error}")

        # 2. Main loop
        while not self._should_stop():
            self.logger.info(f"--- Starting Iteration {self.current_iteration} ---")
            self.user_confirm.show_status(f"Starting Iteration {self.current_iteration}", "bold cyan")

            # 2a. Generate hypotheses
            # Confirm KSE hypothesis generation
            if not self.user_confirm.confirm_kse_generation(self.current_iteration, self.wca_per_iteration):
                self.logger.info("User cancelled hypothesis generation. Stopping.")
                self.stop_reason = "User cancelled hypothesis generation"
                break

            hypotheses = self._generate_hypotheses_for_iteration()
            if not hypotheses:
                 self.logger.warning(f"No hypotheses generated for iteration {self.current_iteration}. Stopping.")
                 self.user_confirm.show_error("Failed to generate hypotheses")
                 self.stop_reason = "Hypothesis generation failed"
                 break

            self.user_confirm.show_success(f"Generated {len(hypotheses)} hypotheses")

            # 2b. Launch experiments
            # Confirm WAA experiment execution
            experiment_ids = [h.experiment_id for h in hypotheses]
            if not self.user_confirm.confirm_waa_execution(experiment_ids):
                self.logger.info("User cancelled experiment execution. Stopping.")
                self.stop_reason = "User cancelled experiment execution"
                break

            launch_result = self.eo.launch_experiments(hypotheses)
            launched_ids = launch_result['launched']
            failed_launches = launch_result['failed']
            total_requested = launch_result['total']

            if not launched_ids:
                 self.logger.warning(f"No experiments were launched for iteration {self.current_iteration}. Stopping.")
                 self.user_confirm.show_error("Failed to launch experiments")
                 self.stop_reason = "Experiment launch failed"
                 break

            # Warn if some experiments failed to launch
            if failed_launches:
                self.logger.warning(f"Partial launch: {len(launched_ids)}/{total_requested} experiments launched")
                for failure in failed_launches:
                    self.logger.warning(f"  Failed: {failure['exp_id']} - {failure['reason']}")
                self.user_confirm.show_warning(
                    f"Only {len(launched_ids)}/{total_requested} experiments launched. "
                    f"{len(failed_launches)} failed to start."
                )

            self.user_confirm.show_success(f"Launched {len(launched_ids)}/{total_requested} experiments")

            running_experiments = set(launched_ids)
            # Store hypotheses in persistent map (survives across iterations for resumed experiments)
            for h in hypotheses:
                self.all_hypotheses[h.experiment_id] = h

            # 2c. Wait for completion & collect results (DO NOT cleanup yet)
            iteration_results = []
            while running_experiments:
                time.sleep(10)  # Check every 10 seconds
                completed_ids = self.eo.check_running_experiments()
                newly_completed = running_experiments.intersection(completed_ids)

                if newly_completed:
                     self.logger.info(f"Experiments completed: {list(newly_completed)}")
                     for exp_id in newly_completed:
                         worktree_path = self.eo.get_worktree_path(exp_id)
                         # Pass hypothesis directly to collect_result for proper metadata
                         # Use all_hypotheses which persists across iterations
                         hypothesis = self.all_hypotheses.get(exp_id)
                         if not hypothesis:
                             self.logger.warning(f"Hypothesis not found for {exp_id}, RAD will load from worktree metadata")
                         result = self.rad.collect_result(exp_id, worktree_path, hypothesis=hypothesis)
                         if result:
                             iteration_results.append(result)
                         else:
                              self.logger.error(f"Failed to collect result for {exp_id}")

                         # Store worktree for later cleanup (after PA analysis)
                         self.pending_cleanup[exp_id] = worktree_path

                     running_experiments -= newly_completed
                     self.logger.info(f"Remaining experiments in iteration: {len(running_experiments)}")

            self.all_results[self.current_iteration] = iteration_results

            # 2d. Submit successful experiments to Kaggle and get official scores
            official_scores = {}
            successful_results = [r for r in iteration_results if r.status == "SUCCESS" and r.score is not None]

            if successful_results:
                # Confirm submission (respects -y flag via skip_confirmations)
                if self.user_confirm.confirm_iteration_submissions(
                    self.current_iteration,
                    [r.experiment_id for r in successful_results]
                ):
                    self.logger.info(f"Submitting {len(successful_results)} successful experiments to Kaggle")
                    for result in successful_results:
                        submission_file = self._find_submission_file(result)
                        if submission_file:
                            if self.kim.submit_predictions(
                                submission_file,
                                f"Iter {self.current_iteration} - {result.experiment_id}"
                            ):
                                # Poll for official score
                                self.logger.info(f"Waiting for official score for {result.experiment_id}...")
                                score_result = self.kim.get_submission_score(wait_timeout=120)
                                if score_result and score_result.get("score"):
                                    official_scores[result.experiment_id] = score_result["score"]
                                    self.logger.info(f"Official score for {result.experiment_id}: {score_result['score']}")
                                else:
                                    self.logger.warning(f"Could not get official score for {result.experiment_id}")
                            else:
                                self.logger.error(f"Failed to submit {result.experiment_id}")
                        else:
                            self.logger.warning(f"No submission file found for {result.experiment_id}")
                else:
                    self.logger.info("User skipped Kaggle submissions for this iteration")

            # 2e. Performance analysis (with official scores)
            if iteration_results:
                # Confirm PA analysis
                if not self.user_confirm.confirm_pa_analysis(self.current_iteration, len(iteration_results)):
                    self.logger.info("User cancelled performance analysis. Skipping.")
                    self.user_confirm.show_warning("Skipping performance analysis for this iteration")
                    analysis_result = None
                else:
                    analysis_result = self.pa.analyze_results(
                        self.current_iteration,
                        iteration_results,
                        official_scores=official_scores
                    )
                    self.user_confirm.show_success("Performance analysis completed")
            else:
                self.logger.warning("No results to analyze for this iteration")
                analysis_result = None

            # 2f. Cleanup worktrees (after PA has finished analyzing)
            if self.pending_cleanup:
                # Safety check: ensure no experiments are pending resume before cleanup
                still_active = set(self.eo.active_processes.keys())
                safe_to_cleanup = {
                    exp_id: path for exp_id, path in self.pending_cleanup.items()
                    if exp_id not in still_active
                }

                if len(safe_to_cleanup) < len(self.pending_cleanup):
                    skipped = set(self.pending_cleanup.keys()) - set(safe_to_cleanup.keys())
                    self.logger.warning(f"Skipping cleanup for {len(skipped)} experiments still active: {skipped}")

                if safe_to_cleanup:
                    self.logger.info(f"Cleaning up {len(safe_to_cleanup)} worktrees")
                    for exp_id, worktree_path in safe_to_cleanup.items():
                        self.eo.cleanup_worktree(exp_id, worktree_path)

                self.pending_cleanup.clear()

            # 2g. Update overall best and check improvement
            if analysis_result:
                self._update_overall_best(analysis_result)

            self.current_iteration += 1
            self.logger.info(f"--- Finished Iteration {self.current_iteration - 1} ---")
            # Loop stop condition checked at start of next cycle

        # 3. Finalization
        self.logger.info("Main loop finished.")
        self._final_reporting()
        self._log_end("run_main_loop")

    def _should_stop(self) -> bool:
        """Decide whether to stop the main loop."""
        if self.stop_reason:
             self.logger.info(f"Stopping loop. Reason: {self.stop_reason}")
             return True

        if self.current_iteration >= self.max_iterations:
            self.stop_reason = f"Reached max iterations ({self.max_iterations})"
            self.logger.info(self.stop_reason)
            return True

        if self.score_threshold and self.best_score_overall and self.best_score_overall >= self.score_threshold:
            self.stop_reason = f"Achieved score threshold ({self.score_threshold}) with score {self.best_score_overall:.4f}"
            self.logger.info(self.stop_reason)
            return True

        if self.iterations_without_improvement >= self.no_improvement_threshold:
             self.stop_reason = f"No improvement in best score for {self.no_improvement_threshold} iterations."
             self.logger.info(self.stop_reason)
             return True

        # TODO: Add budget/time-based conditions

        return False

    def _generate_hypotheses_for_iteration(self) -> List[ExperimentHypothesis]:
        """Generate hypotheses for the current iteration."""
        if self.current_iteration == 0:
            return self.kse.generate_initial_hypotheses(self.competition_info, self.wca_per_iteration)
        else:
            # Pass prior analysis and all past results
            last_iteration = self.current_iteration - 1
            last_analysis = self.pa.analyze_results(last_iteration, self.all_results.get(last_iteration, []))  # Re-analyze or use saved
            all_past_results = [res for iter_res in self.all_results.values() for res in iter_res]
            return self.kse.generate_next_hypotheses(self.competition_info,
                                                      self.current_iteration,
                                                      self.wca_per_iteration,
                                                      last_analysis,
                                                      all_past_results)

    def _update_overall_best(self, analysis_result: AnalysisResult):
        """Update global best score and track iterations without improvement."""
        current_best_iter_score = analysis_result.best_score
        initial_best_score = self.best_score_overall

        if current_best_iter_score is not None:
            if self.best_score_overall is None or current_best_iter_score > self.best_score_overall:
                self.best_score_overall = current_best_iter_score
                self.best_experiment_id_overall = analysis_result.best_experiment_id
                self.iterations_without_improvement = 0  # Reset because improved
                self.logger.info(f"New overall best score: {self.best_score_overall:.4f} (Exp ID: {self.best_experiment_id_overall})")
            else:
                 # Score stayed the same or decreased
                 if initial_best_score is not None:  # Not the first iteration
                     self.iterations_without_improvement += 1
                     self.logger.info(f"Best score did not improve. Iterations without improvement: {self.iterations_without_improvement}")
        else:
             # No valid scores this iteration
             if initial_best_score is not None:  # Not the first iteration
                 self.iterations_without_improvement += 1
                 self.logger.info(f"No valid score in this iteration. Iterations without improvement: {self.iterations_without_improvement}")

    def _find_submission_file(self, result: ExperimentResult) -> Optional[str]:
        """Find the submission file path for an experiment result."""
        if result.result_files:
            for file_path in result.result_files:
                if 'submission' in file_path.lower():
                    # Convert relative path to absolute
                    absolute_path = os.path.join(self.rad.results_base_dir, file_path)
                    if os.path.exists(absolute_path):
                        return absolute_path

        # Also check worktree if pending cleanup still has the path
        if result.experiment_id in self.pending_cleanup:
            worktree_path = self.pending_cleanup[result.experiment_id]
            submission_name = f"submission_{result.experiment_id}.csv"
            worktree_submission = os.path.join(worktree_path, submission_name)
            if os.path.exists(worktree_submission):
                return worktree_submission

        return None

    def _final_reporting(self):
        """Log the final results report."""
        self.logger.info("--- Final Report ---")
        if self.best_score_overall is not None:
            self.logger.info(f"Overall Best Score: {self.best_score_overall:.4f}")
            self.logger.info(f"Best Experiment ID: {self.best_experiment_id_overall}")
            # Display details of best result (from RAD)
            best_result = self.rad.get_result(self.best_experiment_id_overall)
            if best_result:
                 self.logger.info(f"Best Result Details: {best_result}")
                 # Optionally submit here (logging only in current flow)
                 submission_file = next((f for f in best_result.result_files if 'submission' in f), None)
                 if submission_file:
                      submission_path_absolute = os.path.join(self.rad.results_base_dir, submission_file)
                      # Confirm submission to Kaggle
                      if self.user_confirm.confirm_score_submission(
                          self.best_score_overall,
                          self.best_experiment_id_overall
                      ):
                          self.logger.info(f"Submitting: {submission_path_absolute}")
                          self.kim.submit_predictions(
                              submission_path_absolute,
                              f"Final submission based on {self.best_experiment_id_overall}"
                          )
                          self.user_confirm.show_success("Submission completed")
                      else:
                          self.logger.info("User skipped final submission")
                          self.user_confirm.show_status("Submission skipped by user")
                 else:
                      self.logger.warning("Submission file not found for the best experiment.")
                      self.user_confirm.show_warning("No submission file available for best experiment")

        else:
            self.logger.info("No successful experiments were completed.")
        self.logger.info(f"Stopped due to: {self.stop_reason}")
        self.logger.info(f"Total iterations: {self.current_iteration}")
