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
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from enum import Enum


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

    # If dry-run, return dummy success without checking files
    if dry_run:
        logger.info(f"DRY-RUN: Would execute experiment {experiment_id}")
        return CodexResult(
            success=True,
            mode=CodexMode.WAA,
            experiment_id=experiment_id,
            execution_time=0.0,
            result_data={},
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


def execute_kse_hypothesis_generation(
    prompt_content: str,
    output_dir: str | Path,
    iteration: int,
    num_hypotheses: int = 3,
    timeout: int = 600,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None
) -> CodexResult:
    """
    Execute KSE hypothesis generation using Codex.

    Args:
        prompt_content: Filled KSE prompt with competition/dataset/system info
        output_dir: Directory to save hypothesis markdown files
        iteration: Current iteration number
        num_hypotheses: Number of hypotheses to generate
        timeout: Maximum execution time in seconds (default: 10 minutes)
        logger: Optional logger instance

    Returns:
        CodexResult with generated hypotheses
    """
    output_dir = Path(output_dir)
    output_file = output_dir / f"kse_output_iter{iteration}.md"

    if logger is None:
        logger = logging.getLogger("AutoKaggle.CodexExecutor.KSE")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # If dry-run, return dummy success
    if dry_run:
        logger.info(f"DRY-RUN: Would generate {num_hypotheses} KSE hypotheses for iteration {iteration}")
        return CodexResult(
            success=True,
            mode=CodexMode.KSE,
            execution_time=0.0,
            hypotheses=[],  # Empty in dry-run
            output_file=str(output_file)
        )

    # Prepare instruction for Codex
    stdin_input = f"""You are the Knowledge Strategy Engine (KSE) for AutoKaggle.

{prompt_content}

IMPORTANT: Generate exactly {num_hypotheses} hypothesis markdown files.

For each hypothesis, create a separate file named:
- iter{iteration}_exp1_<unique_id>_hypothesis.md
- iter{iteration}_exp2_<unique_id>_hypothesis.md
- iter{iteration}_exp3_<unique_id>_hypothesis.md

Each file should follow the exact template structure provided in the prompt above.

After creating all files, create a summary file named 'kse_summary_iter{iteration}.json' with:
{{
    "iteration": {iteration},
    "hypotheses": [
        {{
            "experiment_id": "iter{iteration}_exp1_<id>",
            "strategy": "strategy_name",
            "category": "category_type",
            "file": "path/to/hypothesis.md"
        }},
        ...
    ]
}}
"""

    logger.info(f"Executing KSE for iteration {iteration} ({num_hypotheses} hypotheses)")
    start_time = time.time()

    try:
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check"],
            input=stdin_input.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(output_dir),
            timeout=timeout,
            check=False
        )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        # Save output
        output_file.write_text(raw_output, encoding="utf-8")
        logger.info(f"KSE completed in {execution_time:.2f}s")

        # Parse generated hypotheses
        summary_file = output_dir / f"kse_summary_iter{iteration}.json"

        if summary_file.exists():
            try:
                with open(summary_file, 'r') as f:
                    summary_data = json.load(f)

                return CodexResult(
                    success=True,
                    mode=CodexMode.KSE,
                    execution_time=execution_time,
                    raw_output=raw_output,
                    output_file=output_file,
                    hypotheses=summary_data.get("hypotheses", [])
                )
            except Exception as e:
                logger.error(f"Failed to parse KSE summary: {e}")

        # If no summary, try to find generated hypothesis files
        hypothesis_files = list(output_dir.glob(f"iter{iteration}_exp*_hypothesis.md"))

        if hypothesis_files:
            hypotheses = []
            for i, file in enumerate(hypothesis_files, 1):
                hypotheses.append({
                    "experiment_id": file.stem.replace("_hypothesis", ""),
                    "file": str(file)
                })

            return CodexResult(
                success=True,
                mode=CodexMode.KSE,
                execution_time=execution_time,
                raw_output=raw_output,
                output_file=output_file,
                hypotheses=hypotheses
            )

        return CodexResult(
            success=False,
            mode=CodexMode.KSE,
            execution_time=execution_time,
            raw_output=raw_output,
            output_file=output_file,
            error="No hypotheses generated",
            error_type="NO_OUTPUT"
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
    timeout: int = 300,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None
) -> CodexResult:
    """
    Execute Performance Analysis using Codex.

    Args:
        results_data: List of experiment results to analyze
        iteration: Current iteration number
        output_dir: Directory to save analysis report
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

    # If dry-run, return dummy success
    if dry_run:
        logger.info(f"DRY-RUN: Would analyze {len(results_data) if isinstance(results_data, list) else 0} results for iteration {iteration}")
        return CodexResult(
            success=True,
            mode=CodexMode.PA,
            execution_time=0.0,
            analysis={},  # Empty in dry-run
            output_file=str(output_file)
        )

    # Prepare results summary for analysis
    results_summary = results_data if isinstance(results_data, str) else json.dumps(results_data, indent=2)

    # Prepare instruction for Codex
    stdin_input = f"""You are the Performance Analyzer (PA) for AutoKaggle.

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
        proc = subprocess.run(
            ["codex", "exec", "--skip-git-repo-check"],
            input=stdin_input.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(output_dir),
            timeout=timeout,
            check=False
        )

        execution_time = time.time() - start_time
        raw_output = proc.stdout.decode("utf-8", errors="replace")

        # Save output
        output_file.write_text(raw_output, encoding="utf-8")
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
