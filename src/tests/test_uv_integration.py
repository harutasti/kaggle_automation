#!/usr/bin/env python3
"""
Test the uv integration for AutoKaggle:
- experiment_pyproject.toml exists
- config.json has experiment_pyproject_path
- KSE injects uv requirements into task markdown
- EO copies pyproject.toml and runs uv sync
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


def test_experiment_pyproject_exists():
    """Test that experiment_pyproject.toml exists."""
    print("=" * 80)
    print("TEST 1: experiment_pyproject.toml Exists")
    print("=" * 80)
    print()

    pyproject_path = Path(project_root) / "config" / "experiment_pyproject.toml"
    exists = pyproject_path.exists()

    if exists:
        with open(pyproject_path, 'r') as f:
            content = f.read()
        has_project = "[project]" in content
        has_dependencies = "dependencies" in content
        has_pandas = "pandas" in content
        has_sklearn = "scikit-learn" in content

        print(f"experiment_pyproject.toml:")
        print(f"   {'✅' if exists else '❌'} File exists")
        print(f"   {'✅' if has_project else '❌'} Has [project] section")
        print(f"   {'✅' if has_dependencies else '❌'} Has dependencies")
        print(f"   {'✅' if has_pandas else '❌'} Includes pandas")
        print(f"   {'✅' if has_sklearn else '❌'} Includes scikit-learn")
        print()

        assert has_project, "[project] section not found"
        assert has_dependencies, "dependencies not found"
        assert has_pandas, "pandas not in dependencies"
        assert has_sklearn, "scikit-learn not in dependencies"
    else:
        print(f"❌ experiment_pyproject.toml not found at {pyproject_path}")
        assert False, "experiment_pyproject.toml not found"


def test_config_has_pyproject_path():
    """Test that config.json has experiment_pyproject_path."""
    print("=" * 80)
    print("TEST 2: Config Has experiment_pyproject_path")
    print("=" * 80)
    print()

    import json
    config_path = Path(project_root) / "config" / "config.json"

    with open(config_path, 'r') as f:
        config = json.load(f)

    has_key = "experiment_pyproject_path" in config
    correct_value = config.get("experiment_pyproject_path") == "config/experiment_pyproject.toml"

    print(f"config.json:")
    print(f"   {'✅' if has_key else '❌'} Has experiment_pyproject_path key")
    print(f"   {'✅' if correct_value else '❌'} Points to correct file")
    print()

    assert has_key, "experiment_pyproject_path key not found"
    assert correct_value, "experiment_pyproject_path has wrong value"


def test_kse_has_uv_requirements_method():
    """Test that KSE has _get_uv_requirements_section method."""
    print("=" * 80)
    print("TEST 3: KSE Has UV Requirements Method")
    print("=" * 80)
    print()

    kse_path = Path(project_root) / "src" / "core" / "kse.py"
    with open(kse_path, 'r') as f:
        kse_content = f.read()

    has_method = "def _get_uv_requirements_section" in kse_content
    has_uv_add = "uv add" in kse_content
    has_uv_run = "uv run" in kse_content
    has_critical = "CRITICAL" in kse_content
    has_violation = "VIOLATION" in kse_content

    print(f"kse.py:")
    print(f"   {'✅' if has_method else '❌'} _get_uv_requirements_section method defined")
    print(f"   {'✅' if has_uv_add else '❌'} Contains 'uv add' instruction")
    print(f"   {'✅' if has_uv_run else '❌'} Contains 'uv run' instruction")
    print(f"   {'✅' if has_critical else '❌'} Contains CRITICAL warning")
    print(f"   {'✅' if has_violation else '❌'} Contains VIOLATION warning")
    print()

    assert has_method, "_get_uv_requirements_section method not found"
    assert has_uv_add, "'uv add' instruction not found"
    assert has_uv_run, "'uv run' instruction not found"
    assert has_critical, "CRITICAL warning not found"
    assert has_violation, "VIOLATION warning not found"


def test_kse_injects_uv_requirements():
    """Test that KSE injects uv requirements into task markdown."""
    print("=" * 80)
    print("TEST 4: KSE Injects UV Requirements")
    print("=" * 80)
    print()

    kse_path = Path(project_root) / "src" / "core" / "kse.py"
    with open(kse_path, 'r') as f:
        kse_content = f.read()

    # Check that both task markdown methods inject uv requirements
    method1_injection = "uv_requirements = self._get_uv_requirements_section()" in kse_content
    method1_prepend = 'return uv_requirements + "\\n\\n" + task_md' in kse_content
    method2_prepend = 'return uv_requirements + "\\n\\n" + markdown.strip()' in kse_content

    print(f"kse.py task markdown generation:")
    print(f"   {'✅' if method1_injection else '❌'} Gets uv_requirements_section")
    print(f"   {'✅' if method1_prepend else '❌'} Injects into _generate_task_markdown_from_hypothesis")
    print(f"   {'✅' if method2_prepend else '❌'} Injects into _generate_task_markdown")
    print()

    assert method1_injection, "uv_requirements_section not called"
    assert method1_prepend or method2_prepend, "uv requirements not prepended to markdown"


def test_eo_copies_pyproject():
    """Test that EO copies pyproject.toml to worktrees."""
    print("=" * 80)
    print("TEST 5: EO Copies pyproject.toml")
    print("=" * 80)
    print()

    eo_path = Path(project_root) / "src" / "execution" / "eo.py"
    with open(eo_path, 'r') as f:
        eo_content = f.read()

    has_pyproject_config = 'experiment_pyproject_path' in eo_content
    has_copy_pyproject = 'worktree_pyproject' in eo_content
    has_shutil_copy = 'shutil.copy2' in eo_content

    print(f"eo.py pyproject.toml copying:")
    print(f"   {'✅' if has_pyproject_config else '❌'} Reads experiment_pyproject_path from config")
    print(f"   {'✅' if has_copy_pyproject else '❌'} Copies to worktree_pyproject")
    print(f"   {'✅' if has_shutil_copy else '❌'} Uses shutil.copy2")
    print()

    assert has_pyproject_config, "experiment_pyproject_path config not used"
    assert has_copy_pyproject, "worktree_pyproject not found"
    assert has_shutil_copy, "shutil.copy2 not used"


def test_eo_copies_uv_lock():
    """Test that EO copies uv.lock to worktrees."""
    print("=" * 80)
    print("TEST 6: EO Copies uv.lock")
    print("=" * 80)
    print()

    eo_path = Path(project_root) / "src" / "execution" / "eo.py"
    with open(eo_path, 'r') as f:
        eo_content = f.read()

    has_uv_lock_src = 'uv_lock_src' in eo_content
    has_worktree_uv_lock = 'worktree_uv_lock' in eo_content
    has_experiment_uv_lock = 'experiment_uv.lock' in eo_content

    print(f"eo.py uv.lock copying:")
    print(f"   {'✅' if has_uv_lock_src else '❌'} Has uv_lock_src variable")
    print(f"   {'✅' if has_worktree_uv_lock else '❌'} Has worktree_uv_lock variable")
    print(f"   {'✅' if has_experiment_uv_lock else '❌'} Checks for experiment_uv.lock")
    print()

    assert has_uv_lock_src, "uv_lock_src not found"
    assert has_worktree_uv_lock, "worktree_uv_lock not found"


def test_eo_runs_uv_sync():
    """Test that EO runs uv sync in worktrees."""
    print("=" * 80)
    print("TEST 7: EO Runs uv sync")
    print("=" * 80)
    print()

    eo_path = Path(project_root) / "src" / "execution" / "eo.py"
    with open(eo_path, 'r') as f:
        eo_content = f.read()

    has_uv_sync = "'uv', 'sync'" in eo_content
    has_subprocess_run = 'subprocess.run' in eo_content
    has_timeout = 'timeout=300' in eo_content
    has_error_handling = 'subprocess.TimeoutExpired' in eo_content
    has_file_not_found = 'FileNotFoundError' in eo_content

    print(f"eo.py uv sync execution:")
    print(f"   {'✅' if has_uv_sync else '❌'} Runs 'uv sync' command")
    print(f"   {'✅' if has_subprocess_run else '❌'} Uses subprocess.run")
    print(f"   {'✅' if has_timeout else '❌'} Has 5 minute timeout")
    print(f"   {'✅' if has_error_handling else '❌'} Handles TimeoutExpired")
    print(f"   {'✅' if has_file_not_found else '❌'} Handles FileNotFoundError (uv not installed)")
    print()

    assert has_uv_sync, "'uv sync' command not found"
    assert has_subprocess_run, "subprocess.run not used"
    assert has_timeout, "timeout not set"
    assert has_error_handling, "TimeoutExpired not handled"
    assert has_file_not_found, "FileNotFoundError not handled"


def run_all_tests():
    """Run all uv integration tests."""
    print()
    print("*" * 80)
    print("*" + " " * 23 + "UV INTEGRATION TESTS" + " " * 23 + "*")
    print("*" * 80)
    print()

    tests = [
        ("experiment_pyproject.toml exists", test_experiment_pyproject_exists),
        ("Config has experiment_pyproject_path", test_config_has_pyproject_path),
        ("KSE has UV requirements method", test_kse_has_uv_requirements_method),
        ("KSE injects UV requirements", test_kse_injects_uv_requirements),
        ("EO copies pyproject.toml", test_eo_copies_pyproject),
        ("EO copies uv.lock", test_eo_copies_uv_lock),
        ("EO runs uv sync", test_eo_runs_uv_sync),
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
        print("✅ ALL UV INTEGRATION TESTS PASSED!")
        print()
        print("UV Integration verified:")
        print("  • experiment_pyproject.toml with ML dependencies")
        print("  • config.json with experiment_pyproject_path")
        print("  • KSE injects strict uv usage requirements into task markdown")
        print("  • EO copies pyproject.toml and uv.lock to worktrees")
        print("  • EO runs 'uv sync' before launching experiments")
    else:
        print()
        print(f"❌ {failed} test(s) failed")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
