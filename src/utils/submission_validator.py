from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

TREE_POLY = [
    (0.0, 0.8),
    (0.125, 0.5),
    (0.0625, 0.5),
    (0.2, 0.25),
    (0.1, 0.25),
    (0.35, 0.0),
    (0.075, 0.0),
    (0.075, -0.2),
    (-0.075, -0.2),
    (-0.075, 0.0),
    (-0.35, 0.0),
    (-0.1, 0.25),
    (-0.2, 0.25),
    (-0.0625, 0.5),
    (-0.125, 0.5),
    (0.0, 0.8),
]

MAX_ABS_COORD = 100.0


@dataclass(frozen=True)
class SubmissionRow:
    row_id: str
    x: float
    y: float
    deg: float


def validate_submission(
    competition_name: str,
    submission_path: str,
    experiment_run_dir: Optional[str] = None,
    *,
    logger=None,
) -> Tuple[bool, Optional[str]]:
    if not competition_name:
        return True, None

    comp = competition_name.strip().lower()
    if comp != "santa-2025":
        return True, None

    try:
        return _validate_santa_2025_submission(
            submission_path=submission_path,
            experiment_run_dir=experiment_run_dir,
            logger=logger,
        )
    except Exception as exc:
        if logger:
            logger.warning("Submission validation crashed: %s", exc)
        return False, f"Submission validation error: {exc}"


def _resolve_sample_submission(
    competition_name: str, experiment_run_dir: Optional[str]
) -> Optional[Path]:
    candidates: List[Path] = []
    if experiment_run_dir:
        candidates.append(Path(experiment_run_dir) / "kaggle_data" / "sample_submission.csv")

    project_root = Path(__file__).resolve().parents[2]
    candidates.append(project_root / "kaggle_competitions" / competition_name / "data" / "sample_submission.csv")

    for path in candidates:
        if path.exists():
            return path
    return None


def _load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Missing CSV header in {path}")
        rows = []
        for row in reader:
            if row:
                rows.append({k: (v if v is not None else "") for k, v in row.items()})
        return rows


def _parse_value(raw: str, label: str, row_id: str) -> float:
    text = str(raw).strip()
    if not text:
        raise ValueError(f"Empty {label} value for id {row_id}")
    if text[0] in ("s", "S"):
        text = text[1:]
    if not text:
        raise ValueError(f"Empty {label} value for id {row_id}")
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid {label} value '{raw}' for id {row_id}") from exc
    if not math.isfinite(value):
        raise ValueError(f"Non-finite {label} value '{raw}' for id {row_id}")
    return value


def _parse_submission_rows(rows: Iterable[Dict[str, str]]) -> Tuple[List[SubmissionRow], Optional[str]]:
    parsed: List[SubmissionRow] = []
    for row in rows:
        row_id = (row.get("id") or "").strip()
        if not row_id:
            return [], "Missing id value in submission."
        try:
            x = _parse_value(row.get("x", ""), "x", row_id)
            y = _parse_value(row.get("y", ""), "y", row_id)
            deg = _parse_value(row.get("deg", ""), "deg", row_id)
        except ValueError as exc:
            return [], str(exc)

        if abs(x) > MAX_ABS_COORD or abs(y) > MAX_ABS_COORD:
            return [], f"Coordinate out of bounds for id {row_id} (x={x}, y={y})"

        parsed.append(SubmissionRow(row_id=row_id, x=x, y=y, deg=deg))

    return parsed, None


def _validate_santa_2025_submission(
    *,
    submission_path: str,
    experiment_run_dir: Optional[str],
    logger=None,
) -> Tuple[bool, Optional[str]]:
    submission_file = Path(submission_path)
    if not submission_file.exists():
        return False, f"Submission file not found: {submission_path}"

    sample_path = _resolve_sample_submission("santa-2025", experiment_run_dir)
    if sample_path is None:
        return False, "sample_submission.csv not found for santa-2025"

    sample_rows = _load_csv_rows(sample_path)
    if not sample_rows:
        return False, "sample_submission.csv is empty"

    if "id" not in sample_rows[0]:
        return False, "sample_submission.csv missing id column"

    expected_ids = [row["id"].strip() for row in sample_rows if row.get("id")]
    expected_ids_set = set(expected_ids)

    submission_rows = _load_csv_rows(submission_file)
    if not submission_rows:
        return False, "Submission CSV is empty"

    header = submission_rows[0].keys()
    for col in ("id", "x", "y", "deg"):
        if col not in header:
            return False, f"Submission missing required column '{col}'"

    parsed_rows, parse_error = _parse_submission_rows(submission_rows)
    if parse_error:
        return False, parse_error

    seen_ids: set[str] = set()
    groups: Dict[int, List[SubmissionRow]] = {}
    extras: List[str] = []

    for row in parsed_rows:
        if row.row_id in seen_ids:
            return False, f"Duplicate id found: {row.row_id}"
        seen_ids.add(row.row_id)

        if row.row_id not in expected_ids_set:
            extras.append(row.row_id)
            continue

        parts = row.row_id.split("_", 1)
        if len(parts) != 2 or not parts[0].isdigit():
            return False, f"Invalid id format: {row.row_id}"
        group_id = int(parts[0])
        groups.setdefault(group_id, []).append(row)

    missing = expected_ids_set - seen_ids
    if missing:
        missing_preview = ", ".join(sorted(missing)[:5])
        return False, f"Submission missing {len(missing)} ids (e.g. {missing_preview})"
    if extras:
        extras_preview = ", ".join(sorted(extras)[:5])
        return False, f"Submission has {len(extras)} unexpected ids (e.g. {extras_preview})"

    for group_id, items in groups.items():
        if group_id != len(items):
            return False, f"Group {group_id:03d} expected {group_id} rows, found {len(items)}"

    ok, reason = _check_overlaps(groups, logger=logger)
    if not ok:
        return False, reason

    return True, None


