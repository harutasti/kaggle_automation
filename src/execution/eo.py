import os
import time
import uuid
import subprocess
import multiprocessing
from typing import List, Dict, Tuple, Optional
import git # GitPython

from ..core.base_component import BaseComponent
from ..data_models import ExperimentHypothesis
from ..utils.file_utils import ensure_dir, remove_dir

class ExperimentOrchestrator(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.experiments_base_dir = config.get("experiments_base_dir", "./experiments")
        self.worktree_base_dir = os.path.abspath(os.path.join(self.experiments_base_dir, "worktrees"))
        self.wca_simulator_script = os.path.abspath(os.path.join(os.path.dirname(__file__), 'wca_simulator.py'))
        ensure_dir(self.worktree_base_dir)
        self.repo = self._get_git_repo()
        self.active_processes: Dict[str, Tuple[multiprocessing.Process, str]] = {} # {exp_id: (process, worktree_path)}

    def _get_git_repo(self):
        """現在のディレクトリのGitリポジトリを取得"""
        try:
            repo = git.Repo(search_parent_directories=True)
            self.logger.info(f"Git repository found at: {repo.working_dir}")
            # Worktreeの初期状態をクリーンアップ（前回の実行が中断した場合など）
            self._cleanup_stale_worktrees(repo)
            return repo
        except git.InvalidGitRepositoryError:
            self.logger.error("Git repository not found in the current directory or parent directories. Please run 'git init'.")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Git Repo object: {e}")
            raise

    def _cleanup_stale_worktrees(self, repo):
        """起動時に既存の管理下Worktreeがあれば削除試行"""
        self.logger.info("Checking for stale worktrees...")
        try:
            existing_worktrees = [wt for wt in repo.git.worktree('list').splitlines() if self.worktree_base_dir in wt]
            for line in existing_worktrees:
                path = line.split()[0]
                if os.path.exists(path): # 物理パスが存在するか確認
                    self.logger.warning(f"Found potentially stale worktree: {path}. Attempting removal.")
                    try:
                        # Git worktree prune で管理情報削除、その後物理ディレクトリ削除
                        repo.git.worktree('prune')
                        remove_dir(path)
                        self.logger.info(f"Successfully removed stale worktree: {path}")
                    except Exception as e:
                        self.logger.error(f"Failed to remove stale worktree {path}: {e}. Manual cleanup might be required.")
        except Exception as e:
            self.logger.error(f"Error during stale worktree cleanup: {e}")


    def launch_experiments(self, hypotheses: List[ExperimentHypothesis]) -> List[str]:
        """実験仮説に基づいてWCAシミュレータを並列起動する"""
        method_name = "launch_experiments"
        self._log_start(method_name, num_hypotheses=len(hypotheses))
        launched_ids = []

        # 利用可能なCPUコア数を考慮（過剰な並列化を防ぐ）
        max_workers = min(len(hypotheses), multiprocessing.cpu_count() * 2) # 例: CPUコア数の2倍まで
        self.logger.info(f"Launching {len(hypotheses)} experiments with max {max_workers} parallel workers.")

        processes_to_start = []
        for hypothesis in hypotheses:
            exp_id = hypothesis.experiment_id
            worktree_path = os.path.join(self.worktree_base_dir, exp_id)
            branch_name = f"exp/{exp_id}" # ブランチ名

            try:
                # 1. Git Worktreeを作成 (既存ならエラーになるので事前削除推奨 or 例外処理)
                if os.path.exists(worktree_path):
                     self.logger.warning(f"Worktree path {worktree_path} already exists. Skipping creation, assuming it's usable or will be cleaned later.")
                     # 必要であればここで削除・再作成のロジックを入れる
                     # remove_dir(worktree_path)
                     # self.repo.git.worktree('prune')
                else:
                     # mainブランチなど、起点となるブランチを指定
                     # ここではリポジトリの現在のHEADから作成
                     start_point = self.repo.head.commit
                     self.repo.git.worktree('add', '-b', branch_name, worktree_path, start_point)
                     self.logger.info(f"Created Git worktree at: {worktree_path} on branch {branch_name}")

                # 2. WCAシミュレータを別プロセスで起動
                cmd = [
                    'python', self.wca_simulator_script,
                    '--worktree-path', worktree_path,
                    '--task-markdown-path', hypothesis.task_markdown_path,
                    '--experiment-id', exp_id,
                    '--log-level', self.config.get("log_level", "INFO") # ログレベルを引き継ぐ
                ]
                # Use subprocess.Popen directly instead of multiprocessing.Process
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                processes_to_start.append((process, exp_id, worktree_path))
                launched_ids.append(exp_id)

            except git.GitCommandError as e:
                self.logger.error(f"Git command failed for {exp_id} at {worktree_path}: {e.stderr}")
            except Exception as e:
                self.logger.error(f"Failed to prepare or launch experiment {exp_id}: {e}")

        # プロセスを一括で開始
        for process, exp_id, worktree_path in processes_to_start:
             # No need to start process as Popen already starts it
             self.active_processes[exp_id] = (process, worktree_path)
             self.logger.info(f"Launched WCA simulator process for experiment {exp_id} (PID: {process.pid})")

        self._log_end(method_name, result=f"Launched {len(launched_ids)} processes.")
        return launched_ids

    # _run_wca_simulator method removed since we now use subprocess.Popen directly


    def check_running_experiments(self) -> List[str]:
        """実行中の実験プロセスが完了したか確認し、完了したIDのリストを返す"""
        method_name = "check_running_experiments"
        # self._log_start(method_name) # ログが多すぎる可能性があるのでコメントアウト
        completed_ids = []
        still_active_processes = {}

        if not self.active_processes:
             # self._log_end(method_name, result=[])
             return []

        for exp_id, (process, worktree_path) in self.active_processes.items():
            done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
            if os.path.exists(done_file_path): # 完了ファイルで判断
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

                self.logger.info(f"Experiment {exp_id} completed.")
                completed_ids.append(exp_id)
                # WorktreeのクリーンアップはRADが行った後が望ましいかもしれない
                # self.cleanup_worktree(exp_id, worktree_path)
            elif process.poll() is not None:  # Process has terminated
                 # 完了ファイルがないのにプロセスが終了している -> 異常終了の可能性
                 self.logger.error(f"Process for experiment {exp_id} (PID: {process.pid}) terminated unexpectedly without creating DONE file. Marking as failed.")
                 # エラー状態を示すために完了ファイルを作成
                 with open(done_file_path, 'w') as f:
                     f.write("UNEXPECTED_FAILURE")
                 completed_ids.append(exp_id)
            else:
                # まだ実行中
                still_active_processes[exp_id] = (process, worktree_path)

        self.active_processes = still_active_processes
        # if completed_ids:
        #     self.logger.info(f"Detected completed experiments: {completed_ids}")
        # self._log_end(method_name, result=completed_ids)
        return completed_ids

    def cleanup_worktree(self, exp_id: str, worktree_path: str):
        """指定されたWorktreeをクリーンアップする"""
        method_name = "cleanup_worktree"
        self._log_start(method_name, exp_id=exp_id, path=worktree_path)
        try:
            # Git worktree prune を先に実行して、Gitの管理情報から削除
            self.repo.git.worktree('prune')
            # 物理ディレクトリを削除
            remove_dir(worktree_path)
            # 対応するブランチも削除（任意）
            try:
                branch_name = f"exp/{exp_id}"
                self.repo.git.branch('-D', branch_name)
                self.logger.info(f"Deleted branch {branch_name}")
            except git.GitCommandError as branch_error:
                 # ブランチが存在しない場合などのエラーは無視してもよい場合がある
                 self.logger.warning(f"Could not delete branch exp/{exp_id}: {branch_error.stderr}. It might have been deleted already.")

            self._log_end(method_name)
        except git.GitCommandError as e:
            self.logger.error(f"Git command failed during cleanup for {exp_id}: {e.stderr}")
        except Exception as e:
            self._log_error(method_name, e)

    def get_worktree_path(self, exp_id: str) -> Optional[str]:
         """実験IDに対応するWorktreeのパスを取得"""
         if exp_id in self.active_processes:
             return self.active_processes[exp_id][1]
         # 完了したものはactive_processesから消えるので、パスを生成して返す
         # (ただし、cleanup_worktreeが呼ばれるとパスは存在しなくなる)
         path = os.path.join(self.worktree_base_dir, exp_id)
         # if os.path.exists(path): # 存在確認は呼び出し元で行うべきか？
         #     return path
         return path # パス自体は返す
