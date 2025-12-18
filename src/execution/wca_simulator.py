import os
import sys
import json
import time
import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# Add project root to sys.path to fix imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.utils.file_utils import ensure_dir, write_json, read_markdown
from src.utils.dry_run import stable_hash_int, stable_uniform

def setup_waa_logger(log_file: str, level: str = "INFO"):
    """Set up the WAA logger."""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    log_level = level_map.get(level, logging.INFO)
    
    logger = logging.getLogger('AutoKaggle.WAA')
    logger.setLevel(log_level)
    
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # Console handler (optional if parent logger already logs to console)
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    return logger

TRAINING_DONE_PREFIX = "DRYRUN_TRAINING_DONE_"


def _status_file_path(worktree_path: str) -> str:
    return os.path.join(worktree_path, "experiment-status.yaml")


def _append_status(worktree_path: str, status: str, message: str):
    """
    Append a status entry to experiment-status.yaml in a YAML-safe way without PyYAML.

    The file is initially created by SessionManager (controller) via yaml.dump, which
    typically formats list items under "statuses:" as:
      statuses:
      - timestamp: '...'
        status: IDLE
        message: ...
    """
    path = _status_file_path(worktree_path)
    ts = datetime.now().isoformat()

    indent = ""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.lstrip().startswith("- timestamp:"):
                        indent = line[: len(line) - len(line.lstrip())]
                        break
    except Exception:
        indent = ""

    child_indent = indent + "  "
    lines = [
        f"{indent}- timestamp: \"{ts}\"",
        f"{child_indent}status: {status}",
        f"{child_indent}message: \"{message}\"",
        "",
    ]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_error(worktree_path: str, exp_id: str, message: str):
    error_file = os.path.join(worktree_path, f"ERROR_{exp_id}.log")
    with open(error_file, "w", encoding="utf-8") as f:
        f.write(f"Error at {datetime.now().isoformat()}\n\n{message}\n")


def _write_done(worktree_path: str, exp_id: str, status: str):
    done_file = os.path.join(worktree_path, f"DONE_{exp_id}")
    with open(done_file, "w", encoding="utf-8") as f:
        f.write(status)


def _write_submission(worktree_path: str, exp_id: str):
    submission_file = os.path.join(worktree_path, f"submission_{exp_id}.csv")
    # Keep it generic; dry-run must not submit to Kaggle.
    with open(submission_file, "w", encoding="utf-8") as f:
        f.write("id,prediction\n1,0.5\n2,0.5\n")


def _write_result(worktree_path: str, exp_id: str, score: float, start_time: datetime):
    result_data = {
        "score": score,
        "start_time": start_time.isoformat(),
        "end_time": datetime.now().isoformat(),
        "dry_run": True,
    }
    result_file = os.path.join(worktree_path, f"result_{exp_id}.json")
    write_json(result_data, result_file)


def _write_codex_jsonl_placeholder(worktree_path: str, exp_id: str, text: str):
    """
    Produce a Codex-like JSONL artifact so RAD can exercise codex-responses/WAA copying.
    """
    jsonl_path = os.path.join(worktree_path, f"codex_output_{exp_id}.jsonl")
    event = {"type": "item.completed", "item": {"type": "agent_message", "text": text}}
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _training_marker_path(worktree_path: str, exp_id: str) -> str:
    return os.path.join(worktree_path, f"{TRAINING_DONE_PREFIX}{exp_id}")


