import os
import sys
import json
import argparse
import shutil
import subprocess
from datetime import datetime

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.core.mcdu import MasterControllerDecisionUnit
from src.utils.logger import setup_logger
from src.utils.file_utils import ensure_dir
from src.utils.system_specs import SystemSpecsDetector

DEFAULT_CONFIG_FILE = "config/config.json"

def _format_preflight_block(title: str, lines: list[str]) -> str:
    header = f"{title}\n" + ("-" * len(title))
    body = "\n".join(f"- {line}" for line in lines)
    return f"{header}\n{body}"


def _run_preflight_checks(config: dict, logger) -> None:
    """
    Fail fast on missing system tools / credentials that would otherwise fail mid-run.
    """
    errors: list[str] = []
    warnings: list[str] = []

    def require_cmd(cmd: str, *, why: str) -> None:
        if shutil.which(cmd) is None:
            errors.append(f"Missing command `{cmd}` ({why}).")

    def optional_cmd(cmd: str, *, why: str) -> None:
        if shutil.which(cmd) is None:
            warnings.append(f"Missing command `{cmd}` ({why}).")

    # tmux is required for separate-terminal live Codex viewing.
    require_cmd("tmux", why="required to display live Codex logs in a separate terminal")

    # Kaggle credentials (kaggle.json or env vars).
    kaggle_user = os.environ.get("KAGGLE_USERNAME")
    kaggle_key = os.environ.get("KAGGLE_KEY")
    if kaggle_user and kaggle_key:
        logger.info("Preflight: Kaggle credentials found in environment variables.")
    else:
        # Prefer project-root kaggle.json, then KAGGLE_CONFIG_DIR, then ~/.kaggle/kaggle.json.
        candidates: list[str] = []
        project_kaggle = os.path.join(project_root, "kaggle.json")
        candidates.append(project_kaggle)
        kaggle_config_dir = os.environ.get("KAGGLE_CONFIG_DIR")
        if kaggle_config_dir:
            candidates.append(os.path.join(kaggle_config_dir, "kaggle.json"))
        home = os.path.expanduser("~")
        candidates.append(os.path.join(home, ".kaggle", "kaggle.json"))

        kaggle_json_path = next((p for p in candidates if p and os.path.exists(p)), None)
        if kaggle_json_path is None:
            errors.append(
                "Missing Kaggle credentials: set KAGGLE_USERNAME/KAGGLE_KEY or provide `kaggle.json` "
                "at repo root or ~/.kaggle/kaggle.json."
            )
        else:
            # Validate structure without printing secrets.
            try:
                with open(kaggle_json_path, "r", encoding="utf-8") as f:
                    creds = json.load(f)
                if not isinstance(creds, dict):
                    raise ValueError("kaggle.json must be a JSON object")
                if not creds.get("username") or not creds.get("key"):
                    raise ValueError("kaggle.json must contain non-empty 'username' and 'key'")
                try:
                    st_mode = os.stat(kaggle_json_path).st_mode & 0o777
                    if st_mode != 0o600:
                        warnings.append(
                            f"`{kaggle_json_path}` permissions are {oct(st_mode)}; Kaggle recommends 0o600."
                        )
                except Exception:
                    pass
                logger.info(f"Preflight: Found kaggle.json at {kaggle_json_path}.")
            except Exception as e:
                errors.append(f"Invalid kaggle.json at `{kaggle_json_path}`: {e}")

    # Confirm Kaggle API can initialize/authenticate (fails fast on malformed creds).
    try:
        try:
            import kaggle  # type: ignore

            logger.info(f"Preflight: kaggle package version {getattr(kaggle, '__version__', 'unknown')}.")
        except Exception:
            pass

        from kaggle.api.kaggle_api_extended import KaggleApi  # type: ignore

        api = KaggleApi()
        api.authenticate()
        logger.info("Preflight: Kaggle API authentication OK.")
    except Exception as e:
        errors.append(f"Kaggle API authentication failed: {e}")

    # Codex CLI required in real mode.
    simulation_mode = bool(config.get("simulation_mode", False))
    if simulation_mode:
        optional_cmd("codex", why="not required in simulation_mode=true")
    else:
        require_cmd("codex", why="required when simulation_mode=false to run Codex workers")

    # Crawler dependencies (only if enabled).
    use_crawler = bool(config.get("use_crawler", True))
    if use_crawler:
        # Ensure crawl4ai-doctor is installed (comes from crawl4ai package).
        require_cmd("crawl4ai-doctor", why="required for crawler health checks (crawl4ai)")

        # Run crawl4ai-doctor (best-effort, but fail if it reports an unhealthy environment).
        try:
            proc = subprocess.run(
                ["crawl4ai-doctor"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0:
                tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
                errors.append(f"`crawl4ai-doctor` failed (exit={proc.returncode}). Output (tail): {tail.strip()}")
            else:
                logger.info("Preflight: crawl4ai-doctor OK.")
        except subprocess.TimeoutExpired:
            errors.append("`crawl4ai-doctor` timed out. Try running `uv run crawl4ai-doctor` manually.")
        except Exception as e:
            errors.append(f"`crawl4ai-doctor` check failed: {e}")

        # Verify Playwright is installed and Chromium can launch headlessly.
        try:
            cmd = [
                sys.executable,
                "-c",
                (
                    "from playwright.sync_api import sync_playwright\n"
                    "with sync_playwright() as p:\n"
                    "    try:\n"
                    "        b = p.chromium.launch(headless=True, chromiumSandbox=False)\n"
                    "    except TypeError:\n"
                    "        b = p.chromium.launch(headless=True, args=['--no-sandbox'])\n"
                    "    b.close()\n"
                    "print('OK')\n"
                ),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if proc.returncode != 0:
                tail = (proc.stdout or "")[-500:] + (proc.stderr or "")[-500:]
                errors.append(
                    "Playwright/Chromium check failed. Install browsers with "
                    "`uv run python -m playwright install chromium`.\n"
                    f"Details (tail): {tail.strip()}"
                )
            else:
                logger.info("Preflight: Playwright Chromium launch OK.")
        except subprocess.TimeoutExpired:
            errors.append("Playwright/Chromium check timed out. Try `uv run python -m playwright install chromium`.")
        except Exception as e:
            errors.append(f"Playwright check failed: {e}")

    if warnings:
        logger.warning(_format_preflight_block("Preflight warnings", warnings))

    if errors:
        msg = _format_preflight_block("Preflight failed", errors)
        logger.critical(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    logger.info("Preflight checks passed.")


def main():
    parser = argparse.ArgumentParser(description="AutoKaggle - Automated Kaggle Competition System")
    parser.add_argument(
        "--config", "-c",
        default=DEFAULT_CONFIG_FILE,
        help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILE})"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume from an existing experiment run directory"
    )
    parser.add_argument(
        "--resume-run-dir",
        default=None,
        help="Explicit run directory to resume (skips interactive selection)"
    )
    parser.add_argument(
        "--skip-confirmations", "-y",
        action="store_true",
        default=False,
        help="Skip all confirmation prompts (run in automatic mode)"
    )
    args = parser.parse_args()

    config_file = args.config
    skip_confirmations = args.skip_confirmations
    resume_mode = args.resume
    resume_run_dir = args.resume_run_dir

    print(f"Starting AutoKaggle with config: {config_file}")
    if skip_confirmations:
        print("Running in automatic mode (skipping all confirmations)")
    if resume_mode:
        print("Resume mode enabled")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading config file '{config_file}': {e}")
        sys.exit(1)

    log_dir = os.path.dirname(config.get("log_file", "./logs/auto_kaggle.log"))
    ensure_dir(log_dir)
    logger = setup_logger(log_file=config.get("log_file", "./logs/auto_kaggle.log"),
                          level=config.get("log_level", "INFO"))

    logger.info("Logger initialized.")
    logger.info(f"Using configuration: {config}")

    # Fail fast on missing tools / credentials before any heavy execution.
    _run_preflight_checks(config, logger)

    # Detect system specifications
    logger.info("Detecting system specifications...")
    system_detector = SystemSpecsDetector()
    system_specs = system_detector.get_specs()
    logger.info(f"System: {system_specs['platform']['os_type']} on {system_specs['platform']['machine']}")
    logger.info(f"CPU: {system_specs['cpu']['count']} cores, {system_specs['cpu']['compute_type']}")
    logger.info(f"Memory: {system_specs['memory'].get('total_gb', 'Unknown'):.1f} GB" if system_specs['memory'].get('total_gb') else "Memory: Unknown")
    logger.info(f"GPU: {'Available' if system_specs['gpu']['available'] else 'Not available'}")

    # Add system specs to config for components to access
    config['system_specs'] = system_specs

    # Add command-line flags to config
    config['skip_confirmations'] = skip_confirmations

    # Get competition name and create timestamped directory
    competition_name = config.get("kaggle_competition_name", "unknown")

    # Build the experiment run directory path
    experiments_root = config.get("experiments_base_dir", "./experiments")

    def _select_resume_dir(root: str, competition: str) -> str | None:
        base_dir = os.path.join(root, competition)
        if not os.path.exists(base_dir):
            return None
        candidates = []
        for entry in sorted(os.listdir(base_dir)):
            full_path = os.path.join(base_dir, entry)
            if not os.path.isdir(full_path):
                continue
            run_state_path = os.path.join(full_path, "run_state.json")
            if os.path.exists(run_state_path):
                candidates.append(full_path)
        if not candidates:
            return None

        print("Available runs:")
        for idx, path in enumerate(candidates, 1):
            print(f"  [{idx}] {path}")

        while True:
            choice = input(f"Select a run to resume [1-{len(candidates)}] (or 'q' to cancel): ").strip()
            if choice.lower() in ("q", "quit", "exit"):
                return None
            try:
                index = int(choice)
                if 1 <= index <= len(candidates):
                    return candidates[index - 1]
            except ValueError:
                pass
            print("Invalid selection. Please try again.")

    if resume_mode:
        if resume_run_dir:
            experiment_run_dir = resume_run_dir
        else:
            experiment_run_dir = _select_resume_dir(experiments_root, competition_name)
            if not experiment_run_dir:
                print("No resumable runs found. Exiting.")
                sys.exit(1)

        if not os.path.isdir(experiment_run_dir):
            print(f"Resume directory not found: {experiment_run_dir}")
            sys.exit(1)

        run_state_path = os.path.join(experiment_run_dir, "run_state.json")
        if not os.path.exists(run_state_path):
            print(f"Run state file not found in {experiment_run_dir}. Cannot resume this run.")
            sys.exit(1)

        # Update config with the run-specific directory
        config['experiment_run_dir'] = experiment_run_dir
        config['timestamp'] = os.path.basename(experiment_run_dir)
        config['resume_mode'] = True
    else:
        # Create timestamp for this experiment run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        experiment_run_dir = os.path.join(experiments_root, competition_name, timestamp)

        # Update config with the run-specific directory
        config['experiment_run_dir'] = experiment_run_dir
        config['timestamp'] = timestamp
        config['resume_mode'] = False

    # Create run directories up front (or ensure they exist)
    logger.info(f"Using experiment directories at: {experiment_run_dir}")
    ensure_dir(experiment_run_dir)
    ensure_dir(os.path.join(experiment_run_dir, "worktrees"))
    ensure_dir(os.path.join(experiment_run_dir, "results"))
    ensure_dir(os.path.join(experiment_run_dir, "hypotheses"))
    ensure_dir(os.path.join(experiment_run_dir, "analysis"))
    ensure_dir(os.path.join(experiment_run_dir, "kaggle_data"))
    # Create codex-responses directories for JSONL output logging
    ensure_dir(os.path.join(experiment_run_dir, "codex-responses"))
    ensure_dir(os.path.join(experiment_run_dir, "codex-responses", "KSE"))
    ensure_dir(os.path.join(experiment_run_dir, "codex-responses", "WAA"))
    ensure_dir(os.path.join(experiment_run_dir, "codex-responses", "PA"))


    try:
        mcdu = MasterControllerDecisionUnit(config)
        mcdu.run_main_loop()
        logger.info("AutoKaggle finished successfully.")
    except Exception as e:
        logger.critical("An unhandled exception occurred in the main loop.", exc_info=True)
        print(f"Critical error: {e}. Check log file for details.")
        sys.exit(1)

if __name__ == "__main__":
    if not os.path.exists(".git"):
        print("Error: Not a Git repository. Please run 'git init' in the project root directory first.")
        sys.exit(1)
    main()
