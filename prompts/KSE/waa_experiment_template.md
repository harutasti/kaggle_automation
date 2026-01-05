# Experiment Blueprint for {{EXPERIMENT_ID}} (Filled by KSE)

## Machine-Readable Summary
- experiment_id: {{EXPERIMENT_ID}}
- strategy_name: {{STRATEGY_NAME}}
- primary_objective: {{PRIMARY_OBJECTIVE}}
- target_metric: {{TARGET_METRIC}}
- metric_direction: {{METRIC_DIRECTION}} ({{METRIC_DIRECTION_EXPLANATION}})
- validation_scheme: {{VALIDATION_SCHEME}}
- data_scope: {{DATA_SCOPE}}
- expected_outcome: {{EXPECTED_OUTCOME}}
- risk_level: {{RISK_LEVEL}}
- complexity_level: {{COMPLEXITY_LEVEL}}
- model_family: {{MODEL_FAMILY_CATEGORY}} (heuristic family)
- feature_philosophy: {{FEATURE_PHILOSOPHY}} (operator/move strategy)

### Parameters (JSON)
```json
{{PARAMETERS_JSON}}
```

---

## Differentiation Statement (REQUIRED)

### How This Experiment is Unique
{{DIFFERENTIATION_STATEMENT}}

### Heuristic Family Positioning
- This experiment uses: {{MODEL_FAMILY_CATEGORY}}
- Other experiments this round use: {{OTHER_MODEL_FAMILIES}}
- Why this family for this hypothesis: {{MODEL_FAMILY_RATIONALE}}

### Operator Strategy Positioning
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

## Data Prep & Evaluation
- Data loading, cleaning, and feasibility checks: {{DATA_PREP}}
- Mandatory official constraint validation (no proxy-only geometry)
- Representation handling (numeric/categorical/text/graph/etc.): {{FEATURE_HANDLING}}
- Evaluation design (local scoring, validation checks) with quick sanity tests: {{VALIDATION_DETAILS}}
- Pre-checks or ablations before long runs: {{PRECHECKS}}

## Search Plan
- Heuristic family and variants to try: {{MODEL_FAMILY}}
- Objective/constraint handling: {{LOSS_AND_REGULARIZATION}}
- Search recipe (schedules, restart logic, budgets): {{TRAINING_RECIPE}}
- Hybridization / multi-start rules if applicable: {{ENSEMBLING_PLAN}}

## Operator Design / Augmentation (if relevant)
- Top operator ideas and transformations: {{FEATURE_ENG_IDEAS}}
- Augmentation strategy for solution diversification: {{AUGMENTATION}}
- Expected gains and risks to monitor: {{FEATURE_RISKS}}

---

## WAA Guidance: Aggressive Execution

### Search Parameter Exploration Space
WAA should explore these ranges (but may go wider if promising):
{{HYPERPARAMETER_RANGES}}

### Minimum Experimentation Requirements
- Minimum runs/iterations: {{MIN_OPTUNA_TRIALS}}
- Must-try variations: {{MUST_TRY_VARIATIONS}}
- Quick wins to test first: {{QUICK_WINS}}

### Freedom to Deviate
WAA is authorized to:
- Widen parameter ranges if early results suggest benefit
- Try additional operators within the philosophy of this experiment
- Combine phases (constructive + local search)
- Document all deviations for PA analysis

---

## Evaluation & Reporting
- What to log to `waa_{{EXPERIMENT_ID}}.log`: {{LOGGING_PLAN}}
- Metrics to compute and how to interpret them: {{METRICS_PLAN}}
- Expected score range and success criteria: {{SUCCESS_CRITERIA}}
- What counts as a failure and how to downgrade to a simpler variant: {{FAILURE_HANDLING}}

## Deliverables for WAA
- Required artifacts (result JSON, submission CSV, DONE marker) and any solution files: {{REQUIRED_ARTIFACTS}}
- File path or naming nuances unique to this experiment: {{FILE_NAMING_NOTES}}
- Quick fallback/timeout plan if resources are constrained: {{TIMEOUT_FALLBACK}}

### Result JSON Requirements (CRITICAL)
Your `result_{{EXPERIMENT_ID}}.json` MUST include a top-level `"score"` field:
```json
{
  "score": <primary_metric>,
  "best_params": {"...": "..."},
  "runtime_seconds": <seconds>,
  "solution_summary": "short description of best solution"
}
```
**The system requires the `"score"` field to track experiment performance.**