def _spawn_training_simulation(worktree_path: str, exp_id: str, seconds: int, logger: logging.Logger):
    """
    Spawn a background process that sleeps and then writes a training-done marker.
    This simulates long training continuing after the "agent session" exits.
    """
    marker = _training_marker_path(worktree_path, exp_id)
    training_log = os.path.join(worktree_path, "training.log")
    cmd = [
        sys.executable,
        "-c",
        (
            "import time, pathlib, sys; "
            f"time.sleep({seconds}); "
            f"pathlib.Path({marker!r}).write_text('done', encoding='utf-8'); "
            "sys.exit(0)"
        ),
    ]

    try:
        with open(training_log, "a", encoding="utf-8") as logf:
            logf.write(f"[dry-run] starting simulated training for {seconds}s\n")
        subprocess.Popen(
            cmd,
            cwd=worktree_path,
            stdout=open(training_log, "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        logger.info(f"Spawned background training simulation for {seconds}s (marker={marker})")
    except Exception as e:
        logger.error(f"Failed to spawn training simulation: {e}", exc_info=True)
        raise


def _is_guaranteed_success(exp_id: str) -> bool:
    # Guarantee at least one success per iteration:
    # - New hypotheses IDs are always iterX_exp1_... for the first slot.
    # - If an iteration contains only continuations (e.g., wca_per_iteration=1), make continuations succeed.
    return ("_exp1_" in exp_id) or ("_cont_" in exp_id)


def _failure_mode(exp_id: str) -> str:
    """
    Deterministically pick a failure mode for resiliency testing.

    Returns one of:
      - "ok"
      - "error_status"
      - "unexpected_exit"
      - "resume_failure"
      - "missing_result"
      - "missing_submission"
    """
    if _is_guaranteed_success(exp_id):
        return "ok"

    h = stable_hash_int(exp_id) % 20
    if h == 0:
        return "unexpected_exit"
    if h == 1:
        return "error_status"
    if h == 2:
        return "resume_failure"
    if h == 3:
        return "missing_result"
    if h == 4:
        return "missing_submission"
    return "ok"


def _deterministic_score(exp_id: str) -> float:
    # Keep in a plausible range; continuations get a small deterministic bump.
    base = stable_uniform(f"{exp_id}:score", 0.70, 0.95)
    if "_cont_" in exp_id:
        base = min(0.99, base + 0.01)
    return float(f"{base:.5f}")


def run_waa_simulation(args):
    """Main routine for the WAA simulator (dry-run worker)."""
    # Configure logger
    log_file = os.path.join(args.worktree_path, f"waa_{args.experiment_id}.log")
    logger = setup_waa_logger(log_file, args.log_level)
    mode = "RESUME" if args.resume else "INITIAL"
    logger.info(f"WAA Simulator started for experiment {args.experiment_id} (mode={mode})")

    worktree_path = args.worktree_path
    exp_id = args.experiment_id

    try:
        start_time = datetime.now()

        # Read task instructions (parity with real runs; content isn't executed)
        logger.info(f"Reading task instructions from {args.task_markdown_path}")
        task_instructions = read_markdown(args.task_markdown_path)
        if not task_instructions:
            raise RuntimeError(f"Failed to read task instructions from {args.task_markdown_path}")
        logger.info(f"Task content length: {len(task_instructions)} chars")

        failure_mode = _failure_mode(exp_id)
        logger.info(f"Dry-run failure mode: {failure_mode}")

        if not args.resume:
            # INITIAL: emulate long training -> set RUNNING, spawn background job, exit.
            if failure_mode == "unexpected_exit":
                logger.error("Simulating unexpected exit (no status updates, no DONE file).")
                return 2

            if failure_mode == "error_status":
                _append_status(worktree_path, "ERROR", "Dry-run simulated unrecoverable error before training")
                _write_error(worktree_path, exp_id, "Dry-run: simulated ERROR status before training.")
                return 0

            # Normal long-training path
            _append_status(worktree_path, "RUNNING", "Dry-run: starting long training simulation (>10 min equivalent)")

            # Deterministic but short duration; controller polls and triggers resume after marker appears.
            seconds = int(2 + (stable_hash_int(exp_id) % 5))  # 2..6 seconds
            _spawn_training_simulation(worktree_path, exp_id, seconds, logger)
            return 0

        # RESUME: training finished; finalize outputs and mark COMPLETE/ERROR.
        marker = _training_marker_path(worktree_path, exp_id)
        if not os.path.exists(marker):
            _append_status(worktree_path, "ERROR", "Dry-run: resume requested but training marker missing")
            _write_error(worktree_path, exp_id, f"Missing training marker: {marker}")
            _write_done(worktree_path, exp_id, "FAILURE_NO_TRAINING_MARKER")
            return 1

        if failure_mode == "resume_failure":
            _append_status(worktree_path, "ERROR", "Dry-run: simulated failure during resume/finalization")
            _write_error(worktree_path, exp_id, "Dry-run: simulated resume failure.")
            _write_done(worktree_path, exp_id, "FAILURE_RESUME")
            _write_codex_jsonl_placeholder(worktree_path, exp_id, "DRY-RUN: simulated resume failure.")
            return 1

        score = _deterministic_score(exp_id)

        # Write artifacts (optionally omit some for failure injection)
        if failure_mode != "missing_result":
            _write_result(worktree_path, exp_id, score, start_time)
        else:
            logger.warning("Dry-run: intentionally skipping result_<exp_id>.json")

        if failure_mode != "missing_submission":
            _write_submission(worktree_path, exp_id)
        else:
            logger.warning("Dry-run: intentionally skipping submission_<exp_id>.csv")

        _write_codex_jsonl_placeholder(worktree_path, exp_id, f"DRY-RUN: finalized experiment {exp_id} with score={score}")

        _append_status(worktree_path, "COMPLETE", f"Dry-run: outputs finalized (score={score})")
        _write_done(worktree_path, exp_id, "SUCCESS")

        logger.info(f"Dry-run resume completed successfully (score={score})")
        return 0

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        _append_status(worktree_path, "ERROR", f"Dry-run: exception {type(e).__name__}: {e}")
        _write_error(worktree_path, exp_id, f"Exception: {e}")
        _write_done(worktree_path, exp_id, "FAILURE_EXCEPTION")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Worker Agent Simulator')
    parser.add_argument('--worktree-path', required=True, help='Path to the git worktree for this experiment')
    parser.add_argument('--task-markdown-path', required=True, help='Path to the task markdown file')
    parser.add_argument('--experiment-id', required=True, help='Unique ID for this experiment')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Logging level')
    parser.add_argument('--resume', action='store_true', help='Finalize after training (resume mode)')
    
    args = parser.parse_args()
    
    # Ensure directories exist
    if not os.path.exists(args.worktree_path):
        print(f"Error: Worktree path does not exist: {args.worktree_path}")
        sys.exit(1)
    
    if not os.path.exists(args.task_markdown_path):
        print(f"Error: Task markdown file does not exist: {args.task_markdown_path}")
        sys.exit(1)
    
    sys.exit(run_waa_simulation(args))
