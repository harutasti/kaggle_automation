#!/usr/bin/env python3
"""
Simple Codex executor optimized for AutoKaggler experiments.

Directly calls `codex exec` to run ML experiments using task markdown files.
No complex wrappers, sessions, or permissions - just execute and get results.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CodexResult:
    """Result from Codex execution"""
    success: bool
    experiment_id: str
    execution_time: float
    raw_output: str = ""
    error: Optional[str] = None
    error_type: Optional[str] = None
    output_file: Optional[Path] = None
    result_data: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.now)


def execute_codex_experiment(
    task_markdown_path: str | Path,
    worktree_path: str | Path,
    experiment_id: str,
    timeout: int = 3600,
    logger: Optional[logging.Logger] = None
) -> CodexResult:
    """
    Execute a Kaggle experiment using Codex.

    Args:
        task_markdown_path: Path to the task instruction markdown file
        worktree_path: Working directory (Git worktree) for the experiment
        experiment_id: Unique experiment identifier
        timeout: Maximum execution time in seconds (default: 1 hour)
        logger: Optional logger instance

    Returns:
        CodexResult with execution details and parsed results

    The function:
    1. Reads the task markdown as instruction
    2. Runs `codex exec` in the worktree directory
    3. Saves output to codex_output_{exp_id}.md
    4. Parses result_{exp_id}.json if created
    5. Returns structured result
    """
    # Setup
    task_markdown_path = Path(task_markdown_path)
    worktree_path = Path(worktree_path)
    output_file = worktree_path / f"codex_output_{experiment_id}.md"

    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor")

    # Validate inputs
    if not task_markdown_path.exists():
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=0.0,
            error=f"Task markdown not found: {task_markdown_path}",
            error_type="FILE_NOT_FOUND"
        )

    if not worktree_path.exists():
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=0.0,
            error=f"Worktree path not found: {worktree_path}",
            error_type="DIRECTORY_NOT_FOUND"
        )

    # Read task instructions
    try:
        task_content = task_markdown_path.read_text(encoding="utf-8")
    except Exception as e:
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=0.0,
            error=f"Failed to read task markdown: {e}",
            error_type="READ_ERROR"
        )

    # Prepare stdin: instruction file content + execution prompt
    stdin_input = f"""Your Task:
{task_content}

