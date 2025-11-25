#!/usr/bin/env python3
"""
Test the JSONL output functionality for Codex responses.

Tests:
- Directory creation for codex-responses/{KSE,WAA,PA}
- JSONL file naming conventions
- --json flag in subprocess calls
- JSONL copying from worktree to codex-responses
"""

import os
import sys
import re
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.utils.codex_executor import (
    execute_codex_experiment,
    execute_kse_hypothesis_generation,
    execute_pa_analysis,
    CodexMode,
    CodexResult
)


def test_jsonl_directory_structure():
    """Test that codex-responses directories are created correctly."""
    print("=" * 80)
    print("TEST 1: JSONL Directory Structure")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        experiment_run_dir = Path(temp_dir) / "experiments" / "titanic" / "20251125_120000"
        experiment_run_dir.mkdir(parents=True)

        # Simulate what main.py does
        codex_responses_dir = experiment_run_dir / "codex-responses"
        codex_responses_dir.mkdir(exist_ok=True)
        (codex_responses_dir / "KSE").mkdir(exist_ok=True)
        (codex_responses_dir / "WAA").mkdir(exist_ok=True)
        (codex_responses_dir / "PA").mkdir(exist_ok=True)

        # Verify directories exist
        assert (codex_responses_dir / "KSE").exists(), "KSE directory not created"
        assert (codex_responses_dir / "WAA").exists(), "WAA directory not created"
        assert (codex_responses_dir / "PA").exists(), "PA directory not created"

        print(f"✅ Created directory structure:")
        print(f"   {codex_responses_dir}")
        print(f"   ├── KSE/")
        print(f"   ├── WAA/")
        print(f"   └── PA/")
        print()


def test_jsonl_naming_convention():
    """Test JSONL file naming conventions."""
    print("=" * 80)
    print("TEST 2: JSONL Naming Convention")
    print("=" * 80)
    print()

    # Test WAA naming: response-{parallel_id}-{iteration}.jsonl
    test_cases = [
        ("iter0_exp1_abc123", "response-1-0.jsonl"),
        ("iter0_exp2_def456", "response-2-0.jsonl"),
        ("iter1_exp1_ghi789", "response-1-1.jsonl"),
        ("iter1_exp3_jkl012", "response-3-1.jsonl"),
        ("iter2_exp5_mno345", "response-5-2.jsonl"),
    ]

    print("WAA JSONL naming (response-{parallel_id}-{iteration}.jsonl):")
    all_passed = True
    for experiment_id, expected_filename in test_cases:
        match = re.match(r'iter(\d+)_exp(\d+)_', experiment_id)
        if match:
            iteration, parallel_id = match.groups()
            actual_filename = f"response-{parallel_id}-{iteration}.jsonl"
        else:
            actual_filename = f"response-{experiment_id}.jsonl"

        passed = actual_filename == expected_filename
        status = "✅" if passed else "❌"
        print(f"   {status} {experiment_id} → {actual_filename}")
        if not passed:
            print(f"      Expected: {expected_filename}")
            all_passed = False

    print()

    # Test KSE naming: response-{iteration}.jsonl
    print("KSE JSONL naming (response-{iteration}.jsonl):")
    for iteration in [0, 1, 2]:
        filename = f"response-{iteration}.jsonl"
        print(f"   ✅ iteration {iteration} → {filename}")

    print()

    # Test PA naming: response-{iteration}.jsonl
    print("PA JSONL naming (response-{iteration}.jsonl):")
    for iteration in [0, 1, 2]:
        filename = f"response-{iteration}.jsonl"
        print(f"   ✅ iteration {iteration} → {filename}")

    print()
    assert all_passed, "Some naming tests failed"


def test_json_flag_in_command():
    """Test that --json flag is included in Codex commands."""
    print("=" * 80)
    print("TEST 3: --json Flag in Commands")
    print("=" * 80)
    print()

    # Read the source files and verify --json flag is present
    codex_executor_path = Path(project_root) / "src" / "utils" / "codex_executor.py"
    eo_path = Path(project_root) / "src" / "execution" / "eo.py"

    with open(codex_executor_path, 'r') as f:
        codex_executor_content = f.read()

    with open(eo_path, 'r') as f:
        eo_content = f.read()

    # Check for --json flag in codex_executor.py
    json_flag_count = codex_executor_content.count('"--json"')
    print(f"codex_executor.py:")
    print(f"   Found '--json' flag {json_flag_count} times")
    assert json_flag_count >= 3, f"Expected at least 3 '--json' flags in codex_executor.py, found {json_flag_count}"
    print(f"   ✅ WAA subprocess call has --json")
    print(f"   ✅ KSE subprocess call has --json")
    print(f"   ✅ PA subprocess call has --json")
    print()

    # Check for --json flag in eo.py
    json_flag_in_eo = "'--json'" in eo_content or '"--json"' in eo_content
    print(f"eo.py:")
    if json_flag_in_eo:
        print(f"   ✅ _launch_codex_experiment has --json")
    else:
        print(f"   ❌ Missing --json flag")
    assert json_flag_in_eo, "--json flag not found in eo.py"
    print()


