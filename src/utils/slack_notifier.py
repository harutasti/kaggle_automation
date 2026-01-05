from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Iterable, Optional


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    return bool(value)


def resolve_webhook_url(config: Dict[str, Any]) -> Optional[str]:
    explicit = config.get("slack_webhook_url")
    if explicit:
        return explicit
    env_name = config.get("slack_webhook_env") or "SLACK_WEBHOOK_URL"
    if not env_name:
        return None
    return os.environ.get(env_name)


def send_message(webhook_url: str, text: str, *, logger=None, timeout_seconds: float = 10.0) -> bool:
    payload = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read()
        return True
    except Exception as exc:
        if logger:
            logger.warning("Slack notification failed: %s", exc)
        return False


def build_iteration_message(
    *,
    competition_name: str,
    iteration: int,
    run_id: str,
    results: Iterable[Any],
    higher_is_better: bool,
    analysis_result: Optional[Any] = None,
    official_scores: Optional[Dict[str, float]] = None,
) -> str:
    results_list = list(results)
    success = sum(1 for r in results_list if getattr(r, "status", "") == "SUCCESS")
    invalid = sum(1 for r in results_list if getattr(r, "status", "") == "FAILURE_INVALID_SUBMISSION")
    failed = max(len(results_list) - success - invalid, 0)

    best_score = None
    best_exp = None
    if analysis_result and getattr(analysis_result, "best_score", None) is not None:
        best_score = analysis_result.best_score
        best_exp = analysis_result.best_experiment_id
    else:
        scored = [
            r for r in results_list
            if getattr(r, "status", "") == "SUCCESS" and getattr(r, "score", None) is not None
        ]
        if scored:
            scored_sorted = sorted(scored, key=lambda r: r.score, reverse=higher_is_better)
            best = scored_sorted[0]
            best_score = best.score
            best_exp = best.experiment_id

    best_official = None
    if official_scores:
        scores = list(official_scores.items())
        if scores:
            scores_sorted = sorted(scores, key=lambda kv: kv[1], reverse=higher_is_better)
            best_official = scores_sorted[0]

    lines = [
        f"[{competition_name}] Iteration {iteration} complete",
        f"Success: {success} | Invalid: {invalid} | Failed: {failed}",
    ]
    if best_score is not None:
        lines.append(f"Best local: {best_score:.6f} ({best_exp})")
    if best_official:
        lines.append(f"Best official: {best_official[1]:.6f} ({best_official[0]})")
    if analysis_result and getattr(analysis_result, "improvement_trend", None):
        lines.append(f"Trend: {analysis_result.improvement_trend}")
    lines.append(f"Run: {run_id}")
    return "\n".join(lines)


def notify_iteration_end(
    *,
    config: Dict[str, Any],
    competition_name: str,
    iteration: int,
    run_id: str,
    results: Iterable[Any],
    higher_is_better: bool,
    analysis_result: Optional[Any],
    official_scores: Optional[Dict[str, float]],
    logger=None,
) -> bool:
    enabled = _as_bool(config.get("slack_notify_on_iteration_end", False))
    if not enabled:
        return False
    webhook_url = resolve_webhook_url(config)
    if not webhook_url:
        if logger:
            logger.warning("Slack notification enabled but no webhook URL configured.")
        return False
    message = build_iteration_message(
        competition_name=competition_name,
        iteration=iteration,
        run_id=run_id,
        results=results,
        higher_is_better=higher_is_better,
        analysis_result=analysis_result,
        official_scores=official_scores,
    )
    return send_message(webhook_url, message, logger=logger)
