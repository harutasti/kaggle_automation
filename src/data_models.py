import dataclasses
from typing import List, Dict, Optional, Any
import datetime

@dataclasses.dataclass
class CompetitionInfo:
    name: str
    evaluation_metric: str
    deadline: Optional[datetime.datetime]
    description_markdown: str  # Competition description in Markdown
    data_files: List[str]
    competition_type: Optional[str] = None  # "regression", "classification", etc.
    competition_subtype: Optional[str] = None  # "binary", "multiclass", "continuous", etc.
    initial_insights: Optional[List[Dict[str, Any]]] = None  # AI-provided feature engineering suggestions
    data_warnings: Optional[List[str]] = None  # Data quality warnings from analysis

@dataclasses.dataclass
class ExperimentHypothesis:
    experiment_id: str
    iteration: int
    strategy_name: str  # e.g., "LightGBM_Optuna", "FeatureEng_Basic"
    parameters: Dict[str, Any]
    task_markdown_path: str  # Path to WAA task markdown

@dataclasses.dataclass
class ExperimentResult:
    experiment_id: str
    iteration: int
    strategy_name: str
    parameters: Dict[str, Any]
    start_time: datetime.datetime
    end_time: datetime.datetime
    execution_time_seconds: float
    score: Optional[float]
    result_files: List[str]  # Paths to generated artifacts (model, predictions, etc.)
    log_path: str  # WAA log file path
    status: str  # "SUCCESS", "FAILURE"
    error_message: Optional[str] = None

@dataclasses.dataclass
class AnalysisResult:
    iteration: int
    summary_markdown: str  # Analysis summary in Markdown
    best_score: Optional[float]
    best_experiment_id: Optional[str]
    improvement_trend: str  # e.g., "Improving", "Stagnant", "Declining"
    recommended_strategies: List[str]  # Recommended strategies to try next
