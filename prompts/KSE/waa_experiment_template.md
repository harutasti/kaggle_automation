# Experiment Blueprint for {{EXPERIMENT_ID}} (Filled by KSE)

## Machine-Readable Summary
- experiment_id: {{EXPERIMENT_ID}}
- strategy_name: {{STRATEGY_NAME}}
- primary_objective: {{PRIMARY_OBJECTIVE}}
- target_metric: {{TARGET_METRIC}}
- validation_scheme: {{VALIDATION_SCHEME}}
- data_scope: {{DATA_SCOPE}}
- expected_outcome: {{EXPECTED_OUTCOME}}
- risk_level: {{RISK_LEVEL}}
- complexity_level: {{COMPLEXITY_LEVEL}}
- model_family: {{MODEL_FAMILY_CATEGORY}}
- feature_philosophy: {{FEATURE_PHILOSOPHY}}

### Parameters (JSON)
```json
{{PARAMETERS_JSON}}
```

---

## Differentiation Statement (REQUIRED)

### How This Experiment is Unique
{{DIFFERENTIATION_STATEMENT}}

### Model Family Positioning
- This experiment uses: {{MODEL_FAMILY_CATEGORY}}
- Other experiments this round use: {{OTHER_MODEL_FAMILIES}}
- Why this family for this hypothesis: {{MODEL_FAMILY_RATIONALE}}

### Feature Strategy Positioning
- This experiment uses: {{FEATURE_PHILOSOPHY}}
- Other experiments this round use: {{OTHER_FEATURE_STRATEGIES}}
- Why this strategy: {{FEATURE_STRATEGY_RATIONALE}}

### Complexity Positioning
- This is a {{COMPLEXITY_LEVEL}} complexity approach
- It complements {{COMPLEMENTARY_EXPERIMENTS}} which are {{COMPLEMENTARY_COMPLEXITY}} approaches
- Why this complexity level: {{COMPLEXITY_RATIONALE}}

### Unique Element
What makes this experiment irreplaceable in the portfolio:
{{UNIQUE_ELEMENT}}

---

## Hypothesis and Rationale

### Core Hypothesis
{{HYPOTHESIS_AND_RATIONALE}}

### Evidence Supporting This Approach
{{EVIDENCE}}

### Research Backing (if applicable)
- Web search finding: {{WEB_SEARCH_SUPPORT}}
- Discussion/notebook insight: {{DISCUSSION_SUPPORT}}
- Why this is expected to work for this competition: {{COMPETITION_FIT}}

---

## Data Prep & Validation
- Data loading, cleaning, and leakage controls: {{DATA_PREP}}
- Feature handling (categorical/numeric/text/image/etc.): {{FEATURE_HANDLING}}
- Validation design (folds/groups/time-awareness) with quick sanity checks: {{VALIDATION_DETAILS}}
- Pre-checks or ablations before long training: {{PRECHECKS}}

## Modeling Plan
- Model family and variants to try: {{MODEL_FAMILY}}
- Loss/metric alignment and regularization: {{LOSS_AND_REGULARIZATION}}
- Training recipe (schedules, early stopping, batch sizes, epochs/trees): {{TRAINING_RECIPE}}
- Ensembling/blending/stacking rules if applicable: {{ENSEMBLING_PLAN}}

## Feature Engineering / Augmentation (if relevant)
- Top feature ideas and transformations: {{FEATURE_ENG_IDEAS}}
- Augmentation strategy for data types that benefit from it: {{AUGMENTATION}}
- Expected gains and risks to monitor: {{FEATURE_RISKS}}

---

## WAA Guidance: Aggressive Execution

### Hyperparameter Exploration Space
WAA should explore these ranges (but may go wider if promising):
{{HYPERPARAMETER_RANGES}}

### Minimum Experimentation Requirements
- Minimum Optuna trials: {{MIN_OPTUNA_TRIALS}}
- Must-try variations: {{MUST_TRY_VARIATIONS}}
- Quick wins to test first: {{QUICK_WINS}}

### Freedom to Deviate
WAA is authorized to:
- Widen hyperparameter ranges if early results suggest benefit
- Try feature variations within the philosophy of this experiment
- Build simple ensembles of best configurations
- Document all deviations for PA analysis

---

## Evaluation & Reporting
- What to log to `waa_{{EXPERIMENT_ID}}.log`: {{LOGGING_PLAN}}
- Metrics to compute and how to interpret them: {{METRICS_PLAN}}
- Expected validation score range and success criteria: {{SUCCESS_CRITERIA}}
- What counts as a failure and how to downgrade to a simpler variant: {{FAILURE_HANDLING}}

## Deliverables for WAA
- Required artifacts (result JSON, submission CSV, DONE marker) and any model files: {{REQUIRED_ARTIFACTS}}
- File path or naming nuances unique to this experiment: {{FILE_NAMING_NOTES}}
- Quick fallback/timeout plan if resources are constrained: {{TIMEOUT_FALLBACK}}

### Result JSON Requirements (CRITICAL)
Your `result_{{EXPERIMENT_ID}}.json` MUST include a top-level `"score"` field:
```json
{
  "score": <primary_validation_metric>,  // REQUIRED - This is what the system uses
  "cv_mean_accuracy": <same_value>,       // Optional: framework-specific field
  "cv_std_accuracy": <std>,
  "best_params": {...},
  "runtime_seconds": <seconds>
}
```
**The system requires the `"score"` field to track experiment performance.**
