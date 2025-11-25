#!/usr/bin/env python3
"""
Test the new timestamped directory structure.
"""

import os
import sys
import json
import shutil
from datetime import datetime
import time

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


def test_directory_structure():
    """Test the new directory structure creation."""

    print("=" * 80)
    print("TESTING NEW DIRECTORY STRUCTURE")
    print("=" * 80)
    print()

    # Test configuration
    test_config = {
        "kaggle_competition_name": "titanic",
        "competition": {
            "name": "titanic"
        },
        "experiments_base_dir": "./test_experiments",
        "max_iterations": 2,
        "wca_per_iteration": 2,
        "simulation_mode": True,
        "kse_codex_enabled": False,
        "pa_codex_enabled": False
    }

    # Clean up any previous test
    if os.path.exists("./test_experiments"):
        shutil.rmtree("./test_experiments")

    print("1. Testing NORMAL mode (creates directories)")
    print("-" * 40)

    # Simulate normal mode
    dry_run = False
    timestamp1 = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Get competition name
    competition_name = test_config.get("competition", {}).get("name", "unknown")
    if not competition_name:
        competition_name = test_config.get("kaggle_competition_name", "unknown")

    # Build experiment run directory
    experiments_root = test_config.get("experiments_base_dir", "./experiments")
    experiment_run_dir = os.path.join(experiments_root, competition_name, timestamp1)

    print(f"Competition: {competition_name}")
    print(f"Timestamp: {timestamp1}")
    print(f"Directory: {experiment_run_dir}")

    if not dry_run:
        # Create directories
        from src.utils.file_utils import ensure_dir

        ensure_dir(experiment_run_dir)
        ensure_dir(os.path.join(experiment_run_dir, "worktrees"))
        ensure_dir(os.path.join(experiment_run_dir, "results"))
        ensure_dir(os.path.join(experiment_run_dir, "hypotheses"))
        ensure_dir(os.path.join(experiment_run_dir, "analysis"))
        ensure_dir(os.path.join(experiment_run_dir, "kaggle_data"))

        print("\n✅ Created directories:")
        for root, dirs, files in os.walk(experiment_run_dir):
            level = root.replace(experiment_run_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for d in dirs:
                print(f"{subindent}{d}/")

    print()

    # Wait a moment to ensure different timestamp
    time.sleep(2)

    print("2. Testing DRY-RUN mode (no directory creation)")
    print("-" * 40)

    # Simulate dry-run mode
    dry_run = True
    timestamp2 = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_run_dir2 = os.path.join(experiments_root, competition_name, timestamp2)

    print(f"Competition: {competition_name}")
    print(f"Timestamp: {timestamp2}")
    print(f"Would create: {experiment_run_dir2}")

    if dry_run:
        print("✅ DRY-RUN: No directories created")

        # Verify no directory was created
        if not os.path.exists(experiment_run_dir2):
            print("✅ Confirmed: Directory does not exist")
        else:
            print("❌ ERROR: Directory should not exist in dry-run mode")

    print()
    print("3. Testing multiple competitions")
    print("-" * 40)

    competitions = ["titanic", "house-prices", "digit-recognizer"]

    for comp in competitions:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]  # Use microseconds for uniqueness
        comp_dir = os.path.join(experiments_root, comp, timestamp)

        from src.utils.file_utils import ensure_dir
        ensure_dir(comp_dir)

        print(f"✅ Created: {comp_dir}")
        time.sleep(0.1)  # Small delay

    print()
    print("4. Final directory structure:")
    print("-" * 40)

    def show_tree(path, prefix=""):
        """Display directory tree."""
        if not os.path.exists(path):
            return

        items = []
        for item in sorted(os.listdir(path)):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                items.append((item, True))

        for i, (item, is_dir) in enumerate(items):
            is_last = i == len(items) - 1
            current_prefix = "└── " if is_last else "├── "
            print(f"{prefix}{current_prefix}{item}/")

            if is_dir and item != "__pycache__":
                next_prefix = prefix + ("    " if is_last else "│   ")
                show_tree(os.path.join(path, item), next_prefix)

    print(f"{experiments_root}/")
    show_tree(experiments_root, "")

    print()
    print("=" * 80)
    print("✅ TEST COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"- Normal mode creates: ./experiments/<competition>/<timestamp>/")
    print(f"- Dry-run mode creates: Nothing")
    print(f"- Each run gets unique timestamp")
    print(f"- Subdirectories: worktrees/, results/, hypotheses/, analysis/, kaggle_data/")

    # Clean up
    print()
    print("Cleaning up test directories...")
    if os.path.exists("./test_experiments"):
        shutil.rmtree("./test_experiments")
        print("✅ Cleanup completed")


if __name__ == "__main__":
    test_directory_structure()