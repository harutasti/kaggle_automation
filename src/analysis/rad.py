import os
import json
import re
import datetime
import glob
from typing import List, Dict, Optional

from ..core.base_component import BaseComponent
from ..data_models import ExperimentResult, ExperimentHypothesis
from ..utils.file_utils import ensure_dir, read_json, copy_file, move_file, write_json, read_markdown

class ResultAggregatorDatabase(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.results_base_dir = os.path.join(self.experiment_run_dir, "results")
        self.manifest_file = os.path.join(self.results_base_dir, "results_manifest.json")

        ensure_dir(self.results_base_dir)

        self.results_cache: Dict[str, ExperimentResult] = self._load_manifest()

    def _load_manifest(self) -> Dict[str, ExperimentResult]:
        """Load results from the manifest file."""
        manifest_data = read_json(self.manifest_file)
        cache = {}
        if manifest_data:
            # Convert JSON into ExperimentResult objects (simple approach)
            # A robust approach would use dataclasses-json, etc.
            for exp_id, data in manifest_data.items():
                 try:
                     # Convert datetime strings to datetime objects
                     data['start_time'] = datetime.datetime.fromisoformat(data['start_time']) if data.get('start_time') else None
                     data['end_time'] = datetime.datetime.fromisoformat(data['end_time']) if data.get('end_time') else None
                     # Derive execution_time_seconds if missing/None
                     if 'execution_time_seconds' not in data or data['execution_time_seconds'] is None:
                         if data.get('start_time') and data.get('end_time'):
                            data['execution_time_seconds'] = (data['end_time'] - data['start_time']).total_seconds()
                         else:
                            data['execution_time_seconds'] = 0.0  # Or another sensible default

                     cache[exp_id] = ExperimentResult(**data)
                 except Exception as e:
                     self.logger.error(f"Error loading result data for {exp_id} from manifest: {e}")
            self.logger.info(f"Loaded {len(cache)} results from manifest.")
        else:
             self.logger.info("Manifest file not found or empty. Starting with empty cache.")
        return cache

    def _save_manifest(self):
        """Persist the current results cache to the manifest file."""
        # Convert ExperimentResult objects into JSON-serializable dicts (simple approach)
        serializable_data = {}
        for exp_id, result in self.results_cache.items():
            data = result.__dict__.copy()
            data['start_time'] = result.start_time.isoformat() if result.start_time else None
            data['end_time'] = result.end_time.isoformat() if result.end_time else None
            serializable_data[exp_id] = data

        write_json(serializable_data, self.manifest_file)

    def collect_result(self, exp_id: str, worktree_path: str, hypothesis: Optional[ExperimentHypothesis] = None) -> Optional[ExperimentResult]:
        """Collect results from a worktree and save them to the manifest.

        Args:
            exp_id: Experiment identifier
            worktree_path: Path to the experiment worktree
            hypothesis: Optional hypothesis to populate metadata (iteration, strategy, params)
        """
        method_name = "collect_result"
        self._log_start(method_name, exp_id=exp_id, worktree_path=worktree_path)

        if not os.path.exists(worktree_path):
             self.logger.error(f"Worktree path does not exist: {worktree_path}")
             return None

        done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
        result_json_path = os.path.join(worktree_path, f"result_{exp_id}.json")
        waa_log_path = os.path.join(worktree_path, f"waa_{exp_id}.log")
        error_log_path = os.path.join(worktree_path, f"ERROR_{exp_id}.log")  # In case the WAA exits abnormally

        status = "UNKNOWN"
        if os.path.exists(done_file_path):
             with open(done_file_path, 'r') as f:
                 status = f.read().strip()
        else:
             self.logger.warning(f"DONE file not found for {exp_id}. Assuming failure.")
             status = "FAILURE_NO_DONE_FILE"


        result_data = read_json(result_json_path)
        score = result_data.get("score") if result_data else None
        error_message = None
        if status != "SUCCESS":
             if os.path.exists(error_log_path):
                  error_message = read_markdown(error_log_path)  # Read error log content
             elif status == "UNEXPECTED_FAILURE":
                  error_message = "WAA process terminated unexpectedly."
             elif status == "FAILURE_NO_DONE_FILE":
                  error_message = "DONE file was not created."
             else:  # status == "FAILURE" from DONE file
                  # Could inspect WAA logs for details (omitted)
                  error_message = "Simulated WAA failure or error during execution."


        # Copy result files and build list
        collected_files_relative = []  # Paths relative to results dir
        exp_result_dir = os.path.join(self.results_base_dir, exp_id)
        ensure_dir(exp_result_dir)

        # Always copy the WAA log
        collected_log_path_relative = os.path.join(exp_id, os.path.basename(waa_log_path))
        collected_log_path_absolute = os.path.join(self.results_base_dir, collected_log_path_relative)
        if os.path.exists(waa_log_path):
            copy_file(waa_log_path, collected_log_path_absolute)
        else:
             self.logger.warning(f"WAA log file not found: {waa_log_path}")
             collected_log_path_relative = None  # If log missing

        # Other potential outputs (submission, model, etc.)
        # First try exact matches for expected file names
        exact_files = [f"submission_{exp_id}.csv", f"model_{exp_id}.pkl"]
        for fname in exact_files:
            src_path = os.path.join(worktree_path, fname)
            if os.path.exists(src_path):
                dst_relative = os.path.join(exp_id, fname)
                dst_absolute = os.path.join(self.results_base_dir, dst_relative)
                copy_file(src_path, dst_absolute)
                collected_files_relative.append(dst_relative)

        # Then glob for common submission/prediction file patterns
        # This catches files like: predictions.csv, submission_final.csv, submission.csv, output.csv
        glob_patterns = [
            "*submission*.csv",
            "*prediction*.csv",
            "output.csv",
            "*.pkl",
            "*.joblib"
        ]

        for pattern in glob_patterns:
            matching_files = glob.glob(os.path.join(worktree_path, pattern))
            for src_path in matching_files:
                fname = os.path.basename(src_path)
                dst_relative = os.path.join(exp_id, fname)
                dst_absolute = os.path.join(self.results_base_dir, dst_relative)

                # Skip if already copied (from exact matches)
                if dst_relative not in collected_files_relative:
                    copy_file(src_path, dst_absolute)
                    collected_files_relative.append(dst_relative)
                    self.logger.info(f"Collected file via glob pattern '{pattern}': {fname}")

        # Copy JSONL output to codex-responses/WAA/ directory
        codex_output_jsonl = os.path.join(worktree_path, f"codex_output_{exp_id}.jsonl")
        if os.path.exists(codex_output_jsonl):
            # Parse experiment_id for naming: response-{parallel_id}-{iteration}.jsonl
            match = re.match(r'iter(\d+)_exp(\d+)_', exp_id)
            if match:
                iteration_num, parallel_id = match.groups()
                jsonl_filename = f"response-{parallel_id}-{iteration_num}.jsonl"
            else:
                jsonl_filename = f"response-{exp_id}.jsonl"

            codex_responses_waa_dir = os.path.join(
                self.experiment_run_dir, "codex-responses", "WAA"
            )
            ensure_dir(codex_responses_waa_dir)
            dst_path = os.path.join(codex_responses_waa_dir, jsonl_filename)
            copy_file(codex_output_jsonl, dst_path)
            self.logger.info(f"Copied JSONL output to {dst_path}")

        # Build ExperimentResult
        # Use hypothesis metadata if provided, otherwise use defaults
        dummy_start = datetime.datetime.now() - datetime.timedelta(minutes=1)
        dummy_end = datetime.datetime.now()
        dummy_duration = (dummy_end-dummy_start).total_seconds()

        # Extract metadata from hypothesis if available
        if hypothesis:
            iteration = hypothesis.iteration
            strategy_name = hypothesis.strategy_name
            parameters = hypothesis.parameters
            self.logger.info(f"Using hypothesis metadata: iteration={iteration}, strategy={strategy_name}")
        else:
            # Fallback 1: Try to load hypothesis metadata from worktree (saved by EO)
            iteration = -1
            strategy_name = "Unknown"
            parameters = {}
            hypothesis_metadata_path = os.path.join(worktree_path, f"hypothesis_{exp_id}.json")
            if os.path.exists(hypothesis_metadata_path):
                try:
                    with open(hypothesis_metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    iteration = metadata.get("iteration", -1)
                    strategy_name = metadata.get("strategy_name", "Unknown")
                    parameters = metadata.get("parameters", {})
                    self.logger.info(f"Loaded hypothesis metadata from worktree: iteration={iteration}, strategy={strategy_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to load hypothesis metadata from {hypothesis_metadata_path}: {e}")

            # Fallback 2: Try to extract iteration from exp_id pattern (e.g., "iter0_exp1_abc123")
            if iteration == -1:
                match = re.match(r'iter(\d+)_', exp_id)
                if match:
                    iteration = int(match.group(1))
                    self.logger.info(f"Extracted iteration {iteration} from exp_id")

        result = ExperimentResult(
            experiment_id=exp_id,
            iteration=iteration,
            strategy_name=strategy_name,
            parameters=parameters,
            start_time=dummy_start,  # Should be recorded/saved by WAA simulator
            end_time=dummy_end,     # Should be recorded/saved by WAA simulator
            execution_time_seconds=dummy_duration,  # Should be calculated/saved by WAA simulator
            score=score,
            result_files=collected_files_relative,
            log_path=collected_log_path_relative if collected_log_path_relative else "log_not_found",
            status=status,
            error_message=error_message
        )

        self.results_cache[exp_id] = result
        self._save_manifest()  # Persist results to disk

        self.logger.info(f"Collected result for {exp_id}. Status: {status}, Score: {score}")
        self._log_end(method_name, result=result)
        return result

    def get_result(self, exp_id: str) -> Optional[ExperimentResult]:
        """Fetch a single experiment result by ID."""
        return self.results_cache.get(exp_id)

    def get_all_results(self) -> List[ExperimentResult]:
        """Return all experiment results."""
        return list(self.results_cache.values())

    def get_results_by_iteration(self, iteration: int) -> List[ExperimentResult]:
        """Return results for a given iteration."""
        return [res for res in self.results_cache.values() if res.iteration == iteration]

    def update_result_metadata(self, exp_id: str, hypothesis: ExperimentHypothesis):
        """Update result metadata using hypothesis details after collection."""
        if exp_id in self.results_cache:
            result = self.results_cache[exp_id]
            result.iteration = hypothesis.iteration
            result.strategy_name = hypothesis.strategy_name
            result.parameters = hypothesis.parameters
            # TODO: If WAA records start/end/duration in result_{exp_id}.json,
            #       read and set those fields here.
            self._save_manifest()
            self.logger.info(f"Updated metadata for result {exp_id}")
        else:
             self.logger.warning(f"Cannot update metadata. Result not found for {exp_id}")
