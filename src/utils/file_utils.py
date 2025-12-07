import os
import shutil
import json
from typing import Any, Optional
import logging

logger = logging.getLogger('AutoKaggle')

def ensure_dir(dir_path: str):
    """Create directory if it does not already exist."""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        logger.info(f"Created directory: {dir_path}")

def write_json(data: Any, file_path: str):
    """Write JSON data to a file."""
    ensure_dir(os.path.dirname(file_path))
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"Successfully wrote JSON to: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write JSON to {file_path}: {e}")

def read_json(file_path: str) -> Optional[Any]:
    """Read JSON data from a file."""
    if not os.path.exists(file_path):
        logger.warning(f"JSON file not found: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.debug(f"Successfully read JSON from: {file_path}")
        return data
    except Exception as e:
        logger.error(f"Failed to read JSON from {file_path}: {e}")
        return None

def write_markdown(content: str, file_path: str):
    """Write Markdown content to a file."""
    ensure_dir(os.path.dirname(file_path))
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.debug(f"Successfully wrote Markdown to: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write Markdown to {file_path}: {e}")

def read_markdown(file_path: str) -> Optional[str]:
    """Read Markdown content from a file."""
    if not os.path.exists(file_path):
        logger.warning(f"Markdown file not found: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        logger.debug(f"Successfully read Markdown from: {file_path}")
        return content
    except Exception as e:
        logger.error(f"Failed to read Markdown from {file_path}: {e}")
        return None

def copy_file(src: str, dst: str):
    """Copy a file."""
    ensure_dir(os.path.dirname(dst))
    try:
        shutil.copy2(src, dst)  # Copy metadata as well
        logger.debug(f"Copied file from {src} to {dst}")
    except Exception as e:
        logger.error(f"Failed to copy file from {src} to {dst}: {e}")

def move_file(src: str, dst: str):
    """Move a file."""
    ensure_dir(os.path.dirname(dst))
    try:
        shutil.move(src, dst)
        logger.debug(f"Moved file from {src} to {dst}")
    except Exception as e:
        logger.error(f"Failed to move file from {src} to {dst}: {e}")

def remove_dir(dir_path: str):
    """Remove a directory and its contents."""
    if os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Removed directory: {dir_path}")
        except Exception as e:
            logger.error(f"Failed to remove directory {dir_path}: {e}")


def is_higher_better_from_leaderboard(competition_name: str, metric: str = None) -> bool:
    """
    Determine if a higher score is better by checking the leaderboard ordering.

    Primary method: Compare top leaderboard scores to determine ordering.
    Fallback: Use metric name keywords if leaderboard has < 2 submissions.

    Args:
        competition_name: The Kaggle competition name/slug
        metric: Optional evaluation metric name for fallback

    Returns:
        True if higher is better, False if lower is better.
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()

        lb = api.competition_view_leaderboard(competition_name)
        submissions = lb.get('submissions', [])

        if len(submissions) >= 2:
            # Compare first and second place scores
            first_score = float(submissions[0]['score'])
            second_score = float(submissions[1]['score'])

            # Leaderboard is sorted by rank, so first is better than second
            # If first_score > second_score, higher is better
            # If first_score < second_score, lower is better
            if first_score > second_score:
                logger.info(f"Leaderboard analysis: higher is better (top={first_score}, 2nd={second_score})")
                return True
            elif first_score < second_score:
                logger.info(f"Leaderboard analysis: lower is better (top={first_score}, 2nd={second_score})")
                return False
            else:
                # Scores are equal, check more entries or fall back
                for i in range(2, min(10, len(submissions))):
                    other_score = float(submissions[i]['score'])
                    if first_score > other_score:
                        logger.info(f"Leaderboard analysis: higher is better")
                        return True
                    elif first_score < other_score:
                        logger.info(f"Leaderboard analysis: lower is better")
                        return False

    except Exception as e:
        logger.warning(f"Failed to check leaderboard for metric direction: {e}")

    # Fallback to metric-based heuristic
    return _is_higher_better_from_metric(metric)


def _is_higher_better_from_metric(metric: str) -> bool:
    """
    Fallback: Determine metric direction from metric name keywords.

    Args:
        metric: The evaluation metric name

    Returns:
        True if higher is better, False if lower is better.
    """
    if not metric:
        logger.warning("No metric provided, assuming higher is better")
        return True

    metric_lower = metric.lower()

    # Keywords indicating lower-is-better metrics
    lower_keywords = [
        "error", "loss", "rmse", "rmsle", "mae", "mse", "mape",
        "logloss", "log_loss", "cross-entropy", "crossentropy",
        "distance", "deviation", "mcrmse", "rmspe", "smape", "wrmsse",
    ]

    for keyword in lower_keywords:
        if keyword in metric_lower:
            logger.info(f"Metric '{metric}' contains '{keyword}': lower is better")
            return False

    # Keywords indicating higher-is-better metrics
    higher_keywords = [
        "accuracy", "auc", "auroc", "roc", "gini",
        "f1", "f2", "precision", "recall", "sensitivity", "specificity",
        "correlation", "pearson", "spearman", "r2", "r_squared",
        "map", "ndcg", "mrr", "iou", "dice", "jaccard", "kappa",
    ]

    for keyword in higher_keywords:
        if keyword in metric_lower:
            logger.info(f"Metric '{metric}' contains '{keyword}': higher is better")
            return True

    # Default: assume higher is better
    logger.warning(f"Unknown metric '{metric}', assuming higher is better")
    return True
