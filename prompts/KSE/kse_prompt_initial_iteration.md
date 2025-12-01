# AutoKaggle KSE: Initial Hypothesis Generation

CONTRACT:
- Goal: Generate {num_hypotheses} **substantially diverse**, executable experiment hypotheses that improve leaderboard-relevant validation metrics.
- Diversity: Hypotheses must be **globally different** (different model families, feature philosophies)—not variations.
- Research: Use web search and discussion mining to inform hypothesis design.
- Data Ethics: No external lookups keyed on test samples; no test-driven feature design.
- Output Format: Use Markdown sections exactly as specified. Do NOT create other files.
- Determinism: Set random_state=42 for all operations. Document exact data split recipe.

---

## PHASE 0: Mandatory Research (Before Hypothesis Generation)

### Web Search Tasks (REQUIRED)
Use available web search tools to gather:
- **Competition-specific**: Winning solutions, top approaches for this problem type
- **Cutting-edge**: Recent advances (last 12-24 months) in relevant ML domain
- **Pitfalls**: Common mistakes and failed approaches

### Discussion/Notebook Mining
For each provided artifact, extract:
- Technique used and performance achieved
- Non-obvious insights
- Warnings about what didn't work

**Document findings in the Research Findings section below.**

---

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

## Research Findings (Fill After PHASE 0)

### Web Search Discoveries
Document key findings from web search:
- **Winning techniques for this problem type:** {web_search_techniques}
- **Recent advances (12-24 months):** {recent_advances}
- **Common pitfalls discovered:** {pitfalls_discovered}

### Discussion/Notebook Insights
| Source | Technique | Reported Score | Key Insight | Warning |
|--------|-----------|----------------|-------------|---------|
| {source_1} | {technique_1} | {score_1} | {insight_1} | {warning_1} |
| {source_2} | {technique_2} | {score_2} | {insight_2} | {warning_2} |
| {source_3} | {technique_3} | {score_3} | {insight_3} | {warning_3} |

### Techniques Worth Incorporating
Based on research, prioritize these in hypothesis design:
1. {technique_priority_1}: {why_promising}
2. {technique_priority_2}: {why_promising}
3. {technique_priority_3}: {why_promising}

---

## System Specifications

{system_specifications_markdown}

---

## Hypothesis Generation Requirements

### CRITICAL: Diversity Philosophy

**Hypotheses must be GLOBALLY DIFFERENT, not variations.**

This means:
- Different MODEL FAMILIES (not just different hyperparameters of same model)
- Different FEATURE PHILOSOPHIES (not just adding one feature to same pipeline)
- Different ARCHITECTURAL APPROACHES (not just ensembling slight variants)

### Diversity Quotas (MANDATORY)
Your {num_hypotheses} hypotheses MUST include:
- **Baseline (1):** Simple, interpretable model for performance floor
- **Feature Engineering Focus (2):** Domain-specific feature creation with DIFFERENT philosophies
- **Advanced Models (2):** Modern ML techniques appropriate for data type - DIFFERENT FAMILIES
- **Ensemble/Stack (1):** ONLY if {num_hypotheses} >= 5, with clear complementarity
- **Creative/Domain-Specific (1):** Novel approach tailored to this competition

### Model Family Orthogonality (Required)
Do NOT generate multiple hypotheses with the same model family:

| Model Family | Examples | Can Only Appear In |
|--------------|----------|-------------------|
| Gradient Boosting | LightGBM, XGBoost, CatBoost | 1-2 hypotheses max |
| Neural Networks | MLP, TabNet, FT-Transformer | 1-2 hypotheses max |
| Linear/Regularized | Ridge, Lasso, ElasticNet, LogReg | 1 hypothesis max |
| Tree Ensembles | Random Forest, ExtraTrees | 1 hypothesis max |
| Instance-Based | KNN, SVM | 1 hypothesis max |
| Meta/Stacking | StackingClassifier, VotingRegressor | 1 hypothesis max |

### Feature Philosophy Divergence (Required)
Different hypotheses should use DIFFERENT feature strategies:

| Philosophy | Description | Example |
|------------|-------------|---------|
| Minimalist | Top-K features only, remove noise | Use top 10 features by importance |
| Comprehensive | All features, let model select | Include all features with regularization |
| Domain-Driven | Hand-crafted domain features | Create business-logic interactions |
| Automated | Featuretools, autofeat, genetic | Auto-generate transformation combinations |
| Target-Encoded | Heavy target encoding use | Target encode all categoricals |
| Embedding-Based | Neural embeddings for categoricals | Use TabNet or Entity Embeddings |

