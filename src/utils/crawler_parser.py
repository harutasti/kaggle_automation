import os
import re
import datetime
from typing import Optional, List, Dict, Any
from ..data_models import CompetitionInfo
from .file_utils import read_markdown, is_higher_better_from_leaderboard


def parse_competition_info(competition_id: str, crawler_output_dir: str = "kaggle_competitions") -> Optional[CompetitionInfo]:
    """
    Parse crawler output and convert to CompetitionInfo dataclass.
    
    Args:
        competition_id: Competition slug (e.g., "titanic")
        crawler_output_dir: Base directory for crawler output
        
    Returns:
        CompetitionInfo object or None if parsing fails
    """
    base_path = os.path.join(crawler_output_dir, competition_id)
    
    if not os.path.exists(base_path):
        return None
    
    # Read overview page
    overview_path = os.path.join(base_path, "pages", f"{competition_id}_overview.md")
    overview_content = read_markdown(overview_path)
    
    if not overview_content:
        return None
    
    # Extract competition name (title)
    name = competition_id  # Default to ID
    title_match = re.search(r'#\s+(.+?)\s*\n', overview_content)
    if title_match:
        name = title_match.group(1).strip()
        # Clean up title if it contains extra text
        if " - " in name:
            name = name.split(" - ")[-1].strip()
    
    # Extract evaluation metric
    evaluation_metric = "Unknown"

    # First, check for explicit metric mentions
    # Pattern: "## Metric\n...accuracy..." or similar
    metric_section_match = re.search(r'##\s*(?:Evaluation\s*)?Metric[s]?\s*\n(.+?)(?=##|\Z)', overview_content, re.IGNORECASE | re.DOTALL)
    if metric_section_match:
        metric_text = metric_section_match.group(1).strip()
        # Look for known metrics in the section
        metric_keywords = [
            ('accuracy', 'Accuracy'),
            ('auc', 'AUC'),
            ('roc', 'AUC-ROC'),
            ('f1', 'F1 Score'),
            ('log loss', 'Log Loss'),
            ('logloss', 'Log Loss'),
            ('rmse', 'RMSE'),
            ('rmsle', 'RMSLE'),
            ('mae', 'MAE'),
            ('mse', 'MSE'),
            ('precision', 'Precision'),
            ('recall', 'Recall'),
            ('mean squared error', 'MSE'),
            ('root mean squared', 'RMSE'),
            ('quadratic weighted kappa', 'QWK'),
        ]
        for keyword, metric_name in metric_keywords:
            if keyword in metric_text.lower():
                evaluation_metric = metric_name
                break

    # Fallback patterns if metric section not found
    if evaluation_metric == "Unknown":
        metric_patterns = [
            r'Submissions are evaluated[^.]+?using\s+(?:the\s+)?(\w+(?:\s+\w+)*)',
            r'Evaluation[^:]*:\s*(\w+(?:\s+\w+)*)',
            r'metric[^:]*:\s*(\w+(?:\s+\w+)*)',
            r'scored[^.]+?(\w+(?:\s+\w+)*)',
        ]

        for pattern in metric_patterns:
            match = re.search(pattern, overview_content, re.IGNORECASE)
            if match:
                evaluation_metric = match.group(1).strip()
                break

    # For regression competitions, check for RMSE, MAE, etc.
    if evaluation_metric == "Unknown":
        if "regression" in competition_id.lower() or "regression" in overview_content.lower():
            if "RMSE" in overview_content or "root mean" in overview_content.lower():
                evaluation_metric = "RMSE"
            elif "RMSLE" in overview_content or "root mean squared log" in overview_content.lower():
                evaluation_metric = "RMSLE"
            elif "MAE" in overview_content or "mean absolute" in overview_content.lower():
                evaluation_metric = "MAE"
    
    # Extract deadline (if available)
    deadline = None
    deadline_patterns = [
        r'Deadline[^:]*:\s*([^\n]+)',
        r'Competition ends[^:]*:\s*([^\n]+)',
        r'Final submission[^:]*:\s*([^\n]+)',
    ]
    
    for pattern in deadline_patterns:
        match = re.search(pattern, overview_content, re.IGNORECASE)
        if match:
            try:
                # Attempt to parse various date formats
                date_str = match.group(1).strip()
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%B %d, %Y']:
                    try:
                        deadline = datetime.datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
            except:
                pass
    
    # Get data files from the data directory
    data_files = []
    data_dir = os.path.join(base_path, "data")
    if os.path.exists(data_dir):
        data_files = [f for f in os.listdir(data_dir) 
                     if os.path.isfile(os.path.join(data_dir, f)) and not f.startswith('.')]
    
    # Create description from overview content
    # Extract the meaningful part after "Description" or "Competition Description"
    description_markdown = overview_content
    desc_match = re.search(r'### (?:Competition )?Description\s*\n([\s\S]+?)(?=###|\Z)', overview_content)
    if desc_match:
        description_markdown = desc_match.group(1).strip()
    else:
        # Try to extract the main content section
        content_match = re.search(r'## Overview\s*\n([\s\S]+?)(?=##|\Z)', overview_content)
        if content_match:
            description_markdown = content_match.group(1).strip()
    
    # Determine metric direction from leaderboard
    higher_is_better = is_higher_better_from_leaderboard(competition_id, evaluation_metric)

    return CompetitionInfo(
        name=name,
        evaluation_metric=evaluation_metric,
        deadline=deadline,
        description_markdown=description_markdown,
        data_files=data_files,
        higher_is_better=higher_is_better,
    )


