#!/usr/bin/env python3
"""
Unified Codex executor for AutoKaggle system.

Handles all Codex invocations:
- KSE: Knowledge Strategy Engine (hypothesis generation)
- WAA: Worker AI Agent (experiment execution)
- PA: Performance Analyzer (results analysis)

Directly calls `codex exec` with appropriate prompts for each component.
"""

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
import uuid

from .codex_jsonl import write_codex_messages_file

class CodexMode(Enum):
    """Types of Codex executions"""
    KSE = "kse"  # Knowledge Strategy Engine - hypothesis generation
    WAA = "waa"  # Worker AI Agent - experiment execution
    PA = "pa"    # Performance Analyzer - results analysis


@dataclass
class CodexResult:
    """Result from Codex execution"""
    success: bool
    mode: CodexMode
    execution_time: float
    raw_output: str = ""
    error: Optional[str] = None
    error_type: Optional[str] = None
    output_file: Optional[Path] = None
    result_data: Optional[dict] = None
    experiment_id: Optional[str] = None  # For WAA mode
    hypotheses: Optional[List[Dict]] = None  # For KSE mode
    analysis: Optional[Dict] = None  # For PA mode
    timestamp: datetime = field(default_factory=datetime.now)


def execute_codex_experiment(
    task_markdown_path: str | Path,
    worktree_path: str | Path,
    experiment_id: str,
    codex_responses_dir: str | Path | None = None,
    timeout: int = 3600,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None
) -> CodexResult:
    """
    Execute a Kaggle experiment using Codex.

    Args:
        task_markdown_path: Path to the task instruction markdown file
        worktree_path: Working directory (Git worktree) for the experiment
        experiment_id: Unique experiment identifier
        codex_responses_dir: Directory for JSONL output logs (e.g., experiment_run_dir/codex-responses)
        timeout: Maximum execution time in seconds (default: 1 hour)
        logger: Optional logger instance

    Returns:
        CodexResult with execution details and parsed results

    The function:
    1. Reads the task markdown as instruction
    2. Runs `codex exec --json` in the worktree directory
    3. Saves JSONL output to codex-responses/WAA/response-{parallel_id}-{iteration}.jsonl
    4. Parses result_{exp_id}.json if created
    5. Returns structured result
    """
    # Setup
    task_markdown_path = Path(task_markdown_path)
    worktree_path = Path(worktree_path)
    output_file = worktree_path / f"codex_output_{experiment_id}.md"

    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor")

    # If dry-run, create placeholder artifacts and return success
    if dry_run:
        logger.info(f"DRY-RUN: Simulating execution for experiment {experiment_id}")
        worktree_path.mkdir(parents=True, exist_ok=True)
        done_file = worktree_path / f"DONE_{experiment_id}"
        result_file = worktree_path / f"result_{experiment_id}.json"
        submission_file = worktree_path / f"submission_{experiment_id}.csv"
        log_file = worktree_path / f"waa_{experiment_id}.log"
        # Populate dummy artifacts
        result_payload = {"score": 0.5, "start_time": datetime.now().isoformat(), "end_time": datetime.now().isoformat()}
        result_file.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
        submission_file.write_text("id,prediction\n1,0.5\n2,0.5\n", encoding="utf-8")
        done_file.write_text("SUCCESS", encoding="utf-8")
        log_file.write_text("DRY-RUN: simulated execution log.\n", encoding="utf-8")
        output_file.write_text("DRY-RUN: Codex output placeholder.\n", encoding="utf-8")

        # Save prompt for debugging
        stdin_input = f"""Your Task:
DRY-RUN placeholding task for {experiment_id}
"""
        _save_prompt_for_debug(
            prompt_text=stdin_input,
            mode="WAA",
            iteration=_parse_iteration_from_experiment_id(experiment_id),
            experiment_id=experiment_id,
            anchor_path=worktree_path
        )
        return CodexResult(
            success=True,
            mode=CodexMode.WAA,
            experiment_id=experiment_id,
            execution_time=0.0,
            result_data=result_payload,
            output_file=str(output_file)
        )

    # Validate inputs
    if not task_markdown_path.exists():
        return CodexResult(
            success=False,
            mode=CodexMode.WAA,
            experiment_id=experiment_id,
            execution_time=0.0,
            error=f"Task markdown not found: {task_markdown_path}",
            error_type="FILE_NOT_FOUND"
        )

    if not worktree_path.exists():
        return CodexResult(
            success=False,
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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

    _save_prompt_for_debug(
        prompt_text=stdin_input,
        mode="WAA",
        iteration=_parse_iteration_from_experiment_id(experiment_id),
        experiment_id=experiment_id,
        anchor_path=worktree_path
    )

    logger.info(f"Executing Codex for experiment {experiment_id}")
    logger.debug(f"Working directory: {worktree_path}")
    logger.debug(f"Task markdown: {task_markdown_path}")

    # Execute Codex
    start_time = time.time()

    try:
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "--json"],
            input=stdin_input.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(worktree_path),
            timeout=timeout,
            check=False
        )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        # Save JSONL output to codex-responses/WAA/
        if codex_responses_dir:
            codex_responses_dir = Path(codex_responses_dir)
            # Parse experiment_id format: iter{N}_exp{M}_{uuid}
            # Naming: response-{parallel_id}-{iteration}.jsonl (parallel-id first)
            match = re.match(r'iter(\d+)_exp(\d+)_', experiment_id)
            if match:
                iteration, parallel_id = match.groups()
                jsonl_filename = f"response-{parallel_id}-{iteration}.jsonl"
            else:
                jsonl_filename = f"response-{experiment_id}.jsonl"

            jsonl_path = codex_responses_dir / "WAA" / jsonl_filename
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_path.write_text(raw_output, encoding="utf-8")
            logger.info(f"Saved JSONL output to {jsonl_path}")
            write_codex_messages_file(jsonl_path=jsonl_path)

        logger.info(f"Codex completed in {execution_time:.2f}s (exit code: {proc.returncode})")

        # Check for Codex execution failure
        if proc.returncode != 0:
            logger.warning(f"Codex returned non-zero exit code: {proc.returncode}")
            return CodexResult(
                success=False,
                mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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

        # Extract score using flexible field names (mirrors RAD's logic)
        score = _extract_score_from_result(result_data)

        if score is None:
            logger.warning("Could not extract score using known field names, checking for any numeric metric...")
            # Last resort: look for any float value that might be a score (0-1 range)
            for key, value in result_data.items():
                if isinstance(value, (int, float)) and 0 <= value <= 1:
                    score = float(value)
                    logger.info(f"Using '{key}' as score: {score}")
                    break

        if score is None:
            logger.error("Result file missing score (tried: score, cv_mean_accuracy, study_best_value, etc.)")
            return CodexResult(
                success=False,
                mode=CodexMode.WAA,
                experiment_id=experiment_id,
                execution_time=execution_time,
                raw_output=raw_output,
                output_file=output_file,
                result_data=result_data,
                error="Could not extract score from result file",
                error_type="MISSING_SCORE"
            )

        # Store extracted score back into result_data for consistency
        result_data["score"] = score
        logger.info(f"Successfully parsed results. Score: {score}")

        # Check for submission file (optional but good to note)
        if not submission_file.exists():
            logger.warning(f"Submission file not created: {submission_file}")

        return CodexResult(
            success=True,
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
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
            mode=CodexMode.WAA,
            experiment_id=experiment_id,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error=f"Unexpected error parsing results: {e}",
            error_type="PARSE_ERROR"
        )


def _extract_score_from_result(result_data: dict) -> Optional[float]:
    """
    Extract score from result JSON using flexible field names.

    Mirrors RAD's _extract_score() logic for consistency across the system.

    Tries common patterns emitted by WAAs:
    - result_data["score"]
    - result_data["cv_mean_accuracy"] (LightGBM outputs)
    - result_data["study_best_value"] (Optuna outputs)
    - result_data["best_metrics"]["accuracy_mean"] (Optuna with metrics)
    - result_data["cv"]["mean_accuracy"]
    - result_data["cv_results"]["cv_metrics"][accuracy_mean|...]
    - result_data["base_cv_accuracy_mean"] (pseudo-label pipelines)
    """
    if not result_data:
        return None

    # Direct score field
    if "score" in result_data:
        return result_data.get("score")

    # LightGBM outputs
    if "cv_mean_accuracy" in result_data:
        return result_data.get("cv_mean_accuracy")

    # Optuna outputs
    if "study_best_value" in result_data:
        return result_data.get("study_best_value")

    # Optuna with detailed metrics
    best_metrics = result_data.get("best_metrics") or {}
    if "accuracy_mean" in best_metrics:
        return best_metrics.get("accuracy_mean")

    # Nested CV structure
    cv = result_data.get("cv") or {}
    if "mean_accuracy" in cv:
        return cv.get("mean_accuracy")

    # Ensemble/stacks
    cv_results = result_data.get("cv_results") or {}
    cv_metrics = cv_results.get("cv_metrics") or {}
    for key in ("accuracy_mean", "lightgbm_accuracy_mean", "blend_accuracy", "stack_accuracy"):
        if key in cv_metrics:
            return cv_metrics.get(key)

    # Pseudo-label pipeline
    if "base_cv_accuracy_mean" in result_data:
        return result_data.get("base_cv_accuracy_mean")

    return None


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


def execute_kse_hypothesis_generation(
    prompt_content: str,
    output_dir: str | Path,
    iteration: int,
    codex_responses_dir: str | Path | None = None,
    timeout: int = 600,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    resume_prompt: str | None = None,
    run_label: str | None = None
) -> CodexResult:
    """
    Execute KSE hypothesis generation using Codex.

    Args:
        prompt_content: Filled KSE prompt with competition/dataset/system info
        output_dir: Directory to save hypothesis markdown files
        iteration: Current iteration number
        codex_responses_dir: Directory for JSONL output logs (e.g., experiment_run_dir/codex-responses)
        timeout: Maximum execution time in seconds (default: 10 minutes)
        resume_prompt: Optional prompt for resume mode (uses `codex exec ... resume --last`)
        run_label: Optional label for differentiating multiple KSE runs (for logging/output naming)
        logger: Optional logger instance

    Returns:
        CodexResult with Codex raw output (templates parsed by caller)
    """
    output_dir = Path(output_dir)
    output_file = output_dir / f"kse_output_iter{iteration}.md"

    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor.KSE")

    output_dir.mkdir(parents=True, exist_ok=True)

    # If dry-run, synthesize success only (templates handled by caller)
    if dry_run:
        _save_prompt_for_debug(
            prompt_text=prompt_content,
            mode="KSE",
            iteration=iteration,
            experiment_id=None,
            anchor_path=output_dir,
            run_label=run_label
        )
        return CodexResult(
            success=True,
            mode=CodexMode.KSE,
            execution_time=0.0,
            output_file=str(output_file)
        )

    # Use prompt_content as-is; templates are pre-created by caller
    stdin_input = resume_prompt if resume_prompt is not None else prompt_content

    _save_prompt_for_debug(
        prompt_text=stdin_input,
        mode="KSE",
        iteration=iteration,
        experiment_id=None,
        anchor_path=output_dir,
        run_label=run_label
    )

    logger.info(f"Executing KSE for iteration {iteration}")
    start_time = time.time()

    try:
        # Build command
        # For resume: codex exec --skip-git-repo-check --json resume --last "prompt"
        # For initial: codex exec --skip-git-repo-check --json
        if resume_prompt:
            cmd = ["codex", "exec", "--skip-git-repo-check", "--json", "resume", "--last", stdin_input]
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(output_dir),
                timeout=timeout,
                check=False
            )
        else:
            cmd = ["codex", "exec", "--skip-git-repo-check", "--json"]
            proc = subprocess.run(
                cmd,
                input=stdin_input.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(output_dir),
                timeout=timeout,
                check=False
            )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        if codex_responses_dir:
            codex_responses_dir_path = Path(codex_responses_dir)
            suffix = run_label if run_label else ("resume" if resume_prompt else "initial")
            jsonl_path = codex_responses_dir_path / "KSE" / f"response-{iteration}-{suffix}.jsonl"
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_path.write_text(raw_output, encoding="utf-8")
            logger.info(f"Saved JSONL output to {jsonl_path}")
            write_codex_messages_file(jsonl_path=jsonl_path)

        logger.info(f"KSE completed in {execution_time:.2f}s")

        return CodexResult(
            success=True,
            mode=CodexMode.KSE,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file
        )

    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return CodexResult(
            success=False,
            mode=CodexMode.KSE,
            execution_time=execution_time,
            error=f"KSE timed out after {timeout}s",
            error_type="TIMEOUT"
        )

    except Exception as e:
        execution_time = time.time() - start_time
        return CodexResult(
            success=False,
            mode=CodexMode.KSE,
            execution_time=execution_time,
            error=f"KSE execution failed: {e}",
            error_type="EXECUTION_ERROR"
        )

