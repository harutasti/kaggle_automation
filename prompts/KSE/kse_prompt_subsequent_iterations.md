# AutoKaggle KSE: Iterative Hypothesis Generation (Iteration {iteration_number})

CONTRACT (read first):
- Goal: Generate {num_hypotheses} diverse experiment hypotheses that improve upon iteration {prev_iter} results without using test data for decisions.
- **Score Priority**: Official Kaggle score is the PRIMARY truth. CV scores are SECONDARY and used only for development guidance.
- Data Ethics: No external lookups keyed on test samples; no test-driven feature design or imputation.
- Output Format: Use Markdown sections exactly as specified. Do NOT create any other files except the required markdown hypothesis files.
- Determinism: Reuse same CV folds as iteration {prev_iter} for comparability. Keep random_state=42.
- Improvement Target: Beat current best {best_score} by ≥{improvement_threshold}% or explore orthogonal approaches.
- **Evolution Required**: Each iteration must EVOLVE strategy based on trajectory (improving/plateauing/declining).

---

## PHASE 0: Targeted Research (Subsequent Iteration)

Even in subsequent iterations, conduct focused research:

### What to Search For
- **Specific technique refinements:** If LightGBM worked, search for "LightGBM tuning tricks {competition_type}"
- **Failure diagnosis:** If neural nets failed, search for "tabular neural network pitfalls"
- **Breakthrough techniques:** Check if any new methods emerged since last iteration

### PA-Directed Research
Based on PA's analysis, investigate:
- {pa_recommended_technique_1}: Search for implementation details and pitfalls
- {pa_recommended_technique_2}: Find examples of successful application
- Unresolved question: Search for similar competition solutions that addressed {pa_question}

**Document new findings in the Research Updates section below.**

---

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

## Score Tracking (Official vs CV)

### Official Kaggle Scores (PRIMARY)
| Iteration | Experiment | Official Score | Rank/Position | Delta from Previous Best |
|-----------|------------|----------------|---------------|--------------------------|
| {iter_1} | {exp_id_1} | {official_1} | {rank_1} | - |
| {iter_2} | {exp_id_2} | {official_2} | {rank_2} | {delta_2} |
| ... | ... | ... | ... | ... |

### CV vs Official Score Correlation
| Experiment | CV Score | Official Score | Gap | Reliable? |
|------------|----------|----------------|-----|-----------|
| {exp_1} | {cv_1} | {official_1} | {gap_1} | {yes/no} |
| {exp_2} | {cv_2} | {official_2} | {gap_2} | {yes/no} |

**CV Reliability Assessment:** {assessment of whether CV tracks official well}
- If CV consistently overestimates: Consider more conservative thresholds
- If CV consistently underestimates: Current CV may be too pessimistic
- If gap varies wildly: CV scheme may not match test distribution

---

## Trajectory Analysis (CRITICAL FOR STRATEGY)

### Current Trajectory Classification

Based on last 2-3 iterations, classify the trajectory:

| Trajectory | Criteria | Strategy Implication |
|------------|----------|---------------------|
| **IMPROVING** | Each iteration beats previous by >1% | Continue current direction, exploit what works |
| **PLATEAUING** | Improvements <0.5% for 2+ iterations | Time to explore orthogonal approaches |
| **DECLINING** | Latest iteration worse than previous | Diagnose failure, potentially reset |

**Current Trajectory:** {IMPROVING / PLATEAUING / DECLINING}

### Strategy Evolution Rules

**If IMPROVING:**
- Allocation: 60% exploit current winners, 30% incremental innovation, 10% moonshot
- Focus: Refine hyperparameters of winning models, add features to working pipelines
- Risk tolerance: Lower (don't break what's working)

**If PLATEAUING:**
- Allocation: 30% exploit, 50% explore new directions, 20% moonshot
- Focus: Try fundamentally different model families, new feature philosophies
- Risk tolerance: Higher (need to break out of local optimum)

**If DECLINING:**
- Allocation: 20% diagnose failures, 40% return to previous winners, 40% reset with new approach
- Focus: Understand what broke, don't repeat mistakes
- Risk tolerance: Medium (controlled experiments to identify issue)

---

## Kill/Replace Protocol

### Approaches to KILL (Do Not Repeat)
Based on PA analysis, these approaches have proven ineffective:

| Killed Approach | Why Killed | Iterations Tried | Evidence |
|-----------------|------------|------------------|----------|
| {killed_1} | {reason_1} | {iterations_1} | {evidence_1} |
| {killed_2} | {reason_2} | {iterations_2} | {evidence_2} |

**Rule:** Do NOT generate hypotheses similar to killed approaches unless you have specific evidence they might work now.

### Approaches to EVOLVE (Modify and Improve)
These showed promise but need refinement:

