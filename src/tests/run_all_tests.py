#!/usr/bin/env python3
"""
Run all tests in the test suite.
"""

import os
import sys
import subprocess
from pathlib import Path

def run_test(test_file: str) -> bool:
    """Run a single test file and return success status."""
    print(f"\n{'=' * 80}")
    print(f"Running: {test_file}")
    print('=' * 80)

    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        # Print output
        print(result.stdout)
        if result.stderr:
            # Filter out pandas warnings
            for line in result.stderr.split('\n'):
                if 'UserWarning' not in line and 'dateutil' not in line:
                    print(line, file=sys.stderr)

        if result.returncode == 0:
            print(f"✅ {test_file}: PASSED")
            return True
        else:
            print(f"❌ {test_file}: FAILED (exit code: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        print(f"❌ {test_file}: TIMEOUT (exceeded 5 minutes)")
        return False
    except Exception as e:
        print(f"❌ {test_file}: ERROR - {e}")
        return False

def main():
    """Run all tests in the tests directory."""
    tests_dir = Path(__file__).parent
    test_files = [
        tests_dir / "test_components.py",
        # tests_dir / "test_codex_integration.py",  # Skip Codex test for now
    ]

    print("=" * 80)
    print("RUNNING ALL TESTS")
    print("=" * 80)

    results = {}
    for test_file in test_files:
        if test_file.exists():
            results[test_file.name] = run_test(str(test_file))
        else:
            print(f"⚠️  Test file not found: {test_file}")
            results[test_file.name] = False

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for test_name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{test_name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    # Clean up test output files if all tests passed
    if passed == total:
        print("\n🧹 Cleaning up test output files...")
        for output_file in tests_dir.glob("test_output_*.md"):
            output_file.unlink()
            print(f"   Removed: {output_file.name}")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())