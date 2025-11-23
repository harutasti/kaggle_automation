import os
import json
import datetime
from typing import List, Dict, Optional

from ..core.base_component import BaseComponent
from ..data_models import ExperimentResult, ExperimentHypothesis
from ..utils.file_utils import ensure_dir, read_json, copy_file, move_file, write_json, read_markdown

class ResultAggregatorDatabase(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.results_base_dir = os.path.join(config.get("experiments_base_dir", "./experiments"), "results")
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

    def collect_result(self, exp_id: str, worktree_path: str) -> Optional[ExperimentResult]:
        """Collect results from a worktree and save them to the manifest."""
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
        potential_files = [f"submission_{exp_id}.csv", f"model_{exp_id}.pkl"]  # Add more if needed
        for fname in potential_files:
            src_path = os.path.join(worktree_path, fname)
            if os.path.exists(src_path):
                dst_relative = os.path.join(exp_id, fname)
                dst_absolute = os.path.join(self.results_base_dir, dst_relative)
                copy_file(src_path, dst_absolute)
                collected_files_relative.append(dst_relative)

        # Build ExperimentResult (start/end times are placeholder values)
        # TODO: Pull hypothesis info to populate iteration, strategy_name, parameters.
        #       That data is not stored in the worktree; pass from MCDU or recover from exp_id.
        dummy_start = datetime.datetime.now() - datetime.timedelta(minutes=1)
        dummy_end = datetime.datetime.now()
        dummy_duration = (dummy_end-dummy_start).total_seconds()

        result = ExperimentResult(
            experiment_id=exp_id,
            iteration=-1,  # To be populated
            strategy_name="Unknown",  # To be populated
            parameters={},  # To be populated
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
