"""
Append-only run state tracking for resumable experiment sessions.

The run_state.json file is written as JSON Lines (one JSON object per line)
to avoid rewriting large files and to preserve an append-only audit trail.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

RUN_STATE_FILENAME = "run_state.json"

# Event type constants
EVENT_RUN_START = "RUN_START"
EVENT_INIT_COMPLETE = "INIT_COMPLETE"
EVENT_ITERATION_START = "ITERATION_START"
EVENT_KSE_COMPLETE = "KSE_COMPLETE"
EVENT_WAA_LAUNCHED = "WAA_LAUNCHED"
EVENT_WAA_COMPLETED = "WAA_COMPLETED"
EVENT_KAGGLE_SUBMISSION_COMPLETE = "KAGGLE_SUBMISSION_COMPLETE"
EVENT_KAGGLE_SCORES_COLLECTED = "KAGGLE_SCORES_COLLECTED"
EVENT_PA_COMPLETE = "PA_COMPLETE"
EVENT_ITERATION_COMPLETE = "ITERATION_COMPLETE"
EVENT_EXPERIMENT_TERMINATED = "EXPERIMENT_TERMINATED"
EVENT_RESUME_ATTEMPT = "RESUME_ATTEMPT"


@dataclass
class IterationState:
    iteration: int
    started: bool = False
    kse_done: bool = False
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    waa_launched: bool = False
    waa_experiments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    waa_completed: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    kaggle_submitted: bool = False
    submitted_refs: Dict[str, int] = field(default_factory=dict)
    kaggle_scores_collected: bool = False
    official_scores: Dict[str, float] = field(default_factory=dict)
    pa_done: bool = False
    analysis_result: Optional[Dict[str, Any]] = None
    complete: bool = False


@dataclass
class RunState:
    run_started: bool = False
    init_complete: bool = False
    init_payload: Optional[Dict[str, Any]] = None
    iterations: Dict[int, IterationState] = field(default_factory=dict)
    resume_attempts: Dict[str, int] = field(default_factory=dict)
    terminated_experiments: Dict[str, str] = field(default_factory=dict)  # exp_id -> reason

    def get_iteration(self, iteration: int) -> IterationState:
        if iteration not in self.iterations:
            self.iterations[iteration] = IterationState(iteration=iteration)
        return self.iterations[iteration]

    def first_incomplete_iteration(self) -> Optional[int]:
        if not self.iterations:
            return None
        for iteration in sorted(self.iterations.keys()):
            if not self.iterations[iteration].complete:
                return iteration
        return None

    def last_completed_iteration(self) -> Optional[int]:
        completed = [i for i, state in self.iterations.items() if state.complete]
        if not completed:
            return None
        return max(completed)


class RunStateManager:
    """Append-only run state recorder and loader."""

    def __init__(self, experiment_run_dir: str, logger: Optional[logging.Logger] = None):
        self.run_dir = Path(experiment_run_dir)
        self.state_path = self.run_dir / RUN_STATE_FILENAME
        self.logger = logger or logging.getLogger(__name__)
        self._state_cache: Optional[RunState] = None

    def append_event(self, event_type: str, iteration: Optional[int] = None, payload: Optional[Dict[str, Any]] = None) -> None:
        """Append a single event to the run_state.json log."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
        }
        if iteration is not None:
            event["iteration"] = iteration
        if payload is not None:
            event["payload"] = payload

        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
            # Update cached state if present
            if self._state_cache is not None:
                self._apply_event(self._state_cache, event)
        except Exception as e:
            self.logger.error(f"Failed to append run state event {event_type}: {e}")

    def load_state(self) -> RunState:
        """Load and replay events from run_state.json."""
        state = RunState()

        if not self.state_path.exists():
            self._state_cache = state
            return state

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        self.logger.warning("Skipping invalid run_state line (JSON decode failed)")
                        continue
                    self._apply_event(state, event)
        except Exception as e:
            self.logger.error(f"Failed to load run state from {self.state_path}: {e}")

        self._state_cache = state
        return state

    def get_state(self) -> RunState:
        if self._state_cache is None:
            return self.load_state()
        return self._state_cache

    def _apply_event(self, state: RunState, event: Dict[str, Any]) -> None:
        event_type = event.get("type")
        iteration = event.get("iteration")
        payload = event.get("payload") or {}

        if event_type == EVENT_RUN_START:
            state.run_started = True
            return
        if event_type == EVENT_INIT_COMPLETE:
            state.init_complete = True
            state.init_payload = payload or {}
            return

        if iteration is None:
            # Non-iteration events handled above
            if event_type == EVENT_RESUME_ATTEMPT:
                exp_id = payload.get("experiment_id")
                if exp_id:
                    state.resume_attempts[exp_id] = state.resume_attempts.get(exp_id, 0) + 1
            elif event_type == EVENT_EXPERIMENT_TERMINATED:
                exp_id = payload.get("experiment_id")
                reason = payload.get("reason", "")
                if exp_id:
                    state.terminated_experiments[exp_id] = reason
            return

        iter_state = state.get_iteration(int(iteration))

        if event_type == EVENT_ITERATION_START:
            iter_state.started = True
        elif event_type == EVENT_KSE_COMPLETE:
            iter_state.kse_done = True
            iter_state.hypotheses = payload.get("hypotheses", [])
        elif event_type == EVENT_WAA_LAUNCHED:
            iter_state.waa_launched = True
            for exp in payload.get("experiments", []):
                exp_id = exp.get("experiment_id")
                if exp_id:
                    iter_state.waa_experiments[exp_id] = exp
        elif event_type == EVENT_WAA_COMPLETED:
            exp_id = payload.get("experiment_id")
            if exp_id:
                iter_state.waa_completed[exp_id] = payload
        elif event_type == EVENT_KAGGLE_SUBMISSION_COMPLETE:
            iter_state.kaggle_submitted = True
            iter_state.submitted_refs = payload.get("submitted_refs", {})
        elif event_type == EVENT_KAGGLE_SCORES_COLLECTED:
            iter_state.kaggle_scores_collected = True
            iter_state.official_scores = payload.get("official_scores", {})
        elif event_type == EVENT_PA_COMPLETE:
            iter_state.pa_done = True
            iter_state.analysis_result = payload.get("analysis_result")
        elif event_type == EVENT_ITERATION_COMPLETE:
            iter_state.complete = True

        if event_type == EVENT_RESUME_ATTEMPT:
            exp_id = payload.get("experiment_id")
            if exp_id:
                state.resume_attempts[exp_id] = state.resume_attempts.get(exp_id, 0) + 1
        elif event_type == EVENT_EXPERIMENT_TERMINATED:
            exp_id = payload.get("experiment_id")
            reason = payload.get("reason", "")
            if exp_id:
                state.terminated_experiments[exp_id] = reason
