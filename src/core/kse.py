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
    # Competition type to strategy mapping
    COMPETITION_TYPE_STRATEGIES = {
        "TABULAR": ["LightGBM_Optimized", "XGBoost_Optimized", "CatBoost_Optimized", "RandomForest_Advanced", "Ensemble_GBM"],
        "IMAGE": ["CNN_ResNet", "CNN_EfficientNet", "ViT_Transformer", "Ensemble_Vision"],
        "TEXT": ["BERT_Classifier", "RoBERTa_Classifier", "LSTM_Attention", "Transformer_NLP", "Ensemble_NLP"],
        "TIMESERIES": ["LSTM_Forecaster", "GRU_Seq2Seq", "Transformer_TimeSeries", "LightGBM_Lagged", "Prophet_Model"],
        "MULTIMODAL": ["Multimodal_Ensemble", "Late_Fusion", "Early_Fusion", "Cross_Attention"]
    }

    def __init__(self, config: dict):
        super().__init__(config)
        # Legacy strategies for backward compatibility
        self.strategies = ["SimpleGBM", "FeatureEngV1_LGBM", "BasicNN", "RandomForest_HyperOpt"]
        self.hypothesis_dir = os.path.join(config.get("experiments_base_dir", "./experiments"), "hypotheses")
        ensure_dir(self.hypothesis_dir)
        self.competition_name = config.get("kaggle_competition_name")
        self.use_crawler = config.get("use_crawler", True)
        self.discussion_strategies: List[Dict[str, Any]] = []
        self.competition_type: Optional[str] = None  # Will be set after detection
        
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

    def _detect_competition_type(self, comp_info: CompetitionInfo) -> str:
        """Detect competition type from description and data files"""
        description = (comp_info.description_markdown or "").lower()
        data_files = [f.lower() for f in comp_info.data_files]

        # Check for image competition
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff')
        image_keywords = ['image', 'picture', 'photo', 'vision', 'cnn', 'convolution', 'object detection', 'classification']
        has_images = any(any(f.endswith(ext) for ext in image_extensions) for f in data_files)
        has_image_keywords = any(keyword in description for keyword in image_keywords)

        # Check for text competition
        text_extensions = ('.txt', '.json', '.tsv')
        text_keywords = ['text', 'nlp', 'natural language', 'sentiment', 'language model', 'bert', 'transformer', 'tokeniz']
        has_text_files = any(any(f.endswith(ext) for ext in text_extensions) for f in data_files)
        has_text_keywords = any(keyword in description for keyword in text_keywords)

        # Check for time series competition
        timeseries_keywords = ['time series', 'forecast', 'predict future', 'temporal', 'sequential', 'lstm', 'rnn']
        has_timeseries_keywords = any(keyword in description for keyword in timeseries_keywords)

        # Determine competition type
        if has_images or has_image_keywords:
            comp_type = "IMAGE"
        elif has_text_files or has_text_keywords:
            comp_type = "TEXT"
        elif has_timeseries_keywords:
            comp_type = "TIMESERIES"
        elif has_images and (has_text_files or has_text_keywords):
            comp_type = "MULTIMODAL"
        else:
            # Default to tabular data competition
            comp_type = "TABULAR"

        self.logger.info(f"Detected competition type: {comp_type}")
        return comp_type

    def generate_initial_hypotheses(self, competition_info: CompetitionInfo, num_hypotheses: int) -> List[ExperimentHypothesis]:
        """初期の実験仮説を生成する"""
        method_name = "generate_initial_hypotheses"
        self._log_start(method_name, num_hypotheses=num_hypotheses)

        # Detect competition type and select appropriate strategies
        self.competition_type = self._detect_competition_type(competition_info)
        available_strategies = self.COMPETITION_TYPE_STRATEGIES.get(self.competition_type, self.strategies).copy()

        # Load strategies from discussion insights
        self._load_discussion_strategies()

        # Merge discussion strategies with type-specific strategies
        if self.discussion_strategies:
            for disc_strategy in self.discussion_strategies:
                strategy_name = disc_strategy['strategy_name']
                if strategy_name not in available_strategies:
                    available_strategies.append(strategy_name)

        self.logger.info(f"Available strategies for {self.competition_type}: {available_strategies}")

        hypotheses = []
        for i in range(num_hypotheses):
            exp_id = f"iter0_exp{i+1}_{uuid.uuid4().hex[:6]}"
            strategy = random.choice(available_strategies)
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
        """分析結果と過去の結果に基づき、次の実験仮説を生成する"""
        method_name = "generate_next_hypotheses"
        self._log_start(method_name, iteration=current_iteration, num_hypotheses=num_hypotheses)
        hypotheses = []

        # Use competition type specific strategies
        base_strategies = self.COMPETITION_TYPE_STRATEGIES.get(self.competition_type, self.strategies)
        possible_strategies = base_strategies.copy()

        if analysis_result and analysis_result.recommended_strategies:
            # 推奨戦略を優先的に選択
            possible_strategies = analysis_result.recommended_strategies + [s for s in base_strategies if s not in analysis_result.recommended_strategies]
            self.logger.info(f"Prioritizing recommended strategies: {analysis_result.recommended_strategies}")

        if previous_results:
             # スコアが良かった戦略のパラメータを微調整する仮説なども生成できる（今回は省略）
             pass

        for i in range(num_hypotheses):
            exp_id = f"iter{current_iteration}_exp{i+1}_{uuid.uuid4().hex[:6]}"
            # 戦略を選択（推奨があればそれを優先、なければランダム）
            strategy = possible_strategies[i % len(possible_strategies)]
            params = self._get_dummy_params(strategy, previous_results) # パラメータも過去の結果から調整可能
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
        """戦略に応じたダミーパラメータを生成"""
        if "GBM" in strategy or "LightGBM" in strategy:
            lr = random.uniform(0.01, 0.1)
            n_estimators = random.randint(100, 1000)
            # 過去の結果があれば、良いスコアのパラメータを中心に探索するなど調整可能
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
        """WCA向けのタスク指示Markdownを生成"""

        # Find relevant discussion insights for this strategy
        relevant_insights = []
        if self.discussion_strategies:
            for disc_strategy in self.discussion_strategies:
                if any(keyword in strategy.lower() for keyword in disc_strategy['strategy_name'].lower().split()):
                    relevant_insights.append(disc_strategy['description'])

        # Competition-type specific advice
        comp_type_advice = {
            "TABULAR": """
**Tabular Data Competition - Advanced Techniques:**
- Create meaningful derived features (e.g., for Titanic: family_size, title from name, fare_per_person, is_alone)
- Handle missing values intelligently (not just mean/mode - consider domain knowledge)
- Engineer interaction features between important columns
- Use target encoding for high-cardinality categorical features
- Apply feature selection to remove noise
- Stack multiple diverse models (LightGBM + XGBoost + CatBoost)
""",
            "IMAGE": """
**Image Competition - Advanced Techniques:**
- Use transfer learning from pretrained models (ResNet, EfficientNet, ViT)
- Apply extensive data augmentation (rotation, flip, color jitter, cutout, mixup)
- Use appropriate image size (balance between performance and computation)
- Implement test-time augmentation (TTA) for predictions
- Consider ensemble of different architectures
""",
            "TEXT": """
**Text Competition - Advanced Techniques:**
- Use pretrained transformers (BERT, RoBERTa, DeBERTa)
- Apply appropriate text preprocessing and tokenization
- Consider multi-task learning or intermediate task training
- Use proper attention mechanisms
- Ensemble different transformer architectures
""",
            "TIMESERIES": """
**Time Series Competition - Advanced Techniques:**
- Create lag features and rolling statistics
- Extract time-based features (hour, day, week, month, seasonality)
- Use proper time-series cross-validation
- Consider LSTM/GRU for sequential patterns
- Combine traditional ML with deep learning approaches
"""
        }

        advice = comp_type_advice.get(self.competition_type or "TABULAR", "")

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

