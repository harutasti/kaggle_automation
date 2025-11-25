# AutoKaggle KSE: Iterative Hypothesis Generation (Iteration {iteration_number})

CONTRACT (read first):
- Goal: Generate {num_hypotheses} diverse experiment hypotheses that improve upon iteration {prev_iter} results without using test data for decisions.
- Data Ethics: No external lookups keyed on test samples; no test-driven feature design or imputation.
- Output Format: Use Markdown sections exactly as specified. Do NOT create any other files except the required markdown hypothesis files.
- Determinism: Reuse same CV folds as iteration {prev_iter} for comparability. Keep random_state=42.
- Improvement Target: Beat current best {best_score} by ≥{improvement_threshold}% or explore orthogonal approaches.

## Competition Context

**Competition Name:** {competition_name}
**Evaluation Metric:** {evaluation_metric}
**Current Best Score:** {best_score} (from {best_experiment_id})
**Score Gap to Leader:** {leaderboard_gap} [ASSUMED if unknown]

### Dataset Echo-Back (Unchanged from Iteration 1)
- Training: {train_size} rows, {feature_count} features
- Test: {test_size} rows
- Target: {target_variable}
- CV Scheme Used: {cv_scheme_from_iter1} (MUST reuse for comparability)

---

## Previous Iteration Analysis

### Performance Summary (Iteration {prev_iter})

| Exp ID | Strategy | Category | Val Score | Train-Val Gap | Runtime | Status |
|--------|----------|----------|-----------|---------------|---------|--------|
| {exp_1} | {strat_1} | {cat_1} | {score_1} | {gap_1}% | {time_1}min | {status_1} |
| {exp_2} | {strat_2} | {cat_2} | {score_2} | {gap_2}% | {time_2}min | {status_2} |
| Best: {best_id} | {best_strat} | {best_cat} | **{best_score}** | {best_gap}% | {best_time}min | Success |

### PA Deep Analysis

**What Worked (exploit these):**
- {success_pattern_1}: Improved {metric} by {delta}
- {success_pattern_2}: Reduced overfitting from {X}% to {Y}%
- {success_pattern_3}: {specific achievement}

**What Failed (avoid or fix):**
- {failure_1}: Caused by {root_cause} → Fix: {mitigation}
- {failure_2}: Caused by {root_cause} → Fix: {mitigation}

**Feature Importance Consensus:**
Top stable features across successful models:
1. {feature_1}: {importance_score} (stable/unstable)
2. {feature_2}: {importance_score} (stable/unstable)
3. {feature_3}: {importance_score} (stable/unstable)

**Unresolved Questions from PA:**
- Q1: {specific_question_1}
- Q2: {specific_question_2}

---

## System Specifications

{system_specifications_markdown}

---

## Hypothesis Generation Strategy for Iteration {iteration_number}

### Mandatory Distribution
Your {num_hypotheses} hypotheses MUST follow this allocation:

**Exploitation (40-50%):** {2-3 hypotheses}
- Refine {best_experiment_id} with better hyperparameters
- Add targeted features to successful approach
- Fix specific weaknesses identified

**Incremental Innovation (30-40%):** {1-2 hypotheses}
- Combine elements from {exp_1} and {exp_2}
- Test PA high-priority recommendation: {recommendation}
- Address unresolved question Q1

**Exploration (10-20%):** {1 hypothesis}
- Orthogonal approach not tried yet
- High-risk/high-reward based on community insights

### Score Targets

Based on iteration trajectory:
- Minimum acceptable: {best_score} + {min_improvement}
- Target: {best_score} + {target_improvement}
- Stretch: {best_score} + {stretch_improvement}
- Theoretical ceiling (from discussions): {ceiling_score}

---

## Output Template (Use EXACTLY This Structure)

