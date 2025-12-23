#!/usr/bin/env python3
"""
Resume/run-state tests for AutoKaggle.

These tests run in simulation mode and avoid invoking Codex or Kaggle APIs.
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.core.mcdu import MasterControllerDecisionUnit
from src.data_models import ExperimentHypothesis
from src.execution.run_state import EVENT_KSE_COMPLETE, EVENT_WAA_LAUNCHED
from src.utils.file_utils import ensure_dir


def _write_minimal_result(worktree: str, exp_id: str):
    Path(worktree, f"result_{exp_id}.json").write_text(json.dumps({"score": 0.5}), encoding="utf-8")
    Path(worktree, f"DONE_{exp_id}").write_text("SUCCESS", encoding="utf-8")
    Path(worktree, f"waa_{exp_id}.log").write_text("ok\n", encoding="utf-8")


def test_resume_collects_completed_results():
    print("=" * 80)
    print("TEST: Resume collects completed results and logs WAA_COMPLETED")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        worktrees = run_dir / "worktrees"
        ensure_dir(str(worktrees))

        config = {
            "experiment_run_dir": str(run_dir),
            "experiments_base_dir": str(run_dir),
            "simulation_mode": True,
            "skip_confirmations": True,
            "wca_per_iteration": 1,
            "kaggle_competition_name": "titanic",
            "use_crawler": False,
        }

        mcdu = MasterControllerDecisionUnit(config)
        exp_id = "iter0_exp1_test"
        worktree = worktrees / exp_id
        ensure_dir(str(worktree))

        task_path = run_dir / "hypotheses" / "iter0" / f"{exp_id}_task.md"
        ensure_dir(str(task_path.parent))
        task_path.write_text("# Task\nDo something.\n", encoding="utf-8")

        hypothesis = ExperimentHypothesis(
            experiment_id=exp_id,
            iteration=0,
            strategy_name="TestStrategy",
            parameters={},
            task_markdown_path=str(task_path),
        )

        _write_minimal_result(str(worktree), exp_id)

        iter_state = mcdu.run_state.get_iteration(0)
        mcdu.run_state_manager.append_event(
            EVENT_KSE_COMPLETE,
            iteration=0,
            payload={"hypotheses": [mcdu._hypothesis_to_dict(hypothesis)]},
        )
        mcdu.run_state_manager.append_event(
            EVENT_WAA_LAUNCHED,
            iteration=0,
            payload={"experiments": [{"experiment_id": exp_id, "worktree_path": str(worktree), "kind": "new"}]},
        )

        iteration_results = []
        running, pending = mcdu._resume_or_restart_iteration_experiments(
            iter_state, [hypothesis], [], iteration_results
        )

        assert exp_id in iter_state.waa_completed, "Expected completed experiment to be logged in run state"
        assert not running, "No running experiments expected"
        assert not pending, "No pending resumes expected"
        assert iteration_results and iteration_results[0].experiment_id == exp_id, "Result should be collected"
        print("✅ Completed experiment was collected and logged")


def test_restart_without_codex_session():
    print("=" * 80)
    print("TEST: Restart when no Codex session exists")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        worktrees = run_dir / "worktrees"
        ensure_dir(str(worktrees))

        config = {
            "experiment_run_dir": str(run_dir),
            "experiments_base_dir": str(run_dir),
            "simulation_mode": True,
            "skip_confirmations": True,
            "wca_per_iteration": 1,
            "kaggle_competition_name": "titanic",
            "use_crawler": False,
        }

        mcdu = MasterControllerDecisionUnit(config)
        exp_id = "iter0_exp1_restart"
        worktree = worktrees / exp_id
        ensure_dir(str(worktree))

        task_path = run_dir / "hypotheses" / "iter0" / f"{exp_id}_task.md"
        ensure_dir(str(task_path.parent))
        task_path.write_text("# Task\nDo something.\n", encoding="utf-8")

        hypothesis = ExperimentHypothesis(
            experiment_id=exp_id,
            iteration=0,
            strategy_name="TestStrategy",
            parameters={},
            task_markdown_path=str(task_path),
        )

        # Simulate failure marker without Codex logs.
        Path(worktree, f"DONE_{exp_id}").write_text("ERROR", encoding="utf-8")

        iter_state = mcdu.run_state.get_iteration(0)
        mcdu.run_state_manager.append_event(
            EVENT_KSE_COMPLETE,
            iteration=0,
            payload={"hypotheses": [mcdu._hypothesis_to_dict(hypothesis)]},
        )
        mcdu.run_state_manager.append_event(
            EVENT_WAA_LAUNCHED,
            iteration=0,
            payload={"experiments": [{"experiment_id": exp_id, "worktree_path": str(worktree), "kind": "new"}]},
        )

        with patch.object(mcdu.eo, "has_codex_session", return_value=False), \
             patch.object(mcdu.eo, "launch_experiments", return_value={"launched": [exp_id], "failed": [], "total": 1}):
            iteration_results = []
            running, pending = mcdu._resume_or_restart_iteration_experiments(
                iter_state, [hypothesis], [], iteration_results
            )

        assert exp_id in running, "Expected restart to launch experiment"
        assert not pending, "No pending resumes expected when restarting"
        print("✅ Restart triggered when no Codex session exists")


def test_resume_uses_yaml_parse_error_prompt():
    print("=" * 80)
    print("TEST: YAML parse error triggers resume with explicit error prompt")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        worktrees = run_dir / "worktrees"
        ensure_dir(str(worktrees))

        config = {
            "experiment_run_dir": str(run_dir),
            "experiments_base_dir": str(run_dir),
            "simulation_mode": True,
            "skip_confirmations": True,
            "wca_per_iteration": 1,
            "kaggle_competition_name": "titanic",
            "use_crawler": False,
        }

        mcdu = MasterControllerDecisionUnit(config)
        exp_id = "iter0_exp1_parse_error"
        worktree = worktrees / exp_id
        ensure_dir(str(worktree))

        # Create a status file that will fail YAML parsing (forced via patch below)
        status_path = worktree / "experiment-status.yaml"
        status_path.write_text("invalid: [\n", encoding="utf-8")

        task_path = run_dir / "hypotheses" / "iter0" / f"{exp_id}_task.md"
        ensure_dir(str(task_path.parent))
        task_path.write_text("# Task\nDo something.\n", encoding="utf-8")

        hypothesis = ExperimentHypothesis(
            experiment_id=exp_id,
            iteration=0,
            strategy_name="TestStrategy",
            parameters={},
            task_markdown_path=str(task_path),
        )

        iter_state = mcdu.run_state.get_iteration(0)
        mcdu.run_state_manager.append_event(
            EVENT_KSE_COMPLETE,
            iteration=0,
            payload={"hypotheses": [mcdu._hypothesis_to_dict(hypothesis)]},
        )
        mcdu.run_state_manager.append_event(
            EVENT_WAA_LAUNCHED,
            iteration=0,
            payload={"experiments": [{"experiment_id": exp_id, "worktree_path": str(worktree), "kind": "new"}]},
        )

        from src.execution import session_manager as sm

        class DummyYamlError(Exception):
            pass

        def _boom(_stream):
            raise DummyYamlError("expected <block end>, but found '-'")

        dummy_yaml = SimpleNamespace(YAMLError=DummyYamlError, safe_load=_boom)

        captured = {}

        def _capture_resume(*args, **kwargs):
            captured["reason"] = kwargs.get("reason")
            captured["prompt"] = kwargs.get("resume_prompt_override")
            return False

        with patch.object(sm, "yaml", dummy_yaml), \
             patch.object(mcdu.eo, "has_codex_session", return_value=True), \
             patch.object(mcdu.eo, "can_attempt_resume", return_value=True), \
             patch.object(mcdu.eo, "resume_experiment", side_effect=_capture_resume):
            iteration_results = []
            running, pending = mcdu._resume_or_restart_iteration_experiments(
                iter_state, [hypothesis], [], iteration_results
            )

        assert captured.get("reason") == "status_yaml_parse_error", "Expected YAML parse error resume reason"
        prompt = captured.get("prompt") or ""
        assert "The YAML file structure is broken. Please fix the file." in prompt
        assert "ERROR: expected <block end>, but found '-'" in prompt
        assert exp_id in pending, "Expected pending resume when resume attempt fails"
        print("✅ YAML parse error prompt used for resume")


if __name__ == "__main__":
    results = []
    results.append(("resume_collect", test_resume_collects_completed_results()))
    results.append(("restart_no_codex", test_restart_without_codex_session()))
    results.append(("resume_yaml_parse_error", test_resume_uses_yaml_parse_error_prompt()))
    print("\nAll resume/run-state tests completed.")
