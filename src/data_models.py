import dataclasses
from typing import List, Dict, Optional, Any
from enum import Enum
import datetime


class ExperimentDecisionType(Enum):
    """PA's decision for whether to continue or terminate an experiment."""
    CONTINUE = "CONTINUE"   # Keep worktree, evolve experiment with improvements
    TERMINATE = "TERMINATE" # Archive worktree, free slot for new hypothesis


@dataclasses.dataclass
class ExperimentDecision:
    """PA's explicit decision for a single experiment."""
    experiment_id: str
    decision: ExperimentDecisionType
    reasoning: str                                   # Why continue or terminate
    confidence: float                                # 0.0-1.0 confidence in decision
    improvement_instructions: Optional[str] = None   # For CONTINUE: what to improve
    termination_reason: Optional[str] = None         # For TERMINATE: why it failed
    potential_ceiling: Optional[float] = None        # Estimated max achievable score
    priority_rank: int = 0                           # 1=highest priority to continue


@dataclasses.dataclass
class ContinuationHypothesis:
    """Hypothesis that continues/evolves an existing experiment."""
    experiment_id: str                  # Original experiment ID (preserved for lineage)
    continuation_id: str                # New ID for this iteration's continuation
    iteration: int
    original_strategy_name: str
    improvement_instructions: str       # From PA's analysis
    new_parameters: Dict[str, Any]      # Updated parameters
    worktree_path: str                  # Existing worktree to reuse
    task_markdown_path: str             # New task markdown for this continuation
    parent_score: float                 # Score from parent experiment

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

    # Evolution decisions (for persistent evolution feature)
    experiment_decisions: List['ExperimentDecision'] = dataclasses.field(default_factory=list)
    experiments_to_continue: int = 0
    experiments_to_terminate: int = 0
    new_slots_available: int = 0
