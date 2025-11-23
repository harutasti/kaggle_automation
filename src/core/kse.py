import os
import uuid
import random
import json
from typing import List, Optional, Dict, Any

from .base_component import BaseComponent
from ..data_models import CompetitionInfo, ExperimentHypothesis, ExperimentResult, AnalysisResult
from ..utils.file_utils import write_markdown, ensure_dir
from ..utils.crawler_parser import parse_discussion_strategies

class KnowledgeStrategyEngine(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.strategies = ["SimpleGBM", "FeatureEngV1_LGBM", "BasicNN", "RandomForest_HyperOpt"]
        self.hypothesis_dir = os.path.join(config.get("experiments_base_dir", "./experiments"), "hypotheses")
        ensure_dir(self.hypothesis_dir)
        self.competition_name = config.get("kaggle_competition_name")
        self.use_crawler = config.get("use_crawler", True)
        self.discussion_strategies: List[Dict[str, Any]] = []
        
    def _load_discussion_strategies(self):
        """Load strategies from crawler discussion data"""
        if self.use_crawler and self.competition_name:
            self.discussion_strategies = parse_discussion_strategies(self.competition_name)
            if self.discussion_strategies:
                self.logger.info(f"Loaded {len(self.discussion_strategies)} strategies from discussions")
                # Add discovered strategies to our list
                for strategy in self.discussion_strategies:
                    strategy_name = strategy['strategy_name']
                    # Normalize algorithm names to our format
                    if strategy_name.lower() in ['xgboost', 'lightgbm', 'catboost']:
                        formatted_name = f"{strategy_name}_FromDiscussion"
                        if formatted_name not in self.strategies:
                            self.strategies.append(formatted_name)
                            self.logger.info(f"Added strategy from discussions: {formatted_name}")
                    elif 'neural' in strategy_name.lower() or 'nn' in strategy_name.lower():
                        if "AdvancedNN" not in self.strategies:
                            self.strategies.append("AdvancedNN")
                    elif 'ensemble' in strategy_name.lower() or 'blend' in strategy_name.lower():
                        if "EnsembleBlend" not in self.strategies:
                            self.strategies.append("EnsembleBlend")

    def generate_initial_hypotheses(self, competition_info: CompetitionInfo, num_hypotheses: int) -> List[ExperimentHypothesis]:
        """Generate initial experiment hypotheses."""
        method_name = "generate_initial_hypotheses"
        self._log_start(method_name, num_hypotheses=num_hypotheses)
        
        # Load strategies from discussion insights
        self._load_discussion_strategies()
        
        hypotheses = []
        for i in range(num_hypotheses):
            exp_id = f"iter0_exp{i+1}_{uuid.uuid4().hex[:6]}"
            strategy = random.choice(self.strategies)
            params = self._get_dummy_params(strategy)
            task_md_path = os.path.join(self.hypothesis_dir, f"{exp_id}_task.md")

            task_markdown = self._generate_task_markdown(exp_id, 0, strategy, params, competition_info)
            write_markdown(task_markdown, task_md_path)

            hypothesis = ExperimentHypothesis(
                experiment_id=exp_id,
                iteration=0,
                strategy_name=strategy,
                parameters=params,
                task_markdown_path=task_md_path
            )
            hypotheses.append(hypothesis)
            self.logger.debug(f"Generated hypothesis: {exp_id} ({strategy})")

        self._log_end(method_name, result=f"Generated {len(hypotheses)} hypotheses")
        return hypotheses

    def generate_next_hypotheses(self,
                                 competition_info: CompetitionInfo,
                                 current_iteration: int,
                                 num_hypotheses: int,
                                 analysis_result: Optional[AnalysisResult],
                                 previous_results: List[ExperimentResult]) -> List[ExperimentHypothesis]:
        """Generate the next set of hypotheses based on analysis and past results."""
        method_name = "generate_next_hypotheses"
        self._log_start(method_name, iteration=current_iteration, num_hypotheses=num_hypotheses)
        hypotheses = []

        # Choose strategies based on analysis/history (simulation uses random + tweaks)
        possible_strategies = self.strategies[:]  # Make a copy
        if analysis_result and analysis_result.recommended_strategies:
            # Prioritize recommended strategies
            possible_strategies = analysis_result.recommended_strategies + [s for s in self.strategies if s not in analysis_result.recommended_strategies]
            self.logger.info(f"Prioritizing recommended strategies: {analysis_result.recommended_strategies}")

        if previous_results:
             # Could generate hypotheses that fine-tune successful strategies (omitted)
             pass

        for i in range(num_hypotheses):
            exp_id = f"iter{current_iteration}_exp{i+1}_{uuid.uuid4().hex[:6]}"
            # Select strategy (prioritize recommendations; otherwise rotate)
            strategy = possible_strategies[i % len(possible_strategies)]
            params = self._get_dummy_params(strategy, previous_results)  # Could adjust params using past results
            task_md_path = os.path.join(self.hypothesis_dir, f"{exp_id}_task.md")

            task_markdown = self._generate_task_markdown(exp_id, current_iteration, strategy, params, competition_info)
            write_markdown(task_markdown, task_md_path)

            hypothesis = ExperimentHypothesis(
                experiment_id=exp_id,
                iteration=current_iteration,
                strategy_name=strategy,
                parameters=params,
                task_markdown_path=task_md_path
            )
            hypotheses.append(hypothesis)
            self.logger.debug(f"Generated hypothesis: {exp_id} ({strategy})")

        self._log_end(method_name, result=f"Generated {len(hypotheses)} hypotheses")
        return hypotheses

    def _get_dummy_params(self, strategy: str, previous_results: Optional[List[ExperimentResult]] = None) -> dict:
        """Generate placeholder parameters based on strategy."""
        if "GBM" in strategy or "LightGBM" in strategy:
            lr = random.uniform(0.01, 0.1)
            n_estimators = random.randint(100, 1000)
            # Could bias toward parameters from strong past results
            return {"learning_rate": round(lr, 4), "n_estimators": n_estimators, "feature_set": "basic"}
        elif "XGBoost" in strategy:
            return {"learning_rate": round(random.uniform(0.01, 0.3), 4), 
                    "n_estimators": random.randint(100, 1000),
                    "max_depth": random.randint(3, 10),
                    "subsample": round(random.uniform(0.6, 1.0), 2)}
        elif "CatBoost" in strategy:
            return {"learning_rate": round(random.uniform(0.01, 0.1), 4),
                    "iterations": random.randint(100, 1000),
                    "depth": random.randint(4, 10)}
        elif "NN" in strategy:
            if "Advanced" in strategy:
                return {"layers": [128, 64, 32], "dropout": round(random.uniform(0.2, 0.5), 2), 
                        "epochs": random.randint(20, 100), "batch_size": random.choice([32, 64, 128])}
            else:
                return {"layers": [64, 32], "dropout": round(random.uniform(0.1, 0.5), 2), "epochs": random.randint(10, 50)}
        elif "RandomForest" in strategy:
            return {"n_estimators": random.randint(50, 500), "max_depth": random.choice([None, 5, 10, 20])}
        elif "Ensemble" in strategy:
            return {"models": ["LightGBM", "XGBoost", "CatBoost"], 
                    "blend_method": random.choice(["weighted", "stacking", "voting"])}
        else:
            return {"param1": "dummy", "param2": random.randint(1, 10)}

    def _generate_task_markdown(self, exp_id: str, iteration: int, strategy: str, params: dict, comp_info: CompetitionInfo) -> str:
        """Generate task markdown for the WAA."""
        
        # Find relevant discussion insights for this strategy
        relevant_insights = []
        if self.discussion_strategies:
            for disc_strategy in self.discussion_strategies:
                if any(keyword in strategy.lower() for keyword in disc_strategy['strategy_name'].lower().split()):
                    relevant_insights.append(disc_strategy['description'])
        
        markdown = f"""
# Experiment Task: {exp_id}

**Iteration:** {iteration}
**Strategy:** {strategy}
**Competition:** {comp_info.name} ({comp_info.evaluation_metric})

## Parameters
```json
{json.dumps(params, indent=2)}
```

{f'''## Community Insights
Based on discussion analysis, here are relevant insights for this strategy:
{chr(10).join(f"- {insight}" for insight in relevant_insights[:3])}
''' if relevant_insights else ''}

## Instructions for AI Agent (WAA)

1.  **Understand the Goal:** The primary goal is to train a model using the '{strategy}' approach with the specified parameters and evaluate it using the '{comp_info.evaluation_metric}' metric.
2.  **Load Data:** Load the necessary data files: {', '.join(comp_info.data_files)}. Assume they are available in the standard data directory relative to the worktree root.
3.  **Preprocessing/Feature Engineering:** Apply preprocessing steps suitable for the '{strategy}'. If the strategy includes 'FeatureEng', implement the corresponding feature engineering logic. Use features specified in parameters if available (e.g., `feature_set`).
4.  **Model Training:**
    *   Instantiate the model based on the '{strategy}' (e.g., LightGBM, RandomForest, a simple Keras/PyTorch NN).
    *   Use the provided `parameters` for model initialization and training (e.g., learning rate, number of estimators, epochs, layers).
    *   Train the model on the training data. Implement cross-validation if appropriate for the strategy.
5.  **Prediction & Evaluation:**
    *   Generate predictions on a validation set (or via CV).
    *   Calculate the score using the '{comp_info.evaluation_metric}' metric.
    *   Generate predictions on the test set.
6.  **Output Generation:**
    *   Save the trained model (optional, if needed later).
    *   Save the validation/CV score to `result_{exp_id}.json` in the worktree root (format: `{{"score": <score_value>}}`).
    *   Save the test predictions to `submission_{exp_id}.csv` in the format required by the competition.
    *   Log key steps and results to `waa_{exp_id}.log`.
7.  **Final Step:** Create a file named `DONE_{exp_id}` in the worktree root to signal completion.

**Important:** Ensure all file paths for output are relative to the root of this Git worktree. Use the provided `experiment_id` (`{exp_id}`) in filenames.
"""
        return markdown.strip()