| Evolve Approach | Current Score | Identified Weakness | Proposed Fix |
|-----------------|---------------|---------------------|--------------|
| {evolve_1} | {score_1} | {weakness_1} | {fix_1} |
| {evolve_2} | {score_2} | {weakness_2} | {fix_2} |

### New Approaches to INTRODUCE
Based on trajectory and research, introduce:
- {new_approach_1}: Rationale: {why_now}
- {new_approach_2}: Rationale: {why_now}

---

## Research Updates (Subsequent Iteration Findings)

### New Discoveries Since Last Iteration
- {new_finding_1}
- {new_finding_2}

### Techniques to Incorporate This Iteration
Based on trajectory + new research:
1. {technique_1}: Apply to {which_hypothesis}
2. {technique_2}: Apply to {which_hypothesis}

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

### Allocation Based on Trajectory (ADAPT TO CURRENT STATE)

**If trajectory is IMPROVING:**
| Category | Allocation | Focus |
|----------|------------|-------|
| Exploit | 60% ({N} hypotheses) | Refine winners, targeted improvements |
| Innovate | 30% ({N} hypotheses) | Combine successful elements, PA recommendations |
| Moonshot | 10% ({N} hypotheses) | One high-risk experiment |

**If trajectory is PLATEAUING:**
| Category | Allocation | Focus |
|----------|------------|-------|
| Exploit | 30% ({N} hypotheses) | Only keep absolute best |
| Explore | 50% ({N} hypotheses) | New model families, new feature philosophies |
| Moonshot | 20% ({N} hypotheses) | Aggressive new approaches |

**If trajectory is DECLINING:**
| Category | Allocation | Focus |
|----------|------------|-------|
| Diagnose | 20% ({N} hypotheses) | Ablations to find what broke |
| Return | 40% ({N} hypotheses) | Return to previous winning approaches |
| Reset | 40% ({N} hypotheses) | Fresh start with different paradigm |

### Current Allocation (Based on {current_trajectory} Trajectory)
Your {num_hypotheses} hypotheses MUST follow:

**Exploitation ({exploit_percent}%):** {exploit_count} hypotheses
- Refine {best_experiment_id} with better hyperparameters
- Add targeted features to successful approach
- Fix specific weaknesses identified

**Exploration/Innovation ({explore_percent}%):** {explore_count} hypotheses
- Combine elements from {exp_1} and {exp_2}
- Test PA high-priority recommendation: {recommendation}
- Address unresolved question Q1
- Try fundamentally different approach if plateauing

**Moonshot/Reset ({moonshot_percent}%):** {moonshot_count} hypotheses
- Orthogonal approach not tried yet
- High-risk/high-reward based on community insights
- Or diagnostic ablation if declining

### Score Targets

Based on iteration trajectory:
- Minimum acceptable: {best_score} + {min_improvement}
- Target: {best_score} + {target_improvement}
- Stretch: {best_score} + {stretch_improvement}
- Theoretical ceiling (from discussions): {ceiling_score}

### Diversity Maintenance (Even in Later Iterations)

Even while exploiting winners, maintain diversity:
- Do NOT generate 3+ variations of the same winning model
- Each "exploit" hypothesis must have a DISTINCT improvement direction
- At least 1 hypothesis should use a model family NOT in current winners

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

### Core Requirements
Iteration {iteration_number} hypotheses must have:
- [ ] Same CV folds as iteration 1 (verified in text)
- [ ] Paired comparison to {best_score}
- [ ] Explicit build-on or fix-for previous experiments
- [ ] Runtime estimates based on actual iteration {prev_iter} times
- [ ] Answers to at least one PA question
- [ ] NO test data usage
- [ ] NO JSON or code blocks
- [ ] [ASSUMED] markers for any missing context

### Trajectory-Aware Checks (NEW)
- [ ] Current trajectory correctly identified (IMPROVING/PLATEAUING/DECLINING)
- [ ] Allocation matches trajectory rules (not generic 40/40/20)
- [ ] If PLATEAUING: At least 50% are genuinely new directions
- [ ] If DECLINING: At least 40% are diagnostic or return-to-previous

### Kill/Replace Protocol Checks
- [ ] No hypotheses resurrect killed approaches without new evidence
- [ ] Approaches marked for evolution have specific fixes
- [ ] New approaches have clear rationale for why NOW

### Official Score Priority Checks
- [ ] Official scores (if available) are tracked and prioritized
- [ ] CV vs Official gap is analyzed and acknowledged
- [ ] If CV and Official diverge, hypotheses address the gap

### Diversity Check (Even for Exploit-Heavy Iterations)
- [ ] No more than 2 hypotheses use exact same model family
- [ ] Each "exploit" hypothesis has a DISTINCT improvement direction
- [ ] At least 1 hypothesis explores something not in current winners

### Research Integration Check
- [ ] Targeted research conducted for this iteration
- [ ] At least 1 hypothesis incorporates new research findings
- [ ] PA recommendations are addressed in at least 1 hypothesis