def parse_discussion_strategies(competition_id: str, crawler_output_dir: str = "kaggle_competitions") -> List[Dict[str, Any]]:
    """
    Parse discussion threads to extract strategies and insights.
    
    Args:
        competition_id: Competition slug
        crawler_output_dir: Base directory for crawler output
        
    Returns:
        List of strategy dictionaries with keys: strategy_name, description, upvotes
    """
    strategies = []
    discussions_path = os.path.join(crawler_output_dir, competition_id, "discussions", "top_5_most_voted")
    
    if not os.path.exists(discussions_path):
        return strategies
    
    # Read aggregated upvoted discussions
    upvoted_path = os.path.join(discussions_path, "upvoted_discussions.md")
    upvoted_content = read_markdown(upvoted_path)
    
    if not upvoted_content:
        return strategies
    
    # Extract strategies from discussions
    # Look for common patterns indicating strategies
    strategy_patterns = [
        # Model approaches
        r'(?:using|used|try|tried)\s+(\w+(?:\s+\w+)*)\s+(?:model|algorithm|approach)',
        r'(\w+(?:\s+\w+)*)\s+(?:gives|gave|achieves|achieved)\s+(?:good|best|high)',
        r'(?:recommend|suggest)\s+(\w+(?:\s+\w+)*)',
        # Feature engineering
        r'(?:feature|features):\s*([^\n]+)',
        r'(?:important|useful)\s+features?\s*(?:are|is|were|was)?\s*([^\n]+)',
        # Ensemble methods
        r'(?:ensemble|blend|stack)\s+(?:of|with)?\s*([^\n]+)',
    ]
    
    seen_strategies = set()
    
    for pattern in strategy_patterns:
        matches = re.finditer(pattern, upvoted_content, re.IGNORECASE)
        for match in matches:
            strategy_text = match.group(1).strip()
            # Clean up and normalize
            strategy_text = re.sub(r'\s+', ' ', strategy_text)
            
            if strategy_text.lower() not in seen_strategies and len(strategy_text) > 3:
                seen_strategies.add(strategy_text.lower())
                
                # Try to find context around the strategy mention
                start = max(0, match.start() - 100)
                end = min(len(upvoted_content), match.end() + 100)
                context = upvoted_content[start:end].strip()
                
                strategies.append({
                    'strategy_name': strategy_text,
                    'description': context,
                    'upvotes': 1  # Default, could extract actual upvotes if needed
                })
    
    # Also look for specific ML algorithms mentioned
    ml_algorithms = [
        'XGBoost', 'LightGBM', 'CatBoost', 'Random Forest', 'Neural Network',
        'LSTM', 'GRU', 'CNN', 'Transformer', 'Ridge', 'Lasso', 'ElasticNet',
        'SVM', 'Gradient Boosting', 'AdaBoost', 'Extra Trees'
    ]
    
    for algo in ml_algorithms:
        if algo.lower() in upvoted_content.lower() and algo.lower() not in seen_strategies:
            seen_strategies.add(algo.lower())
            # Find context
            pattern = re.compile(rf'\b{re.escape(algo)}\b', re.IGNORECASE)
            match = pattern.search(upvoted_content)
            if match:
                start = max(0, match.start() - 100)
                end = min(len(upvoted_content), match.end() + 100)
                context = upvoted_content[start:end].strip()
                
                strategies.append({
                    'strategy_name': algo,
                    'description': f"Community mentioned {algo}: {context}",
                    'upvotes': 1
                })
    
    return strategies[:10]  # Return top 10 strategies to avoid overwhelming