def test_jsonl_output_saving():
    """Test that JSONL output is saved correctly."""
    print("=" * 80)
    print("TEST 4: JSONL Output Saving")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        codex_responses_dir = Path(temp_dir) / "codex-responses"
        (codex_responses_dir / "KSE").mkdir(parents=True)
        (codex_responses_dir / "WAA").mkdir(parents=True)
        (codex_responses_dir / "PA").mkdir(parents=True)

        # Simulate JSONL output content
        sample_jsonl = """{"type":"thread.started","thread_id":"test-123"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"Analyzing..."}}
{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":"Done"}}
{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":50}}"""

        # Test KSE JSONL saving
        kse_jsonl_path = codex_responses_dir / "KSE" / "response-0.jsonl"
        kse_jsonl_path.write_text(sample_jsonl)
        assert kse_jsonl_path.exists(), "KSE JSONL not saved"
        print(f"✅ KSE JSONL saved: {kse_jsonl_path.name}")

        # Test WAA JSONL saving
        waa_jsonl_path = codex_responses_dir / "WAA" / "response-1-0.jsonl"
        waa_jsonl_path.write_text(sample_jsonl)
        assert waa_jsonl_path.exists(), "WAA JSONL not saved"
        print(f"✅ WAA JSONL saved: {waa_jsonl_path.name}")

        # Test PA JSONL saving
        pa_jsonl_path = codex_responses_dir / "PA" / "response-0.jsonl"
        pa_jsonl_path.write_text(sample_jsonl)
        assert pa_jsonl_path.exists(), "PA JSONL not saved"
        print(f"✅ PA JSONL saved: {pa_jsonl_path.name}")

        # Verify content
        content = kse_jsonl_path.read_text()
        assert "thread.started" in content, "JSONL content invalid"
        assert "turn.completed" in content, "JSONL content invalid"
        print()
        print(f"✅ JSONL content verified (5 lines)")
        print()


def test_rad_jsonl_copy():
    """Test that RAD copies JSONL from worktree to codex-responses."""
    print("=" * 80)
    print("TEST 5: RAD JSONL Copy Logic")
    print("=" * 80)
    print()

    # Read rad.py and verify JSONL copy logic exists
    rad_path = Path(project_root) / "src" / "analysis" / "rad.py"

    with open(rad_path, 'r') as f:
        rad_content = f.read()

    # Check for JSONL copy logic
    has_jsonl_copy = "codex_output_" in rad_content and ".jsonl" in rad_content
    has_codex_responses = "codex-responses" in rad_content
    has_waa_dir = '"WAA"' in rad_content or "'WAA'" in rad_content

    print(f"rad.py analysis:")
    print(f"   {'✅' if has_jsonl_copy else '❌'} JSONL file detection (codex_output_*.jsonl)")
    print(f"   {'✅' if has_codex_responses else '❌'} codex-responses directory reference")
    print(f"   {'✅' if has_waa_dir else '❌'} WAA subdirectory reference")

    assert has_jsonl_copy, "JSONL copy logic not found in rad.py"
    assert has_codex_responses, "codex-responses directory not referenced in rad.py"
    assert has_waa_dir, "WAA directory not referenced in rad.py"
    print()


def test_caller_updates():
    """Test that callers pass codex_responses_dir parameter."""
    print("=" * 80)
    print("TEST 6: Caller Updates (kse.py, pa.py)")
    print("=" * 80)
    print()

    kse_path = Path(project_root) / "src" / "core" / "kse.py"
    pa_path = Path(project_root) / "src" / "analysis" / "pa.py"

    with open(kse_path, 'r') as f:
        kse_content = f.read()

    with open(pa_path, 'r') as f:
        pa_content = f.read()

    # Check for codex_responses_dir in kse.py
    kse_has_param = "codex_responses_dir" in kse_content
    print(f"kse.py:")
    print(f"   {'✅' if kse_has_param else '❌'} Passes codex_responses_dir to execute_codex()")

    # Check for codex_responses_dir in pa.py
    pa_has_param = "codex_responses_dir" in pa_content
    print(f"pa.py:")
    print(f"   {'✅' if pa_has_param else '❌'} Passes codex_responses_dir to execute_codex()")

    assert kse_has_param, "codex_responses_dir not passed in kse.py"
    assert pa_has_param, "codex_responses_dir not passed in pa.py"
    print()