def _polygon_area_signed(poly: List[Tuple[float, float]]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _point_in_triangle(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
    eps: float = 1e-12,
) -> bool:
    def cross(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])

    c1 = cross(a, b, p)
    c2 = cross(b, c, p)
    c3 = cross(c, a, p)
    has_neg = (c1 < -eps) or (c2 < -eps) or (c3 < -eps)
    has_pos = (c1 > eps) or (c2 > eps) or (c3 > eps)
    return not (has_neg and has_pos)


def _triangulate(poly: List[Tuple[float, float]]) -> List[Tuple[Tuple[float, float], ...]]:
    pts = list(poly)
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return []
    indices = list(range(n))
    triangles = []
    sign = 1.0 if _polygon_area_signed(pts) > 0 else -1.0
    guard = 0
    while len(indices) > 3 and guard < n * n:
        ear_found = False
        for i in range(len(indices)):
            i_prev = indices[i - 1]
            i_curr = indices[i]
            i_next = indices[(i + 1) % len(indices)]
            a = pts[i_prev]
            b = pts[i_curr]
            c = pts[i_next]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cross * sign <= 1e-12:
                continue
            if any(
                _point_in_triangle(pts[j], a, b, c)
                for j in indices
                if j not in (i_prev, i_curr, i_next)
            ):
                continue
            triangles.append((a, b, c))
            del indices[i]
            ear_found = True
            break
        if not ear_found:
            break
        guard += 1
    if len(indices) == 3:
        a, b, c = (pts[idx] for idx in indices)
        triangles.append((a, b, c))
    return triangles


def _rotate_triangles(
    triangles: Iterable[Tuple[Tuple[float, float], ...]], deg: float
) -> List[Tuple[Tuple[float, float], ...]]:
    rad = math.radians(deg)
    c = math.cos(rad)
    s = math.sin(rad)
    rotated = []
    for tri in triangles:
        rotated.append(tuple((x * c - y * s, x * s + y * c) for x, y in tri))
    return rotated


def _translate_triangles(
    triangles: Iterable[Tuple[Tuple[float, float], ...]], dx: float, dy: float
) -> List[Tuple[Tuple[float, float], ...]]:
    return [tuple((x + dx, y + dy) for x, y in tri) for tri in triangles]


def _triangles_bounds(triangles: Iterable[Tuple[Tuple[float, float], ...]]) -> Tuple[float, float, float, float]:
    xs = []
    ys = []
    for tri in triangles:
        for x, y in tri:
            xs.append(x)
            ys.append(y)
    return min(xs), max(xs), min(ys), max(ys)


def _bounds_overlap(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
) -> bool:
    min_ax, max_ax, min_ay, max_ay = a
    min_bx, max_bx, min_by, max_by = b
    if max_ax <= min_bx or max_bx <= min_ax:
        return False
    if max_ay <= min_by or max_by <= min_ay:
        return False
    return True


def _tri_intersect(
    t1: Tuple[Tuple[float, float], ...],
    t2: Tuple[Tuple[float, float], ...],
    eps: float = 1e-12,
) -> bool:
    for tri in (t1, t2):
        for i in range(3):
            x1, y1 = tri[i]
            x2, y2 = tri[(i + 1) % 3]
            ax = -(y2 - y1)
            ay = x2 - x1
            min1 = max1 = t1[0][0] * ax + t1[0][1] * ay
            for x, y in t1[1:]:
                val = x * ax + y * ay
                if val < min1:
                    min1 = val
                elif val > max1:
                    max1 = val
            min2 = max2 = t2[0][0] * ax + t2[0][1] * ay
            for x, y in t2[1:]:
                val = x * ax + y * ay
                if val < min2:
                    min2 = val
                elif val > max2:
                    max2 = val
            if max1 <= min2 + eps or max2 <= min1 + eps:
                return False
    return True


def _triangles_overlap(
    tris1: Iterable[Tuple[Tuple[float, float], ...]],
    tris2: Iterable[Tuple[Tuple[float, float], ...]],
) -> bool:
    for t1 in tris1:
        for t2 in tris2:
            if _tri_intersect(t1, t2):
                return True
    return False


def _check_overlaps(
    groups: Dict[int, List[SubmissionRow]], *, logger=None
) -> Tuple[bool, Optional[str]]:
    base_triangles = _triangulate(TREE_POLY)
    rotation_cache: Dict[float, List[Tuple[Tuple[float, float], ...]]] = {}

    for group_id in sorted(groups.keys()):
        items = groups[group_id]
        if len(items) < 2:
            continue

        shapes = []
        for row in items:
            cached = rotation_cache.get(row.deg)
            if cached is None:
                cached = _rotate_triangles(base_triangles, row.deg)
                rotation_cache[row.deg] = cached
            triangles = _translate_triangles(cached, row.x, row.y)
            bounds = _triangles_bounds(triangles)
            shapes.append((row.row_id, bounds, triangles))

        for i in range(len(shapes)):
            id_a, bounds_a, tris_a = shapes[i]
            for j in range(i + 1, len(shapes)):
                id_b, bounds_b, tris_b = shapes[j]
                if not _bounds_overlap(bounds_a, bounds_b):
                    continue
                if _triangles_overlap(tris_a, tris_b):
                    group_label = f"{group_id:03d}"
                    message = f"Overlapping trees in group {group_label} ({id_a}, {id_b})"
                    if logger:
                        logger.warning(message)
                    return False, message

    return True, None
