#!/usr/bin/env python3
"""
Test script for Codex integration.

This script demonstrates how to:
1. Create a simple test task
2. Execute it with Codex
3. Parse and validate results

Run this before full integration to verify Codex is working correctly.
"""

import json
import logging
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.codex_executor import execute_codex_experiment, execute_with_retry
from src.utils.file_utils import ensure_dir


def create_simple_test_task(task_path: Path, exp_id: str) -> None:
    """Create a minimal test task for Codex"""
    task_content = f"""# Test Experiment: {exp_id}

**Iteration:** 0
**Strategy:** TestBasic
**Competition:** test-competition (Accuracy)

## Parameters
```json
{{
  "model": "simple",
  "test_mode": true
}}
```

## Instructions for Codex Agent

This is a minimal test to verify Codex integration. Please:

1. **Create a test result file**:
   - Create `result_{exp_id}.json` with content:
     ```json
     {{
       "score": 0.85,
       "test": true,
       "message": "Codex is working!"
     }}
     ```

2. **Create a completion signal**:
   - Create an empty file named `DONE_{exp_id}`

3. **Optional - Create test submission**:
   - Create `submission_{exp_id}.csv` with simple content:
     ```
     id,prediction
     1,0.5
     2,0.7
     ```

That's it! This is just to test the Codex integration pipeline.
"""
    task_path.write_text(task_content, encoding="utf-8")
    print(f"✓ Created test task: {task_path}")


def main():
    """Run integration test"""
    print("=" * 60)
    print("Codex Integration Test")
    print("=" * 60)
    print()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create temporary test environment
    with tempfile.TemporaryDirectory(prefix="codex_test_") as tmpdir:
        tmpdir = Path(tmpdir)
        print(f"Test directory: {tmpdir}\n")

        # Create test files
        exp_id = "test_exp_simple"
        task_path = tmpdir / f"{exp_id}_task.md"
        worktree_path = tmpdir / "worktree"
        worktree_path.mkdir()

        create_simple_test_task(task_path, exp_id)

        # Test 1: Basic execution
        print("\n" + "=" * 60)
        print("TEST 1: Basic Execution")
        print("=" * 60)

        result = execute_codex_experiment(
            task_markdown_path=task_path,
            worktree_path=worktree_path,
            experiment_id=exp_id,
            timeout=120  # 2 minutes
        )

        print(f"\nResult:")
        print(f"  Success: {result.success}")
        print(f"  Execution Time: {result.execution_time:.2f}s")

        if result.success:
            print(f"  Score: {result.result_data.get('score')}")
            print(f"  Output File: {result.output_file}")
            print(f"\n✓ TEST 1 PASSED - Codex executed successfully!")

            # Verify files created
            result_file = worktree_path / f"result_{exp_id}.json"
            done_file = worktree_path / f"DONE_{exp_id}"

            print(f"\nFiles created:")
            print(f"  result_{exp_id}.json: {result_file.exists()}")
            print(f"  DONE_{exp_id}: {done_file.exists()}")
            print(f"  codex_output_{exp_id}.md: {result.output_file.exists()}")

            if result_file.exists():
                with open(result_file) as f:
                    data = json.load(f)
                print(f"\nResult content:")
                print(json.dumps(data, indent=2))

        else:
            print(f"  Error: {result.error}")
            print(f"  Error Type: {result.error_type}")
            print(f"\n✗ TEST 1 FAILED - Codex did not complete successfully")

            if result.output_file and result.output_file.exists():
                print(f"\nCodex output preview:")
                print("-" * 60)
                print(result.raw_output[:500])
                print("-" * 60)

            return 1

        # Test 2: Retry logic
        print("\n" + "=" * 60)
        print("TEST 2: Retry Logic (using same task, should succeed immediately)")
        print("=" * 60)

        # Clean up previous results
        for file in worktree_path.glob("*"):
            file.unlink()

        result2 = execute_with_retry(
            task_markdown_path=task_path,
            worktree_path=worktree_path,
            experiment_id=exp_id,
            timeout=120,
            max_retries=2
        )

        print(f"\nResult:")
        print(f"  Success: {result2.success}")
        print(f"  Execution Time: {result2.execution_time:.2f}s")

        if result2.success:
            print(f"  Score: {result2.result_data.get('score')}")
            print(f"\n✓ TEST 2 PASSED - Retry logic works!")
        else:
            print(f"\n✗ TEST 2 FAILED - Retry logic issue")
            return 1

    # Summary
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    print("\nCodex integration is working correctly.")
    print("\nNext steps:")
    print("1. Update config/config.json to enable Codex:")
    print('   "execution_mode": "codex"')
    print("2. Run with 1 experiment first:")
    print('   "wca_per_iteration": 1, "max_iterations": 1')
    print("3. Test on Titanic or House Prices competition")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