def execute_pa_analysis(
    results_data: List[Dict[str, Any]] | str,
    iteration: int,
    output_dir: str | Path,
    codex_responses_dir: str | Path | None = None,
    timeout: int = 300,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    resume_prompt: str | None = None,
    run_label: str | None = None
) -> CodexResult:
    """
    Execute Performance Analysis using Codex.

    Args:
        results_data: List of experiment results to analyze
        iteration: Current iteration number
        output_dir: Directory to save analysis report
        codex_responses_dir: Directory for JSONL output logs (e.g., experiment_run_dir/codex-responses)
        timeout: Maximum execution time in seconds (default: 5 minutes)
        logger: Optional logger instance

    Returns:
        CodexResult with analysis report
    """
    output_dir = Path(output_dir)
    output_file = output_dir / f"pa_output_iter{iteration}.md"

    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor.PA")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prepare results summary for analysis
    results_summary = results_data if isinstance(results_data, str) else json.dumps(results_data, indent=2)

    # If dry-run, create placeholder analysis artifacts
    if dry_run:
        logger.info(f"DRY-RUN: Simulating PA analysis for iteration {iteration}")
        output_dir.mkdir(parents=True, exist_ok=True)
        analysis_file = output_dir / f"analysis_iter{iteration}.md"
        summary_file = output_dir / f"pa_summary_iter{iteration}.json"
        analysis_file.write_text(f"# Analysis Report - Iteration {iteration}\n\nDRY-RUN placeholder.", encoding="utf-8")
        summary_payload = {
            "iteration": iteration,
            "best_score": 0.5,
            "best_experiment": "iter{}_exp1_dryrun".format(iteration),
            "average_score": 0.5,
            "success_rate": 1.0,
            "recommended_strategies": ["DryRunStrategy1"],
            "avoid_strategies": [],
            "key_insights": ["DRY-RUN placeholder insights"]
        }
        summary_file.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
        _save_prompt_for_debug(
            prompt_text=resume_prompt if resume_prompt is not None else results_summary,
            mode="PA",
            iteration=iteration,
            experiment_id=None,
            anchor_path=output_dir,
            run_label=run_label
        )
        return CodexResult(
            success=True,
            mode=CodexMode.PA,
            execution_time=0.0,
            analysis=summary_payload,
            output_file=str(output_file)
        )

    # Prepare instruction for Codex
    stdin_input = resume_prompt if resume_prompt is not None else f"""You are the Performance Analyzer (PA) for AutoKaggle.

Analyze the following experiment results from iteration {iteration}:

```json
{results_summary}
```

Please provide a comprehensive analysis including:

1. **Performance Summary**
   - Best performing experiment (ID and score)
   - Worst performing experiment
   - Average score across all experiments
   - Standard deviation

2. **Pattern Analysis**
   - What strategies worked well?
   - What strategies failed?
   - Common patterns in successful experiments
   - Common patterns in failed experiments

3. **Feature Importance Insights**
   - Most important features across successful models
   - Features that may be causing overfitting

4. **Recommendations for Next Iteration**
   - High priority: Strategies to exploit
   - Medium priority: Strategies to explore
   - Low priority: Strategies to avoid

5. **Specific Improvements**
   - Hyperparameter adjustments
   - Feature engineering suggestions
   - Model architecture changes

Create two output files:

1. `analysis_iter{iteration}.md` - Detailed markdown report
2. `pa_summary_iter{iteration}.json` - Structured summary with:
   {{
       "iteration": {iteration},
       "best_score": <score>,
       "best_experiment": "<exp_id>",
       "average_score": <score>,
       "success_rate": <percentage>,
       "recommended_strategies": ["strategy1", "strategy2", ...],
       "avoid_strategies": ["strategy1", ...],
       "key_insights": ["insight1", "insight2", ...]
   }}
"""

    logger.info(f"Executing PA for iteration {iteration} ({len(results_data)} results)")
    start_time = time.time()

    try:
        _save_prompt_for_debug(
            prompt_text=stdin_input,
            mode="PA",
            iteration=iteration,
            experiment_id=None,
            anchor_path=output_dir,
            run_label=run_label
        )

        # Build command
        # For resume: codex exec --skip-git-repo-check --json resume --last "prompt"
        # For initial: codex exec --skip-git-repo-check --json
        if resume_prompt:
            cmd = ["codex", "exec", "--skip-git-repo-check", "--json", "resume", "--last", stdin_input]
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(output_dir),
                timeout=timeout,
                check=False
            )
        else:
            cmd = ["codex", "exec", "--skip-git-repo-check", "--json"]
            proc = subprocess.run(
                cmd,
                input=stdin_input.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(output_dir),
                timeout=timeout,
                check=False
            )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        # Save JSONL output to codex-responses/PA/
        if codex_responses_dir:
            codex_responses_dir_path = Path(codex_responses_dir)
            suffix = run_label if run_label else ("resume" if resume_prompt else "initial")
            jsonl_path = codex_responses_dir_path / "PA" / f"response-{iteration}-{suffix}.jsonl"
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            jsonl_path.write_text(raw_output, encoding="utf-8")
            logger.info(f"Saved JSONL output to {jsonl_path}")
            write_codex_messages_file(jsonl_path=jsonl_path)

        logger.info(f"PA completed in {execution_time:.2f}s")

        # Parse analysis summary
        summary_file = output_dir / f"pa_summary_iter{iteration}.json"
        analysis_file = output_dir / f"analysis_iter{iteration}.md"

        analysis_data = None
        if summary_file.exists():
            try:
                with open(summary_file, 'r') as f:
                    analysis_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to parse PA summary: {e}")

        # Check if analysis report was created
        if analysis_file.exists() or analysis_data:
            return CodexResult(
                success=True,
                mode=CodexMode.PA,
                execution_time=execution_time,
                raw_output=raw_output,
                output_file=output_file,
                analysis=analysis_data or {"report_created": True}
            )

        # Fallback: treat non-empty JSONL/text output as success even if files were not written
        text_output = extract_text_from_jsonl(raw_output or "")
        if text_output.strip():
            return CodexResult(
                success=True,
                mode=CodexMode.PA,
                execution_time=execution_time,
                raw_output=raw_output,
                output_file=output_file,
                analysis=analysis_data or {"report_created": False, "text_output": text_output}
            )

        return CodexResult(
            success=False,
            mode=CodexMode.PA,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error="No analysis report generated",
            error_type="NO_OUTPUT"
        )

    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        return CodexResult(
            success=False,
            mode=CodexMode.PA,
            execution_time=execution_time,
            error=f"PA timed out after {timeout}s",
            error_type="TIMEOUT"
        )

    except Exception as e:
        execution_time = time.time() - start_time
        return CodexResult(
            success=False,
            mode=CodexMode.PA,
            execution_time=execution_time,
            error=f"PA execution failed: {e}",
            error_type="EXECUTION_ERROR"
        )