### Complexity Spectrum (Required)
Cover different complexity levels:
- **Simple (1-2 hypotheses):** Few hyperparameters, fast training, interpretable
- **Medium (2-3 hypotheses):** Standard ML with tuning, reasonable complexity
- **Complex (1-2 hypotheses):** Ensembles, stacking, neural networks, cutting-edge

### Similarity Guard
For each hypothesis after the first, explicitly state:
- **Model Family Difference:** {how model family differs from others}
- **Feature Philosophy Difference:** {how feature approach differs}
- **Complexity Difference:** {simple/medium/complex positioning}

### Diversity Matrix (REQUIRED)
Before generating hypotheses, fill this matrix to ensure coverage:

| Hypothesis | Model Family | Feature Philosophy | Complexity | Unique Element |
|------------|--------------|-------------------|------------|----------------|
| exp_1 | {family_1} | {philosophy_1} | {level_1} | {unique_1} |
| exp_2 | {family_2} | {philosophy_2} | {level_2} | {unique_2} |
| exp_3 | {family_3} | {philosophy_3} | {level_3} | {unique_3} |
| ... | ... | ... | ... | ... |

**Validation Rule:** No two hypotheses should match in more than 1 dimension (model family, feature philosophy, or complexity level).

---

## Complex Approaches: ENCOURAGED

Do not shy away from sophisticated techniques. At least 1-2 hypotheses should include:

### Cutting-Edge Techniques to Consider
- **Stacking/Blending:** Multi-level ensembles with diverse base learners
- **Neural Tabular Models:** TabNet, FT-Transformer, TabTransformer for tabular data
- **Advanced Boosting:** CatBoost with ordered boosting, XGBoost with histogram-based splits
- **Automated Feature Discovery:** Featuretools deep feature synthesis, genetic feature generation
- **Target Encoding Variants:** CatBoost-style target encoding, leave-one-out encoding, WOE
- **Semi-Supervised Learning:** Pseudo-labeling with confident test predictions
- **Multi-Task Learning:** Auxiliary targets that correlate with main target

### Information Sources to Mine for Complex Ideas
1. **Kaggle Discussions:** Look for non-obvious tricks mentioned by top scorers
2. **Competition Writeups:** Past winners' approaches for similar problem types
3. **Recent Papers:** ArXiv papers from last 12-24 months on tabular/CV/NLP advances
4. **Framework Changelogs:** New features in LightGBM, XGBoost, CatBoost releases

### Anti-Patterns to Avoid
- Generating 5 variations of LightGBM with slightly different hyperparameters
- Using only tree-based models when neural approaches might excel
- Ignoring domain-specific techniques mentioned in discussions
- Playing it safe with only simple approaches
- Copying generic starter notebooks without adaptation

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
- Validation {metric} ≥ {minimum_acceptable_score}
- Train-val gap < {acceptable_overfit_threshold}%
- Output files correctly formatted
- No test data used for decisions

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

### Per-Hypothesis Checks
Verify each hypothesis contains:
- [ ] NO JSON code blocks or script files
- [ ] Exact markdown structure as template
- [ ] CV scheme with justification
- [ ] Runtime estimate with fallback
- [ ] 3-6 concrete features with leak checks
- [ ] Tight hyperparameter ranges (no 10x10 grids)
- [ ] Diagnostic signals for over/underfitting
- [ ] Similarity guard stating uniqueness (model family + feature philosophy + complexity)
- [ ] Random seeds documented
- [ ] [ASSUMED] markers where context missing

### Portfolio-Level Diversity Checks (CRITICAL)
Before submitting, verify the ENTIRE SET of hypotheses:
- [ ] Diversity Matrix is complete and shows no duplicate patterns
- [ ] At least 2 different model families represented
- [ ] At least 2 different feature philosophies represented
- [ ] At least 1 simple, 1 medium, and 1 complex approach
- [ ] At least 1 hypothesis incorporates insights from web search
- [ ] At least 1 hypothesis uses a technique from discussions/notebooks
- [ ] No two hypotheses are "the same model with different hyperparameters"
- [ ] Research findings section is complete

### Anti-Duplication Final Check
Read through all hypotheses and ask: "If hypothesis X fails, would hypothesis Y still provide unique learning?"
- If the answer is "no" for any pair, revise one of them to be more distinct.