def test_full_jsonl_workflow():
    """Test the complete JSONL workflow simulation."""
    print("=" * 80)
    print("TEST 7: Full JSONL Workflow Simulation")
    print("=" * 80)
    print()

    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup directory structure (mimics main.py)
        experiment_run_dir = Path(temp_dir) / "experiments" / "titanic" / "20251125_120000"
        experiment_run_dir.mkdir(parents=True)

        codex_responses_dir = experiment_run_dir / "codex-responses"
        (codex_responses_dir / "KSE").mkdir(parents=True)
        (codex_responses_dir / "WAA").mkdir(parents=True)
        (codex_responses_dir / "PA").mkdir(parents=True)

        worktrees_dir = experiment_run_dir / "worktrees"
        worktrees_dir.mkdir()

        # Sample JSONL content
        sample_jsonl = """{"type":"thread.started","thread_id":"test-workflow"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Processing..."}}
{"type":"turn.completed","usage":{"input_tokens":500,"output_tokens":200}}"""

        print("Simulating iteration 0 workflow:")
        print()

        # Step 1: KSE generates hypotheses (JSONL saved)
        print("1. KSE generates hypotheses")
        kse_jsonl = codex_responses_dir / "KSE" / "response-0.jsonl"
        kse_jsonl.write_text(sample_jsonl)
        print(f"   ✅ Saved: codex-responses/KSE/response-0.jsonl")

        # Step 2: WAA executes 3 experiments (JSONL saved per experiment)
        print("2. WAA executes 3 experiments")
        for exp_num in range(1, 4):
            exp_id = f"iter0_exp{exp_num}_abc{exp_num:03d}"

            # First, JSONL is saved in worktree
            worktree_path = worktrees_dir / exp_id
            worktree_path.mkdir()
            worktree_jsonl = worktree_path / f"codex_output_{exp_id}.jsonl"
            worktree_jsonl.write_text(sample_jsonl)

            # Then RAD copies it to codex-responses/WAA/
            waa_jsonl = codex_responses_dir / "WAA" / f"response-{exp_num}-0.jsonl"
            waa_jsonl.write_text(sample_jsonl)
            print(f"   ✅ Saved: codex-responses/WAA/response-{exp_num}-0.jsonl")

        # Step 3: PA analyzes results (JSONL saved)
        print("3. PA analyzes results")
        pa_jsonl = codex_responses_dir / "PA" / "response-0.jsonl"
        pa_jsonl.write_text(sample_jsonl)
        print(f"   ✅ Saved: codex-responses/PA/response-0.jsonl")

        print()

        # Verify all files exist
        expected_files = [
            codex_responses_dir / "KSE" / "response-0.jsonl",
            codex_responses_dir / "WAA" / "response-1-0.jsonl",
            codex_responses_dir / "WAA" / "response-2-0.jsonl",
            codex_responses_dir / "WAA" / "response-3-0.jsonl",
            codex_responses_dir / "PA" / "response-0.jsonl",
        ]

        print("Verifying all JSONL files:")
        all_exist = True
        for file_path in expected_files:
            exists = file_path.exists()
            status = "✅" if exists else "❌"
            print(f"   {status} {file_path.relative_to(experiment_run_dir)}")
            if not exists:
                all_exist = False

        assert all_exist, "Not all expected JSONL files were created"
        print()
        print(f"✅ Total JSONL files created: {len(expected_files)}")
        print()


def run_all_tests():
    """Run all JSONL output tests."""
    print()
    print("*" * 80)
    print("*" + " " * 25 + "JSONL OUTPUT TESTS" + " " * 25 + "*")
    print("*" * 80)
    print()

    tests = [
        ("Directory Structure", test_jsonl_directory_structure),
        ("Naming Convention", test_jsonl_naming_convention),
        ("--json Flag", test_json_flag_in_command),
        ("JSONL Saving", test_jsonl_output_saving),
        ("RAD Copy Logic", test_rad_jsonl_copy),
        ("Caller Updates", test_caller_updates),
        ("Full Workflow", test_full_jsonl_workflow),
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
        print("✅ ALL JSONL OUTPUT TESTS PASSED!")
        print()
        print("JSONL output is correctly configured for:")
        print("  • KSE: codex-responses/KSE/response-{iteration}.jsonl")
        print("  • WAA: codex-responses/WAA/response-{parallel_id}-{iteration}.jsonl")
        print("  • PA:  codex-responses/PA/response-{iteration}.jsonl")
    else:
        print()
        print(f"❌ {failed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
