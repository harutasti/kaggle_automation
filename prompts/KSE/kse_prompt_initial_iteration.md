# AutoKaggle KSE: Initial Hypothesis Generation

CONTRACT (read first):
- Goal: Generate {num_hypotheses} diverse, executable experiment hypotheses that improve leaderboard-relevant validation metrics without using test data for decisions.
- Data Ethics: No external lookups keyed on test samples; no test-driven feature design or imputation.
- Output Format: Use Markdown sections exactly as specified. Do NOT create any other files except the required markdown hypothesis files.
- Determinism: Set and document random_state=42 for all operations. Document exact data split recipe in prose.
- Time Budget: Each hypothesis must complete within 1-3 hours on standard hardware.

## Competition Context

**Competition Name:** {competition_name}
**Competition Type:** {competition_type}
**Evaluation Metric:** {evaluation_metric}
**Submission Format:** {submission_format} [ASSUMED if not provided]

### Dataset Echo-Back (Confirm Understanding)
Please verify these dataset characteristics:
- Training samples: {train_size} rows
- Test samples: {test_size} rows [ASSUMED if not provided]
- Features: {feature_count} ({numeric_count} numeric, {categorical_count} categorical)
- Target variable: {target_variable} with distribution {target_distribution}
- Missing data: {missing_data_summary}
- Class balance: {class_distribution} [Mark as ASSUMED if unknown]
- Data collection: {temporal/cross-sectional/hierarchical} [ASSUMED: cross-sectional if not specified]

### Cross-Validation Selection Matrix

Choose CV strategy based on data properties:

| Data Property | Recommended CV | Rationale |
|--------------|----------------|-----------|
| Imbalanced classes (<30% minority) | StratifiedKFold(5) | Preserves class distribution |
| Small dataset (<1000 samples) | RepeatedStratifiedKFold(5, 2) | Reduces variance |
| Temporal data | TimeSeriesSplit(5) + 10% embargo | Prevents future leakage |
| Grouped data (user/session) | GroupKFold(5) | Prevents entity leakage |
| Large dataset (>50K) | StratifiedKFold(3) or holdout(0.2) | Computational efficiency |
| [DEFAULT] | StratifiedKFold(5) with random_state=42 | Standard baseline |

### Community Insights Summary
{discussion_winning_approaches}
{discussion_benchmarks}
{discussion_common_pitfalls}

---

## Hypothesis Generation Requirements

### Diversity Quotas (MANDATORY)
Your {num_hypotheses} hypotheses MUST include:
- **Baseline (1):** Simple, interpretable model for performance floor
- **Feature Engineering Focus (2):** Domain-specific feature creation
- **Advanced Models (2):** Modern ML techniques appropriate for data type
- **Ensemble/Stack (1):** ONLY if {num_hypotheses} >= 5, with clear complementarity
- **Creative/Domain-Specific (1):** Novel approach tailored to this competition

### Similarity Guard
For each hypothesis after the first, explicitly state: "**How this differs:** {key difference in model class/features/CV/regularization}"

---

## Output Template (Use EXACTLY This Structure)