def execute_codex(
    mode: CodexMode,
    **kwargs
) -> CodexResult:
    """
    Unified interface for all Codex executions.

    Args:
        mode: Type of Codex execution (KSE, WAA, or PA)
        **kwargs: Mode-specific arguments

    Returns:
        CodexResult appropriate for the mode
    """
    if mode == CodexMode.WAA:
        # WAA requires: task_markdown_path, worktree_path, experiment_id
        return execute_codex_experiment(**kwargs)

    elif mode == CodexMode.KSE:
        # KSE requires: prompt_content, output_dir, iteration, num_hypotheses
        return execute_kse_hypothesis_generation(**kwargs)

    elif mode == CodexMode.PA:
        # PA requires: results_data, iteration, output_dir
        return execute_pa_analysis(**kwargs)

    else:
        return CodexResult(
            success=False,
            mode=mode,
            execution_time=0.0,
            error=f"Unknown Codex mode: {mode}",
            error_type="INVALID_MODE"
        )


def extract_text_from_jsonl(jsonl_output: str) -> str:
    """
    Extract agent message text from Codex JSONL output.

    When using --json mode, Codex outputs JSONL events to stdout.
    This function parses those events and extracts the text content
    from agent_message items.

    Args:
        jsonl_output: Raw JSONL string from Codex --json mode

    Returns:
        Concatenated text from all agent_message items
    """
    if not jsonl_output:
        return ""

    messages = []
    for line in jsonl_output.strip().split('\n'):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            # Look for completed agent messages
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") == "agent_message":
                    text = item.get("text", "")
                    if text:
                        messages.append(text)
        except json.JSONDecodeError:
            # Skip malformed lines
            continue

    return "\n\n".join(messages)


