import os
import shutil
import time
import uuid
import subprocess
import multiprocessing
import json
from typing import List, Dict, Tuple, Optional
import git # GitPython

from ..core.base_component import BaseComponent
from ..data_models import ExperimentHypothesis
from ..utils.file_utils import ensure_dir, remove_dir
from .codex_launcher import CodexExperimentLauncher
from .session_manager import SessionManager, SessionStatus
from ..utils.resource_monitor import ResourceMonitor
from ..utils.gpu_allocator import GPUAllocator

class ExperimentOrchestrator(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.worktree_base_dir = os.path.abspath(os.path.join(self.experiment_run_dir, "worktrees"))
        self.wca_simulator_script = os.path.abspath(os.path.join(os.path.dirname(__file__), 'wca_simulator.py'))
        self.dry_run = config.get("dry_run", False)
        ensure_dir(self.worktree_base_dir)

        self.repo = self._get_git_repo()
        self.active_processes: Dict[str, Tuple[subprocess.Popen, str]] = {} # {exp_id: (process, worktree_path)}

        # Execution mode: 'simulation' or 'codex'
        self.execution_mode = config.get("execution_mode", "simulation")
        self.codex_launcher = None

        if self.execution_mode == "codex":
            self.logger.info("Initializing Codex execution mode")
            self.codex_launcher = CodexExperimentLauncher(config)
        else:
            self.logger.info("Using simulation execution mode")

        # Initialize session manager for long-running experiment tracking
        self.session_manager = SessionManager(self.experiment_run_dir, self.logger)

        # Track resource monitors for RUNNING experiments
        self._resource_monitors: Dict[str, ResourceMonitor] = {}

        # Track resumed processes for session continuation
        self._resumed_processes: Dict[str, Tuple[subprocess.Popen, str]] = {}

        # Track resume retry counts per experiment (for failed resume attempts)
        self._resume_retry_count: Dict[str, int] = {}

        # Initialize GPU allocator for parallel WAA resource management
        self.gpu_allocator = GPUAllocator(config)
        self.logger.info(f"GPU allocator initialized")

    def _get_git_repo(self):
        """Return the Git repository for the current directory."""
        try:
            repo = git.Repo(search_parent_directories=True)
            self.logger.info(f"Git repository found at: {repo.working_dir}")
            # Clean up stale worktrees that might be left from prior runs
            self._cleanup_stale_worktrees(repo)
            return repo
        except git.InvalidGitRepositoryError:
            self.logger.error("Git repository not found in the current directory or parent directories. Please run 'git init'.")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Git Repo object: {e}")
            raise

    def _cleanup_stale_worktrees(self, repo):
        """Try to remove managed worktrees that already exist on startup."""
        self.logger.info("Checking for stale worktrees...")
        try:
            existing_worktrees = [wt for wt in repo.git.worktree('list').splitlines() if self.worktree_base_dir in wt]
            for line in existing_worktrees:
                path = line.split()[0]
                if os.path.exists(path):  # Ensure physical path exists
                    self.logger.warning(f"Found potentially stale worktree: {path}. Attempting removal.")
                    try:
                        # Prune Git worktree metadata, then remove the directory
                        repo.git.worktree('prune')
                        remove_dir(path)
                        self.logger.info(f"Successfully removed stale worktree: {path}")
                    except Exception as e:
                        self.logger.error(f"Failed to remove stale worktree {path}: {e}. Manual cleanup might be required.")
        except Exception as e:
            self.logger.error(f"Error during stale worktree cleanup: {e}")


    def launch_experiments(self, hypotheses: List[ExperimentHypothesis]) -> Dict[str, any]:
        """Launch WAA simulator or Codex processes in parallel for each hypothesis.

        Returns:
            Dict with keys:
                - 'launched': List[str] - successfully launched experiment IDs
                - 'failed': List[Dict] - failed launches with {'exp_id': str, 'reason': str}
                - 'total': int - total number of hypotheses
        """
        method_name = "launch_experiments"
        self._log_start(method_name, num_hypotheses=len(hypotheses))
        launched_ids = []
        failed_launches = []

        # Note: max_workers calculated for potential future use with process pools
        max_workers = min(len(hypotheses), multiprocessing.cpu_count() * 2)
        self.logger.info(f"Launching {len(hypotheses)} experiments with max {max_workers} parallel workers.")

        # Calculate total WAAs for GPU allocation
        total_waas = len(hypotheses)

        # Log GPU allocation summary
        self.logger.info(self.gpu_allocator.get_allocation_summary(total_waas))

        processes_to_start = []

        # Dry-run: simulate full lifecycle without external commands
        if self.dry_run:
            ensure_dir(self.worktree_base_dir)
            for hypothesis in hypotheses:
                exp_id = hypothesis.experiment_id
                worktree_path = os.path.join(self.worktree_base_dir, exp_id)
                ensure_dir(worktree_path)
                # Create minimal artifacts
                done_file = os.path.join(worktree_path, f"DONE_{exp_id}")
                result_file = os.path.join(worktree_path, f"result_{exp_id}.json")
                submission_file = os.path.join(worktree_path, f"submission_{exp_id}.csv")
                log_file = os.path.join(worktree_path, f"waa_{exp_id}.log")
                with open(done_file, "w") as f:
                    f.write("SUCCESS")
                with open(result_file, "w") as f:
                    json.dump({"score": 0.5, "status": "DRY_RUN"}, f, indent=2)
                with open(submission_file, "w") as f:
                    f.write("id,prediction\n1,0.5\n2,0.5\n")
                with open(log_file, "w") as f:
                    f.write("DRY-RUN: simulated WAA execution log\n")
                try:
                    self.session_manager.create_status_file(worktree_path, exp_id)
                except Exception:
                    pass
                self.active_processes[exp_id] = (None, worktree_path)
                launched_ids.append(exp_id)
            self._log_end(method_name, result=f"DRY-RUN: Simulated {len(launched_ids)}/{len(hypotheses)} processes.")
            return {
                'launched': launched_ids,
                'failed': failed_launches,
                'total': len(hypotheses)
            }
        for hypothesis in hypotheses:
            exp_id = hypothesis.experiment_id
            worktree_path = os.path.join(self.worktree_base_dir, exp_id)
            branch_name = f"exp/{exp_id}"  # Branch name

            try:
                # 1. Create Git worktree (warn if it already exists)
                if os.path.exists(worktree_path):
                     self.logger.warning(f"Worktree path {worktree_path} already exists. Skipping creation, assuming it's usable or will be cleaned later.")
                else:
                     start_point = self.repo.head.commit
                     self.repo.git.worktree('add', '-b', branch_name, worktree_path, start_point)
                     self.logger.info(f"Created Git worktree at: {worktree_path} on branch {branch_name}")

                # Copy kaggle_data to worktree for WAA access
                kaggle_data_src = os.path.join(self.experiment_run_dir, "kaggle_data")
                worktree_kaggle_data = os.path.join(worktree_path, "kaggle_data")
                if os.path.exists(kaggle_data_src) and not os.path.exists(worktree_kaggle_data):
                    try:
                        shutil.copytree(kaggle_data_src, worktree_kaggle_data)
                        self.logger.info(f"Copied kaggle_data to worktree: {worktree_path}")
                    except Exception as copy_error:
                        self.logger.warning(f"Failed to copy kaggle_data to worktree: {copy_error}")

                # Copy experiment pyproject.toml for uv environment
                experiment_pyproject = self.config.get("experiment_pyproject_path", "config/experiment_pyproject.toml")
                experiment_pyproject_abs = os.path.abspath(experiment_pyproject)
                worktree_pyproject = os.path.join(worktree_path, "pyproject.toml")

                if os.path.exists(experiment_pyproject_abs) and not os.path.exists(worktree_pyproject):
                    try:
                        shutil.copy2(experiment_pyproject_abs, worktree_pyproject)
                        self.logger.info(f"Copied pyproject.toml to worktree: {worktree_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to copy pyproject.toml: {e}")

                # Copy uv.lock if exists (for reproducibility)
                uv_lock_src = os.path.join(os.path.dirname(experiment_pyproject_abs), "experiment_uv.lock")
                # Also check project root
                if not os.path.exists(uv_lock_src):
                    uv_lock_src = os.path.abspath("uv.lock")
                worktree_uv_lock = os.path.join(worktree_path, "uv.lock")

                if os.path.exists(uv_lock_src) and not os.path.exists(worktree_uv_lock):
                    try:
                        shutil.copy2(uv_lock_src, worktree_uv_lock)
                        self.logger.info(f"Copied uv.lock to worktree: {worktree_path}")
                    except Exception as e:
                        self.logger.warning(f"Failed to copy uv.lock: {e}")

                # Run uv sync to install dependencies
                try:
                    self.logger.info(f"Running 'uv sync' in worktree: {worktree_path}")
                    result = subprocess.run(
                        ['uv', 'sync'],
                        cwd=worktree_path,
                        capture_output=True,
                        text=True,
                        timeout=300  # 5 minutes timeout
                    )
                    if result.returncode != 0:
                        self.logger.error(f"uv sync failed for {exp_id}: {result.stderr}")
                        raise RuntimeError(f"uv sync failed: {result.stderr}")
                    else:
                        self.logger.info(f"uv sync completed in {worktree_path}")
                except subprocess.TimeoutExpired:
                    self.logger.error(f"uv sync timed out for {exp_id} in {worktree_path}")
                    raise RuntimeError(f"uv sync timed out after 300 seconds")
                except FileNotFoundError:
                    self.logger.error("uv command not found. Is uv installed?")
                    raise RuntimeError("uv command not found - please install uv")
                except RuntimeError:
                    raise  # Re-raise RuntimeError from above
                except Exception as e:
                    self.logger.error(f"Failed to run uv sync for {exp_id}: {e}")
                    raise RuntimeError(f"uv sync failed: {e}")

                # Create initial experiment-status.yaml for session tracking
                try:
                    self.session_manager.create_status_file(worktree_path, exp_id)
                    self.logger.info(f"Created experiment-status.yaml in {worktree_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to create status file: {e}")

                # Save hypothesis metadata to worktree for resume context
                # This ensures we can reconstruct hypothesis info even after session resume
                try:
                    hypothesis_metadata = {
                        "experiment_id": hypothesis.experiment_id,
                        "iteration": hypothesis.iteration,
                        "strategy_name": hypothesis.strategy_name,
                        "parameters": hypothesis.parameters,
                        "task_markdown_path": hypothesis.task_markdown_path,
                    }
                    metadata_path = os.path.join(worktree_path, f"hypothesis_{exp_id}.json")
                    with open(metadata_path, 'w', encoding='utf-8') as f:
                        json.dump(hypothesis_metadata, f, indent=2)
                    self.logger.debug(f"Saved hypothesis metadata to {metadata_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to save hypothesis metadata: {e}")

                # Calculate GPU allocation for this WAA
                waa_index = GPUAllocator.parse_waa_index(exp_id)
                gpu_allocation = self.gpu_allocator.allocate(waa_index, total_waas)

                # Prepare environment with GPU settings
                env = os.environ.copy()
                env.update(gpu_allocation.env_vars)

                self.logger.info(f"GPU allocation for {exp_id}: "
                                f"CUDA_VISIBLE_DEVICES={gpu_allocation.cuda_visible_devices or 'N/A'}, "
                                f"memory_fraction={gpu_allocation.memory_fraction:.2f}, "
                                f"gpu_count={gpu_allocation.gpu_count}")

                # 2. Launch per execution mode
                if self.execution_mode == "codex":
                    # Codex mode: use codex exec with GPU env vars
                    process = self._launch_codex_experiment(hypothesis, worktree_path, exp_id, env=env, gpu_allocation=gpu_allocation)
                else:
                    # Simulation mode: use WAA simulator with GPU env vars
                    cmd = [
                        'python', self.wca_simulator_script,
                        '--worktree-path', worktree_path,
                        '--task-markdown-path', hypothesis.task_markdown_path,
                        '--experiment-id', exp_id,
                        '--log-level', self.config.get("log_level", "INFO")
                    ]
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

                if process:
                    processes_to_start.append((process, exp_id, worktree_path))
                    launched_ids.append(exp_id)

            except git.GitCommandError as e:
                error_msg = f"Git command failed: {e.stderr}"
                self.logger.error(f"Git command failed for {exp_id} at {worktree_path}: {e.stderr}")
                failed_launches.append({'exp_id': exp_id, 'reason': error_msg})
            except Exception as e:
                error_msg = str(e)
                self.logger.error(f"Failed to prepare or launch experiment {exp_id}: {e}")
                failed_launches.append({'exp_id': exp_id, 'reason': error_msg})

        # Register processes in bulk
        for process, exp_id, worktree_path in processes_to_start:
             self.active_processes[exp_id] = (process, worktree_path)
             self.logger.info(f"Launched {'Codex' if self.execution_mode == 'codex' else 'WAA simulator'} process for experiment {exp_id} (PID: {process.pid})")

        # Log summary
        if failed_launches:
            self.logger.warning(f"Failed to launch {len(failed_launches)}/{len(hypotheses)} experiments")
            for failure in failed_launches:
                self.logger.warning(f"  - {failure['exp_id']}: {failure['reason']}")

        self._log_end(method_name, result=f"Launched {len(launched_ids)}/{len(hypotheses)} processes.")
        return {
            'launched': launched_ids,
            'failed': failed_launches,
            'total': len(hypotheses)
        }

    def _launch_codex_experiment(
        self,
        hypothesis: ExperimentHypothesis,
        worktree_path: str,
        exp_id: str,
        env: Optional[Dict[str, str]] = None,
        gpu_allocation: Optional[any] = None
    ) -> Optional[subprocess.Popen]:
        """Launch a single experiment using Codex.

        Args:
            hypothesis: Experiment hypothesis with task markdown path
            worktree_path: Working directory for the experiment
            exp_id: Experiment identifier
            env: Environment variables to set (including GPU allocation)
            gpu_allocation: GPU allocation information for this experiment
        """
        try:
            # Read task markdown
            with open(hypothesis.task_markdown_path, 'r', encoding='utf-8') as f:
                task_content = f.read()

            # Prepare hardware allocation info if available
            hardware_info = ""
            if gpu_allocation:
                cuda_devices = gpu_allocation.cuda_visible_devices or "N/A (CPU only)"
                hardware_info = f"""
**HARDWARE ALLOCATION**:
- GPUs assigned: {cuda_devices}
- Memory fraction: {gpu_allocation.memory_fraction:.2f}
- GPU count: {gpu_allocation.gpu_count}

Please ensure your code respects these GPU constraints. The environment variables are already set:
- CUDA_VISIBLE_DEVICES={cuda_devices}
- TF_FORCE_GPU_ALLOW_GROWTH=true
- If no GPU is assigned, use CPU only.

"""

            # Prepare stdin for Codex
            stdin_input = f"""Your Task:
{task_content}
{hardware_info}
Please execute the experiment exactly as described above. Ensure you:
1. Create the result_{exp_id}.json file with the score
2. Create the DONE_{exp_id} file when complete
3. Save predictions to submission_{exp_id}.csv
"""
            # Start codex exec in background with --json flag for JSONL output
            codex_config = self.config.get("codex", {})
            cmd = ['codex', 'exec', '--json']

            if codex_config.get("skip_confirmation", True):
                cmd.append('--skip-git-repo-check')

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=worktree_path,
                text=True,
                env=env or os.environ
            )

            # Send stdin asynchronously (avoid blocking)
            if process.stdin:
                process.stdin.write(stdin_input)
                process.stdin.close()

            self.logger.info(f"Launched Codex process for {exp_id} in {worktree_path}")
            return process

        except FileNotFoundError as e:
            self.logger.error(f"Codex CLI not found. Is it installed and in PATH? Error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to launch Codex for {exp_id}: {e}")
            return None

    # _run_wca_simulator method removed since we now use subprocess.Popen directly


    def check_running_experiments(self) -> List[str]:
        """Check running experiments with status-aware completion detection."""
        if self.dry_run:
            completed = list(self.active_processes.keys())
            self.active_processes = {}
            return completed

        completed_ids = []
        still_active_processes = {}
        sessions_needing_resume = []

        if not self.active_processes:
            return []

        for exp_id, (process, worktree_path) in self.active_processes.items():
            done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")

            # 1. Read current status from experiment-status.yaml
            try:
                current_status = self.session_manager.read_current_status(worktree_path)
            except Exception as e:
                self.logger.error(f"Status file corrupted for {exp_id}: {e}")
                # Create error marker for debugging
                error_marker = os.path.join(worktree_path, f"STATUS_ERROR_{exp_id}")
                try:
                    with open(error_marker, 'w') as f:
                        f.write(f"Status file read error: {e}")
                except:
                    pass  # Don't fail on marker creation
                current_status = None
                self.logger.warning(f"Falling back to DONE file check for {exp_id} due to status file error")

            # 2. Check status-based completion
            if current_status:
                if current_status.status == SessionStatus.COMPLETE:
                    # Training complete, collect results
                    self._finalize_completed_experiment(exp_id, process, worktree_path)
                    completed_ids.append(exp_id)
                    continue
                elif current_status.status == SessionStatus.ERROR:
                    # Error state, mark failed and collect what we can
                    self._handle_error_experiment(exp_id, process, worktree_path, current_status)
                    completed_ids.append(exp_id)
                    continue
                elif current_status.status == SessionStatus.RUNNING:
                    # Process exited with RUNNING status - check if training is complete
                    if process.poll() is not None:
                        # Codex session exited, training may still be running in background
                        if self._is_training_complete(exp_id, worktree_path):
                            sessions_needing_resume.append((exp_id, process, worktree_path))
                        else:
                            # Training still running, keep tracking
                            still_active_processes[exp_id] = (process, worktree_path)
                    else:
                        # Codex session still running
                        still_active_processes[exp_id] = (process, worktree_path)
                    continue

            # 3. Fallback: check DONE file (backward compatibility)
            if os.path.exists(done_file_path):
                self._finalize_completed_experiment(exp_id, process, worktree_path)
                completed_ids.append(exp_id)
            elif process.poll() is not None:
                # Process exited without DONE or status file
                self._handle_unexpected_exit(exp_id, process, worktree_path)
                completed_ids.append(exp_id)
            else:
                still_active_processes[exp_id] = (process, worktree_path)

        # 4. Handle sessions needing resume
        # Note: execute_codex_resume() is BLOCKING - it waits for the resumed session to complete
        for exp_id, process, worktree_path in sessions_needing_resume:
            resumed = self._trigger_resume(exp_id, process, worktree_path)
            if resumed:
                # Resume completed successfully (blocking call returned)
                # Check if experiment actually completed by looking for DONE file or status
                done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
                try:
                    current_status = self.session_manager.read_current_status(worktree_path)
                except Exception:
                    current_status = None

                if os.path.exists(done_file_path):
                    # Experiment completed - add to completed_ids
                    self.logger.info(f"Resume completed and experiment {exp_id} finished successfully")
                    completed_ids.append(exp_id)
                elif current_status and current_status.status == SessionStatus.COMPLETE:
                    # Status shows complete - finalize
                    self._finalize_completed_experiment(exp_id, process, worktree_path)
                    completed_ids.append(exp_id)
                elif current_status and current_status.status == SessionStatus.ERROR:
                    # Resumed but ended in error
                    self._handle_error_experiment(exp_id, process, worktree_path, current_status)
                    completed_ids.append(exp_id)
                else:
                    # Resume succeeded but experiment not complete (rare - WAA may have set RUNNING again)
                    # Keep in active processes for next check cycle
                    self.logger.warning(f"Resume completed for {exp_id} but experiment not finished. Continuing to monitor.")
                    still_active_processes[exp_id] = (process, worktree_path)

                # Reset retry count on successful resume
                self._resume_retry_count[exp_id] = 0
            else:
                # Resume failed - check retry count
                retry_count = self._resume_retry_count.get(exp_id, 0)
                if retry_count < 1:
                    # First failure - increment retry count and keep in active processes for retry
                    self._resume_retry_count[exp_id] = retry_count + 1
                    still_active_processes[exp_id] = (process, worktree_path)
                    self.logger.warning(f"Resume failed for {exp_id} (attempt {retry_count + 1}/2). Will retry next check.")
                else:
                    # Second failure - mark as failed and complete
                    self.logger.error(f"Resume failed for {exp_id} after {retry_count + 1} attempts. Marking as failed.")
                    done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
                    with open(done_file_path, 'w') as f:
                        f.write("RESUME_FAILURE")
                    completed_ids.append(exp_id)
                    # Clean up retry count
                    self._resume_retry_count.pop(exp_id, None)

        self.active_processes = still_active_processes
        return completed_ids

    def _finalize_completed_experiment(self, exp_id: str, process: subprocess.Popen, worktree_path: str):
        """Finalize a completed experiment."""
        # Terminate process if still running
        if process and process.poll() is None:
            self.logger.warning(f"Process for {exp_id} still running at completion. Terminating.")
            try:
                process.terminate()
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
            except Exception as e:
                self.logger.error(f"Error terminating process {exp_id}: {e}")

        # Save JSONL output
        self._save_codex_jsonl_output(exp_id, process, worktree_path)

        # Ensure DONE file exists
        done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
        if not os.path.exists(done_file_path):
            with open(done_file_path, 'w') as f:
                f.write("SUCCESS")

        self.logger.info(f"Experiment {exp_id} completed successfully.")

        # Log session event
        self.session_manager.log_session_event(exp_id, "COMPLETE", SessionStatus.COMPLETE)

    def _handle_error_experiment(self, exp_id: str, process: subprocess.Popen, worktree_path: str, status):
        """Handle an experiment that ended with ERROR status."""
        self._save_codex_jsonl_output(exp_id, process, worktree_path)

        done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
        with open(done_file_path, 'w') as f:
            f.write(f"ERROR: {status.message}")

        self.logger.error(f"Experiment {exp_id} failed with error: {status.message}")

        # Log session event
        self.session_manager.log_session_event(
            exp_id, "ERROR", SessionStatus.ERROR,
            {'error_type': status.error_type, 'message': status.message}
        )

    def _handle_unexpected_exit(self, exp_id: str, process: subprocess.Popen, worktree_path: str):
        """Handle process that exited without proper completion."""
        self.logger.error(f"Process for {exp_id} terminated unexpectedly. Marking as failed.")
        self._save_codex_jsonl_output(exp_id, process, worktree_path)

        done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
        with open(done_file_path, 'w') as f:
            f.write("UNEXPECTED_FAILURE")

    def _is_training_complete(self, exp_id: str, worktree_path: str) -> bool:
        """Check if training is complete using resource monitoring."""
        # Get or create resource monitor for this experiment
        if exp_id not in self._resource_monitors:
            self._resource_monitors[exp_id] = ResourceMonitor(worktree_path, self.logger)

        monitor = self._resource_monitors[exp_id]
        idle_threshold = self.config.get("training_idle_threshold_minutes", 3)

        return monitor.is_training_likely_complete(idle_threshold_minutes=idle_threshold)

    def _trigger_resume(self, exp_id: str, process: subprocess.Popen, worktree_path: str) -> bool:
        """Trigger Codex resume using `codex resume --last`."""
        self.logger.info(f"Triggering session resume for {exp_id}")

        # Read training log for context
        training_log_tail = ""
        log_path = os.path.join(worktree_path, "training.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    training_log_tail = f.read()[-10000:]  # Last 10KB
            except Exception as e:
                self.logger.warning(f"Failed to read training log: {e}")

        exit_code = process.poll() if process.poll() is not None else 0

        try:
            # Import resume function
            from ..utils.codex_executor import execute_codex_resume, build_resume_prompt

            resume_prompt = build_resume_prompt(exp_id, exit_code, training_log_tail)

            # Use `codex resume --last` to continue the session
            codex_responses_dir = os.path.join(self.experiment_run_dir, "codex-responses", "WAA")
            result = execute_codex_resume(
                experiment_id=exp_id,
                worktree_path=worktree_path,
                codex_responses_dir=codex_responses_dir,
                resume_prompt=resume_prompt,
                timeout=self.config.get("waa_resume_timeout", 600),
                logger=self.logger
            )

            if result.success:
                self.logger.info(f"Resume completed for {exp_id}")
                # Log session event
                self.session_manager.log_session_event(exp_id, "RESUME", SessionStatus.RUNNING)
                return True
            else:
                self.logger.error(f"Resume failed for {exp_id}: {result.error}")
                return False

        except ImportError as e:
            self.logger.error(f"Cannot import resume function: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Resume failed for {exp_id}: {e}")
            return False

    def _save_codex_jsonl_output(self, exp_id: str, process: subprocess.Popen, worktree_path: str):
        """Save JSONL output from completed Codex process to worktree directory."""
        if self.execution_mode != "codex" or process is None:
            return  # Only for Codex mode

        try:
            # Read stdout from the process (contains JSONL output)
            if process.stdout:
                jsonl_output = process.stdout.read()
                if jsonl_output:
                    jsonl_path = os.path.join(worktree_path, f"codex_output_{exp_id}.jsonl")
                    with open(jsonl_path, 'w', encoding='utf-8') as f:
                        f.write(jsonl_output)
                    self.logger.info(f"Saved JSONL output to {jsonl_path}")
        except Exception as e:
            self.logger.warning(f"Failed to save JSONL output for {exp_id}: {e}")

    def cleanup_worktree(self, exp_id: str, worktree_path: str):
        """Clean up the specified worktree."""
        method_name = "cleanup_worktree"
        self._log_start(method_name, exp_id=exp_id, path=worktree_path)
        try:
            if self.dry_run:
                remove_dir(worktree_path)
                self._log_end(method_name)
                return
            # Prune Git worktree metadata first
            self.repo.git.worktree('prune')
            # Remove the physical directory
            remove_dir(worktree_path)
            # Optionally delete the corresponding branch
            try:
                branch_name = f"exp/{exp_id}"
                self.repo.git.branch('-D', branch_name)
                self.logger.info(f"Deleted branch {branch_name}")
            except git.GitCommandError as branch_error:
                 # Branch may already be gone; safe to ignore
                 self.logger.warning(f"Could not delete branch exp/{exp_id}: {branch_error.stderr}. It might have been deleted already.")

            self._log_end(method_name)
        except git.GitCommandError as e:
            self.logger.error(f"Git command failed during cleanup for {exp_id}: {e.stderr}")
        except Exception as e:
            self._log_error(method_name, e)

    def get_worktree_path(self, exp_id: str) -> Optional[str]:
        """Return the worktree path for a given experiment ID."""
        if exp_id in self.active_processes:
            return self.active_processes[exp_id][1]
        # Completed experiments drop from active_processes; reconstruct path
        path = os.path.join(self.worktree_base_dir, exp_id)
        # Caller can check existence as needed
        return path