```markdown
# Experiment Hypothesis: {hypothesis_id}

## Strategy Name
{concise_strategy_name} ({category: Baseline/FeatureEng/Advanced/Ensemble/Creative})

## Similarity Guard
**How this differs:** {explicit difference from other hypotheses, if not first}

## Dataset Grounding
- Confirmed samples: {train_size} train, {test_size} test
- Target: {target_variable} ({metric})
- Key challenge: {main difficulty based on data}

## Metric-Method Fit
- Eval metric: {evaluation_metric}
- Optimization loss: {loss_function}
- Justification: {one-line explanation why this loss optimizes the metric}
- Threshold strategy (if classification): {method} [ASSUMED: 0.5 if not tuned]

## Runtime & Fallback
- Expected runtime: ~{X}-{Y} minutes on {CPU/GPU}
- Memory estimate: {X}GB RAM
- If over budget: Reduce {folds from 5→3 / trees from 1000→500 / epochs from 50→20}
- Emergency stop: Hard limit at {2x expected} minutes

## Implementation Steps

### 1. Data Loading & Verification
- Load {specific_files}
- Assert shape: ({expected_rows}, {expected_cols})
- Verify target distribution matches expectation
- Random seed: 42 (set globally)

### 2. Data Splits
- CV Scheme: {chosen_scheme}
- Justification: {why this scheme for this data}
- Leakage addressed: {how leakage is prevented}
- Split recipe: "sklearn {CV_class}(n_splits={n}, random_state=42, shuffle=True)"

### 3. Feature Engineering (3-6 Concrete Features)

| Feature | Description | Cost | Signal Pathway | Leak Check |
|---------|------------|------|----------------|------------|
| {feature_1} | {what it is} | {cheap/medium/expensive} | {how it helps prediction} | {why no leakage} |
| {feature_2} | {what it is} | {cheap/medium/expensive} | {how it helps prediction} | {why no leakage} |
| {feature_3} | {what it is} | {cheap/medium/expensive} | {how it helps prediction} | {why no leakage} |

### 4. Preprocessing Pipeline
- Missing values: {specific strategy per feature type}
- Encoding: {method for categoricals}
- Scaling: {method if needed, with justification}
- Order: {exact sequence to prevent leakage}

### 5. Model Training

**Model Choice:** {specific_model}
**Hyperparameter Ranges (tight, budget-aware):**
- {param_1}: {narrow_range} (e.g., learning_rate: [0.03, 0.05, 0.1])
- {param_2}: {narrow_range} (e.g., max_depth: [5, 7, 9])
- {param_3}: {narrow_range} (e.g., n_estimators: [100, 300, 500])

**Search Strategy:** {GridSearchCV with 3x3 grid / RandomizedSearchCV with 20 iters / Successive Halving}
**Early Stopping:** {patience=10 rounds if applicable}

### 6. Diagnostic Signals

**Overfitting Detectors:**
- Monitor: train-val gap > {threshold}%
- Monitor: CV fold std > {threshold}
- Mitigation: If triggered, {increase reg_alpha/reg_lambda, reduce max_depth}

**Underfitting Detectors:**
- Monitor: train score < {benchmark - 10%}
- Mitigation: If triggered, {increase model capacity, add interactions}

### 7. Validation & Output
- Validation scores: Report mean ± std across folds
- Expected range: {low}-{high} {metric}
- Save format: submission_{hypothesis_id}.csv with exact column names
- Results JSON: result_{hypothesis_id}.json with score, parameters, timing

## Success Criteria
- ✓ Completes in < {time_budget} minutes
- ✓ Validation {metric} ≥ {minimum_acceptable_score}
- ✓ Train-val gap < {acceptable_overfit_threshold}%
- ✓ Output files correctly formatted
- ✓ No test data used for decisions

## How to Replicate
1. Set numpy.random.seed(42), random.seed(42), model random_state=42
2. Load data from {exact_path}
3. Apply {CV_scheme} with n_splits={n}, random_state=42
4. Run {model_class} with documented parameters
5. Save outputs to {output_pattern}

---
**CONSTRAINTS REMINDER:**
- NO test data for feature engineering or model selection
- NO external data keyed on test samples
- NO files created except this markdown
- NO broad hyperparameter sweeps that can't complete in time budget
```

### Domain-Specific Adaptations

**For Tabular Data:**
- Consider monotonic constraints if domain appropriate
- Target encoding with proper CV to avoid leakage
- Quantile/Huber loss for skewed regression targets
- Feature interactions for top {k} important features

**For Computer Vision:**
- Start with pretrained backbone, freeze→unfreeze schedule
- Light augmentations first (flip, rotate), heavy later (mixup, cutmix)
- Smaller input size (224→384→512) progression
- Batch size: largest that fits in memory

**For Time Series:**
- Embargo window: {5-10}% of test period
- Features: lags with business-appropriate windows
- No future information in any feature
- Walk-forward validation with expanding window

**For Analytics/Interpretability:**
- Feature importance stability across CV folds
- SHAP values for top predictions (note: expensive)
- Partial dependence plots for key features
- Business-actionable insight documentation

---

## Self-Check (Before Submitting Hypotheses)

Verify each hypothesis contains:
- [ ] NO JSON code blocks or script files
- [ ] Exact markdown structure as template
- [ ] CV scheme with justification
- [ ] Runtime estimate with fallback
- [ ] 3-6 concrete features with leak checks
- [ ] Tight hyperparameter ranges (no 10x10 grids)
- [ ] Diagnostic signals for over/underfitting
- [ ] Similarity guard stating uniqueness
- [ ] Random seeds documented
- [ ] [ASSUMED] markers where context missing