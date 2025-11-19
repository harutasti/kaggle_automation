import os
import sys
import json

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from src.core.mcdu import MasterControllerDecisionUnit
from src.utils.logger import setup_logger
from src.utils.file_utils import ensure_dir

CONFIG_FILE = "config/config.json"

def main():
    print("Starting AutoKaggle Simulator...")

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error loading config file '{CONFIG_FILE}': {e}")
        sys.exit(1)

    log_dir = os.path.dirname(config.get("log_file", "./logs/auto_kaggle.log"))
    ensure_dir(log_dir)
    logger = setup_logger(log_file=config.get("log_file", "./logs/auto_kaggle.log"),
                          level=config.get("log_level", "INFO"))

    logger.info("Logger initialized.")
    logger.info(f"Using configuration: {config}")

    exp_base_dir = config.get("experiments_base_dir", "./experiments")
    ensure_dir(exp_base_dir)
    ensure_dir(os.path.join(exp_base_dir, "worktrees"))
    ensure_dir(os.path.join(exp_base_dir, "results"))
    ensure_dir(os.path.join(exp_base_dir, "hypotheses"))
    ensure_dir(os.path.join(exp_base_dir, "analysis"))
    ensure_dir(os.path.join(exp_base_dir, "kaggle_data"))


    try:
        mcdu = MasterControllerDecisionUnit(CONFIG_FILE)
        mcdu.run_main_loop()
        logger.info("AutoKaggle Simulator finished successfully.")
    except Exception as e:
        logger.critical("An unhandled exception occurred in the main loop.", exc_info=True)
        print(f"Critical error: {e}. Check log file for details.")
        sys.exit(1)

if __name__ == "__main__":
    if not os.path.exists(".git"):
         print("Error: Not a Git repository. Please run 'git init' in the project root directory first.")
         sys.exit(1)
    main()