def _parse_iteration_from_experiment_id(experiment_id: str) -> Optional[int]:
    """Extract iteration number from experiment_id like iter2_exp3_xxxx."""
    match = re.match(r"iter(\d+)_exp", experiment_id)
    if match:
        return int(match.group(1))
    return None


def _infer_run_dir(anchor_path: str | Path) -> Optional[Path]:
    """Given a path inside the run, find the experiment run root (parent of worktrees/hypotheses/etc.)."""
    p = Path(anchor_path).resolve()
    for parent in [p] + list(p.parents):
        if parent.name in {"worktrees", "hypotheses", "analysis", "results", "sessions", "codex-responses"}:
            return parent.parent
    return p if p.exists() else None


def _save_prompt_for_debug(
    prompt_text: str,
    mode: str,
    iteration: Optional[int],
    experiment_id: Optional[str],
    anchor_path: str | Path,
    run_label: Optional[str] = None
) -> None:
    """Persist the actual prompt used for Codex execution for debugging."""
    try:
        run_dir = _infer_run_dir(anchor_path)
        if run_dir is None:
            return

        prompt_root = run_dir / "prompts" / mode.upper()
        if iteration is not None:
            prompt_root = prompt_root / f"iter{iteration}"
        prompt_root.mkdir(parents=True, exist_ok=True)

        if experiment_id:
            filename = f"{experiment_id}"
        else:
            label = run_label or "prompt"
            filename = f"iter{iteration}_{label}" if iteration is not None else f"prompt_{label}"

        path = prompt_root / f"{filename}.md"
        if path.exists():
            path = prompt_root / f"{filename}_{uuid.uuid4().hex[:6]}.md"

        path.write_text(prompt_text, encoding="utf-8")
    except Exception:
        # Debug prompt saving should never break main execution
        return


