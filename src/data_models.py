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

    # Enhanced fields for comprehensive PA analysis
    success_patterns: List[str] = dataclasses.field(default_factory=list)
    failure_patterns: List[str] = dataclasses.field(default_factory=list)
    feature_importance: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    hyperparameter_insights: List[str] = dataclasses.field(default_factory=list)

    # Priority-based recommendations
    high_priority_recommendations: List[str] = dataclasses.field(default_factory=list)
    medium_priority_recommendations: List[str] = dataclasses.field(default_factory=list)
    experimental_recommendations: List[str] = dataclasses.field(default_factory=list)
    avoid_recommendations: List[str] = dataclasses.field(default_factory=list)

    # Analysis insights
    unresolved_questions: List[str] = dataclasses.field(default_factory=list)
    overfitting_analysis: Optional[str] = None
    convergence_status: Optional[str] = None  # "Improving", "Plateau", "Declining"
    improvement_rate: Optional[float] = None  # Percentage improvement per iteration
    computational_efficiency: List[str] = dataclasses.field(default_factory=list)

    # Key insights
    top_discoveries: List[str] = dataclasses.field(default_factory=list)
    critical_decisions: List[str] = dataclasses.field(default_factory=list)
