import os
import shutil
import time
import uuid
import subprocess
import multiprocessing
from typing import List, Dict, Tuple, Optional
import git # GitPython

from ..core.base_component import BaseComponent
from ..data_models import ExperimentHypothesis
from ..utils.file_utils import ensure_dir, remove_dir
from .codex_launcher import CodexExperimentLauncher

class ExperimentOrchestrator(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.worktree_base_dir = os.path.abspath(os.path.join(self.experiment_run_dir, "worktrees"))
        self.wca_simulator_script = os.path.abspath(os.path.join(os.path.dirname(__file__), 'wca_simulator.py'))

        # Only ensure directory if not in dry-run mode
        if not config.get("dry_run", False):
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


    def launch_experiments(self, hypotheses: List[ExperimentHypothesis]) -> List[str]:
        """Launch WAA simulator or Codex processes in parallel for each hypothesis."""
        method_name = "launch_experiments"
        self._log_start(method_name, num_hypotheses=len(hypotheses))
        launched_ids = []

        # Respect available CPU cores to avoid over-parallelism
        max_workers = min(len(hypotheses), multiprocessing.cpu_count() * 2)  # e.g., up to 2x core count
        self.logger.info(f"Launching {len(hypotheses)} experiments with max {max_workers} parallel workers.")

        processes_to_start = []
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
                        self.logger.warning(f"uv sync failed: {result.stderr}")
                    else:
                        self.logger.info(f"uv sync completed in {worktree_path}")
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"uv sync timed out in {worktree_path}")
                except FileNotFoundError:
                    self.logger.error("uv command not found. Is uv installed?")
                except Exception as e:
                    self.logger.warning(f"Failed to run uv sync: {e}")

                # 2. Launch per execution mode
                if self.execution_mode == "codex":
                    # Codex mode: use codex exec
                    process = self._launch_codex_experiment(hypothesis, worktree_path, exp_id)
                else:
                    # Simulation mode: use WAA simulator
                    cmd = [
                        'python', self.wca_simulator_script,
                        '--worktree-path', worktree_path,
                        '--task-markdown-path', hypothesis.task_markdown_path,
                        '--experiment-id', exp_id,
                        '--log-level', self.config.get("log_level", "INFO")
                    ]
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

                if process:
                    processes_to_start.append((process, exp_id, worktree_path))
                    launched_ids.append(exp_id)

            except git.GitCommandError as e:
                self.logger.error(f"Git command failed for {exp_id} at {worktree_path}: {e.stderr}")
            except Exception as e:
                self.logger.error(f"Failed to prepare or launch experiment {exp_id}: {e}")

        # Register processes in bulk
        for process, exp_id, worktree_path in processes_to_start:
             self.active_processes[exp_id] = (process, worktree_path)
             self.logger.info(f"Launched {'Codex' if self.execution_mode == 'codex' else 'WAA simulator'} process for experiment {exp_id} (PID: {process.pid})")

        self._log_end(method_name, result=f"Launched {len(launched_ids)} processes.")
        return launched_ids

    def _launch_codex_experiment(self, hypothesis: ExperimentHypothesis, worktree_path: str, exp_id: str) -> Optional[subprocess.Popen]:
        """Launch a single experiment using Codex."""
        try:
            # Read task markdown
            with open(hypothesis.task_markdown_path, 'r', encoding='utf-8') as f:
                task_content = f.read()

            # Prepare stdin for Codex
            stdin_input = f"""Your Task:
{task_content}

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
                text=True
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
        """Check running experiment processes and return IDs that have completed."""
        method_name = "check_running_experiments"
        # self._log_start(method_name)  # Suppressed to avoid noisy logs
        completed_ids = []
        still_active_processes = {}

        if not self.active_processes:
            # self._log_end(method_name, result=[])
            return []

        for exp_id, (process, worktree_path) in self.active_processes.items():
            done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
            if os.path.exists(done_file_path):  # Use DONE file as completion signal
                # Check if process is still running
                poll_result = process.poll()
                if poll_result is None:  # Process is still running
                     self.logger.warning(f"DONE file found for {exp_id}, but process (PID: {process.pid}) is still running. Terminating process.")
                     try:
                          process.terminate()
                          # Give it a moment to terminate
                          time.sleep(2)
                          if process.poll() is None:  # Still not terminated
                               self.logger.error(f"Process {exp_id} did not terminate gracefully. Killing forcefully.")
                               process.kill()
                     except Exception as e:
                          self.logger.error(f"Error terminating process {exp_id}: {e}")

                # Save JSONL output from Codex process
                self._save_codex_jsonl_output(exp_id, process, worktree_path)

                self.logger.info(f"Experiment {exp_id} completed.")
                completed_ids.append(exp_id)
                # Prefer to clean worktree after RAD collects results
                # self.cleanup_worktree(exp_id, worktree_path)
            elif process.poll() is not None:  # Process has terminated
                 # No DONE file but process exited -> likely abnormal termination
                 self.logger.error(f"Process for experiment {exp_id} (PID: {process.pid}) terminated unexpectedly without creating DONE file. Marking as failed.")
                 # Save JSONL output even for failed experiments (for debugging)
                 self._save_codex_jsonl_output(exp_id, process, worktree_path)
                 # Create failure marker for downstream handling
                 with open(done_file_path, 'w') as f:
                     f.write("UNEXPECTED_FAILURE")
                 completed_ids.append(exp_id)
            else:
                # Still running
                still_active_processes[exp_id] = (process, worktree_path)

        self.active_processes = still_active_processes
        # if completed_ids:
        #     self.logger.info(f"Detected completed experiments: {completed_ids}")
        # self._log_end(method_name, result=completed_ids)
        return completed_ids

    def _save_codex_jsonl_output(self, exp_id: str, process: subprocess.Popen, worktree_path: str):
        """Save JSONL output from completed Codex process to worktree directory."""
        if self.execution_mode != "codex":
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