---

## 🏆 COMPETITION OBJECTIVE - AIM FOR GOLD MEDAL (TOP 10%)

**THIS IS A SERIOUS KAGGLE COMPETITION. Your goal is NOT just to build a model, but to:**

1. **Compete at the highest level** - Target Top 10% on the leaderboard (Gold Medal zone)
2. **Maximize score** - Every 0.001 improvement matters in competitive Kaggle
3. **Use state-of-the-art techniques** - Don't settle for basic/naive approaches

### Success Criteria:
- **Minimum acceptable CV score:** 0.75 (baseline - you MUST beat this)
- **Good score:** 0.78+ (competitive territory)
- **Excellent score:** 0.80+ (top tier performance)
- **Gold medal target:** 0.82+ (TOP 10% - this is your goal!)

If your initial approach scores below minimum, you MUST iterate and improve before finalizing.

{advice}

---

## Instructions for Codex AI Agent

### 1. Understand the Goal
Train a highly competitive model using the '{strategy}' approach. The metric is '{comp_info.evaluation_metric}' - optimize aggressively for this.

### 2. Load Data
**Data files location:** `../../kaggle_data/` (relative to worktree root)

Load these files:
{chr(10).join(f"- `../../kaggle_data/{f}`" for f in comp_info.data_files)}

