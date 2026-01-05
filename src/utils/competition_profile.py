from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .file_utils import read_json

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


@dataclass
class CompetitionProfile:
    competition: str
    path: Path
    kse_guidance: str = ""
    waa_guidance: str = ""
    asset_paths: List[str] = field(default_factory=list)
    entry_points: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def format_for_kse(self) -> str:
        lines = [
            "## Competition Profile (Auto)",
            f"- profile_path: {self.path}",
        ]
        if self.kse_guidance:
            lines.append("KSE guidance:")
            lines.append(self.kse_guidance.strip())
        if self.asset_paths:
            lines.append("Asset paths:")
            lines.extend(f"- {p}" for p in self.asset_paths)
        if self.entry_points:
            lines.append("Entry points:")
            for key, value in self.entry_points.items():
                lines.append(f"- {key}: {value}")
        if self.notes:
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)

    def format_for_waa(self) -> str:
        lines = [
            "## Competition Profile Guidance (Auto)",
            f"- profile_path: {self.path}",
        ]
        if self.waa_guidance:
            lines.append("WAA guidance:")
            lines.append(self.waa_guidance.strip())
        if self.asset_paths:
            lines.append("Asset paths:")
            lines.extend(f"- {p}" for p in self.asset_paths)
        if self.entry_points:
            lines.append("Entry points:")
            for key, value in self.entry_points.items():
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)


def load_competition_profile(
    competition_name: Optional[str],
    *,
    base_dir: str = "competitions",
    explicit_path: Optional[str] = None,
    logger=None,
) -> Optional[CompetitionProfile]:
    if not competition_name and not explicit_path:
        return None

    candidates: List[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    if competition_name:
        comp_dir = Path(base_dir) / competition_name
        candidates.append(comp_dir / "profile.yaml")
        candidates.append(comp_dir / "profile.yml")
        candidates.append(comp_dir / "profile.json")

    profile_path = next((p for p in candidates if p.exists()), None)
    if not profile_path:
        if logger:
            logger.info("No competition profile found.")
        return None

    data: Dict[str, Any] = {}
    if profile_path.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            if logger:
                logger.warning("PyYAML is not installed; cannot load %s", profile_path)
            return None
        try:
            data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            if logger:
                logger.warning("Failed to parse profile YAML %s: %s", profile_path, exc)
            return None
    else:
        data = read_json(str(profile_path)) or {}

    competition = data.get("competition") or competition_name or "unknown"
    profile = CompetitionProfile(
        competition=competition,
        path=profile_path,
        kse_guidance=str(data.get("kse_guidance") or "").strip(),
        waa_guidance=str(data.get("waa_guidance") or "").strip(),
        asset_paths=list(data.get("asset_paths") or []),
        entry_points=dict(data.get("entry_points") or {}),
        notes=list(data.get("notes") or []),
    )

    if logger:
        logger.info("Loaded competition profile: %s", profile_path)
    return profile
