import os
import uuid
import random
import json
from typing import List, Optional, Dict, Any

from .base_component import BaseComponent
from ..data_models import CompetitionInfo, ExperimentHypothesis, ExperimentResult, AnalysisResult
from ..utils.file_utils import write_markdown, ensure_dir
from ..utils.crawler_parser import parse_discussion_strategies
from ..utils.dataset_analyzer import DatasetAnalyzer
from ..utils.system_specs import SystemSpecsDetector
from ..utils.prompt_filler import PromptFiller

class KnowledgeStrategyEngine(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.strategies = ["SimpleGBM", "FeatureEngV1_LGBM", "BasicNN", "RandomForest_HyperOpt"]
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.hypothesis_dir = os.path.join(self.experiment_run_dir, "hypotheses")

        # Only ensure directory if not in dry-run mode
        if not config.get("dry_run", False):
            ensure_dir(self.hypothesis_dir)

        self.competition_name = config.get("kaggle_competition_name")
        self.use_crawler = config.get("use_crawler", True)
        self.discussion_strategies: List[Dict[str, Any]] = []

        # Initialize new components
        self.system_specs_detector = SystemSpecsDetector()
        self.system_specs = None  # Will be populated on first use
        self.prompt_filler = PromptFiller(prompts_dir=config.get("prompts_dir", "prompts/KSE"))
        self.dataset_analyzer = None  # Will be initialized when needed
        self.dataset_analysis = None  # Cache for dataset analysis

        # Codex execution mode for KSE (if enabled)
        self.use_codex_for_generation = config.get("kse_codex_enabled", False)
        self.codex_timeout = config.get("kse_codex_timeout", 600)
        
    def _get_system_specs(self) -> Dict[str, Any]:
        """Get system specifications, caching the result."""
        if self.system_specs is None:
            self.logger.info("Detecting system specifications...")
            self.system_specs = self.system_specs_detector.get_specs()
            self.logger.info(f"System: {self.system_specs['cpu']['compute_type']} CPU, "
                           f"{self.system_specs['memory']['memory_class']}, "
                           f"GPU: {self.system_specs['gpu']['available']}")
        return self.system_specs_detector.get_prompt_placeholders()

    def _get_dataset_analysis(self, competition_info: CompetitionInfo) -> Dict[str, Any]:
        """Get dataset analysis, caching the result."""
        if self.dataset_analysis is None:
            self.logger.info("Analyzing competition dataset...")
            # Initialize dataset analyzer with competition data directory
            data_dir = os.path.join("kaggle_competitions", self.competition_name, "data")
            if os.path.exists(data_dir):
                self.dataset_analyzer = DatasetAnalyzer(self.competition_name, data_dir)
                self.dataset_analysis = self.dataset_analyzer.get_prompt_placeholders()
                self.logger.info(f"Dataset: {self.dataset_analysis.get('train_size', 0)} train samples, "
                               f"{self.dataset_analysis.get('feature_count', 0)} features")
            else:
                self.logger.warning(f"Data directory not found: {data_dir}")
                self.dataset_analysis = self._get_default_dataset_placeholders()
        return self.dataset_analysis

    def _get_default_dataset_placeholders(self) -> Dict[str, Any]:
        """Return default dataset placeholders when analysis isn't possible."""
        return {
            "train_size": "[ASSUMED: 1000]",
            "test_size": "[ASSUMED: 500]",
            "feature_count": "[ASSUMED: 20]",
            "numeric_count": "[ASSUMED: 10]",
            "categorical_count": "[ASSUMED: 10]",
            "target_variable": "[ASSUMED: target]",
            "competition_type": "[ASSUMED: classification]",
            "target_distribution": "[ASSUMED: balanced]",
            "class_distribution": "[ASSUMED: balanced]",
            "missing_data_summary": "[ASSUMED: no missing data]",
            "unique_characteristics": "[ASSUMED: standard tabular dataset]",
            "temporal_or_cross_sectional": "[ASSUMED: cross-sectional]"
        }

    def _get_community_insights(self) -> Dict[str, Any]:
        """Get community insights from discussions."""
        insights = {
            "winning_approaches": [],
            "benchmarks": {},
            "common_pitfalls": [],
            "recommended_techniques": [],
            "domain_knowledge": "[ASSUMED: No specific domain knowledge]",
            "ceiling_score": 0.95
        }

        if self.discussion_strategies:
            # Extract insights from discussion strategies
            for strategy in self.discussion_strategies:
                if strategy.get('description'):
                    insights["winning_approaches"].append(strategy['description'][:200])
                if strategy.get('algorithm'):
                    insights["recommended_techniques"].append(strategy['algorithm'])

            # Add benchmark scores if available
            for strategy in self.discussion_strategies:
                if strategy.get('score'):
                    insights["benchmarks"][strategy['strategy_name']] = strategy['score']

        return insights

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

        if self.use_codex_for_generation:
            # Use Codex with external prompts for hypothesis generation
            hypotheses = self._generate_hypotheses_with_codex(
                competition_info, num_hypotheses, iteration=0, is_initial=True
            )
        else:
            # Fallback to original programmatic generation
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

    def _generate_hypotheses_with_codex(self,
                                       competition_info: CompetitionInfo,
                                       num_hypotheses: int,
                                       iteration: int,
                                       is_initial: bool = True,
                                       analysis_result: Optional[AnalysisResult] = None,
                                       previous_results: Optional[List[ExperimentResult]] = None) -> List[ExperimentHypothesis]:
        """Generate hypotheses using Codex with external prompt templates."""
        self.logger.info(f"Generating hypotheses using Codex for iteration {iteration}")

        # Gather all data for placeholder filling
        competition_data = {
            "name": competition_info.name,
            "evaluation_metric": competition_info.evaluation_metric,
            "submission_format": "csv with id and prediction columns",  # Default format
            "deadline": str(competition_info.deadline) if competition_info.deadline else "[ASSUMED: No deadline]"
        }

        # Get system specs
        system_specs = self._get_system_specs()

        # Get dataset analysis
        dataset_analysis = self._get_dataset_analysis(competition_info)

        # Get community insights
        community_insights = self._get_community_insights()

        if is_initial:
            # Fill initial iteration prompt
            filled_prompt = self.prompt_filler.fill_initial_prompt(
                competition_info=competition_data,
                dataset_analysis=dataset_analysis,
                system_specs=system_specs,
                community_insights=community_insights,
                num_hypotheses=num_hypotheses
            )
        else:
            # Prepare iteration results for subsequent prompts
            iteration_results = self._prepare_iteration_results(previous_results)
            pa_analysis = self._prepare_pa_analysis(analysis_result)

            # Fill subsequent iteration prompt
            filled_prompt = self.prompt_filler.fill_subsequent_prompt(
                competition_info=competition_data,
                dataset_analysis=dataset_analysis,
                system_specs=system_specs,
                community_insights=community_insights,
                iteration_results=iteration_results,
                pa_analysis=pa_analysis,
                iteration_number=iteration,
                num_hypotheses=num_hypotheses
            )

        # Save filled prompt for debugging
        prompt_path = os.path.join(self.hypothesis_dir, f"kse_prompt_iter{iteration}.md")
        self.prompt_filler.save_filled_prompt(filled_prompt, prompt_path)
        self.logger.info(f"Saved filled prompt to {prompt_path}")

        # TODO: Execute Codex to generate hypotheses from the filled prompt
        # For now, return empty list or fallback to programmatic generation
        self.logger.warning("Codex execution for KSE not yet implemented, falling back to programmatic generation")

        # Fallback to programmatic generation
        hypotheses = []
        for i in range(num_hypotheses):
            exp_id = f"iter{iteration}_exp{i+1}_{uuid.uuid4().hex[:6]}"
            strategy = random.choice(self.strategies)
            params = self._get_dummy_params(strategy, previous_results)
            task_md_path = os.path.join(self.hypothesis_dir, f"{exp_id}_task.md")

            task_markdown = self._generate_task_markdown(exp_id, iteration, strategy, params, competition_info)
            write_markdown(task_markdown, task_md_path)

            hypothesis = ExperimentHypothesis(
                experiment_id=exp_id,
                iteration=iteration,
                strategy_name=strategy,
                parameters=params,
                task_markdown_path=task_md_path
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def _prepare_iteration_results(self, previous_results: Optional[List[ExperimentResult]]) -> Dict[str, Any]:
        """Prepare iteration results for prompt filling."""
        if not previous_results:
            return {"experiments": [], "best_experiment": {}, "worst_experiment": {}}

        # Find best and worst experiments
        valid_results = [r for r in previous_results if r.validation_score is not None]
        if valid_results:
            best_result = max(valid_results, key=lambda r: r.validation_score)
            worst_result = min(valid_results, key=lambda r: r.validation_score)
            scores = [r.validation_score for r in valid_results]

            return {
                "experiments": [
                    {
                        "id": r.experiment_id,
                        "strategy": r.strategy_name,
                        "validation_score": r.validation_score,
                        "runtime_minutes": r.runtime_seconds / 60 if r.runtime_seconds else 0,
                        "status": r.status,
                        "train_val_gap": 0  # Would need to calculate from logs
                    }
                    for r in previous_results
                ],
                "best_experiment": {
                    "id": best_result.experiment_id,
                    "strategy": best_result.strategy_name,
                    "score": best_result.validation_score,
                    "runtime_minutes": best_result.runtime_seconds / 60 if best_result.runtime_seconds else 0
                },
                "worst_experiment": {
                    "id": worst_result.experiment_id,
                    "strategy": worst_result.strategy_name,
                    "score": worst_result.validation_score
                },
                "mean_score": sum(scores) / len(scores),
                "std_score": 0,  # Would need numpy for std
                "min_score": min(scores),
                "max_score": max(scores),
                "success_rate": len(valid_results) / len(previous_results) * 100 if previous_results else 0,
                "cv_scheme": "StratifiedKFold(5)"
            }

        return {"experiments": [], "best_experiment": {}, "worst_experiment": {}}

    def _prepare_pa_analysis(self, analysis_result: Optional[AnalysisResult]) -> Dict[str, Any]:
        """Prepare PA analysis for prompt filling."""
        if not analysis_result:
            return {
                "success_patterns": [],
                "failure_patterns": [],
                "feature_importance": [],
                "high_priority": [],
                "medium_priority": [],
                "experimental": [],
                "avoid": [],
                "unresolved_questions": [],
                "summary": "No analysis available yet."
            }

        return {
            "success_patterns": getattr(analysis_result, 'success_patterns', []),
            "failure_patterns": getattr(analysis_result, 'failure_patterns', []),
            "feature_importance": getattr(analysis_result, 'feature_importance', []),
            "high_priority": analysis_result.recommended_strategies if analysis_result.recommended_strategies else [],
            "medium_priority": [],
            "experimental": [],
            "avoid": getattr(analysis_result, 'strategies_to_avoid', []),
            "unresolved_questions": getattr(analysis_result, 'unresolved_questions', []),
            "summary": analysis_result.summary if analysis_result.summary else "Analysis complete."
        }

    def generate_next_hypotheses(self,
                                 competition_info: CompetitionInfo,
                                 current_iteration: int,
                                 num_hypotheses: int,
                                 analysis_result: Optional[AnalysisResult],
                                 previous_results: List[ExperimentResult]) -> List[ExperimentHypothesis]:
        """Generate the next set of hypotheses based on analysis and past results."""
        method_name = "generate_next_hypotheses"
        self._log_start(method_name, iteration=current_iteration, num_hypotheses=num_hypotheses)

        if self.use_codex_for_generation:
            # Use Codex with external prompts for hypothesis generation
            hypotheses = self._generate_hypotheses_with_codex(
                competition_info, num_hypotheses, iteration=current_iteration,
                is_initial=False, analysis_result=analysis_result, previous_results=previous_results
            )
        else:
            # Fallback to original programmatic generation
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