Please execute the experiment exactly as described above. Ensure you:
1. Create the result_{experiment_id}.json file with the score
2. Create the DONE_{experiment_id} file when complete
3. Save predictions to submission_{experiment_id}.csv
"""

    logger.info(f"Executing Codex for experiment {experiment_id}")
    logger.debug(f"Working directory: {worktree_path}")
    logger.debug(f"Task markdown: {task_markdown_path}")

    # Execute Codex
    start_time = time.time()

    try:
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check"],
            input=stdin_input.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(worktree_path),
            timeout=timeout,
            check=False
        )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        # Save output
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(raw_output, encoding="utf-8")

        logger.info(f"Codex completed in {execution_time:.2f}s (exit code: {proc.returncode})")

        # Check for Codex execution failure
        if proc.returncode != 0:
            logger.warning(f"Codex returned non-zero exit code: {proc.returncode}")
            return CodexResult(
                success=False,
                experiment_id=experiment_id,
                execution_time=execution_time,
                raw_output=raw_output,
                output_file=output_file,
                error=f"Codex execution failed with exit code {proc.returncode}",
                error_type="CODEX_ERROR"
            )

    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        logger.error(f"Codex execution timed out after {timeout}s")

        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            error=f"Execution timed out after {timeout}s",
            error_type="TIMEOUT"
        )

    except FileNotFoundError:
        execution_time = time.time() - start_time
        logger.error("Codex CLI not found. Is it installed and in PATH?")

        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            error="Codex CLI not found. Please install it first.",
            error_type="CODEX_NOT_FOUND"
        )

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Unexpected error during Codex execution: {e}", exc_info=True)

        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            error=f"Unexpected error: {e}",
            error_type="UNKNOWN_ERROR"
        )

    # Parse experiment results
    return _parse_experiment_results(
        experiment_id=experiment_id,
        worktree_path=worktree_path,
        execution_time=execution_time,
        raw_output=raw_output,
        output_file=output_file,
        logger=logger
    )


def _parse_experiment_results(
    experiment_id: str,
    worktree_path: Path,
    execution_time: float,
    raw_output: str,
    output_file: Path,
    logger: logging.Logger
) -> CodexResult:
    """
    Parse the results of an experiment execution.

    Looks for:
    - result_{exp_id}.json: Must contain {"score": <value>}
    - DONE_{exp_id}: Completion signal file
    - submission_{exp_id}.csv: Optional predictions file
    """
    result_file = worktree_path / f"result_{experiment_id}.json"
    done_file = worktree_path / f"DONE_{experiment_id}"
    submission_file = worktree_path / f"submission_{experiment_id}.csv"

    # Check for completion signal
    if not done_file.exists():
        logger.warning(f"DONE file not found: {done_file}")
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error="Experiment did not complete (DONE file not created)",
            error_type="INCOMPLETE"
        )

    # Check for result file
    if not result_file.exists():
        logger.error(f"Result file not found: {result_file}")
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error="Result file not created",
            error_type="MISSING_RESULT"
        )

    # Parse result JSON
    try:
        with open(result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        # Validate required fields
        if "score" not in result_data:
            logger.error("Result file missing 'score' field")
            return CodexResult(
                success=False,
                experiment_id=experiment_id,
                execution_time=execution_time,
                raw_output=raw_output,
                output_file=output_file,
                result_data=result_data,
                error="Result file missing required 'score' field",
                error_type="INVALID_RESULT"
            )

        logger.info(f"Successfully parsed results. Score: {result_data.get('score')}")

        # Check for submission file (optional but good to note)
        if not submission_file.exists():
            logger.warning(f"Submission file not created: {submission_file}")

        return CodexResult(
            success=True,
            experiment_id=experiment_id,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            result_data=result_data
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse result JSON: {e}")
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error=f"Failed to parse result JSON: {e}",
            error_type="JSON_PARSE_ERROR"
        )

    except Exception as e:
        logger.error(f"Unexpected error parsing results: {e}", exc_info=True)
        return CodexResult(
            success=False,
            experiment_id=experiment_id,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error=f"Unexpected error parsing results: {e}",
            error_type="PARSE_ERROR"
        )


def execute_with_retry(
    task_markdown_path: str | Path,
    worktree_path: str | Path,
    experiment_id: str,
    timeout: int = 3600,
    max_retries: int = 2,
    logger: Optional[logging.Logger] = None
) -> CodexResult:
    """
    Execute Codex with retry logic for transient failures.

    Args:
        task_markdown_path: Path to task markdown
        worktree_path: Working directory
        experiment_id: Experiment ID
        timeout: Timeout per attempt
        max_retries: Maximum number of retry attempts
        logger: Optional logger

    Returns:
        CodexResult from the last attempt
    """
    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor")

    for attempt in range(max_retries + 1):
        if attempt > 0:
            logger.info(f"Retry attempt {attempt}/{max_retries} for experiment {experiment_id}")
            time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s...

        result = execute_codex_experiment(
            task_markdown_path=task_markdown_path,
            worktree_path=worktree_path,
            experiment_id=experiment_id,
            timeout=timeout,
            logger=logger
        )

        # Success or non-retryable error
        if result.success:
            if attempt > 0:
                logger.info(f"Experiment succeeded on retry {attempt}")
            return result

        # Don't retry certain errors
        non_retryable_errors = {
            "FILE_NOT_FOUND",
            "DIRECTORY_NOT_FOUND",
            "CODEX_NOT_FOUND",
            "READ_ERROR"
        }

        if result.error_type in non_retryable_errors:
            logger.error(f"Non-retryable error: {result.error_type}")
            return result

        # Last attempt
        if attempt == max_retries:
            logger.error(f"All {max_retries + 1} attempts failed for experiment {experiment_id}")
            return result

        logger.warning(f"Attempt {attempt + 1} failed: {result.error}. Retrying...")

    return result


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Example: Execute a test experiment
    result = execute_codex_experiment(
        task_markdown_path="experiments/hypotheses/iter0_exp1_test_task.md",
        worktree_path="experiments/worktrees/iter0_exp1_test",
        experiment_id="iter0_exp1_test",
        timeout=300  # 5 minutes for testing
    )

    print(f"\nExecution Result:")
    print(f"  Success: {result.success}")
    print(f"  Time: {result.execution_time:.2f}s")

    if result.success:
        print(f"  Score: {result.result_data.get('score')}")
        print(f"  Output: {result.output_file}")
    else:
        print(f"  Error: {result.error}")
        print(f"  Error Type: {result.error_type}")