```markdown
# Experiment Hypothesis: iter{iteration_number}_exp{exp_number}_{unique_id}

## Strategy Name
{concise_strategy_name} ({category: Exploitation/Innovation/Exploration})

## Iteration Learning Context
**Builds on:** {previous_experiment_id} (score: {prev_score})
**Addresses:** {PA recommendation or question}
**Key change:** {specific modification and why}

## Similarity Guard
**How this differs from iter{iteration}_others:** {explicit uniqueness claim}
**How this improves on iter{prev_iter}:** {specific improvement hypothesis}

## Metric-Method Fit
- Eval metric: {evaluation_metric}
- Optimization loss: {loss_function}
- Why better than iter{prev_iter}: {specific reasoning}
- Threshold (if applicable): {value} (was {prev_value} in iter{prev_iter})

## Runtime & Fallback
- Expected runtime: ~{X}-{Y} minutes (cf. {best_prev_time} min for similar approach)
- Memory: {X}GB (same/more/less than iter{prev_iter})
- If over budget: {specific degradation plan}
- Abort trigger: {condition}

## Implementation Steps

### 1. Data Loading & Verification
- Reuse exact preprocessing from iter{prev_iter}_exp{X}
- Verify: same {train_size} rows, {feature_count} features
- Assert: random_state=42 throughout

### 2. CV Consistency Check
- MUST use: {same_cv_scheme} with same random_state=42
- Verify fold indices match iter{prev_iter} exactly
- This ensures score comparability

### 3. Feature Engineering Delta

**Features from iter{prev_iter} to KEEP:**
| Feature | Why Keep | Importance |
|---------|----------|------------|
| {kept_1} | {reason} | {score} |
| {kept_2} | {reason} | {score} |

**NEW Features for iter{iteration_number}:**
| Feature | Description | Cost | Expected Impact | Leak Check |
|---------|------------|------|-----------------|------------|
| {new_1} | {what} | {cost} | +{expected_delta} {metric} | {safety} |
| {new_2} | {what} | {cost} | +{expected_delta} {metric} | {safety} |

**Features to DROP (based on PA analysis):**
- {dropped_1}: Low importance ({score}), adds noise

### 4. Model Configuration Delta

**Base Configuration (from {best_prev_exp}):**
```
{model_type}(
    {param_1}={prev_value_1},
    {param_2}={prev_value_2},
    random_state=42
)
```

**Refined Configuration (this iteration):**
```
{model_type}(
    {param_1}={new_value_1},  # Changed from {prev}: {reason}
    {param_2}={prev_value_2},  # Kept: performed well
    {param_3}={new_value_3},   # New: {reason}
    random_state=42
)
```

**Search Space (tight, informed by iter{prev_iter}):**
- {param_1}: [{low}, {mid}, {high}] (was [{prev_range}], narrowed based on {insight})
- {param_3}: [{low}, {high}] (new, based on {reasoning})

### 5. Training Improvements

**Fix for iter{prev_iter} issue:** {specific_issue}
- Solution: {concrete_fix}
- Expected impact: {quantified_improvement}

**Early Stopping Refinement:**
- Patience: {value} rounds (was {prev_value})
- Monitor: {metric} (same/different from iter{prev_iter})
- Restore best: True

### 6. Diagnostic Monitoring

**Overfitting Check (threshold based on iter{prev_iter}):**
- Alert if train-val gap > {threshold}% (was {prev_threshold}%)
- Alert if fold std > {threshold} (was {prev_threshold})
- Action: {mitigation_action}

**Improvement Tracking:**
- Baseline to beat: {best_score} from {best_experiment_id}
- Report paired difference: this_score - {best_score}
- Statistical significance: paired t-test on fold scores

### 7. Validation & Comparison

**Scoring Protocol:**
- Use exact same folds as iter{prev_iter}
- Report: mean ± std across folds
- Report: paired improvement over {best_experiment_id}
- Target: {best_score} + {improvement_target}

## Expected Outcomes
- Point estimate: {best_score} + {expected_improvement} = {target_score}
- Confidence interval: [{low}, {high}] {metric}
- Key learning: Answer to {PA_question}
- Risk: {main_risk} (probability: {low/medium/high})

## Success Criteria
- ✓ Beats {best_score} by ≥{threshold}%
- ✓ Answers: {specific_PA_question}
- ✓ Maintains/improves stability (fold std ≤{threshold})
- ✓ Completes in ≤{time_budget} minutes
- ✓ Provides actionable insight for iteration {next_iter}

## Failure Analysis Plan
If score < {best_score}:
1. Check: {diagnostic_1}
2. Compare: feature importance shift vs iter{prev_iter}
3. Hypothesis for iteration {next_iter}: {what_to_try_next}

## How to Replicate
1. Load iter{prev_iter} preprocessing pipeline
2. Add new features: {feature_list}
3. Apply model config: {config_summary}
4. Use CV folds from pickle: cv_folds_iter1.pkl
5. Compare scores with paired t-test vs {best_experiment_id}

---
**CONSTRAINTS REMINDER:**
- MUST use same CV folds as all previous iterations
- NO test data for any decisions
- NO files except this markdown
- Report paired improvements, not absolute scores
```

### Convergence Monitoring

**Plateau Detection:**
- If best score improvement < {threshold}% for 2 iterations → shift to exploration
- If variance increasing → shift to stabilization
- If approaching theoretical ceiling {ceiling_score} → focus on consistency

**Computational Budget Status:**
- Total time used: {cumulative_time} minutes
- Remaining budget: {remaining_time} minutes
- Average time per experiment: {avg_time} minutes
- Can afford: {remaining_experiments} more experiments

---

## Self-Check (Before Submitting Hypotheses)

Iteration {iteration_number} hypotheses must have:
- [ ] Same CV folds as iteration 1 (verified in text)
- [ ] Paired comparison to {best_score}
- [ ] Explicit build-on or fix-for previous experiments
- [ ] Distribution compliance (40% exploit, 40% innovate, 20% explore)
- [ ] Runtime estimates based on actual iteration {prev_iter} times
- [ ] Answers to at least one PA question
- [ ] NO test data usage
- [ ] NO JSON or code blocks
- [ ] [ASSUMED] markers for any missing context