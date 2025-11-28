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

### Parameters (JSON)
```json
{{PARAMETERS_JSON}}
```

## Hypothesis and Rationale
- Core idea and why it should work for this competition: {{HYPOTHESIS_AND_RATIONALE}}
- Evidence from data/discussions/benchmarks supporting this plan: {{EVIDENCE}}
- Differentiation from other experiments this round: {{DIFFERENTIATION}}

## Data Prep & Validation
- Data loading, cleaning, and leakage controls: {{DATA_PREP}}
- Feature handling (categorical/numeric/text/image/etc.): {{FEATURE_HANDLING}}
- Validation design (folds/groups/time-awareness) with quick sanity checks: {{VALIDATION_DETAILS}}
- Pre-checks or ablations before long training: {{PRECHECKS}}

## Modeling Plan
- Model family and variants to try: {{MODEL_FAMILY}}
- Loss/metric alignment and regularization: {{LOSS_AND_REGULARIZATION}}
- Training recipe (schedules, early stopping, batch sizes, epochs/trees): {{TRAINING_RECIPE}}
- Ensembling/blending/staking rules if applicable: {{ENSEMBLING_PLAN}}

## Feature Engineering / Augmentation (if relevant)
- Top feature ideas and transformations: {{FEATURE_ENG_IDEAS}}
- Augmentation strategy for data types that benefit from it: {{AUGMENTATION}}
- Expected gains and risks to monitor: {{FEATURE_RISKS}}

## Evaluation & Reporting
- What to log to `waa_{{EXPERIMENT_ID}}.log`: {{LOGGING_PLAN}}
- Metrics to compute and how to interpret them: {{METRICS_PLAN}}
- Expected validation score range and success criteria: {{SUCCESS_CRITERIA}}
- What counts as a failure and how to downgrade to a simpler variant: {{FAILURE_HANDLING}}

## Deliverables for WAA
- Required artifacts (result JSON, submission CSV, DONE marker) and any model files: {{REQUIRED_ARTIFACTS}}
- File path or naming nuances unique to this experiment: {{FILE_NAMING_NOTES}}
- Quick fallback/timeout plan if resources are constrained: {{TIMEOUT_FALLBACK}}
