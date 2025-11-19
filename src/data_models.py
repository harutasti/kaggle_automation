import dataclasses
from typing import List, Dict, Optional, Any
import datetime

@dataclasses.dataclass
class CompetitionInfo:
    name: str
    evaluation_metric: str
    deadline: Optional[datetime.datetime]
    description_markdown: str # Markdown形式のコンペ説明
    data_files: List[str]
    competition_type: Optional[str] = None  # "regression", "classification", etc.
    competition_subtype: Optional[str] = None  # "binary", "multiclass", "continuous", etc.
    initial_insights: Optional[List[Dict[str, Any]]] = None  # Claude's feature engineering suggestions
    data_warnings: Optional[List[str]] = None  # Data quality warnings from Claude

@dataclasses.dataclass
class ExperimentHypothesis:
    experiment_id: str
    iteration: int
    strategy_name: str # 例: "LightGBM_Optuna", "FeatureEng_Basic"
    parameters: Dict[str, Any]
    task_markdown_path: str # WCAへの指示Markdownファイルのパス

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
    result_files: List[str] # 生成されたファイル(モデル、予測結果等)のパスリスト
    log_path: str # WCAのログファイルパス
    status: str # "SUCCESS", "FAILURE"
    error_message: Optional[str] = None

@dataclasses.dataclass
class AnalysisResult:
    iteration: int
    summary_markdown: str # Markdown形式の分析サマリ
    best_score: Optional[float]
    best_experiment_id: Optional[str]
    improvement_trend: str # 例: "Improving", "Stagnant", "Declining"
    recommended_strategies: List[str] # 次に試すべき戦略の提案
