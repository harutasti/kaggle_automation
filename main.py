import os
import sys
import json
import argparse
from datetime import datetime

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.core.mcdu import MasterControllerDecisionUnit
from src.utils.logger import setup_logger
from src.utils.file_utils import ensure_dir
from src.utils.system_specs import SystemSpecsDetector

DEFAULT_CONFIG_FILE = "config/config.json"

def main():
    parser = argparse.ArgumentParser(description="AutoKaggle - Automated Kaggle Competition System")
    parser.add_argument(
        "--config", "-c",
        default=DEFAULT_CONFIG_FILE,
        help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILE})"
    )
    parser.add_argument(
        "--skip-confirmations", "-y",
        action="store_true",
        default=False,
        help="Skip all confirmation prompts (run in automatic mode)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run in dry-run mode (skip actual Codex executions)"
    )
    args = parser.parse_args()

    config_file = args.config
    skip_confirmations = args.skip_confirmations
    dry_run = args.dry_run

    print(f"Starting AutoKaggle with config: {config_file}")
    if skip_confirmations:
        print("Running in automatic mode (skipping all confirmations)")
    if dry_run:
        print("Running in dry-run mode (skipping Codex executions)")

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
    config['dry_run'] = dry_run

    # Get competition name and create timestamped directory
    competition_name = config.get("competition", {}).get("name", "unknown")
    if not competition_name:
        # Fallback to old config format
        competition_name = config.get("kaggle_competition_name", "unknown")

    # Create timestamp for this experiment run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Build the experiment run directory path
    experiments_root = config.get("experiments_base_dir", "./experiments")
    experiment_run_dir = os.path.join(experiments_root, competition_name, timestamp)

    # Update config with the run-specific directory
    config['experiment_run_dir'] = experiment_run_dir
    config['timestamp'] = timestamp

    # Only create directories if not in dry-run mode
    if not dry_run:
        logger.info(f"Creating experiment directories at: {experiment_run_dir}")
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
    else:
        logger.info(f"DRY-RUN MODE: Would create directories at: {experiment_run_dir}")


    try:
        mcdu = MasterControllerDecisionUnit(config_file)
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
