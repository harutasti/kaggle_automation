from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .file_utils import ensure_dir, read_json, write_json, copy_file


@dataclass
class KnowledgeEntry:
    experiment_id: str
    iteration: int
    score: float
    strategy_name: str
    parameters: Dict[str, Any]
    status: str
    run_id: str
    submission_path: Optional[str] = None
    official_score: Optional[float] = None


@dataclass
class CompetitionKnowledge:
    competition: str
    higher_is_better: Optional[bool] = None
    updated_at: Optional[str] = None
    top_results: List[KnowledgeEntry] = field(default_factory=list)


class CompetitionKnowledgeStore:
    def __init__(
        self,
        competition_name: Optional[str],
        *,
        base_dir: str = "competitions",
        top_k: int = 5,
        logger=None,
    ):
        self.competition_name = competition_name or "unknown"
        self.base_dir = Path(base_dir) / self.competition_name / "knowledge"
        self.knowledge_path = self.base_dir / "knowledge.json"
        self.solutions_dir = self.base_dir / "solutions"
        self.top_k = top_k
        self.logger = logger

        ensure_dir(str(self.base_dir))
        ensure_dir(str(self.solutions_dir))

        self._data = self._load()

    def _load(self) -> CompetitionKnowledge:
        data = read_json(str(self.knowledge_path)) or {}
        entries = []
        for item in data.get("top_results", []) or []:
            try:
                entries.append(KnowledgeEntry(**item))
            except Exception:
                continue
        return CompetitionKnowledge(
            competition=data.get("competition", self.competition_name),
            higher_is_better=data.get("higher_is_better"),
            updated_at=data.get("updated_at"),
            top_results=entries,
        )

    def update_with_results(
        self,
        results: Iterable[Any],
        *,
        experiment_run_dir: str,
        results_base_dir: str,
        official_scores: Optional[Dict[str, float]] = None,
        higher_is_better: Optional[bool] = None,
    ) -> None:
        official_scores = official_scores or {}
        run_id = os.path.basename(os.path.abspath(experiment_run_dir))
        new_entries: List[KnowledgeEntry] = []

        for result in results:
            if result is None:
                continue
            if getattr(result, "status", None) != "SUCCESS":
                continue
            score = getattr(result, "score", None)
            if score is None:
                continue

            submission_path = self._copy_submission(result, results_base_dir, run_id)
            entry = KnowledgeEntry(
                experiment_id=result.experiment_id,
                iteration=result.iteration,
                score=float(score),
                strategy_name=result.strategy_name,
                parameters=dict(result.parameters or {}),
                status=result.status,
                run_id=run_id,
                submission_path=submission_path,
                official_score=official_scores.get(result.experiment_id),
            )
            new_entries.append(entry)

        if not new_entries:
            return

        all_entries = self._merge_entries(self._data.top_results, new_entries)
        if higher_is_better is not None:
            self._data.higher_is_better = higher_is_better

        sorted_entries = self._sort_entries(all_entries, self._data.higher_is_better)
        self._data.top_results = sorted_entries[: self.top_k]
        self._data.updated_at = dt.datetime.utcnow().isoformat() + "Z"
        self._data.competition = self.competition_name

        self._save()

    def format_for_kse(self, max_entries: int = 3) -> str:
        if not self._data.top_results:
            return "## Competition Knowledge (Auto)\nNo prior knowledge available."
        lines = ["## Competition Knowledge (Auto)"]
        hib = self._data.higher_is_better
        if hib is not None:
            direction = "higher is better" if hib else "lower is better"
            lines.append(f"- metric_direction: {direction}")
        for entry in self._data.top_results[:max_entries]:
            params = self._compact_params(entry.parameters)
            lines.append(
                f"- best: exp_id={entry.experiment_id} run={entry.run_id} score={entry.score:.6f} "
                f"strategy={entry.strategy_name}"
            )
            if params:
                lines.append(f"  params={params}")
            if entry.submission_path:
                lines.append(f"  submission={entry.submission_path}")
        return "\n".join(lines)

    def format_for_waa(self, max_entries: int = 2) -> str:
        if not self._data.top_results:
            return ""
        lines = ["## Competition Knowledge (Auto)"]
        for entry in self._data.top_results[:max_entries]:
            params = self._compact_params(entry.parameters)
            lines.append(
                f"- seed: exp_id={entry.experiment_id} score={entry.score:.6f} strategy={entry.strategy_name}"
            )
            if params:
                lines.append(f"  params={params}")
            if entry.submission_path:
                lines.append(f"  submission={entry.submission_path}")
        return "\n".join(lines)

    def _merge_entries(self, existing: List[KnowledgeEntry], new: List[KnowledgeEntry]) -> List[KnowledgeEntry]:
        merged: Dict[str, KnowledgeEntry] = {}
        for entry in existing + new:
            key = f"{entry.run_id}:{entry.experiment_id}"
            merged[key] = entry
        return list(merged.values())

    def _sort_entries(self, entries: List[KnowledgeEntry], higher_is_better: Optional[bool]) -> List[KnowledgeEntry]:
        if higher_is_better is None:
            # Default to lower-is-better for optimization-style competitions.
            higher_is_better = False
        return sorted(entries, key=lambda e: e.score, reverse=higher_is_better)

    def _compact_params(self, params: Dict[str, Any]) -> str:
        if not params:
            return ""
        try:
            text = json.dumps(params, sort_keys=True)
        except Exception:
            text = str(params)
        if len(text) > 240:
            text = text[:237] + "..."
        return text

    def _copy_submission(self, result: Any, results_base_dir: str, run_id: str) -> Optional[str]:
        result_files = getattr(result, "result_files", None) or []
        submission_rel = None
        for candidate in result_files:
            name = os.path.basename(candidate)
            if name.startswith("submission_") or name == "submission.csv":
                submission_rel = candidate
                break
        if submission_rel is None:
            submission_rel = next((p for p in result_files if p.endswith(".csv")), None)
        if not submission_rel:
            return None
        source_path = Path(results_base_dir) / submission_rel
        if not source_path.exists():
            return None
        safe_name = f"{run_id}_{result.experiment_id}.csv"
        dest_path = self.solutions_dir / safe_name
        copy_file(str(source_path), str(dest_path))
        return str(dest_path)

    def _save(self) -> None:
        payload = {
            "competition": self._data.competition,
            "higher_is_better": self._data.higher_is_better,
            "updated_at": self._data.updated_at,
            "top_results": [entry.__dict__ for entry in self._data.top_results],
        }
        write_json(payload, str(self.knowledge_path))
        if self.logger:
            self.logger.info("Updated competition knowledge: %s", self.knowledge_path)
