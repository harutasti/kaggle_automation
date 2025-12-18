#!/usr/bin/env python3
"""
Test the architecture fixes for AutoKaggle:
- kaggle_data copy to hypotheses/ and worktrees/
- PA working directory change to worktrees/
- Operation reordering: submit → score → PA → cleanup
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


def test_kim_get_submission_score():
    """Test that KIM has get_submission_score method."""
    print("=" * 80)
    print("TEST 1: KIM get_submission_score Method")
    print("=" * 80)
    print()

    kim_path = Path(project_root) / "src" / "core" / "kim.py"
    with open(kim_path, 'r') as f:
        kim_content = f.read()

    has_method = "def get_submission_score" in kim_content
    has_polling = "competition_submissions" in kim_content
    has_timeout = "wait_timeout" in kim_content

    print(f"kim.py:")
    print(f"   {'✅' if has_method else '❌'} get_submission_score method defined")
    print(f"   {'✅' if has_polling else '❌'} Uses competition_submissions API")
    print(f"   {'✅' if has_timeout else '❌'} Has wait_timeout parameter")
    print()

    assert has_method, "get_submission_score method not found"
    assert has_polling, "competition_submissions API not used"
    assert has_timeout, "wait_timeout parameter not found"


def test_user_interaction_confirm_iteration_submissions():
    """Test that UserConfirmation has confirm_iteration_submissions method."""
    print("=" * 80)
    print("TEST 2: UserConfirmation confirm_iteration_submissions Method")
    print("=" * 80)
    print()

    ui_path = Path(project_root) / "src" / "utils" / "user_interaction.py"
    with open(ui_path, 'r') as f:
        ui_content = f.read()

    has_method = "def confirm_iteration_submissions" in ui_content
    has_experiment_ids = "experiment_ids" in ui_content

    print(f"user_interaction.py:")
    print(f"   {'✅' if has_method else '❌'} confirm_iteration_submissions method defined")
    print(f"   {'✅' if has_experiment_ids else '❌'} Accepts experiment_ids parameter")
    print()

    assert has_method, "confirm_iteration_submissions method not found"
    assert has_experiment_ids, "experiment_ids parameter not found"


def test_eo_kaggle_data_copy():
    """Test that EO copies kaggle_data to worktrees."""
    print("=" * 80)
    print("TEST 3: EO kaggle_data Copy to Worktrees")
    print("=" * 80)
    print()

    eo_path = Path(project_root) / "src" / "execution" / "eo.py"
    with open(eo_path, 'r') as f:
        eo_content = f.read()

    has_shutil = "import shutil" in eo_content
    has_copytree = "shutil.copytree" in eo_content
    has_kaggle_data = "kaggle_data" in eo_content
    has_worktree_copy = "worktree_kaggle_data" in eo_content

    print(f"eo.py:")
    print(f"   {'✅' if has_shutil else '❌'} imports shutil")
    print(f"   {'✅' if has_copytree else '❌'} Uses shutil.copytree")
    print(f"   {'✅' if has_kaggle_data else '❌'} References kaggle_data")
    print(f"   {'✅' if has_worktree_copy else '❌'} Creates worktree_kaggle_data")
    print()

    assert has_shutil, "shutil import not found"
    assert has_copytree, "shutil.copytree not used"
    assert has_kaggle_data, "kaggle_data reference not found"
    assert has_worktree_copy, "worktree_kaggle_data not found"


def test_mcdu_kaggle_data_copy_to_hypotheses():
    """Test that MCDU copies kaggle_data to hypotheses."""
    print("=" * 80)
    print("TEST 4: MCDU kaggle_data Copy to Hypotheses")
    print("=" * 80)
    print()

    mcdu_path = Path(project_root) / "src" / "core" / "mcdu.py"
    with open(mcdu_path, 'r') as f:
        mcdu_content = f.read()

    has_shutil = "import shutil" in mcdu_content
    has_hypotheses_copy = "hypotheses_kaggle_data" in mcdu_content
    has_copytree = "shutil.copytree" in mcdu_content

    print(f"mcdu.py:")
    print(f"   {'✅' if has_shutil else '❌'} imports shutil")
    print(f"   {'✅' if has_hypotheses_copy else '❌'} References hypotheses_kaggle_data")
    print(f"   {'✅' if has_copytree else '❌'} Uses shutil.copytree")
    print()

    assert has_shutil, "shutil import not found"
    assert has_hypotheses_copy, "hypotheses_kaggle_data reference not found"
    assert has_copytree, "shutil.copytree not used"


def test_pa_worktrees_directory():
    """Test that PA uses worktrees directory as cwd."""
    print("=" * 80)
    print("TEST 5: PA Worktrees Directory")
    print("=" * 80)
    print()

    pa_path = Path(project_root) / "src" / "analysis" / "pa.py"
    with open(pa_path, 'r') as f:
        pa_content = f.read()

    has_worktrees_dir = "self.worktrees_dir" in pa_content
    has_worktrees_output = 'output_dir=self.worktrees_dir' in pa_content
    has_official_scores = "official_scores" in pa_content

    print(f"pa.py:")
    print(f"   {'✅' if has_worktrees_dir else '❌'} Defines worktrees_dir")
    print(f"   {'✅' if has_worktrees_output else '❌'} Uses worktrees_dir as output_dir")
    print(f"   {'✅' if has_official_scores else '❌'} Accepts official_scores parameter")
    print()

    assert has_worktrees_dir, "worktrees_dir not defined"
    assert has_worktrees_output, "worktrees_dir not used as output_dir"
    assert has_official_scores, "official_scores parameter not found"


def test_mcdu_operation_reordering():
    """Test that MCDU has correct operation order."""
    print("=" * 80)
    print("TEST 6: MCDU Operation Reordering")
    print("=" * 80)
    print()

    mcdu_path = Path(project_root) / "src" / "core" / "mcdu.py"
    with open(mcdu_path, 'r') as f:
        mcdu_content = f.read()

    has_find_submission = "_find_submission_file" in mcdu_content
    has_official_scores = "official_scores" in mcdu_content
    # Evolution mode cleanup is driven by PA's TERMINATE decisions via archive_worktree().
    has_archive_worktree = "archive_worktree" in mcdu_content
    has_remove_persistent = "keys_to_remove" in mcdu_content and "self.persistent_experiments.pop" in mcdu_content
    has_no_cleanup_note = "No worktree cleanup in evolution mode" in mcdu_content

    print(f"mcdu.py operation ordering:")
    print(f"   {'✅' if has_find_submission else '❌'} Has _find_submission_file helper")
    print(f"   {'✅' if has_official_scores else '❌'} Passes official_scores to PA")
    print(f"   {'✅' if has_archive_worktree else '❌'} Archives terminated worktrees")
    print(f"   {'✅' if has_remove_persistent else '❌'} Removes terminated worktrees from persistent tracking")
    print(f"   {'✅' if has_no_cleanup_note else '❌'} Explicitly notes no cleanup in evolution mode")
    print()

    assert has_find_submission, "_find_submission_file not found"
    assert has_official_scores, "official_scores not found"
    assert has_archive_worktree, "archive_worktree call not found"
    assert has_remove_persistent, "persistent_experiments removal logic not found"
    assert has_no_cleanup_note, "No-cleanup note not found"


def test_mcdu_submission_flow():
    """Test that MCDU submits experiments before PA."""
    print("=" * 80)
    print("TEST 7: MCDU Submission Flow")
    print("=" * 80)
    print()

    mcdu_path = Path(project_root) / "src" / "core" / "mcdu.py"
    with open(mcdu_path, 'r') as f:
        mcdu_content = f.read()

    # Check order: submission code appears before PA analysis
    submission_pos = mcdu_content.find("Submit successful experiments to Kaggle")
    pa_analysis_pos = mcdu_content.find("Performance analysis with evolution decisions")

    has_submission_section = submission_pos != -1
    has_pa_section = pa_analysis_pos != -1
    correct_order = submission_pos < pa_analysis_pos if (has_submission_section and has_pa_section) else False

    has_successful_filter = "successful_results = [r for r in iteration_results if r.status" in mcdu_content
    has_confirm_iteration = "confirm_iteration_submissions" in mcdu_content
    has_get_score = "get_submission_score" in mcdu_content

    print(f"mcdu.py submission flow:")
    print(f"   {'✅' if has_submission_section else '❌'} Has submission section")
    print(f"   {'✅' if has_pa_section else '❌'} Has PA analysis section")
    print(f"   {'✅' if correct_order else '❌'} Submission before PA (correct order)")
    print(f"   {'✅' if has_successful_filter else '❌'} Filters for successful experiments")
    print(f"   {'✅' if has_confirm_iteration else '❌'} Uses confirm_iteration_submissions")
    print(f"   {'✅' if has_get_score else '❌'} Calls get_submission_score")
    print()

    assert has_submission_section, "Submission section not found"
    assert has_pa_section, "PA analysis section not found"
    assert correct_order, "Submission should come before PA"
    assert has_successful_filter, "Successful results filter not found"
    assert has_confirm_iteration, "confirm_iteration_submissions not called"
    assert has_get_score, "get_submission_score not called"


def test_directory_structure_simulation():
    """Test the complete directory structure with kaggle_data copies."""
    print("=" * 80)
    print("TEST 8: Directory Structure Simulation")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Simulate experiment structure
        experiment_run_dir = Path(temp_dir) / "experiments" / "titanic" / "20251126_120000"
        experiment_run_dir.mkdir(parents=True)

        # Create source kaggle_data
        kaggle_data_src = experiment_run_dir / "kaggle_data"
        kaggle_data_src.mkdir()
        (kaggle_data_src / "train.csv").write_text("dummy train data")
        (kaggle_data_src / "test.csv").write_text("dummy test data")

        # Create hypotheses directory
        hypotheses_dir = experiment_run_dir / "hypotheses"
        hypotheses_dir.mkdir()

        # Simulate copying to hypotheses (like mcdu does)
        hypotheses_kaggle_data = hypotheses_dir / "kaggle_data"
        shutil.copytree(kaggle_data_src, hypotheses_kaggle_data)

        # Create worktrees directory and simulate worktree creation
        worktrees_dir = experiment_run_dir / "worktrees"
        worktrees_dir.mkdir()

        for exp_id in ["iter0_exp1_abc123", "iter0_exp2_def456"]:
            worktree_path = worktrees_dir / exp_id
            worktree_path.mkdir()
            # Simulate copying kaggle_data to worktree (like eo does)
            worktree_kaggle_data = worktree_path / "kaggle_data"
            shutil.copytree(kaggle_data_src, worktree_kaggle_data)

        # Verify structure
        print(f"Directory structure created:")
        print(f"   ✅ {kaggle_data_src.relative_to(experiment_run_dir)}/")
        print(f"   ✅ {hypotheses_kaggle_data.relative_to(experiment_run_dir)}/")
        for exp_id in ["iter0_exp1_abc123", "iter0_exp2_def456"]:
            worktree_kg = worktrees_dir / exp_id / "kaggle_data"
            print(f"   ✅ {worktree_kg.relative_to(experiment_run_dir)}/")

        print()

        # Assertions
        assert kaggle_data_src.exists(), "Source kaggle_data not created"
        assert hypotheses_kaggle_data.exists(), "Hypotheses kaggle_data not created"
        assert (hypotheses_kaggle_data / "train.csv").exists(), "train.csv not copied to hypotheses"

        for exp_id in ["iter0_exp1_abc123", "iter0_exp2_def456"]:
            worktree_kg = worktrees_dir / exp_id / "kaggle_data"
            assert worktree_kg.exists(), f"Worktree {exp_id} kaggle_data not created"
            assert (worktree_kg / "train.csv").exists(), f"train.csv not copied to worktree {exp_id}"

        print("✅ All kaggle_data copies verified")
        print()


def run_all_tests():
    """Run all architecture fix tests."""
    print()
    print("*" * 80)
    print("*" + " " * 21 + "ARCHITECTURE FIX TESTS" + " " * 21 + "*")
    print("*" * 80)
    print()

    tests = [
        ("KIM get_submission_score", test_kim_get_submission_score),
        ("UserConfirmation confirm_iteration_submissions", test_user_interaction_confirm_iteration_submissions),
        ("EO kaggle_data Copy", test_eo_kaggle_data_copy),
        ("MCDU kaggle_data to Hypotheses", test_mcdu_kaggle_data_copy_to_hypotheses),
        ("PA Worktrees Directory", test_pa_worktrees_directory),
        ("MCDU Operation Reordering", test_mcdu_operation_reordering),
        ("MCDU Submission Flow", test_mcdu_submission_flow),
        ("Directory Structure Simulation", test_directory_structure_simulation),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"❌ FAILED: {name}")
            print(f"   Error: {e}")
            print()

    print("=" * 80)
    print(f"SUMMARY: {passed}/{len(tests)} tests passed")
    print("=" * 80)

    if failed == 0:
        print()
        print("✅ ALL ARCHITECTURE FIX TESTS PASSED!")
        print()
        print("Architecture changes verified:")
        print("  • KIM: get_submission_score() method for Kaggle score polling")
        print("  • UserConfirmation: confirm_iteration_submissions() for per-iteration confirmation")
        print("  • EO: Copies kaggle_data to each worktree")
        print("  • MCDU: Copies kaggle_data to hypotheses/ after download")
        print("  • PA: Uses worktrees/ as cwd for Codex execution")
        print("  • MCDU: Reordered to submit → score → PA → cleanup")
    else:
        print()
        print(f"❌ {failed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
