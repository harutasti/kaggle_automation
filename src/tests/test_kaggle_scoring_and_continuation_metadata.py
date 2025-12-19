#!/usr/bin/env python3
"""
Test script for two production issues observed in AutoKaggle runs:

1) Kaggle submission score polling:
   Kaggle 1.8+ returns kagglesdk objects where scores are exposed via snake_case
   properties (e.g., `public_score`) even though the serialized payload uses
   camelCase keys (e.g., `publicScore`). Ensure our score polling logic supports
   both shapes.

2) Continuation strategy metadata:
   Continuation experiments reuse an existing worktree. Ensure the orchestrator
   writes hypothesis metadata for the continuation ID so RAD can preserve
   `strategy_name` instead of falling back to "Unknown".
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.core.kim import KaggleInterfaceManager
from src.data_models import ContinuationHypothesis
from src.execution.eo import ExperimentOrchestrator


class _FakeSubmission:
    def __init__(
        self,
        ref: int,
        *,
        public_score: str | None = None,
        publicScore: str | None = None,
        status: str = "PENDING",
        description: str | None = None,
        date: str | None = None,
    ):
        self.ref = ref
        if public_score is not None:
            self.public_score = public_score
        if publicScore is not None:
            self.publicScore = publicScore
        self.status = status
        self.description = description
        self.date = date


class _FakeSubmitResponse:
    def __init__(self, ref: int):
        self.ref = ref

    def __repr__(self) -> str:  # Keep logs readable if printed
        return json.dumps({"message": "OK", "ref": self.ref})


def test_kaggle_version() -> bool:
    print("=" * 80)
    print("TESTING KAGGLE VERSION (informational)")
    print("=" * 80)
    try:
        import kaggle  # type: ignore

        print(f"kaggle.__version__ = {getattr(kaggle, '__version__', 'unknown')}")
        return True
    except Exception as e:
        print(f"❌ Failed to import kaggle: {e}")
        return False


def test_submission_score_polling_compat() -> bool:
    print("=" * 80)
    print("TESTING SUBMISSION SCORE POLLING COMPATIBILITY")
    print("=" * 80)

    mock_api = MagicMock()

    # Simulate Kaggle 1.8+ object shape: snake_case property `public_score`
    mock_api.competition_submissions.return_value = [
        _FakeSubmission(ref=111, public_score=None, status="PENDING"),
        _FakeSubmission(ref=222, public_score="0.22222", status="COMPLETE", description="desc", date="2025-01-01"),
    ]
    mock_api.competition_submit.return_value = _FakeSubmitResponse(ref=222)

    with patch.object(KaggleInterfaceManager, "_authenticate_kaggle", return_value=mock_api):
        with tempfile.TemporaryDirectory() as td:
            kim = KaggleInterfaceManager(
                {
                    "kaggle_competition_name": "titanic",
                    "experiment_run_dir": td,
                    "simulation_mode": False,
                }
            )

            # Ensure submit stores the ref for later polling
            submission_path = os.path.join(td, "submission.csv")
            Path(submission_path).write_text("PassengerId,Survived\n1,0\n", encoding="utf-8")
            ok = kim.submit_predictions(submission_path, "test submit")
            assert ok is True
            assert kim.last_submission_ref == 222

            # Single-shot fetch should work (no waiting).
            res0 = kim.get_submission_score_once()
            assert res0 is not None
            assert abs(res0["score"] - 0.22222) < 1e-9
            assert res0["submission_id"] == 222

            # Poll using stored ref (no explicit submission_ref)
            res = kim.get_submission_score(wait_timeout=1)
            assert res is not None, "Expected score result, got None"
            assert abs(res["score"] - 0.22222) < 1e-9
            assert res["submission_id"] == 222

            # Explicit polling by ref should select the correct submission (not necessarily first)
            res2 = kim.get_submission_score(wait_timeout=1, submission_ref=222)
            assert res2 is not None
            assert abs(res2["score"] - 0.22222) < 1e-9

            # Simulate older/dict-like payloads: camelCase key `publicScore`
            mock_api.competition_submissions.return_value = [
                {"ref": 333, "publicScore": "0.33333", "status": "COMPLETE", "description": "d", "date": "2025-01-02"}
            ]
            kim.last_submission_ref = 333
            res3_once = kim.get_submission_score_once()
            assert res3_once is not None
            assert abs(res3_once["score"] - 0.33333) < 1e-9
            res3 = kim.get_submission_score(wait_timeout=1)
            assert res3 is not None
            assert abs(res3["score"] - 0.33333) < 1e-9
            assert res3["submission_id"] == 333

    print("✅ Submission score polling supports snake_case + camelCase shapes")
    return True


def test_continuation_hypothesis_metadata_written() -> bool:
    print("=" * 80)
    print("TESTING CONTINUATION HYPOTHESIS METADATA WRITING")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as td:
        experiment_run_dir = os.path.join(td, "run")
        worktree_base_dir = os.path.join(experiment_run_dir, "worktrees")
        worktree_path = os.path.join(worktree_base_dir, "existing_worktree")
        os.makedirs(worktree_path, exist_ok=True)

        # Source task markdown (copied into the worktree by EO)
        task_src = os.path.join(td, "cont_task.md")
        Path(task_src).write_text("# Continuation Task\nDo the thing.\n", encoding="utf-8")

        cont = ContinuationHypothesis(
            experiment_id="iter0_exp1_deadbeef",
            continuation_id="iter1_exp1_cont_deadbeef",
            iteration=1,
            original_strategy_name="CatBoost GBDT + Feature Chemistry",
            improvement_instructions="Tune params and add bagging",
            new_parameters={"learning_rate": 0.05, "depth": 6},
            worktree_path=worktree_path,
            task_markdown_path=task_src,
            parent_score=0.85,
        )

        eo = ExperimentOrchestrator(
            {
                "experiment_run_dir": experiment_run_dir,
                "simulation_mode": False,
            }
        )

        with patch.object(ExperimentOrchestrator, "_launch_continuation_codex", return_value=MagicMock()):
            result = eo.launch_continuation_experiments([cont], total_waas=3)

        assert cont.continuation_id in result.get("launched", []), f"Expected launched continuation, got: {result}"

        hypothesis_path = os.path.join(worktree_path, f"hypothesis_{cont.continuation_id}.json")
        assert os.path.exists(hypothesis_path), f"Expected continuation hypothesis file at {hypothesis_path}"

        with open(hypothesis_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["experiment_id"] == cont.continuation_id
        assert data["iteration"] == cont.iteration
        assert data["strategy_name"] == cont.original_strategy_name
        assert data["parameters"] == cont.new_parameters
        assert data["parent_experiment_id"] == cont.experiment_id

    print("✅ Continuation hypothesis metadata is persisted for RAD")
    return True


def main():
    results = []
    results.append(("kaggle_version", test_kaggle_version()))
    results.append(("submission_score_polling", test_submission_score_polling_compat()))
    results.append(("continuation_metadata", test_continuation_hypothesis_metadata_written()))

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = 0
    for name, ok in results:
        status = "✅" if ok else "❌"
        print(f"{status} {name}")
        passed += int(ok)

    print(f"\nPassed {passed}/{len(results)} checks")

    # Exit non-zero on failure for CI friendliness
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
