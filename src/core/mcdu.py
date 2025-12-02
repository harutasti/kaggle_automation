import os
import shutil
import time
import json
import sys
from typing import Dict, List, Optional, Any

from .base_component import BaseComponent
from .kim import KaggleInterfaceManager
from .kse import KnowledgeStrategyEngine
from ..execution.eo import ExperimentOrchestrator
from ..analysis.rad import ResultAggregatorDatabase
from ..analysis.pa import PerformanceAnalyzer
from ..utils.user_interaction import UserConfirmation
from ..data_models import (
    CompetitionInfo, ExperimentHypothesis, ExperimentResult, AnalysisResult,
    ExperimentDecision, ExperimentDecisionType, ContinuationHypothesis
)

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
            skip_confirmations=self.config.get("skip_confirmations", False)
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
        self.iteration_analysis_results: Dict[int, AnalysisResult] = {}
        self.iteration_official_scores: Dict[int, Dict[str, float]] = {}

        # Persistent evolution state - tracks active experiments across iterations
        self.persistent_experiments: Dict[str, str] = {}  # {exp_id: worktree_path} for active experiments
        self.continuation_map: Dict[str, str] = {}  # {continuation_id: original_exp_id} for lineage tracking
        self.all_continuation_hypotheses: Dict[str, ContinuationHypothesis] = {}  # {continuation_id: hypothesis}

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

        # Copy crawler data to hypotheses for Codex/KSE context
        crawler_src = os.path.join("kaggle_competitions", self.kim.competition_name)
        hypotheses_crawler_data = os.path.join(experiment_run_dir, "hypotheses", "crawler_data")
        if os.path.exists(crawler_src):
            try:
                shutil.copytree(crawler_src, hypotheses_crawler_data, dirs_exist_ok=True)
                self.logger.info("Copied crawler data to hypotheses/ for KSE access")
            except Exception as copy_error:
                self.logger.warning(f"Failed to copy crawler data to hypotheses: {copy_error}")

        # 2. Main loop with persistent evolution
        while not self._should_stop():
            self.logger.info(f"--- Starting Iteration {self.current_iteration} ---")
            self.user_confirm.show_status(f"Starting Iteration {self.current_iteration}", "bold cyan")

            # Track variables for this iteration
            hypotheses = []
            continuations = []
            running_experiments = set()
            iteration_results = []
            official_scores = {}

            if self.current_iteration == 0:
                # ================== ITERATION 0: Fresh Start ==================
                # 2a. Generate initial hypotheses
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

                self.user_confirm.show_success(f"Generated {len(hypotheses)} new hypotheses")

                # 2b. Launch experiments
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

                if failed_launches:
                    self.logger.warning(f"Partial launch: {len(launched_ids)}/{total_requested} experiments launched")
                    for failure in failed_launches:
                        self.logger.warning(f"  Failed: {failure['exp_id']} - {failure['reason']}")

                self.user_confirm.show_success(f"Launched {len(launched_ids)}/{total_requested} experiments")

                running_experiments = set(launched_ids)

                # Store hypotheses and track persistent experiments
                for h in hypotheses:
                    self.all_hypotheses[h.experiment_id] = h
                    worktree_path = self.eo.get_worktree_path(h.experiment_id)
                    if worktree_path:
                        self.persistent_experiments[h.experiment_id] = worktree_path

            else:
                # ================== ITERATION > 0: Evolution Mode ==================
                # Get PA's evolution decisions from previous iteration analysis
                last_iteration = self.current_iteration - 1
                last_analysis = self.iteration_analysis_results.get(last_iteration)
                prior_official_scores = self.iteration_official_scores.get(last_iteration, {})
                prior_results = self.all_results.get(last_iteration, [])

                if not last_analysis or not last_analysis.experiment_decisions:
                    self.logger.warning("No evolution decisions available. Running PA with evolution decisions...")
                    # Re-run PA with evolution decisions
                    experiment_ids_for_decisions = list(self.persistent_experiments.keys())
                    last_analysis = self.pa.analyze_with_evolution_decisions(
                        iteration=last_iteration,
                        results=prior_results,
                        experiment_ids=experiment_ids_for_decisions,
                        official_scores=prior_official_scores
                    )
                    if last_analysis:
                        self.iteration_analysis_results[last_iteration] = last_analysis

                if not last_analysis or not last_analysis.experiment_decisions:
                    self.logger.error("Failed to get evolution decisions from PA. Stopping.")
                    self.stop_reason = "Evolution decisions failed"
                    break

                # 2a-evolution. Handle evolution decisions
                continue_decisions, terminate_decisions = self._handle_evolution_decisions(
                    last_analysis, prior_results, prior_official_scores
                )

                # 2b-evolution. Generate continuation hypotheses and new hypotheses
                if not self.user_confirm.confirm_kse_generation(
                    self.current_iteration,
                    len(continue_decisions) + len(terminate_decisions)
                ):
                    self.logger.info("User cancelled hypothesis generation. Stopping.")
                    self.stop_reason = "User cancelled hypothesis generation"
                    break

                continuations, hypotheses = self._generate_evolution_hypotheses_for_iteration(
                    continue_decisions, terminate_decisions, prior_results, prior_official_scores
                )

                if not continuations and not hypotheses:
                    self.logger.warning("No experiments to run in this iteration. Stopping.")
                    self.stop_reason = "No experiments generated"
                    break

                self.user_confirm.show_success(
                    f"Generated {len(continuations)} continuations and {len(hypotheses)} new hypotheses"
                )

                # 2c-evolution. Launch evolution experiments
                all_exp_ids = [c.continuation_id for c in continuations] + [h.experiment_id for h in hypotheses]
                if not self.user_confirm.confirm_waa_execution(all_exp_ids):
                    self.logger.info("User cancelled experiment execution. Stopping.")
                    self.stop_reason = "User cancelled experiment execution"
                    break

                launch_result = self._launch_evolution_experiments(continuations, hypotheses)
                launched_ids = launch_result['launched']
                failed_launches = launch_result['failed']
                total_requested = launch_result['total']

                if not launched_ids:
                    self.logger.warning(f"No experiments were launched for iteration {self.current_iteration}. Stopping.")
                    self.user_confirm.show_error("Failed to launch experiments")
                    self.stop_reason = "Experiment launch failed"
                    break

                if failed_launches:
                    self.logger.warning(f"Partial launch: {len(launched_ids)}/{total_requested} experiments launched")

                self.user_confirm.show_success(f"Launched {len(launched_ids)}/{total_requested} experiments")

                running_experiments = set(launched_ids)

                # Store new hypotheses
                for h in hypotheses:
                    self.all_hypotheses[h.experiment_id] = h

            # ================== Common: Wait for completion ==================
            # 2d. Wait for completion & collect results
            while running_experiments:
                time.sleep(10)  # Check every 10 seconds
                completed_ids = self.eo.check_running_experiments()
                newly_completed = running_experiments.intersection(completed_ids)

                if newly_completed:
                    self.logger.info(f"Experiments completed: {list(newly_completed)}")
                    for exp_id in newly_completed:
                        worktree_path = self.eo.get_worktree_path(exp_id)

                        # Get hypothesis (check all sources)
                        hypothesis = self.all_hypotheses.get(exp_id)
                        continuation = self.all_continuation_hypotheses.get(exp_id)

                        if not hypothesis and not continuation:
                            self.logger.warning(f"Hypothesis not found for {exp_id}, RAD will load from worktree metadata")

                        result = self.rad.collect_result(exp_id, worktree_path, hypothesis=hypothesis)
                        if result:
                            iteration_results.append(result)
                        else:
                            self.logger.error(f"Failed to collect result for {exp_id}")

                        # Update persistent experiments map (worktree stays active)
                        if worktree_path:
                            self.persistent_experiments[exp_id] = worktree_path

                    running_experiments -= newly_completed
                    self.logger.info(f"Remaining experiments in iteration: {len(running_experiments)}")

            self.all_results[self.current_iteration] = iteration_results

            # ================== Common: Submit to Kaggle ==================
            # 2e. Submit successful experiments to Kaggle and get official scores
            successful_results = [r for r in iteration_results if r.status == "SUCCESS" and r.score is not None]

            if successful_results:
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

            # ================== Common: Performance Analysis ==================
            # 2f. Performance analysis with evolution decisions
            self._log_waa_results_to_terminal(iteration_results, official_scores)

            analysis_result = None
            if iteration_results:
                if not self.user_confirm.confirm_pa_analysis(self.current_iteration, len(iteration_results)):
                    self.logger.info("User cancelled performance analysis. Skipping.")
                    self.user_confirm.show_warning("Skipping performance analysis for this iteration")
                else:
                    # Use evolution decisions mode for PA
                    experiment_ids_for_decisions = list(self.persistent_experiments.keys())
                    analysis_result = self.pa.analyze_with_evolution_decisions(
                        iteration=self.current_iteration,
                        results=iteration_results,
                        experiment_ids=experiment_ids_for_decisions,
                        official_scores=official_scores
                    )

                    if analysis_result:
                        self.iteration_analysis_results[self.current_iteration] = analysis_result
                        self.iteration_official_scores[self.current_iteration] = official_scores
                        self.user_confirm.show_success(
                            f"Performance analysis completed: "
                            f"{analysis_result.experiments_to_continue} CONTINUE, "
                            f"{analysis_result.experiments_to_terminate} TERMINATE"
                        )
            else:
                self.logger.warning("No results to analyze for this iteration")

            # NOTE: No worktree cleanup in evolution mode - worktrees persist until PA decides TERMINATE

            # 2g. Update overall best and check improvement
            if analysis_result:
                self._update_overall_best(analysis_result)

            self.current_iteration += 1
            self.logger.info(f"--- Finished Iteration {self.current_iteration - 1} ---")
            self.logger.info(f"Active persistent experiments: {len(self.persistent_experiments)}")

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
            last_iteration = self.current_iteration - 1
            # Use stored analysis and official scores from the prior iteration if available
            last_analysis = self.iteration_analysis_results.get(last_iteration)
            if last_analysis is None:
                last_analysis = self.pa.analyze_results(
                    last_iteration,
                    self.all_results.get(last_iteration, []),
                    official_scores=self.iteration_official_scores.get(last_iteration, {})
                )
                if last_analysis:
                    self.iteration_analysis_results[last_iteration] = last_analysis

            all_past_results = [res for iter_res in self.all_results.values() for res in iter_res]
            prior_official_scores = self.iteration_official_scores.get(last_iteration, {})
            return self.kse.generate_next_hypotheses(self.competition_info,
                                                      self.current_iteration,
                                                      self.wca_per_iteration,
                                                      last_analysis,
                                                      all_past_results,
                                                      official_scores=prior_official_scores)

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

    def _log_waa_results_to_terminal(self, iteration_results: List[ExperimentResult],
                                     official_scores: Dict[str, float]) -> None:
        """Print a compact summary of WAA results (including official scores) to the terminal."""
        if not iteration_results:
            self.logger.info("No WAA results to display for this iteration.")
            return

        self.logger.info("WAA Results Summary (cv vs official):")
        for res in iteration_results:
            official = official_scores.get(res.experiment_id)
            official_str = f"{official:.4f}" if official is not None else "N/A"
            cv_str = f"{res.score:.4f}" if res.score is not None else "N/A"
            self.logger.info(f"  - {res.experiment_id}: strategy={res.strategy_name}, cv_score={cv_str}, official_score={official_str}, status={res.status}")

    def _find_submission_file(self, result: ExperimentResult) -> Optional[str]:
        """Find the submission file path for an experiment result."""
        if result.result_files:
            for file_path in result.result_files:
                if 'submission' in file_path.lower():
                    # Convert relative path to absolute
                    absolute_path = os.path.join(self.rad.results_base_dir, file_path)
                    if os.path.exists(absolute_path):
                        return absolute_path

        # Check persistent experiments (evolution mode)
        if result.experiment_id in self.persistent_experiments:
            worktree_path = self.persistent_experiments[result.experiment_id]
            # Check for submission file with experiment_id
            submission_name = f"submission_{result.experiment_id}.csv"
            worktree_submission = os.path.join(worktree_path, submission_name)
            if os.path.exists(worktree_submission):
                return worktree_submission

            # Also check for continuation-style submission
            original_exp_id = self.continuation_map.get(result.experiment_id)
            if original_exp_id:
                # For continuations, the submission might use the original experiment ID
                original_submission = os.path.join(worktree_path, f"submission_{original_exp_id}.csv")
                if os.path.exists(original_submission):
                    return original_submission

            # Generic submission.csv fallback
            generic_submission = os.path.join(worktree_path, "submission.csv")
            if os.path.exists(generic_submission):
                return generic_submission

        return None

    def _handle_evolution_decisions(self, analysis_result: AnalysisResult,
                                     iteration_results: List[ExperimentResult],
                                     official_scores: Dict[str, float]) -> tuple:
        """
        Handle PA's evolution decisions: archive terminated experiments, prepare continuations.

        Returns:
            Tuple of (continue_decisions, terminate_decisions)
        """
        if not analysis_result.experiment_decisions:
            self.logger.warning("No evolution decisions found in analysis result")
            return [], []

        continue_decisions = []
        terminate_decisions = []

        for decision in analysis_result.experiment_decisions:
            if decision.decision == ExperimentDecisionType.CONTINUE:
                continue_decisions.append(decision)
                self.logger.info(
                    f"CONTINUE: {decision.experiment_id} "
                    f"(confidence={decision.confidence:.2f}, ceiling={decision.potential_ceiling})"
                )
            else:  # TERMINATE
                terminate_decisions.append(decision)
                self.logger.info(
                    f"TERMINATE: {decision.experiment_id} "
                    f"(reason={decision.termination_reason})"
                )

                # Archive the terminated worktree
                worktree_path = self.persistent_experiments.get(decision.experiment_id)
                if worktree_path and os.path.exists(worktree_path):
                    archived_path = self.eo.archive_worktree(decision.experiment_id, worktree_path)
                    if archived_path:
                        self.logger.info(f"Archived {decision.experiment_id} to {archived_path}")
                    else:
                        self.logger.warning(f"Failed to archive {decision.experiment_id}")
                    # Remove from persistent tracking
                    del self.persistent_experiments[decision.experiment_id]
                else:
                    self.logger.warning(f"No worktree found for terminated experiment {decision.experiment_id}")

        self.logger.info(
            f"Evolution decisions: {len(continue_decisions)} CONTINUE, "
            f"{len(terminate_decisions)} TERMINATE, "
            f"{len(terminate_decisions)} new slots available"
        )

        return continue_decisions, terminate_decisions

    def _generate_evolution_hypotheses_for_iteration(
        self,
        continue_decisions: List[ExperimentDecision],
        terminate_decisions: List[ExperimentDecision],
        iteration_results: List[ExperimentResult],
        official_scores: Dict[str, float]
    ) -> tuple:
        """
        Generate continuation hypotheses for CONTINUE decisions and new hypotheses for freed slots.

        Returns:
            Tuple of (continuation_hypotheses, new_hypotheses)
        """
        # Use KSE's evolution hypothesis generation
        continuations, new_hypotheses = self.kse.generate_evolution_hypotheses(
            iteration=self.current_iteration,
            continue_decisions=continue_decisions,
            terminate_decisions=terminate_decisions,
            competition_info=self.competition_info,
            persistent_experiments=self.persistent_experiments,
            iteration_results=iteration_results,
            official_scores=official_scores
        )

        self.logger.info(
            f"Generated {len(continuations)} continuation hypotheses and "
            f"{len(new_hypotheses)} new hypotheses"
        )

        # Track continuation hypotheses
        for cont in continuations:
            self.all_continuation_hypotheses[cont.continuation_id] = cont
            self.continuation_map[cont.continuation_id] = cont.experiment_id

        return continuations, new_hypotheses

    def _launch_evolution_experiments(
        self,
        continuations: List[ContinuationHypothesis],
        new_hypotheses: List[ExperimentHypothesis]
    ) -> Dict[str, Any]:
        """
        Launch both continuation experiments and new experiments.

        Returns:
            Combined launch result dict with 'launched', 'failed', 'total' keys
        """
        all_launched = []
        all_failed = []

        # Launch continuations first (resume existing worktrees)
        if continuations:
            cont_result = self.eo.launch_continuation_experiments(continuations)
            all_launched.extend(cont_result.get('launched', []))
            all_failed.extend(cont_result.get('failed', []))

            # Update persistent experiments with continuation IDs
            for cont in continuations:
                if cont.continuation_id in cont_result.get('launched', []):
                    # Map continuation_id to the worktree path (same worktree reused)
                    self.persistent_experiments[cont.continuation_id] = cont.worktree_path

        # Launch new hypotheses (create fresh worktrees)
        if new_hypotheses:
            new_result = self.eo.launch_experiments(new_hypotheses)
            all_launched.extend(new_result.get('launched', []))
            all_failed.extend(new_result.get('failed', []))

            # Track new experiments in persistent map
            for h in new_hypotheses:
                if h.experiment_id in new_result.get('launched', []):
                    worktree_path = self.eo.get_worktree_path(h.experiment_id)
                    if worktree_path:
                        self.persistent_experiments[h.experiment_id] = worktree_path

        return {
            'launched': all_launched,
            'failed': all_failed,
            'total': len(continuations) + len(new_hypotheses)
        }

    def _final_reporting(self):
        """Log the final results report."""
        self.logger.info("--- Final Report ---")

        # Evolution summary
        self.logger.info(f"Persistent experiments remaining: {len(self.persistent_experiments)}")
        self.logger.info(f"Continuation experiments run: {len(self.continuation_map)}")

        # Log experiment lineage
        if self.continuation_map:
            self.logger.info("Continuation lineage:")
            for cont_id, orig_id in self.continuation_map.items():
                self.logger.info(f"  {orig_id} -> {cont_id}")

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
