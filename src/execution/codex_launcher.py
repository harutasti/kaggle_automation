#!/usr/bin/env python3
"""
Integration module for launching experiments using Codex.

This replaces the WCA simulator with real Codex execution.
Can be used by ExperimentOrchestrator to launch real ML experiments.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from ..utils.codex_executor import execute_with_retry, CodexResult
from ..data_models import ExperimentHypothesis


class CodexExperimentLauncher:
    """
    Launches Kaggle experiments using Codex.

    Designed to integrate with the existing ExperimentOrchestrator workflow:
    1. EO creates Git worktree
    2. EO calls this launcher with hypothesis
    3. Launcher executes Codex in worktree
    4. Returns result for RAD to collect
    """

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("AutoKaggle.CodexLauncher")

        # Configuration
        self.timeout = config.get("codex", {}).get("timeout", 3600)
        self.max_retries = config.get("codex", {}).get("max_retries", 2)
        self.enabled = config.get("codex", {}).get("enabled", True)

        # Validate Codex is available
        if self.enabled:
            self._validate_codex_available()

    def _validate_codex_available(self):
        """Check if Codex CLI is available"""
        import shutil
        if not shutil.which("codex"):
            self.logger.error("Codex CLI not found in PATH")
            raise RuntimeError(
                "Codex CLI not found. Please install it first.\n"
                "See: https://github.com/anthropics/anthropic-tools"
            )
        self.logger.info("Codex CLI found and ready")

    def launch_experiment(
        self,
        hypothesis: ExperimentHypothesis,
        worktree_path: str | Path
    ) -> CodexResult:
        """
        Launch a single experiment using Codex.

        Args:
            hypothesis: ExperimentHypothesis with task markdown path
            worktree_path: Path to Git worktree for isolated execution

        Returns:
            CodexResult with execution details and parsed results
        """
        self.logger.info(f"Launching Codex experiment: {hypothesis.experiment_id}")
        self.logger.debug(f"  Strategy: {hypothesis.strategy_name}")
        self.logger.debug(f"  Task: {hypothesis.task_markdown_path}")
        self.logger.debug(f"  Worktree: {worktree_path}")

        # Validate inputs
        if not Path(hypothesis.task_markdown_path).exists():
            self.logger.error(f"Task markdown not found: {hypothesis.task_markdown_path}")
            return CodexResult(
                success=False,
                experiment_id=hypothesis.experiment_id,
                execution_time=0.0,
                error="Task markdown file not found",
                error_type="CONFIGURATION_ERROR"
            )

        if not Path(worktree_path).exists():
            self.logger.error(f"Worktree not found: {worktree_path}")
            return CodexResult(
                success=False,
                experiment_id=hypothesis.experiment_id,
                execution_time=0.0,
                error="Worktree directory not found",
                error_type="CONFIGURATION_ERROR"
            )

        # Execute with retry logic
        result = execute_with_retry(
            task_markdown_path=hypothesis.task_markdown_path,
            worktree_path=worktree_path,
            experiment_id=hypothesis.experiment_id,
            timeout=self.timeout,
            max_retries=self.max_retries,
            logger=self.logger
        )

        # Log result
        if result.success:
            self.logger.info(
                f"Experiment {hypothesis.experiment_id} completed successfully. "
                f"Score: {result.result_data.get('score')}, "
                f"Time: {result.execution_time:.2f}s"
            )
        else:
            self.logger.error(
                f"Experiment {hypothesis.experiment_id} failed: "
                f"{result.error_type} - {result.error}"
            )

        return result

    def launch_experiments_parallel(
        self,
        hypotheses: list[ExperimentHypothesis],
        worktree_paths: dict[str, Path],
        max_parallel: int = 3
    ) -> dict[str, CodexResult]:
        """
        Launch multiple experiments in parallel (future enhancement).

        For now, launches sequentially. Can be enhanced with:
        - multiprocessing.Pool
        - concurrent.futures.ThreadPoolExecutor
        - asyncio for better resource management

        Args:
            hypotheses: List of experiment hypotheses
            worktree_paths: Mapping of experiment_id -> worktree_path
            max_parallel: Maximum parallel executions

        Returns:
            Dictionary mapping experiment_id -> CodexResult
        """
        self.logger.info(f"Launching {len(hypotheses)} experiments (sequential for now)")

        results = {}

        for hypothesis in hypotheses:
            worktree_path = worktree_paths.get(hypothesis.experiment_id)

            if not worktree_path:
                self.logger.error(f"No worktree path for {hypothesis.experiment_id}")
                results[hypothesis.experiment_id] = CodexResult(
                    success=False,
                    experiment_id=hypothesis.experiment_id,
                    execution_time=0.0,
                    error="Worktree path not provided",
                    error_type="CONFIGURATION_ERROR"
                )
                continue

            result = self.launch_experiment(hypothesis, worktree_path)
            results[hypothesis.experiment_id] = result

        # Summary
        successful = sum(1 for r in results.values() if r.success)
        self.logger.info(
            f"Batch complete: {successful}/{len(hypotheses)} successful"
        )

        return results


def convert_codex_result_to_experiment_result(codex_result: CodexResult) -> dict:
    """
    Convert CodexResult to format expected by RAD (ResultAggregatorDatabase).

    This bridges the gap between Codex executor and the existing result collection.
    """
    if codex_result.success:
        return {
            "experiment_id": codex_result.experiment_id,
            "status": "SUCCESS",
            "score": codex_result.result_data.get("score"),
            "execution_time": codex_result.execution_time,
            "result_file_path": str(Path(codex_result.output_file).parent / f"result_{codex_result.experiment_id}.json"),
            "metadata": {
                "codex_output": str(codex_result.output_file),
                "raw_output_preview": codex_result.raw_output[:500] if codex_result.raw_output else None
            }
        }
    else:
        return {
            "experiment_id": codex_result.experiment_id,
            "status": "FAILURE",
            "score": None,
            "execution_time": codex_result.execution_time,
            "error": codex_result.error,
            "error_type": codex_result.error_type,
            "metadata": {
                "codex_output": str(codex_result.output_file) if codex_result.output_file else None,
                "raw_output_preview": codex_result.raw_output[:500] if codex_result.raw_output else None
            }
        }


# Example integration with EO
if __name__ == "__main__":
    import json
    from ..data_models import ExperimentHypothesis

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Load config
    with open("config/config.json") as f:
        config = json.load(f)

    # Create launcher
    launcher = CodexExperimentLauncher(config)

    # Example: Create a test hypothesis
    hypothesis = ExperimentHypothesis(
        experiment_id="test_exp_001",
        iteration=0,
        strategy_name="TestStrategy",
        parameters={"test": True},
        task_markdown_path="experiments/hypotheses/test_exp_001_task.md"
    )

    # Launch
    result = launcher.launch_experiment(
        hypothesis=hypothesis,
        worktree_path="experiments/worktrees/test_exp_001"
    )

    # Convert for RAD
    rad_format = convert_codex_result_to_experiment_result(result)

    print("\nCodex Result:")
    print(json.dumps(rad_format, indent=2))