def build_resume_prompt(exp_id: str, exit_code: int, training_log_tail: str) -> str:
    """
    Build prompt to guide resumed session after training completes.

    Args:
        exp_id: Experiment identifier
        exit_code: Exit code from previous process (0 = success)
        training_log_tail: Last portion of training log

    Returns:
        Formatted prompt string for resume session
    """
    return f"""The training process has completed or exited.

**Experiment ID**: {exp_id}
**Exit Code**: {exit_code}

**Training Log (last 10KB)**:
```
{training_log_tail[-10000:] if training_log_tail else '[No training log found]'}
```

**Your Task**:

1. **Check if training completed successfully**:
   - Look for model files (.pkl, .pt, .pth, .bin, .h5, .joblib)
   - Check the training log for completion messages or final metrics
   - Verify no error messages in the log

2. **If training was successful**:
   - Run inference on the test data if not already done
   - Create `result_{exp_id}.json` with the validation/CV score:
     ```json
     {{"score": <validation_score>}}
     ```
   - Create `submission_{exp_id}.csv` with predictions in competition format
   - Update `experiment-status.yaml`:
     ```yaml
       - timestamp: "<current_timestamp>"
         status: COMPLETE
         message: "Training complete. Score: <score>"
     ```
   - Create `DONE_{exp_id}` file with "SUCCESS"

3. **If training failed**:
   - Analyze the error from the training log
   - Update `experiment-status.yaml`:
     ```yaml
       - timestamp: "<current_timestamp>"
         status: ERROR
         message: "<error description>"
         error_type: "<error_category>"
         recovery_suggestion: "<what could fix it>"
     ```
   - Create `DONE_{exp_id}` file with "FAILURE: <reason>"

**IMPORTANT**: After completing these tasks, exit immediately.
"""


