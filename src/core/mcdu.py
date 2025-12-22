import os
import shutil
import time
import json
import sys
import datetime
from typing import Dict, List, Optional, Any

from .base_component import BaseComponent
from .kim import KaggleInterfaceManager
from .kse import KnowledgeStrategyEngine
from ..execution.eo import ExperimentOrchestrator
from ..analysis.rad import ResultAggregatorDatabase
from ..analysis.pa import PerformanceAnalyzer
from ..utils.user_interaction import UserConfirmation
from ..execution.session_manager import SessionStatus
from ..execution.run_state import (
    RunStateManager,
    EVENT_RUN_START,
    EVENT_INIT_COMPLETE,
    EVENT_ITERATION_START,
    EVENT_KSE_COMPLETE,
    EVENT_WAA_LAUNCHED,
    EVENT_WAA_COMPLETED,
    EVENT_KAGGLE_SUBMISSION_COMPLETE,
    EVENT_KAGGLE_SCORES_COLLECTED,
    EVENT_PA_COMPLETE,
    EVENT_ITERATION_COMPLETE,
    EVENT_EXPERIMENT_TERMINATED,
)
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
        # Run-state manager (append-only) for resumable runs
        experiment_run_dir = self.config.get("experiment_run_dir", self.config.get("experiments_base_dir", "./experiments"))
        self.run_state_manager = RunStateManager(experiment_run_dir, logger=self.logger)
        self.run_state = self.run_state_manager.get_state()
        self.resume_mode = bool(self.config.get("resume_mode", False)) or bool(self.config.get("resume", False))

        self.eo = ExperimentOrchestrator(self.config, run_state_manager=self.run_state_manager)
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

        # Restore prior state if resuming
        if self.resume_mode:
            self._restore_from_run_state()

        # Log run start once
        if not self.run_state.run_started:
            self.run_state_manager.append_event(EVENT_RUN_START)

        # 1. Initialization: fetch competition info & download data
        competition_name = self.config.get("kaggle_competition_name", "unknown")
        init_completed = self.run_state.init_complete and self.competition_info is not None

        if init_completed:
            self.logger.info("Resume mode: initialization already complete; skipping fetch/download.")
        else:
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

            init_payload = {
                "competition_info": self._serialize_competition_info(self.competition_info),
                "dataset_placeholders": dataset_placeholders or {}
            }
            self.run_state_manager.append_event(EVENT_INIT_COMPLETE, payload=init_payload)

        # 2. Main loop with persistent evolution
        while not self._should_stop():
            self.logger.info(f"--- Starting Iteration {self.current_iteration} ---")
            self.user_confirm.show_status(f"Starting Iteration {self.current_iteration}", "bold cyan")

            # Track variables for this iteration
            hypotheses = []
            continuations = []
            running_experiments = set()
            pending_resume = set()
            iteration_results = []
            official_scores = {}

            iter_state = self.run_state.get_iteration(self.current_iteration)
            if not iter_state.started:
                self.run_state_manager.append_event(EVENT_ITERATION_START, iteration=self.current_iteration)

            if self.resume_mode and iter_state.waa_completed:
                iteration_results = self.rad.get_results_by_iteration(self.current_iteration)
                # Backfill any missing results for completed experiments
                for exp_id in iter_state.waa_completed.keys():
                    if any(r.experiment_id == exp_id for r in iteration_results):
                        continue
                    worktree_path = self.eo.get_worktree_path(exp_id)
                    if not worktree_path:
                        continue
                    hypothesis = self.all_hypotheses.get(exp_id)
                    result = self.rad.collect_result(exp_id, worktree_path, hypothesis=hypothesis)
                    if result:
                        iteration_results.append(result)

            if self.current_iteration == 0:
                # ================== ITERATION 0: Fresh Start ==================
                # 2a. Generate initial hypotheses
                kse_ready = iter_state.kse_done
                if kse_ready:
                    continuations, hypotheses = self._load_hypotheses_from_state(iter_state)
                    if not hypotheses or not self._tasks_valid_for_iteration(hypotheses, continuations):
                        self.logger.warning("KSE tasks missing/corrupt; regenerating hypotheses.")
                        kse_ready = False

                if not kse_ready:
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
                    payload = {"hypotheses": [self._hypothesis_to_dict(h) for h in hypotheses]}
                    self.run_state_manager.append_event(
                        EVENT_KSE_COMPLETE,
                        iteration=self.current_iteration,
                        payload=payload
                    )

                # 2b. Launch or resume experiments
                experiment_ids = [h.experiment_id for h in hypotheses]
                waa_already_launched = iter_state.waa_launched and kse_ready
                if waa_already_launched:
                    incomplete_ids = [exp_id for exp_id in experiment_ids if exp_id not in iter_state.waa_completed]
                    if incomplete_ids:
                        if not self.user_confirm.confirm_waa_execution(incomplete_ids):
                            self.logger.info("User cancelled experiment execution. Stopping.")
                            self.stop_reason = "User cancelled experiment execution"
                            break
                    running_experiments, pending_resume = self._resume_or_restart_iteration_experiments(
                        iter_state, hypotheses, continuations, iteration_results
                    )
                else:
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
                    experiments_payload = []
                    for exp_id in launched_ids:
                        worktree_path = self.eo.get_worktree_path(exp_id) or ""
                        experiments_payload.append({
                            "experiment_id": exp_id,
                            "worktree_path": worktree_path,
                            "kind": "new"
                        })
                    if experiments_payload:
                        self.run_state_manager.append_event(
                            EVENT_WAA_LAUNCHED,
                            iteration=self.current_iteration,
                            payload={"experiments": experiments_payload}
                        )

                # Store hypotheses and track persistent experiments
                for h in hypotheses:
                    self.all_hypotheses[h.experiment_id] = h
                    worktree_path = self.eo.get_worktree_path(h.experiment_id)
                    if worktree_path:
                        self.persistent_experiments[h.experiment_id] = worktree_path

            else:
                # ================== ITERATION > 0: Evolution Mode ==================
                kse_ready = iter_state.kse_done
                if kse_ready:
                    continuations, hypotheses = self._load_hypotheses_from_state(iter_state)
                    if not self._tasks_valid_for_iteration(hypotheses, continuations):
                        self.logger.warning("KSE tasks missing/corrupt; regenerating hypotheses.")
                        kse_ready = False

                if not kse_ready:
                    # Get PA's evolution decisions from previous iteration analysis
                    last_iteration = self.current_iteration - 1
                    last_analysis = self.iteration_analysis_results.get(last_iteration)
                    prior_official_scores = self.iteration_official_scores.get(last_iteration, {})
                    prior_results = self.all_results.get(last_iteration, [])

                    if not last_analysis or not last_analysis.experiment_decisions:
                        self.logger.warning("No evolution decisions available. Running PA with evolution decisions...")
                        if not self.user_confirm.confirm_pa_analysis(last_iteration, len(prior_results)):
                            self.logger.info("User cancelled performance analysis. Stopping.")
                            self.stop_reason = "User cancelled performance analysis"
                            break
                        # Re-run PA with evolution decisions
                        # NOTE: Do not pass experiment_ids - let PA derive them from results
                        # to ensure consistency between prompt IDs and validation IDs
                        last_analysis = self.pa.analyze_with_evolution_decisions(
                            iteration=last_iteration,
                            results=prior_results,
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
                        last_analysis, prior_results, prior_official_scores
                    )

                    if not continuations and not hypotheses:
                        self.logger.warning("No experiments to run in this iteration. Stopping.")
                        self.stop_reason = "No experiments generated"
                        break

                    self.user_confirm.show_success(
                        f"Generated {len(continuations)} continuations and {len(hypotheses)} new hypotheses"
                    )

                    payload = {
                        "hypotheses": [self._continuation_to_dict(c) for c in continuations]
                        + [self._hypothesis_to_dict(h) for h in hypotheses]
                    }
                    self.run_state_manager.append_event(
                        EVENT_KSE_COMPLETE,
                        iteration=self.current_iteration,
                        payload=payload
                    )

                # 2c-evolution. Launch or resume experiments
                all_exp_ids = [c.continuation_id for c in continuations] + [h.experiment_id for h in hypotheses]
                waa_already_launched = iter_state.waa_launched and kse_ready
                if waa_already_launched:
                    incomplete_ids = [exp_id for exp_id in all_exp_ids if exp_id not in iter_state.waa_completed]
                    if incomplete_ids:
                        if not self.user_confirm.confirm_waa_execution(incomplete_ids):
                            self.logger.info("User cancelled experiment execution. Stopping.")
                            self.stop_reason = "User cancelled experiment execution"
                            break
                    running_experiments, pending_resume = self._resume_or_restart_iteration_experiments(
                        iter_state, hypotheses, continuations, iteration_results
                    )
                else:
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

                    experiments_payload = []
                    for cont in continuations:
                        if cont.continuation_id in launched_ids:
                            worktree_path = self.eo.get_worktree_path(cont.continuation_id) or cont.worktree_path
                            experiments_payload.append({
                                "experiment_id": cont.continuation_id,
                                "worktree_path": worktree_path,
                                "kind": "continuation"
                            })
                    for h in hypotheses:
                        if h.experiment_id in launched_ids:
                            worktree_path = self.eo.get_worktree_path(h.experiment_id) or ""
                            experiments_payload.append({
                                "experiment_id": h.experiment_id,
                                "worktree_path": worktree_path,
                                "kind": "new"
                            })
                    if experiments_payload:
                        self.run_state_manager.append_event(
                            EVENT_WAA_LAUNCHED,
                            iteration=self.current_iteration,
                            payload={"experiments": experiments_payload}
                        )

                # Store new hypotheses
                for h in hypotheses:
                    self.all_hypotheses[h.experiment_id] = h

            # ================== Common: Wait for completion ==================
            # 2d. Wait for completion & collect results
            if self.config.get("simulation_mode", False):
                poll_interval_seconds = 1
            else:
                # Keep this configurable since EO's resource monitor is driven by this poll loop.
                poll_interval_seconds = int(self.config.get("resource_monitor_interval_seconds", 10))
                poll_interval_seconds = max(1, poll_interval_seconds)
            while running_experiments or pending_resume:
                time.sleep(poll_interval_seconds)
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
                            payload = {
                                "experiment_id": exp_id,
                                "status": result.status,
                                "score": result.score,
                            }
                            self.run_state_manager.append_event(
                                EVENT_WAA_COMPLETED,
                                iteration=self.current_iteration,
                                payload=payload
                            )
                        else:
                            self.logger.error(f"Failed to collect result for {exp_id}")

                        # Update persistent experiments map (worktree stays active)
                        if worktree_path:
                            self.persistent_experiments[exp_id] = worktree_path

                    running_experiments -= newly_completed
                    self.logger.info(f"Remaining experiments in iteration: {len(running_experiments)}")

                # Handle pending resumes (no active process)
                if pending_resume:
                    for exp_id in list(pending_resume):
                        worktree_path = self.eo.get_worktree_path(exp_id)
                        if not worktree_path:
                            pending_resume.discard(exp_id)
                            continue

                        done_path = os.path.join(worktree_path, f"DONE_{exp_id}")
                        done_status = None
                        if os.path.exists(done_path):
                            try:
                                with open(done_path, "r", encoding="utf-8") as f:
                                    done_status = f.read().strip()
                            except Exception:
                                done_status = None

                        status_entry = None
                        try:
                            status_entry = self.eo.session_manager.read_current_status(worktree_path)
                        except Exception:
                            status_entry = None

                        status_value = status_entry.status.value if status_entry else None
                        done_success = done_status is not None and done_status.startswith("SUCCESS")
                        done_failure = done_status is not None and not done_success
                        status_complete = status_value == SessionStatus.COMPLETE.value
                        status_error = status_value == SessionStatus.ERROR.value
                        status_running = status_value == SessionStatus.RUNNING.value

                        if done_success or status_complete:
                            self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                            pending_resume.discard(exp_id)
                            continue

                        # If no Codex session remains, restart from scratch when possible
                        if not self.eo.has_codex_session(exp_id, worktree_path):
                            pending_resume.discard(exp_id)
                            continuation = self.all_continuation_hypotheses.get(exp_id)
                            hypothesis = self.all_hypotheses.get(exp_id)
                            if continuation:
                                cont_result = self.eo.launch_continuation_experiments([continuation], total_waas=1)
                                if continuation.continuation_id in cont_result.get("launched", []):
                                    running_experiments.add(continuation.continuation_id)
                                    self.run_state_manager.append_event(
                                        EVENT_WAA_LAUNCHED,
                                        iteration=self.current_iteration,
                                        payload={"experiments": [{
                                            "experiment_id": continuation.continuation_id,
                                            "worktree_path": self.eo.get_worktree_path(continuation.continuation_id) or continuation.worktree_path,
                                            "kind": "continuation"
                                        }]}
                                    )
                            elif hypothesis:
                                new_result = self.eo.launch_experiments([hypothesis], total_waas=1)
                                if hypothesis.experiment_id in new_result.get("launched", []):
                                    running_experiments.add(hypothesis.experiment_id)
                                    self.run_state_manager.append_event(
                                        EVENT_WAA_LAUNCHED,
                                        iteration=self.current_iteration,
                                        payload={"experiments": [{
                                            "experiment_id": hypothesis.experiment_id,
                                            "worktree_path": self.eo.get_worktree_path(hypothesis.experiment_id) or "",
                                            "kind": "new"
                                        }]}
                                    )
                            continue

                        if done_failure or status_error:
                            if self.eo.can_attempt_resume(exp_id):
                                resumed = self.eo.resume_experiment(exp_id, worktree_path, reason="pending_error")
                                if resumed:
                                    status_entry = self.eo.session_manager.read_current_status(worktree_path)
                                    status_value = status_entry.status.value if status_entry else None
                                    done_success = False
                                    if os.path.exists(done_path):
                                        with open(done_path, "r", encoding="utf-8") as f:
                                            done_success = f.read().strip().startswith("SUCCESS")
                                    if done_success or status_value == SessionStatus.COMPLETE.value:
                                        self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                                        pending_resume.discard(exp_id)
                                else:
                                    if not self.eo.can_attempt_resume(exp_id):
                                        if not os.path.exists(done_path):
                                            with open(done_path, "w", encoding="utf-8") as f:
                                                f.write("RESUME_FAILURE")
                                        self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                                        pending_resume.discard(exp_id)
                            else:
                                if not os.path.exists(done_path):
                                    with open(done_path, "w", encoding="utf-8") as f:
                                        f.write("RESUME_FAILURE")
                                self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                                pending_resume.discard(exp_id)
                            continue

                        if status_running:
                            if self.eo.is_training_complete(exp_id, worktree_path):
                                if self.eo.can_attempt_resume(exp_id):
                                    resumed = self.eo.resume_experiment(exp_id, worktree_path, reason="pending_running")
                                    if resumed:
                                        status_entry = self.eo.session_manager.read_current_status(worktree_path)
                                        status_value = status_entry.status.value if status_entry else None
                                        done_success = False
                                        if os.path.exists(done_path):
                                            with open(done_path, "r", encoding="utf-8") as f:
                                                done_success = f.read().strip().startswith("SUCCESS")
                                        if done_success or status_value == SessionStatus.COMPLETE.value:
                                            self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                                            pending_resume.discard(exp_id)
                            continue

                        # Default: if training appears complete, attempt resume
                        if self.eo.is_training_complete(exp_id, worktree_path) and self.eo.can_attempt_resume(exp_id):
                            resumed = self.eo.resume_experiment(exp_id, worktree_path, reason="pending_default")
                            if resumed:
                                status_entry = self.eo.session_manager.read_current_status(worktree_path)
                                status_value = status_entry.status.value if status_entry else None
                                done_success = False
                                if os.path.exists(done_path):
                                    with open(done_path, "r", encoding="utf-8") as f:
                                        done_success = f.read().strip().startswith("SUCCESS")
                                if done_success or status_value == SessionStatus.COMPLETE.value:
                                    self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                                    pending_resume.discard(exp_id)

            self.all_results[self.current_iteration] = iteration_results

            # ================== Common: Submit to Kaggle ==================
            # 2e. Submit successful experiments to Kaggle and get official scores
            successful_results = [r for r in iteration_results if r.status == "SUCCESS" and r.score is not None]

            # Dry-run (simulation_mode) must not submit artifacts to Kaggle.
            if self.config.get("simulation_mode", False):
                if successful_results:
                    self.logger.info("Dry-run: skipping Kaggle submissions for this iteration")
                # Mark Kaggle steps as complete in dry-run
                self.run_state_manager.append_event(
                    EVENT_KAGGLE_SUBMISSION_COMPLETE,
                    iteration=self.current_iteration,
                    payload={"submitted_refs": {}}
                )
                self.run_state_manager.append_event(
                    EVENT_KAGGLE_SCORES_COLLECTED,
                    iteration=self.current_iteration,
                    payload={"official_scores": {}}
                )
            else:
                if not successful_results and not iter_state.kaggle_scores_collected:
                    # Nothing to submit; mark Kaggle steps as complete.
                    self.run_state_manager.append_event(
                        EVENT_KAGGLE_SUBMISSION_COMPLETE,
                        iteration=self.current_iteration,
                        payload={"submitted_refs": {}}
                    )
                    self.run_state_manager.append_event(
                        EVENT_KAGGLE_SCORES_COLLECTED,
                        iteration=self.current_iteration,
                        payload={"official_scores": {}}
                    )
                elif iter_state.kaggle_scores_collected:
                    official_scores = dict(iter_state.official_scores)
                    self.logger.info("Resume: official scores already collected; skipping Kaggle polling.")
                else:
                    submitted_refs: Dict[str, int] = {}
                    if iter_state.kaggle_submitted and iter_state.submitted_refs:
                        submitted_refs = dict(iter_state.submitted_refs)
                        self.logger.info("Resume: reusing prior Kaggle submission refs.")
                    elif successful_results:
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
                                        if self.kim.last_submission_ref is not None:
                                            submitted_refs[result.experiment_id] = int(self.kim.last_submission_ref)
                                        else:
                                            self.logger.warning(
                                                f"Submission succeeded for {result.experiment_id} but no ref was captured; "
                                                "skipping score polling for this submission."
                                            )
                                    else:
                                        self.logger.error(f"Failed to submit {result.experiment_id}")
                                else:
                                    self.logger.warning(f"No submission file found for {result.experiment_id}")
                        else:
                            self.logger.info("User cancelled Kaggle submissions. Stopping.")
                            self.stop_reason = "User cancelled Kaggle submissions"
                            break

                    if submitted_refs:
                        self.run_state_manager.append_event(
                            EVENT_KAGGLE_SUBMISSION_COMPLETE,
                            iteration=self.current_iteration,
                            payload={"submitted_refs": submitted_refs}
                        )

                        wait_timeout = int(self.config.get("kaggle_score_wait_timeout_seconds", 300))
                        poll_interval = self.config.get("kaggle_score_poll_interval_seconds", 10)
                        try:
                            poll_interval = float(poll_interval)
                        except Exception:
                            poll_interval = 10.0
                        if poll_interval <= 0:
                            poll_interval = 10.0

                        self.logger.info(
                            f"Polling Kaggle for official scores (count={len(submitted_refs)}, "
                            f"timeout={wait_timeout}s, interval={poll_interval}s)..."
                        )

                        start = time.time()
                        pending: Dict[str, int] = dict(submitted_refs)
                        while pending and (time.time() - start) < wait_timeout:
                            for exp_id, ref in list(pending.items()):
                                score_result = self.kim.get_submission_score_once(submission_ref=ref)
                                if score_result and score_result.get("score") is not None:
                                    official_scores[exp_id] = score_result["score"]
                                    self.logger.info(f"Official score for {exp_id}: {score_result['score']}")
                                    pending.pop(exp_id, None)

                            if pending:
                                time.sleep(poll_interval)

                        for exp_id, ref in pending.items():
                            self.logger.warning(f"Could not get official score for {exp_id} (ref={ref})")

                        self.run_state_manager.append_event(
                            EVENT_KAGGLE_SCORES_COLLECTED,
                            iteration=self.current_iteration,
                            payload={"official_scores": official_scores}
                        )

            # ================== Common: Performance Analysis ==================
            # 2f. Performance analysis with evolution decisions
            self._log_waa_results_to_terminal(iteration_results, official_scores)

            analysis_result = None
            if iter_state.pa_done and iter_state.analysis_result:
                analysis_result = self._analysis_from_dict(iter_state.analysis_result, self.current_iteration)
                self.iteration_analysis_results[self.current_iteration] = analysis_result
                self.iteration_official_scores[self.current_iteration] = official_scores
                self.logger.info("Resume: PA analysis already completed; skipping.")
            else:
                if iteration_results:
                    if not self.user_confirm.confirm_pa_analysis(self.current_iteration, len(iteration_results)):
                        self.logger.info("User cancelled performance analysis. Stopping.")
                        self.stop_reason = "User cancelled performance analysis"
                        break
                    else:
                        # Use evolution decisions mode for PA
                        # NOTE: Do not pass experiment_ids - let PA derive them from results
                        # to ensure consistency between prompt IDs and validation IDs
                        analysis_result = self.pa.analyze_with_evolution_decisions(
                            iteration=self.current_iteration,
                            results=iteration_results,
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
                            payload = {"analysis_result": self._analysis_to_dict(analysis_result)}
                            self.run_state_manager.append_event(
                                EVENT_PA_COMPLETE,
                                iteration=self.current_iteration,
                                payload=payload
                            )
                else:
                    self.logger.warning("No results to analyze for this iteration")

            # NOTE: No worktree cleanup in evolution mode - worktrees persist until PA decides TERMINATE

            # 2g. Update overall best and check improvement
            if analysis_result:
                self._update_overall_best(analysis_result)

            self.run_state_manager.append_event(
                EVENT_ITERATION_COMPLETE,
                iteration=self.current_iteration
            )

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

        if self.score_threshold and self.best_score_overall:
            # Check threshold based on metric direction
            threshold_met = (
                self.best_score_overall >= self.score_threshold if self.pa.higher_is_better
                else self.best_score_overall <= self.score_threshold
            )
            if threshold_met:
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
            # Check if score improved based on metric direction
            is_improvement = False
            if self.best_score_overall is None:
                is_improvement = True
            elif self.pa.higher_is_better:
                is_improvement = current_best_iter_score > self.best_score_overall
            else:
                is_improvement = current_best_iter_score < self.best_score_overall

            if is_improvement:
                self.best_score_overall = current_best_iter_score
                self.best_experiment_id_overall = analysis_result.best_experiment_id
                self.iterations_without_improvement = 0  # Reset because improved
                self.logger.info(f"New overall best score: {self.best_score_overall:.4f} (Exp ID: {self.best_experiment_id_overall})")
            else:
                 # Score stayed the same or got worse
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

    def _serialize_competition_info(self, info: CompetitionInfo) -> Dict[str, Any]:
        return {
            "name": info.name,
            "evaluation_metric": info.evaluation_metric,
            "deadline": info.deadline.isoformat() if info.deadline else None,
            "description_markdown": info.description_markdown,
            "data_files": info.data_files,
            "competition_type": info.competition_type,
            "competition_subtype": info.competition_subtype,
            "initial_insights": info.initial_insights,
            "data_warnings": info.data_warnings,
            "higher_is_better": info.higher_is_better,
        }

    def _deserialize_competition_info(self, data: Dict[str, Any]) -> Optional[CompetitionInfo]:
        if not data:
            return None
        deadline = None
        if data.get("deadline"):
            try:
                deadline = datetime.datetime.fromisoformat(data["deadline"])
            except Exception:
                deadline = None
        return CompetitionInfo(
            name=data.get("name", ""),
            evaluation_metric=data.get("evaluation_metric", ""),
            deadline=deadline,
            description_markdown=data.get("description_markdown", ""),
            data_files=data.get("data_files", []) or [],
            competition_type=data.get("competition_type"),
            competition_subtype=data.get("competition_subtype"),
            initial_insights=data.get("initial_insights"),
            data_warnings=data.get("data_warnings"),
            higher_is_better=bool(data.get("higher_is_better", True)),
        )

    def _decision_to_dict(self, decision: ExperimentDecision) -> Dict[str, Any]:
        return {
            "experiment_id": decision.experiment_id,
            "decision": decision.decision.value,
            "reasoning": decision.reasoning,
            "confidence": decision.confidence,
            "improvement_instructions": decision.improvement_instructions,
            "termination_reason": decision.termination_reason,
            "potential_ceiling": decision.potential_ceiling,
            "priority_rank": decision.priority_rank,
        }

    def _decision_from_dict(self, data: Dict[str, Any]) -> Optional[ExperimentDecision]:
        if not data or not data.get("experiment_id") or not data.get("decision"):
            return None
        try:
            decision_type = ExperimentDecisionType(data["decision"])
        except Exception:
            decision_type = ExperimentDecisionType.CONTINUE
        return ExperimentDecision(
            experiment_id=data.get("experiment_id", ""),
            decision=decision_type,
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.0)),
            improvement_instructions=data.get("improvement_instructions"),
            termination_reason=data.get("termination_reason"),
            potential_ceiling=data.get("potential_ceiling"),
            priority_rank=int(data.get("priority_rank", 0)),
        )

    def _analysis_to_dict(self, analysis: AnalysisResult) -> Dict[str, Any]:
        return {
            "iteration": analysis.iteration,
            "summary_markdown": analysis.summary_markdown,
            "best_score": analysis.best_score,
            "best_experiment_id": analysis.best_experiment_id,
            "improvement_trend": analysis.improvement_trend,
            "recommended_strategies": analysis.recommended_strategies,
            "success_patterns": analysis.success_patterns,
            "failure_patterns": analysis.failure_patterns,
            "feature_importance": analysis.feature_importance,
            "hyperparameter_insights": analysis.hyperparameter_insights,
            "high_priority_recommendations": analysis.high_priority_recommendations,
            "medium_priority_recommendations": analysis.medium_priority_recommendations,
            "experimental_recommendations": analysis.experimental_recommendations,
            "avoid_recommendations": analysis.avoid_recommendations,
            "unresolved_questions": analysis.unresolved_questions,
            "overfitting_analysis": analysis.overfitting_analysis,
            "convergence_status": analysis.convergence_status,
            "improvement_rate": analysis.improvement_rate,
            "computational_efficiency": analysis.computational_efficiency,
            "top_discoveries": analysis.top_discoveries,
            "critical_decisions": analysis.critical_decisions,
            "experiment_decisions": [self._decision_to_dict(d) for d in analysis.experiment_decisions],
            "experiments_to_continue": analysis.experiments_to_continue,
            "experiments_to_terminate": analysis.experiments_to_terminate,
            "new_slots_available": analysis.new_slots_available,
        }

    def _analysis_from_dict(self, data: Dict[str, Any], iteration: int) -> AnalysisResult:
        decisions = []
        for raw in data.get("experiment_decisions", []) if data else []:
            decision = self._decision_from_dict(raw)
            if decision:
                decisions.append(decision)

        return AnalysisResult(
            iteration=data.get("iteration", iteration),
            summary_markdown=data.get("summary_markdown", ""),
            best_score=data.get("best_score"),
            best_experiment_id=data.get("best_experiment_id"),
            improvement_trend=data.get("improvement_trend", "N/A"),
            recommended_strategies=data.get("recommended_strategies", []) or [],
            success_patterns=data.get("success_patterns", []) or [],
            failure_patterns=data.get("failure_patterns", []) or [],
            feature_importance=data.get("feature_importance", []) or [],
            hyperparameter_insights=data.get("hyperparameter_insights", []) or [],
            high_priority_recommendations=data.get("high_priority_recommendations", []) or [],
            medium_priority_recommendations=data.get("medium_priority_recommendations", []) or [],
            experimental_recommendations=data.get("experimental_recommendations", []) or [],
            avoid_recommendations=data.get("avoid_recommendations", []) or [],
            unresolved_questions=data.get("unresolved_questions", []) or [],
            overfitting_analysis=data.get("overfitting_analysis"),
            convergence_status=data.get("convergence_status"),
            improvement_rate=data.get("improvement_rate"),
            computational_efficiency=data.get("computational_efficiency", []) or [],
            top_discoveries=data.get("top_discoveries", []) or [],
            critical_decisions=data.get("critical_decisions", []) or [],
            experiment_decisions=decisions,
            experiments_to_continue=int(data.get("experiments_to_continue", 0)),
            experiments_to_terminate=int(data.get("experiments_to_terminate", 0)),
            new_slots_available=int(data.get("new_slots_available", 0)),
        )

    def _hypothesis_to_dict(self, hypothesis: ExperimentHypothesis) -> Dict[str, Any]:
        return {
            "kind": "new",
            "experiment_id": hypothesis.experiment_id,
            "iteration": hypothesis.iteration,
            "strategy_name": hypothesis.strategy_name,
            "parameters": hypothesis.parameters,
            "task_markdown_path": hypothesis.task_markdown_path,
        }

    def _continuation_to_dict(self, continuation: ContinuationHypothesis) -> Dict[str, Any]:
        return {
            "kind": "continuation",
            "experiment_id": continuation.experiment_id,
            "continuation_id": continuation.continuation_id,
            "iteration": continuation.iteration,
            "original_strategy_name": continuation.original_strategy_name,
            "improvement_instructions": continuation.improvement_instructions,
            "new_parameters": continuation.new_parameters,
            "worktree_path": continuation.worktree_path,
            "task_markdown_path": continuation.task_markdown_path,
            "parent_score": continuation.parent_score,
        }

    def _load_hypotheses_from_state(self, iter_state: Any) -> tuple[List[ContinuationHypothesis], List[ExperimentHypothesis]]:
        continuations: List[ContinuationHypothesis] = []
        hypotheses: List[ExperimentHypothesis] = []

        for entry in iter_state.hypotheses or []:
            kind = entry.get("kind") if isinstance(entry, dict) else None
            if kind == "continuation" or entry.get("continuation_id"):
                cont = ContinuationHypothesis(
                    experiment_id=entry.get("experiment_id", ""),
                    continuation_id=entry.get("continuation_id", ""),
                    iteration=int(entry.get("iteration", iter_state.iteration)),
                    original_strategy_name=entry.get("original_strategy_name", ""),
                    improvement_instructions=entry.get("improvement_instructions", ""),
                    new_parameters=entry.get("new_parameters", {}) or {},
                    worktree_path=entry.get("worktree_path", ""),
                    task_markdown_path=entry.get("task_markdown_path", ""),
                    parent_score=entry.get("parent_score", 0.0),
                )
                continuations.append(cont)
                self.all_continuation_hypotheses[cont.continuation_id] = cont
                if cont.continuation_id:
                    self.continuation_map[cont.continuation_id] = cont.experiment_id
            else:
                hyp = ExperimentHypothesis(
                    experiment_id=entry.get("experiment_id", ""),
                    iteration=int(entry.get("iteration", iter_state.iteration)),
                    strategy_name=entry.get("strategy_name", ""),
                    parameters=entry.get("parameters", {}) or {},
                    task_markdown_path=entry.get("task_markdown_path", ""),
                )
                hypotheses.append(hyp)
                if hyp.experiment_id:
                    self.all_hypotheses[hyp.experiment_id] = hyp

        return continuations, hypotheses

    def _is_task_markdown_valid(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            return bool(content)
        except Exception:
            return False

    def _tasks_valid_for_iteration(self, hypotheses: List[ExperimentHypothesis],
                                   continuations: List[ContinuationHypothesis]) -> bool:
        for hyp in hypotheses:
            if not self._is_task_markdown_valid(hyp.task_markdown_path):
                return False
        for cont in continuations:
            if not self._is_task_markdown_valid(cont.task_markdown_path):
                return False
        return True

    def _restore_from_run_state(self) -> None:
        if not self.resume_mode or not self.run_state.run_started:
            return

        # Restore initialization payload (competition info and dataset analysis)
        if self.run_state.init_complete and self.run_state.init_payload:
            comp_data = self.run_state.init_payload.get("competition_info")
            if comp_data:
                self.competition_info = self._deserialize_competition_info(comp_data)
            dataset_placeholders = self.run_state.init_payload.get("dataset_placeholders") or {}
            if dataset_placeholders:
                self.kse.set_dataset_analysis(dataset_placeholders)

        # Restore hypotheses from all iterations
        for iter_state in self.run_state.iterations.values():
            self._load_hypotheses_from_state(iter_state)

        # Restore results, official scores, and analysis artifacts
        for iteration, iter_state in self.run_state.iterations.items():
            results = self.rad.get_results_by_iteration(iteration)
            if results:
                self.all_results[iteration] = results
            if iter_state.official_scores:
                self.iteration_official_scores[iteration] = iter_state.official_scores
            if iter_state.analysis_result:
                analysis = self._analysis_from_dict(iter_state.analysis_result, iteration)
                self.iteration_analysis_results[iteration] = analysis

        # Restore persistent experiments from WAA launch records
        for iter_state in self.run_state.iterations.values():
            for exp_id, exp_entry in iter_state.waa_experiments.items():
                worktree_path = exp_entry.get("worktree_path")
                if worktree_path and os.path.exists(worktree_path):
                    self.persistent_experiments[exp_id] = worktree_path

        # Remove terminated experiments from persistent tracking
        for exp_id in self.run_state.terminated_experiments.keys():
            self.persistent_experiments.pop(exp_id, None)

        # Recompute best score and improvement counters
        self.best_score_overall = None
        self.best_experiment_id_overall = None
        self.iterations_without_improvement = 0
        for iter_num in sorted(self.iteration_analysis_results.keys()):
            self._update_overall_best(self.iteration_analysis_results[iter_num])

        # Set current iteration to first incomplete, or next after last complete
        incomplete = self.run_state.first_incomplete_iteration()
        if incomplete is not None:
            self.current_iteration = incomplete
        else:
            last_complete = self.run_state.last_completed_iteration()
            if last_complete is not None:
                self.current_iteration = last_complete + 1

    def _collect_and_log_result(self, exp_id: str, worktree_path: str, iter_state: Any,
                                iteration_results: List[ExperimentResult]) -> Optional[ExperimentResult]:
        if exp_id in iter_state.waa_completed:
            return None
        if any(r.experiment_id == exp_id for r in iteration_results):
            return None

        hypothesis = self.all_hypotheses.get(exp_id)
        result = self.rad.collect_result(exp_id, worktree_path, hypothesis=hypothesis)
        if result:
            iteration_results.append(result)
            payload = {
                "experiment_id": exp_id,
                "status": result.status,
                "score": result.score,
            }
            self.run_state_manager.append_event(
                EVENT_WAA_COMPLETED,
                iteration=iter_state.iteration,
                payload=payload
            )
        return result

    def _get_expected_experiment_ids(self, iter_state: Any,
                                     hypotheses: List[ExperimentHypothesis],
                                     continuations: List[ContinuationHypothesis]) -> List[str]:
        exp_ids = []
        exp_ids.extend([h.experiment_id for h in hypotheses])
        exp_ids.extend([c.continuation_id for c in continuations])
        if exp_ids:
            return exp_ids
        if iter_state.waa_experiments:
            return list(iter_state.waa_experiments.keys())
        return []

    def _resume_or_restart_iteration_experiments(self,
                                                 iter_state: Any,
                                                 hypotheses: List[ExperimentHypothesis],
                                                 continuations: List[ContinuationHypothesis],
                                                 iteration_results: List[ExperimentResult]) -> tuple[set, set]:
        running_experiments: set[str] = set()
        pending_resume: set[str] = set()

        exp_map: Dict[str, Any] = {}
        for hyp in hypotheses:
            exp_map[hyp.experiment_id] = ("new", hyp)
        for cont in continuations:
            exp_map[cont.continuation_id] = ("continuation", cont)

        expected_ids = self._get_expected_experiment_ids(iter_state, hypotheses, continuations)

        if expected_ids:
            # Backfill missing WAA launch records for expected experiments
            experiments_payload = []
            for exp_id in expected_ids:
                if exp_id in iter_state.waa_experiments:
                    continue
                kind, obj = exp_map.get(exp_id, ("new", None))
                worktree_path = ""
                if kind == "continuation" and obj is not None:
                    worktree_path = obj.worktree_path
                if not worktree_path:
                    worktree_path = self.eo.get_worktree_path(exp_id) or ""
                iter_state.waa_experiments[exp_id] = {
                    "experiment_id": exp_id,
                    "worktree_path": worktree_path,
                    "kind": kind,
                }
                experiments_payload.append(iter_state.waa_experiments[exp_id])
            if experiments_payload:
                self.run_state_manager.append_event(
                    EVENT_WAA_LAUNCHED,
                    iteration=iter_state.iteration,
                    payload={"experiments": experiments_payload}
                )

        restart_hypotheses: List[ExperimentHypothesis] = []
        restart_continuations: List[ContinuationHypothesis] = []

        for exp_id in expected_ids:
            if exp_id in iter_state.waa_completed:
                continue

            exp_entry = iter_state.waa_experiments.get(exp_id, {})
            worktree_path = exp_entry.get("worktree_path") or ""
            if not worktree_path:
                worktree_path = self.eo.get_worktree_path(exp_id) or ""

            if not worktree_path:
                # Missing worktree info - restart from scratch
                kind, obj = exp_map.get(exp_id, ("new", None))
                if kind == "continuation" and obj is not None:
                    restart_continuations.append(obj)
                elif obj is not None:
                    restart_hypotheses.append(obj)
                continue

            done_path = os.path.join(worktree_path, f"DONE_{exp_id}")
            done_status = None
            if os.path.exists(done_path):
                try:
                    with open(done_path, "r", encoding="utf-8") as f:
                        done_status = f.read().strip()
                except Exception:
                    done_status = None

            status_entry = None
            try:
                status_entry = self.eo.session_manager.read_current_status(worktree_path)
            except Exception:
                status_entry = None

            status_value = status_entry.status.value if status_entry else None
            done_success = done_status is not None and done_status.startswith("SUCCESS")
            done_failure = done_status is not None and not done_success
            status_complete = status_value == SessionStatus.COMPLETE.value
            status_error = status_value == SessionStatus.ERROR.value
            status_running = status_value == SessionStatus.RUNNING.value

            # Completed successfully
            if done_success or status_complete:
                self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                continue

            # Failure or error: attempt resume if possible
            if done_failure or status_error:
                if self.eo.has_codex_session(exp_id, worktree_path):
                    if self.eo.can_attempt_resume(exp_id):
                        resumed = self.eo.resume_experiment(exp_id, worktree_path, reason="error_or_failure")
                        if resumed:
                            # Check completion after resume
                            status_entry = self.eo.session_manager.read_current_status(worktree_path)
                            status_value = status_entry.status.value if status_entry else None
                            done_success = False
                            if os.path.exists(done_path):
                                with open(done_path, "r", encoding="utf-8") as f:
                                    done_success = f.read().strip().startswith("SUCCESS")
                            if done_success or status_value == SessionStatus.COMPLETE.value:
                                self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                            else:
                                pending_resume.add(exp_id)
                        else:
                            if self.eo.can_attempt_resume(exp_id):
                                pending_resume.add(exp_id)
                            else:
                                if not os.path.exists(done_path):
                                    with open(done_path, "w", encoding="utf-8") as f:
                                        f.write("RESUME_FAILURE")
                                self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                    else:
                        if not os.path.exists(done_path):
                            with open(done_path, "w", encoding="utf-8") as f:
                                f.write("RESUME_FAILURE")
                        self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                else:
                    # No Codex session - restart from scratch
                    kind, obj = exp_map.get(exp_id, ("new", None))
                    if kind == "continuation" and obj is not None:
                        restart_continuations.append(obj)
                    elif obj is not None:
                        restart_hypotheses.append(obj)
                continue

            # RUNNING without DONE: resume immediately
            if status_running:
                if self.eo.has_codex_session(exp_id, worktree_path):
                    if self.eo.can_attempt_resume(exp_id):
                        resumed = self.eo.resume_experiment(exp_id, worktree_path, reason="status_running")
                        if resumed:
                            status_entry = self.eo.session_manager.read_current_status(worktree_path)
                            status_value = status_entry.status.value if status_entry else None
                            done_success = False
                            if os.path.exists(done_path):
                                with open(done_path, "r", encoding="utf-8") as f:
                                    done_success = f.read().strip().startswith("SUCCESS")
                            if done_success or status_value == SessionStatus.COMPLETE.value:
                                self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                            else:
                                pending_resume.add(exp_id)
                        else:
                            if self.eo.can_attempt_resume(exp_id):
                                pending_resume.add(exp_id)
                            else:
                                if not os.path.exists(done_path):
                                    with open(done_path, "w", encoding="utf-8") as f:
                                        f.write("RESUME_FAILURE")
                                self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                    else:
                        if not os.path.exists(done_path):
                            with open(done_path, "w", encoding="utf-8") as f:
                                f.write("RESUME_FAILURE")
                        self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                else:
                    # No Codex session - restart from scratch
                    kind, obj = exp_map.get(exp_id, ("new", None))
                    if kind == "continuation" and obj is not None:
                        restart_continuations.append(obj)
                    elif obj is not None:
                        restart_hypotheses.append(obj)
                continue

            # Default path: resume if possible, otherwise restart
            if self.eo.has_codex_session(exp_id, worktree_path):
                if self.eo.can_attempt_resume(exp_id):
                    resumed = self.eo.resume_experiment(exp_id, worktree_path, reason="resume_default")
                    if resumed:
                        status_entry = self.eo.session_manager.read_current_status(worktree_path)
                        status_value = status_entry.status.value if status_entry else None
                        done_success = False
                        if os.path.exists(done_path):
                            with open(done_path, "r", encoding="utf-8") as f:
                                done_success = f.read().strip().startswith("SUCCESS")
                        if done_success or status_value == SessionStatus.COMPLETE.value:
                            self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                        else:
                            pending_resume.add(exp_id)
                    else:
                        if self.eo.can_attempt_resume(exp_id):
                            pending_resume.add(exp_id)
                        else:
                            if not os.path.exists(done_path):
                                with open(done_path, "w", encoding="utf-8") as f:
                                    f.write("RESUME_FAILURE")
                            self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
                else:
                    if not os.path.exists(done_path):
                        with open(done_path, "w", encoding="utf-8") as f:
                            f.write("RESUME_FAILURE")
                    self._collect_and_log_result(exp_id, worktree_path, iter_state, iteration_results)
            else:
                kind, obj = exp_map.get(exp_id, ("new", None))
                if kind == "continuation" and obj is not None:
                    restart_continuations.append(obj)
                elif obj is not None:
                    restart_hypotheses.append(obj)

        # Launch restarts
        if restart_continuations:
            cont_result = self.eo.launch_continuation_experiments(restart_continuations, total_waas=len(expected_ids))
            launched = cont_result.get("launched", [])
            for cont in restart_continuations:
                if cont.continuation_id in launched:
                    running_experiments.add(cont.continuation_id)
            experiments_payload = []
            for cont_id in launched:
                worktree_path = self.eo.get_worktree_path(cont_id) or ""
                experiments_payload.append({
                    "experiment_id": cont_id,
                    "worktree_path": worktree_path,
                    "kind": "continuation"
                })
            if experiments_payload:
                self.run_state_manager.append_event(
                    EVENT_WAA_LAUNCHED,
                    iteration=iter_state.iteration,
                    payload={"experiments": experiments_payload}
                )

        if restart_hypotheses:
            new_result = self.eo.launch_experiments(restart_hypotheses, total_waas=len(expected_ids))
            launched = new_result.get("launched", [])
            for exp_id in launched:
                running_experiments.add(exp_id)
            experiments_payload = []
            for exp_id in launched:
                worktree_path = self.eo.get_worktree_path(exp_id) or ""
                experiments_payload.append({
                    "experiment_id": exp_id,
                    "worktree_path": worktree_path,
                    "kind": "new"
                })
            if experiments_payload:
                self.run_state_manager.append_event(
                    EVENT_WAA_LAUNCHED,
                    iteration=iter_state.iteration,
                    payload={"experiments": experiments_payload}
                )

        return running_experiments, pending_resume

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
                    self.run_state_manager.append_event(
                        EVENT_EXPERIMENT_TERMINATED,
                        payload={
                            "experiment_id": decision.experiment_id,
                            "reason": decision.termination_reason or "TERMINATE"
                        }
                    )
                    # Remove from persistent tracking (drop all keys pointing to the same worktree).
                    keys_to_remove = [
                        exp_key
                        for exp_key, path in list(self.persistent_experiments.items())
                        if path == worktree_path
                    ]
                    for exp_key in keys_to_remove:
                        self.persistent_experiments.pop(exp_key, None)
                else:
                    self.logger.warning(f"No worktree found for terminated experiment {decision.experiment_id}")
                    self.run_state_manager.append_event(
                        EVENT_EXPERIMENT_TERMINATED,
                        payload={
                            "experiment_id": decision.experiment_id,
                            "reason": decision.termination_reason or "TERMINATE"
                        }
                    )

        self.logger.info(
            f"Evolution decisions: {len(continue_decisions)} CONTINUE, "
            f"{len(terminate_decisions)} TERMINATE, "
            f"{len(terminate_decisions)} new slots available"
        )

        return continue_decisions, terminate_decisions

    def _generate_evolution_hypotheses_for_iteration(
        self,
        analysis_result: AnalysisResult,
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
            competition_info=self.competition_info,
            current_iteration=self.current_iteration,
            num_hypotheses=self.wca_per_iteration,
            analysis_result=analysis_result,
            previous_results=iteration_results,
            persistent_experiments=self.persistent_experiments,
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

        # Total WAAs being launched (for GPU allocation)
        total_waas = len(continuations) + len(new_hypotheses)

        # Launch continuations first (resume existing worktrees)
        if continuations:
            cont_result = self.eo.launch_continuation_experiments(continuations, total_waas)
            all_launched.extend(cont_result.get('launched', []))
            all_failed.extend(cont_result.get('failed', []))

            # Update persistent experiments with continuation IDs
            for cont in continuations:
                if cont.continuation_id in cont_result.get('launched', []):
                    # Map continuation_id to the worktree path (same worktree reused)
                    self.persistent_experiments[cont.continuation_id] = cont.worktree_path

        # Launch new hypotheses (create fresh worktrees)
        if new_hypotheses:
            new_result = self.eo.launch_experiments(new_hypotheses, total_waas=total_waas)
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
            direction = "higher is better" if self.pa.higher_is_better else "lower is better"
            self.logger.info(f"Overall Best Score: {self.best_score_overall:.4f} ({direction})")
            self.logger.info(f"Best Experiment ID: {self.best_experiment_id_overall}")
            # Display details of best result (from RAD)
            best_result = self.rad.get_result(self.best_experiment_id_overall)
            if best_result:
                 self.logger.info(f"Best Result Details: {best_result}")
                 # Optionally submit here (logging only in current flow)
                 submission_file = next((f for f in best_result.result_files if 'submission' in f), None)
                 if submission_file:
                      submission_path_absolute = os.path.join(self.rad.results_base_dir, submission_file)
                      if self.config.get("simulation_mode", False):
                          self.logger.info("Dry-run: skipping final Kaggle submission")
                          self.user_confirm.show_status("Dry-run: final submission skipped", "dim")
                      else:
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