**CRITICAL:** Do NOT attempt to download from Kaggle API - data is already provided in kaggle_data directory.

### 3. Feature Engineering (MANDATORY - Not Optional!)
- Implement domain-specific features (use competition description for context)
- Create interaction features between important variables
- Handle missing values intelligently (not just simple imputation)
- Apply feature transformations where appropriate
- Remove or regularize noisy features

### 4. Cross-Validation Strategy (REQUIRED)
- Use StratifiedKFold with minimum 5 folds
- Report both mean CV score AND standard deviation
- Ensure CV strategy matches the competition's evaluation metric
- Check for overfitting (gap between train and validation)

### 5. Hyperparameter Optimization
- Use systematic optimization (Optuna, GridSearch, or RandomSearch)
- Optimize for at least 30-50 trials if time permits
- Focus on high-impact hyperparameters first
- Log best parameters found

### 6. Model Training
- Instantiate model based on '{strategy}' with optimized parameters
- Train on full training data after CV validation
- Monitor for overfitting via learning curves
- Save model for potential later use

### 7. Prediction & Evaluation
- Generate predictions on validation set via CV
- Calculate '{comp_info.evaluation_metric}' score
- Verify score meets minimum threshold (>0.75)
- Generate predictions on test set

### 8. Output Generation
**All outputs must be in worktree root:**

a) **Validation Score:** `result_{exp_id}.json`
   ```json
   {{"score": <your_cv_score>}}
   ```

b) **Test Predictions:** `submission_{exp_id}.csv`
   - **CRITICAL:** Use ID column values from test file (NOT generated IDs)
   - Check `../../kaggle_data/sample_submission.csv` for exact format
   - For Titanic example: PassengerId should be 892-1309 from test.csv

c) **Logs:** `wca_{exp_id}.log`
   - Log all major steps, scores, and decisions

d) **Completion Signal:** `DONE_{exp_id}`
   - Write ONLY "completed" (success) or "error" (failure)

### 9. Quality Checks Before Finalizing
- [ ] CV score > 0.75 (minimum acceptable)
- [ ] No overfitting (train-val gap < 5%)
- [ ] Submission file format matches sample_submission.csv exactly
- [ ] All required output files created
- [ ] Logged key metrics and decisions

---

**Remember:** You are competing for a gold medal. Push for excellence, not just completion!
"""
        return markdown.strip()