def execute_codex_resume(
    experiment_id: str,
    worktree_path: str | Path,
    codex_responses_dir: str | Path,
    resume_prompt: str,
    timeout: int = 600,
    logger: Optional[logging.Logger] = None
) -> CodexResult:
    """
    Resume a Codex session using `codex resume --last`.

    This uses Codex's built-in session resume feature which continues
    the previous conversation in the worktree directory.

    Args:
        experiment_id: Experiment identifier
        worktree_path: Path to the experiment worktree (for cwd)
        codex_responses_dir: Directory for JSONL output logs
        resume_prompt: Prompt providing context about what happened
        timeout: Maximum execution time in seconds
        logger: Optional logger instance

    Returns:
        CodexResult with execution details
    """
    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor")

    worktree_path = Path(worktree_path)
    codex_responses_dir = Path(codex_responses_dir)

    start_time = time.time()
    logger.info(f"Resuming Codex session for {experiment_id} in {worktree_path}")

    try:
        # Use codex exec with resume --last to continue the previous session
        # The resume_prompt is passed as a command argument (not stdin)
        # Correct format: codex exec --skip-git-repo-check --json resume --last "prompt"
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check", "--json", "resume", "--last", resume_prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(worktree_path),
            timeout=timeout,
            check=False
        )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        logger.info(f"Codex resume completed in {execution_time:.2f}s with exit code {proc.returncode}")

        # Save JSONL output for audit trail
        codex_responses_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = codex_responses_dir / f"resume-{experiment_id}.jsonl"
        jsonl_path.write_text(raw_output, encoding="utf-8")
        logger.info(f"Saved resume JSONL output to {jsonl_path}")
        write_codex_messages_file(jsonl_path=jsonl_path)

        # Check for completion indicators
        done_file = worktree_path / f"DONE_{experiment_id}"
        result_file = worktree_path / f"result_{experiment_id}.json"

        if done_file.exists():
            # Check DONE file content
            done_content = done_file.read_text().strip()
            success = done_content.startswith("SUCCESS") or done_content == "SUCCESS"

            result_data = None
            if result_file.exists():
                try:
                    with open(result_file, 'r') as f:
                        result_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to parse result file: {e}")

            return CodexResult(
                success=success,
                mode=CodexMode.WAA,
                execution_time=execution_time,
                raw_output=raw_output,
                experiment_id=experiment_id,
                result_data=result_data,
                error=None if success else f"Experiment failed: {done_content}"
            )

        # No DONE file - check if process ran successfully
        if proc.returncode == 0:
            return CodexResult(
                success=True,
                mode=CodexMode.WAA,
                execution_time=execution_time,
                raw_output=raw_output,
                experiment_id=experiment_id
            )

        return CodexResult(
            success=False,
            mode=CodexMode.WAA,
            execution_time=execution_time,
            raw_output=raw_output,
            experiment_id=experiment_id,
            error=f"Codex resume exited with code {proc.returncode}",
            error_type="RESUME_FAILURE"
        )

    except subprocess.TimeoutExpired:
        execution_time = time.time() - start_time
        logger.error(f"Codex resume timed out after {timeout}s")
        return CodexResult(
            success=False,
            mode=CodexMode.WAA,
            execution_time=execution_time,
            raw_output="",
            experiment_id=experiment_id,
            error=f"Resume timed out after {timeout}s",
            error_type="TIMEOUT"
        )

    except FileNotFoundError:
        logger.error("Codex CLI not found. Is it installed?")
        return CodexResult(
            success=False,
            mode=CodexMode.WAA,
            execution_time=0.0,
            raw_output="",
            experiment_id=experiment_id,
            error="Codex CLI not found",
            error_type="CODEX_NOT_FOUND"
        )

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Codex resume failed: {e}")
        return CodexResult(
            success=False,
            mode=CodexMode.WAA,
            execution_time=execution_time,
            raw_output="",
            experiment_id=experiment_id,
            error=str(e),
            error_type="EXECUTION_ERROR"
        )

# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("CODEX EXECUTOR EXAMPLES")
    print("=" * 80)

    # Example 1: KSE - Generate hypotheses
    print("\n1. KSE - Hypothesis Generation")
    print("-" * 40)

    kse_prompt = """
    Competition: Titanic
    Evaluation Metric: Accuracy
    Dataset: 891 training samples, 12 features

    Generate 3 diverse ML experiment hypotheses.
    """

    kse_result = execute_codex(
        mode=CodexMode.KSE,
        prompt_content=kse_prompt,
        output_dir="./test_kse_output",
        iteration=0,
        num_hypotheses=3,
        timeout=60  # 1 minute for demo
    )

    print(f"KSE Result: {kse_result.success}")
    if kse_result.hypotheses:
        print(f"Generated {len(kse_result.hypotheses)} hypotheses")

    # Example 2: WAA - Execute experiment
    print("\n2. WAA - Experiment Execution")
    print("-" * 40)

    waa_result = execute_codex(
        mode=CodexMode.WAA,
        task_markdown_path="experiments/hypotheses/iter0_exp1_test_task.md",
        worktree_path="experiments/worktrees/iter0_exp1_test",
        experiment_id="iter0_exp1_test",
        timeout=300  # 5 minutes
    )

    print(f"WAA Result: {waa_result.success}")
    if waa_result.success and waa_result.result_data:
        print(f"Score: {waa_result.result_data.get('score')}")

    # Example 3: PA - Performance Analysis
    print("\n3. PA - Performance Analysis")
    print("-" * 40)

    sample_results = [
        {"experiment_id": "exp1", "score": 0.85, "strategy": "LightGBM"},
        {"experiment_id": "exp2", "score": 0.82, "strategy": "XGBoost"},
        {"experiment_id": "exp3", "score": 0.79, "strategy": "RandomForest"}
    ]

    pa_result = execute_codex(
        mode=CodexMode.PA,
        results_data=sample_results,
        iteration=0,
        output_dir="./test_pa_output",
        timeout=60  # 1 minute for demo
    )

    print(f"PA Result: {pa_result.success}")
    if pa_result.analysis:
        print(f"Analysis: {pa_result.analysis}")

    print("\n" + "=" * 80)
    print("Examples completed")
