import os
import shutil
import time
import uuid
import subprocess
import multiprocessing
import json
import sys
from typing import List, Dict, Tuple, Optional
import git # GitPython

import datetime

from ..core.base_component import BaseComponent
from ..data_models import ExperimentHypothesis, ContinuationHypothesis
from ..utils.file_utils import ensure_dir, remove_dir
from ..utils.codex_live_view_launcher import CodexLiveViewLauncher
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
        self.simulation_mode = config.get("simulation_mode", False)
        ensure_dir(self.worktree_base_dir)

        self.repo = self._get_git_repo()
        self.active_processes: Dict[str, Tuple[subprocess.Popen, str]] = {} # {exp_id: (process, worktree_path)}
        # Track worktree locations for both fresh experiments and continuations
        self.experiment_worktree_map: Dict[str, str] = {}

        # Execution mode derives from simulation_mode
        if not self.simulation_mode:
            self.logger.info("Initializing Codex execution mode")
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

        # Resolved uv command (absolute path if found); used for worktree env setup and dry-run execution.
        self._uv_cmd: Optional[str] = None

        # When a DONE/status COMPLETE marker appears but the process is still running,
        # enforce a configurable grace period before terminating the process.
        self._completion_grace_started_at: Dict[str, float] = {}

        # Initialize GPU allocator for parallel WAA resource management
        self.gpu_allocator = GPUAllocator(config)
        self.logger.info(f"GPU allocator initialized")

        # Optional: spawn a separate terminal per WAA to follow Codex JSONL output.
        self._codex_live_view = CodexLiveViewLauncher(config, logger=self.logger)

        # Dry-run marker prefix used by src/execution/wca_simulator.py
        self._dry_run_training_done_prefix = "DRYRUN_TRAINING_DONE_"

    def _maybe_spawn_live_view(self, *, label: str, jsonl_path: str, pid: int | None) -> None:
        """
        Spawn a separate terminal to follow a Codex JSONL output file, if enabled.

        This is best-effort and must never break experiment execution.
        """
        try:
            if not self._codex_live_view.enabled():
                return

            launched = self._codex_live_view.launch(label=label, jsonl_path=jsonl_path, pid=pid)
            if not launched:
                # Keep this at DEBUG to avoid spamming the main terminal; it remains actionable for users.
                manual = self._codex_live_view.build_manual_command(label=label, jsonl_path=jsonl_path, pid=pid)
                self.logger.debug(f"Live view not launched (label={label}). Manual command: {manual}")
        except Exception as e:
            self.logger.debug(f"Live view spawn failed (ignored): {e}")

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

    def _ensure_uv_available(self):
        """
        Ensure `uv` is available.

        This project relies on Astral's `uv` as the dependency manager for:
        - Controller execution (recommended: `uv run python main.py`)
        - Per-worktree environment setup (`uv sync`)

        IMPORTANT: We deliberately avoid "helpful" system mutations here (apt/yum/brew/npm),
        because they are risky and often incorrect in minimal/CI environments.
        """
        if self._uv_cmd and os.path.exists(self._uv_cmd):
            return

        uv_path = shutil.which("uv")
        if uv_path:
            self._uv_cmd = uv_path
            return

        # Common fallbacks when uv is installed but PATH isn't configured.
        candidate_paths = [
            os.path.abspath(os.path.join(os.getcwd(), ".venv", "bin", "uv")),
            os.path.expanduser("~/.local/bin/uv"),
        ]
        for candidate in candidate_paths:
            if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                self._uv_cmd = candidate
                return

        if self.config.get("auto_install_uv", False):
            # Safer (still mutating) alternative: install into the current Python environment.
            # This avoids system package managers and keeps the change scoped to Python tooling.
            self.logger.warning("uv not found. auto_install_uv=true: attempting `python -m pip install --user uv`")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--user", "uv"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "Failed to auto-install uv via pip. "
                    f"stdout_tail={result.stdout[-500:] if result.stdout else ''} "
                    f"stderr_tail={result.stderr[-500:] if result.stderr else ''}"
                )

            # Re-check after install.
            uv_path = shutil.which("uv")
            if uv_path:
                self._uv_cmd = uv_path
                return
            for candidate in candidate_paths:
                if os.path.exists(candidate) and os.access(candidate, os.X_OK):
                    self._uv_cmd = candidate
                    return

        raise RuntimeError(
            "uv command not found. Install Astral uv and ensure it's on PATH "
            "(recommended: `curl -LsSf https://astral.sh/uv/install.sh | sh`). "
            "Alternatively set config `auto_install_uv=true` to attempt a user-scoped pip install."
        )

    def _get_uv_cmd(self) -> str:
        """Return the resolved `uv` command (absolute path if available)."""
        self._ensure_uv_available()
        if not self._uv_cmd:
            # Defensive; should be set by _ensure_uv_available()
            raise RuntimeError("uv command not resolved")
        return self._uv_cmd

    def launch_experiments(self, hypotheses: List[ExperimentHypothesis], total_waas: Optional[int] = None) -> Dict[str, any]:
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

        # Total WAAs for GPU allocation should reflect the configured parallel slots (not just the
        # number of hypotheses in this specific launch call). In evolution mode, new hypotheses
        # may occupy higher-numbered exp slots even when only a subset of slots are being launched.
        effective_total_waas = total_waas if total_waas is not None else len(hypotheses)

        # Log GPU allocation summary
        self.logger.info(self.gpu_allocator.get_allocation_summary(effective_total_waas))

        use_codex_execution = not self.simulation_mode
        processes_to_start = []
        # Ensure dependency manager is present before syncing environments
        self._ensure_uv_available()
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

                # Track worktree for later result collection
                self.experiment_worktree_map[exp_id] = worktree_path

                # Copy kaggle_data to worktree for WAA access
                kaggle_data_src = os.path.join(self.experiment_run_dir, "kaggle_data")
                worktree_kaggle_data = os.path.join(worktree_path, "kaggle_data")
                if os.path.exists(kaggle_data_src) and not os.path.exists(worktree_kaggle_data):
                    try:
                        shutil.copytree(kaggle_data_src, worktree_kaggle_data)
                        self.logger.info(f"Copied kaggle_data to worktree: {worktree_path}")
                    except Exception as copy_error:
                        self.logger.warning(f"Failed to copy kaggle_data to worktree: {copy_error}")

                # Copy crawler data to worktree if available
                crawler_src = os.path.join("kaggle_competitions", self.config.get("kaggle_competition_name", ""))
                worktree_crawler = os.path.join(worktree_path, "kaggle_competitions", self.config.get("kaggle_competition_name", ""))
                if os.path.exists(crawler_src) and not os.path.exists(worktree_crawler):
                    try:
                        shutil.copytree(crawler_src, worktree_crawler, dirs_exist_ok=True)
                        self.logger.info(f"Copied crawler data to worktree: {worktree_path}")
                    except Exception as copy_error:
                        self.logger.warning(f"Failed to copy crawler data to worktree: {copy_error}")

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

                # Copy the per-experiment task markdown into the worktree
                task_src = hypothesis.task_markdown_path
                task_dst = os.path.join(worktree_path, os.path.basename(task_src))
                try:
                    shutil.copy2(task_src, task_dst)
                    hypothesis.task_markdown_path = task_dst  # ensure execution uses the local copy
                    self.logger.info(f"Copied task markdown for {exp_id} to worktree")
                except Exception as copy_error:
                    self.logger.error(f"Failed to copy task markdown for {exp_id}: {copy_error}")
                    raise

                # Run uv sync to install dependencies
                try:
                    self.logger.info(f"Running 'uv sync' in worktree: {worktree_path}")
                    uv_env = os.environ.copy()
                    # Ensure per-worktree environment by ignoring parent virtualenv
                    uv_env.pop("VIRTUAL_ENV", None)
                    result = subprocess.run(
                        [self._get_uv_cmd(), 'sync'],
                        cwd=worktree_path,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 minutes timeout
                        env=uv_env
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
                gpu_allocation = self.gpu_allocator.allocate(waa_index, effective_total_waas)

                # Prepare environment with GPU settings
                env = os.environ.copy()
                env.update(gpu_allocation.env_vars)

                self.logger.info(f"GPU allocation for {exp_id}: "
                                f"CUDA_VISIBLE_DEVICES={gpu_allocation.cuda_visible_devices or 'N/A'}, "
                                f"memory_fraction={gpu_allocation.memory_fraction:.2f}, "
                                f"gpu_count={gpu_allocation.gpu_count}")

                # 2. Launch per execution mode
                if use_codex_execution:
                    # Codex mode: use codex exec with GPU env vars
                    process = self._launch_codex_experiment(hypothesis, worktree_path, exp_id, env=env, gpu_allocation=gpu_allocation)
                else:
                    # Simulation mode: use WAA simulator with GPU env vars
                    cmd = [
                        self._get_uv_cmd(), 'run', 'python', 'src/execution/wca_simulator.py',
                        '--worktree-path', worktree_path,
                        '--task-markdown-path', hypothesis.task_markdown_path,
                        '--experiment-id', exp_id,
                        '--log-level', self.config.get("log_level", "INFO")
                    ]
                    log_path = os.path.join(worktree_path, f"process_output_{exp_id}.log")
                    with open(log_path, "w", encoding="utf-8") as log_file:
                        process = subprocess.Popen(
                            cmd,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            text=True,
                            env=env,
                            cwd=worktree_path
                        )

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
             self.logger.info(f"Launched {'Codex' if use_codex_execution else 'WAA simulator'} process for experiment {exp_id} (PID: {process.pid})")

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

            # Avoid deadlock: codex emits a chatty JSONL stream; writing to a PIPE without
            # continuously draining it can fill the OS pipe buffer and stall the subprocess.
            # Stream stdout directly to a file in the worktree instead.
            jsonl_path = os.path.join(worktree_path, f"codex_output_{exp_id}.jsonl")
            with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=jsonl_file,
                    stderr=subprocess.STDOUT,
                    cwd=worktree_path,
                    text=True,
                    env=env or os.environ
                )

            # Send stdin asynchronously (avoid blocking)
            if process.stdin:
                process.stdin.write(stdin_input)
                process.stdin.close()

            self._maybe_spawn_live_view(label=exp_id, jsonl_path=jsonl_path, pid=process.pid)

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
                    # Only finalize after Codex process has actually exited
                    if process.poll() is None:
                        grace_seconds = int(self.config.get("process_completion_grace_seconds", 120))
                        started_at = self._completion_grace_started_at.get(exp_id)
                        if started_at is None:
                            self._completion_grace_started_at[exp_id] = time.time()
                            self.logger.debug(
                                f"Experiment {exp_id} marked COMPLETE but process still running; "
                                f"starting grace timer ({grace_seconds}s)."
                            )
                            still_active_processes[exp_id] = (process, worktree_path)
                        else:
                            elapsed = time.time() - started_at
                            if elapsed >= grace_seconds:
                                self.logger.warning(
                                    f"Experiment {exp_id} marked COMPLETE but process still running after "
                                    f"{elapsed:.1f}s (grace={grace_seconds}s). Terminating process."
                                )
                                try:
                                    process.terminate()
                                    process.wait(timeout=10)
                                except Exception:
                                    try:
                                        process.kill()
                                    except Exception:
                                        pass
                                self._finalize_completed_experiment(exp_id, process, worktree_path)
                                completed_ids.append(exp_id)
                                self._completion_grace_started_at.pop(exp_id, None)
                            else:
                                still_active_processes[exp_id] = (process, worktree_path)
                    else:
                        self._finalize_completed_experiment(exp_id, process, worktree_path)
                        completed_ids.append(exp_id)
                        self._completion_grace_started_at.pop(exp_id, None)
                    continue
                elif current_status.status == SessionStatus.ERROR:
                    # Error state, mark failed and collect what we can
                    self._handle_error_experiment(exp_id, process, worktree_path, current_status)
                    completed_ids.append(exp_id)
                    self._completion_grace_started_at.pop(exp_id, None)
                    continue
                elif current_status.status == SessionStatus.RUNNING:
                    # Clear any stale completion grace tracking if the experiment reports RUNNING.
                    self._completion_grace_started_at.pop(exp_id, None)
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
                if process.poll() is None:
                    grace_seconds = int(self.config.get("process_completion_grace_seconds", 120))
                    started_at = self._completion_grace_started_at.get(exp_id)
                    if started_at is None:
                        self._completion_grace_started_at[exp_id] = time.time()
                        self.logger.debug(
                            f"DONE file present for {exp_id} but process still running; "
                            f"starting grace timer ({grace_seconds}s)."
                        )
                        still_active_processes[exp_id] = (process, worktree_path)
                    else:
                        elapsed = time.time() - started_at
                        if elapsed >= grace_seconds:
                            self.logger.warning(
                                f"DONE file present for {exp_id} but process still running after "
                                f"{elapsed:.1f}s (grace={grace_seconds}s). Terminating process."
                            )
                            try:
                                process.terminate()
                                process.wait(timeout=10)
                            except Exception:
                                try:
                                    process.kill()
                                except Exception:
                                    pass
                            self._finalize_completed_experiment(exp_id, process, worktree_path)
                            completed_ids.append(exp_id)
                            self._completion_grace_started_at.pop(exp_id, None)
                        else:
                            still_active_processes[exp_id] = (process, worktree_path)
                else:
                    self._finalize_completed_experiment(exp_id, process, worktree_path)
                    completed_ids.append(exp_id)
                    self._completion_grace_started_at.pop(exp_id, None)
            elif process.poll() is not None:
                # Process exited without DONE or status file
                self._handle_unexpected_exit(exp_id, process, worktree_path)
                completed_ids.append(exp_id)
                self._completion_grace_started_at.pop(exp_id, None)
            else:
                still_active_processes[exp_id] = (process, worktree_path)
                self._completion_grace_started_at.pop(exp_id, None)

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
        # Do not kill or wait—finalization should only occur after the process has exited
        if process and process.poll() is None:
            self.logger.info(f"Process for {exp_id} still running; deferring finalization.")
            return

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
        if self.simulation_mode:
            marker = os.path.join(worktree_path, f"{self._dry_run_training_done_prefix}{exp_id}")
            return os.path.exists(marker)

        # Get or create resource monitor for this experiment
        if exp_id not in self._resource_monitors:
            self._resource_monitors[exp_id] = ResourceMonitor(worktree_path, self.logger)

        monitor = self._resource_monitors[exp_id]
        idle_threshold = self.config.get("training_idle_threshold_minutes", 3)

        return monitor.is_training_likely_complete(idle_threshold_minutes=idle_threshold)

    def _trigger_resume(self, exp_id: str, process: subprocess.Popen, worktree_path: str) -> bool:
        """Trigger Codex resume using `codex resume --last`."""
        self.logger.info(f"Triggering session resume for {exp_id}")

        if self.simulation_mode:
            # Dry-run: re-run the simulator in resume mode (blocking) to finalize outputs.
            task_path = os.path.join(worktree_path, f"{exp_id}_task.md")
            if not os.path.exists(task_path):
                try:
                    candidates = [
                        os.path.join(worktree_path, f)
                        for f in os.listdir(worktree_path)
                        if f.endswith("_task.md") and exp_id in f
                    ]
                    if candidates:
                        task_path = candidates[0]
                except Exception:
                    pass

            cmd = [
                self._get_uv_cmd(), "run", "python", "src/execution/wca_simulator.py",
                "--worktree-path", worktree_path,
                "--task-markdown-path", task_path,
                "--experiment-id", exp_id,
                "--log-level", self.config.get("log_level", "INFO"),
                "--resume",
            ]

            try:
                result = subprocess.run(
                    cmd,
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    timeout=self.config.get("waa_resume_timeout", 600),
                    check=False
                )
                if result.returncode == 0:
                    self.logger.info(f"Dry-run resume completed for {exp_id}")
                    self.session_manager.log_session_event(exp_id, "RESUME", SessionStatus.RUNNING)
                    return True

                self.logger.error(
                    f"Dry-run resume failed for {exp_id} (exit={result.returncode}). "
                    f"stdout_tail={result.stdout[-500:] if result.stdout else ''} "
                    f"stderr_tail={result.stderr[-500:] if result.stderr else ''}"
                )
                return False
            except subprocess.TimeoutExpired:
                self.logger.error(f"Dry-run resume timed out for {exp_id}")
                return False
            except Exception as e:
                self.logger.error(f"Dry-run resume failed for {exp_id}: {e}")
                return False

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
        if self.simulation_mode or process is None:
            return  # Only for Codex mode

        try:
            jsonl_path = os.path.join(worktree_path, f"codex_output_{exp_id}.jsonl")
            # Newer launch path streams Codex JSONL directly to this file to avoid pipe deadlocks.
            if os.path.exists(jsonl_path):
                return

            # Backward-compatible fallback: if stdout was piped, drain it now.
            if process.stdout:
                jsonl_output = process.stdout.read()
                if jsonl_output:
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
            # Remove worktree via git to avoid "branch is checked out" warnings
            try:
                self.repo.git.worktree('remove', '-f', worktree_path)
            except git.GitCommandError as wt_err:
                self.logger.warning(f"git worktree remove failed for {worktree_path}: {wt_err.stderr}")

            # Prune metadata and delete branch
            self.repo.git.worktree('prune')
            try:
                branch_name = f"exp/{exp_id}"
                self.repo.git.branch('-D', branch_name)
                self.logger.info(f"Deleted branch {branch_name}")
            except git.GitCommandError as branch_error:
                 # Branch may already be gone; safe to ignore
                 self.logger.warning(f"Could not delete branch exp/{exp_id}: {branch_error.stderr}. It might have been deleted already.")

            # Remove the physical directory if it still exists
            remove_dir(worktree_path)

            self._log_end(method_name)
        except git.GitCommandError as e:
            self.logger.error(f"Git command failed during cleanup for {exp_id}: {e.stderr}")
        except Exception as e:
            self._log_error(method_name, e)

    # ========== Evolution: Continuation Launching and Archival ==========

    def launch_continuation_experiments(
        self,
        continuations: List[ContinuationHypothesis],
        total_waas: int
    ) -> Dict[str, any]:
        """
        Launch continuation experiments that REUSE existing worktrees.

        Unlike launch_experiments(), this does NOT create new worktrees.
        Instead, it:
        1. Copies the new task markdown to the existing worktree
        2. Resets the experiment status
        3. Launches Codex with resume context

        Args:
            continuations: List of ContinuationHypothesis objects
            total_waas: Total number of WAAs running (for GPU allocation)

        Returns:
            Dict with keys: 'launched', 'failed', 'total'
        """
        method_name = "launch_continuation_experiments"
        self._log_start(method_name, num_continuations=len(continuations))
        launched_ids = []
        failed_launches = []

        for continuation in continuations:
            cont_id = continuation.continuation_id
            exp_id = continuation.experiment_id  # Original experiment ID
            worktree_path = continuation.worktree_path

            try:
                # Validate worktree exists
                if not os.path.exists(worktree_path):
                    raise FileNotFoundError(f"Worktree not found: {worktree_path}")

                # Copy new task markdown to worktree
                task_src = continuation.task_markdown_path
                task_dst = os.path.join(worktree_path, f"{cont_id}_task.md")
                if os.path.exists(task_src):
                    shutil.copy2(task_src, task_dst)
                    self.logger.info(f"Copied continuation task to {task_dst}")

                # Reset experiment status for continuation
                self.session_manager.create_status_file(worktree_path, cont_id)
                self.logger.info(f"Reset status file for continuation: {cont_id}")

                # Track worktree mapping for continuation ID and original experiment
                self.experiment_worktree_map[cont_id] = worktree_path
                self.experiment_worktree_map[exp_id] = worktree_path

                # Save continuation metadata
                metadata = {
                    "continuation_id": cont_id,
                    "original_experiment_id": exp_id,
                    "iteration": continuation.iteration,
                    "original_strategy": continuation.original_strategy_name,
                    "parent_score": continuation.parent_score,
                    "improvement_instructions": continuation.improvement_instructions,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                metadata_path = os.path.join(worktree_path, f"continuation_{cont_id}.json")
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)

                # Save hypothesis-style metadata for the continuation so RAD can preserve strategy info.
                # RAD currently looks for hypothesis_{exp_id}.json in the worktree as a fallback.
                try:
                    hypothesis_metadata = {
                        "experiment_id": cont_id,
                        "iteration": continuation.iteration,
                        "strategy_name": continuation.original_strategy_name,
                        "parameters": continuation.new_parameters,
                        "task_markdown_path": task_dst,
                        "parent_experiment_id": exp_id,
                    }
                    hypothesis_path = os.path.join(worktree_path, f"hypothesis_{cont_id}.json")
                    with open(hypothesis_path, "w", encoding="utf-8") as f:
                        json.dump(hypothesis_metadata, f, indent=2)
                    self.logger.debug(f"Saved continuation hypothesis metadata to {hypothesis_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to save continuation hypothesis metadata: {e}")

                # Launch experiment using Codex or simulator
                if self.simulation_mode:
                    # Simulation mode (still exercise GPU allocation env vars)
                    waa_index = GPUAllocator.parse_waa_index(cont_id)
                    gpu_allocation = self.gpu_allocator.allocate(waa_index, total_waas)
                    env = os.environ.copy()
                    env.update(gpu_allocation.env_vars)
                    process = self._launch_simulation_process(cont_id, worktree_path, task_dst, env=env)
                else:
                    # Codex mode - use resume with continuation context
                    process = self._launch_continuation_codex(continuation, worktree_path, task_dst, total_waas)

                if process:
                    self.active_processes[cont_id] = (process, worktree_path)
                    launched_ids.append(cont_id)
                    self.logger.info(f"Launched continuation {cont_id} in existing worktree {worktree_path}")
                else:
                    failed_launches.append({"exp_id": cont_id, "reason": "Process launch returned None"})

            except Exception as e:
                self.logger.error(f"Failed to launch continuation {cont_id}: {e}")
                failed_launches.append({"exp_id": cont_id, "reason": str(e)})

        result = {
            "launched": launched_ids,
            "failed": failed_launches,
            "total": len(continuations)
        }
        self._log_end(method_name, result=result)
        return result

    def _launch_continuation_codex(
        self,
        continuation: ContinuationHypothesis,
        worktree_path: str,
        task_path: str,
        total_waas: int
    ) -> Optional[subprocess.Popen]:
        """Launch Codex for a continuation experiment with resume context."""
        cont_id = continuation.continuation_id

        try:
            # Read continuation task markdown
            with open(task_path, 'r', encoding='utf-8') as f:
                task_content = f.read()

            # Get GPU allocation
            waa_index = GPUAllocator.parse_waa_index(cont_id)
            gpu_allocation = self.gpu_allocator.allocate(waa_index, total_waas)

            # Prepare environment with GPU settings
            env = os.environ.copy()
            env.update(gpu_allocation.env_vars)

            # Prepare hardware allocation info
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

            # Build continuation context
            continuation_context = f"""
**CONTINUATION EXPERIMENT**
This is a CONTINUATION experiment building on {continuation.experiment_id}.
Parent experiment achieved score: {continuation.parent_score:.4f}

Your task: Implement the improvements described below in the existing codebase.
DO NOT start from scratch - build on what already exists in this worktree.

Output files should use the continuation ID: {cont_id}
- Result file: result_{cont_id}.json
- Submission file: submission_{cont_id}.csv
- Done marker: DONE_{cont_id}

"""

            # Prepare stdin for Codex
            stdin_input = f"""{continuation_context}
{hardware_info}
**TASK:**
{task_content}

Please execute the continuation experiment exactly as described above. Ensure you:
1. Create the result_{cont_id}.json file with the score
2. Create the DONE_{cont_id} file when complete
3. Save predictions to submission_{cont_id}.csv
"""

            # Start codex exec in background with --json flag for JSONL output
            codex_config = self.config.get("codex", {})
            cmd = ['codex', 'exec', '--json']

            if codex_config.get("skip_confirmation", True):
                cmd.append('--skip-git-repo-check')

            # Avoid deadlock on chatty JSONL: stream Codex stdout to a file instead of a PIPE.
            jsonl_path = os.path.join(worktree_path, f"codex_output_{cont_id}.jsonl")
            with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=jsonl_file,
                    stderr=subprocess.STDOUT,
                    cwd=worktree_path,
                    text=True,
                    env=env
                )

            # Send stdin asynchronously (avoid blocking)
            if process.stdin:
                process.stdin.write(stdin_input)
                process.stdin.close()

            self._maybe_spawn_live_view(label=cont_id, jsonl_path=jsonl_path, pid=process.pid)

            self.logger.info(f"Launched Codex continuation process for {cont_id} in {worktree_path}")
            return process

        except FileNotFoundError as e:
            self.logger.error(f"Codex CLI not found or task file missing. Error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to launch Codex for continuation {cont_id}: {e}")
            return None

    def _launch_simulation_process(
        self,
        exp_id: str,
        worktree_path: str,
        task_path: str,
        env: Optional[Dict[str, str]] = None
    ) -> Optional[subprocess.Popen]:
        """Launch simulation process for a continuation experiment."""
        try:
            log_path = os.path.join(worktree_path, f"process_output_{exp_id}.log")
            with open(log_path, "w", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    [
                        self._get_uv_cmd(), 'run', 'python', 'src/execution/wca_simulator.py',
                        '--worktree-path', worktree_path,
                        '--task-markdown-path', task_path,
                        '--experiment-id', exp_id,
                        '--log-level', self.config.get("log_level", "INFO"),
                    ],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=worktree_path,
                    env=env or os.environ.copy()
                )
            return process
        except Exception as e:
            self.logger.error(f"Failed to launch simulation for {exp_id}: {e}")
            return None

    def archive_worktree(
        self,
        exp_id: str,
        worktree_path: str,
        termination_reason: Optional[str] = None
    ) -> Optional[str]:
        """
        Archive a terminated experiment's worktree instead of deleting it.

        Moves the worktree to archived_experiments/ directory with metadata.

        Args:
            exp_id: Experiment ID
            worktree_path: Path to the worktree
            termination_reason: Optional reason for termination

        Returns:
            Archive path if successful, None otherwise
        """
        method_name = "archive_worktree"
        self._log_start(method_name, exp_id=exp_id, path=worktree_path)

        try:
            # Ensure source exists before touching git metadata
            if not os.path.exists(worktree_path):
                self.logger.warning(f"Worktree path does not exist: {worktree_path}")
                return None

            # Create archive directory
            archive_base = os.path.join(self.experiment_run_dir, "archived_experiments")
            ensure_dir(archive_base)

            # Generate archive name with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"{exp_id}_archived_{timestamp}"
            archive_path = os.path.join(archive_base, archive_name)

            # Create archive metadata
            metadata = {
                "experiment_id": exp_id,
                "original_path": worktree_path,
                "archived_at": datetime.datetime.now().isoformat(),
                "termination_reason": termination_reason,
                "archive_path": archive_path
            }

            # Worktree directory name corresponds to the branch name used when the worktree was created
            # (e.g., worktrees/<exp_id> with branch refs/heads/exp/<exp_id>). Continuations reuse the
            # same worktree, so exp_id may differ from the underlying branch/worktree id.
            worktree_id = os.path.basename(os.path.normpath(worktree_path))

            # Move worktree to archive before running git cleanup to avoid deleting contents
            shutil.move(worktree_path, archive_path)
            self.logger.info(f"Moved worktree to archive: {archive_path}")

            # Save archive metadata
            metadata_path = os.path.join(archive_path, "archive_metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Clean git metadata after the move; prune will drop stale entries
            try:
                self.repo.git.worktree('prune')
            except git.GitCommandError:
                pass

            # Delete the experiment branch
            try:
                branch_name = f"exp/{worktree_id}"
                self.repo.git.branch('-D', branch_name)
                self.logger.info(f"Deleted branch {branch_name}")
            except git.GitCommandError as e:
                self.logger.warning(f"Could not delete branch: {e}")

            self._log_end(method_name, result=archive_path)
            return archive_path

        except Exception as e:
            self._log_error(method_name, e)
            return None

    def get_active_worktree_paths(self) -> Dict[str, str]:
        """
        Get all active worktree paths.

        Returns:
            Dict mapping experiment_id to worktree_path
        """
        worktree_map = {}
        try:
            # List all worktrees managed by git
            worktree_list = self.repo.git.worktree('list', '--porcelain')
            current_path = None
            current_branch = None

            for line in worktree_list.splitlines():
                if line.startswith('worktree '):
                    current_path = line[9:]  # Remove 'worktree ' prefix
                elif line.startswith('branch refs/heads/exp/'):
                    current_branch = line[22:]  # Extract exp_id from branch name
                    if current_path and current_branch and self.worktree_base_dir in current_path:
                        # This is one of our managed worktrees
                        worktree_map[current_branch] = current_path
                    current_path = None
                    current_branch = None
                elif line == '':
                    # Reset for next worktree entry
                    current_path = None
                    current_branch = None

        except Exception as e:
            self.logger.error(f"Failed to list worktrees: {e}")

        return worktree_map

    def get_worktree_path(self, exp_id: str) -> Optional[str]:
        """Return the worktree path for a given experiment ID."""
        # Prefer active process mapping
        if exp_id in self.active_processes:
            return self.active_processes[exp_id][1]

        # Use stored worktree map if available
        mapped_path = self.experiment_worktree_map.get(exp_id)
        if mapped_path and os.path.exists(mapped_path):
            return mapped_path

        # Fallback: scan known worktrees for continuation markers
        try:
            for entry in os.listdir(self.worktree_base_dir):
                candidate = os.path.join(self.worktree_base_dir, entry)
                if not os.path.isdir(candidate):
                    continue
                continuation_marker = os.path.join(candidate, f"continuation_{exp_id}.json")
                done_marker = os.path.join(candidate, f"DONE_{exp_id}")
                if os.path.exists(continuation_marker) or os.path.exists(done_marker):
                    # Cache for future lookups
                    self.experiment_worktree_map[exp_id] = candidate
                    return candidate
        except FileNotFoundError:
            pass

        # Completed experiments drop from active_processes; reconstruct path (may be wrong for continuations)
        path = os.path.join(self.worktree_base_dir, exp_id)
        # Caller can check existence as needed
        return path
