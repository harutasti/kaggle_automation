# Codex Extension Roadmap: From WAA-Only to Full AI System

## Current State vs Target State

### Current: Only WAA Uses Codex

```
┌─────────────────────────────────────────────────────────────────┐
│                         Iteration Loop                           │
└─────────────────────────────────────────────────────────────────┘

    KSE (Programmatic)
         │
         │  Random strategies from hardcoded list
         │  Random parameters
         ▼
    [Task Markdowns Generated]
         │
         ▼
    EO (Orchestrator)
         │
         ├──► Git Worktree 1 ──► WAA 1 (CODEX) ──► Results
         ├──► Git Worktree 2 ──► WAA 2 (CODEX) ──► Results
         └──► Git Worktree 3 ──► WAA 3 (CODEX) ──► Results
                                    │
                                    ▼
                              RAD (Collects)
                                    │
                                    ▼
                          PA (Programmatic Analysis)
                                    │
                                    │  Simple statistics
                                    │  Basic recommendations
                                    │
                            (Loop back to KSE)
```

**Problems**:
- KSE: No intelligence in strategy generation
- PA: Shallow analysis, missed patterns
- No learning loop between iterations
- Wasting WAA Codex potential on mediocre strategies

---

### Target: Full AI-Powered System

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI-Powered Iteration Loop                     │
└─────────────────────────────────────────────────────────────────┘

    KSE (CODEX-Powered) 🤖
         │
         │  Input: Competition data, crawler insights,
         │         PA recommendations from previous iteration
         │
         │  AI generates creative, well-reasoned hypotheses
         │  Deep analysis of data patterns
         │  Learning from past results
         ▼
    [AI-Generated Idea Markdowns]
         │
         ▼
    EO (Orchestrator)
         │
         ├──► Git Worktree 1 ──► WAA 1 (CODEX) 🤖 ──► Results
         ├──► Git Worktree 2 ──► WAA 2 (CODEX) 🤖 ──► Results
         └──► Git Worktree 3 ──► WAA 3 (CODEX) 🤖 ──► Results
                                    │
                                    ▼
                              RAD (Collects)
                                    │
                                    ▼
                          PA (CODEX-Powered) 🤖
                                    │
                                    │  Input: All experiment logs, scores,
                                    │         parameters, errors, patterns
                                    │
                                    │  AI performs deep analysis
                                    │  Identifies success factors
                                    │  Root cause failure analysis
                                    │  Generates actionable recommendations
                                    │
                                    ▼
                        [Structured Insights Feed to KSE]
                                    │
                            (Loop back to KSE with learning)
```

**Benefits**:
- KSE: Intelligent, adaptive strategy generation
- PA: Deep insights, pattern recognition
- True learning across iterations
- Continuous improvement cycle

---

## Implementation Roadmap

### Phase 1: KSE Codex Integration (Weeks 1-2)

**Goal**: Replace programmatic strategy generation with AI-powered ideation

**Tasks**:
1. Create `src/core/kse_codex.py`
   - Prompt builder for strategy generation
   - Codex execution wrapper
   - Parse AI-generated ideas

2. Update `src/core/kse.py`
   - Add mode switch: programmatic vs Codex
   - Delegate to `kse_codex` when enabled
   - Maintain backward compatibility

3. Update `src/core/mcdu.py`
   - Pass PA recommendations to KSE
   - Handle KSE Codex execution
   - Manage idea markdowns

4. Configuration
   - Add `execution_modes.kse: "codex"`
   - Add KSE Codex settings

**Input to KSE Codex**:
```markdown
# Strategy Generation Task - Iteration {N}

## Competition Context
- Name: {competition_name}
- Type: {classification/regression}
- Metric: {evaluation_metric}
- Description: {competition_description}

## Data Insights (from crawler)
{discussion_strategies}
{data_characteristics}

## Previous Iteration Results (Iteration {N-1})
- Best Score: {best_score}
- Successful Strategies: {successful_strategies}
- Failed Approaches: {failed_strategies}

## PA Recommendations
{pa_recommendations}

## Your Task
Generate {num_hypotheses} creative, well-reasoned ML experiment strategies.
For each strategy:
1. Name the approach
2. Explain the reasoning
3. Specify model type and key parameters
4. Describe expected strengths/weaknesses
5. Reference relevant discussion insights if applicable

Output format: One markdown file per hypothesis with complete task description.
```

**Output from KSE Codex**:
```markdown
# Strategy 1: Advanced Feature Engineering + LightGBM

## Rationale
Based on the competition's tabular nature and the strong performance of
gradient boosting in discussions (threads #12, #47), this strategy focuses
on aggressive feature engineering combined with LightGBM.

The previous iteration showed that simple GBM achieved 0.78 score, suggesting
room for improvement through better features.

## Approach
- Feature Engineering:
  * Polynomial features (degree 2) for numeric columns
  * Target encoding for high-cardinality categoricals
  * Interaction terms between top 5 important features

- Model: LightGBM
  * learning_rate: 0.03 (lower than previous 0.05 for better convergence)
  * n_estimators: 1000 (with early stopping)
  * max_depth: 7
  * num_leaves: 50

## Expected Outcome
Estimated score range: 0.82-0.85
Risk: May overfit on small dataset (use CV)

## Implementation Notes
1. Load train/test data
2. Apply feature engineering pipeline
3. Train LightGBM with 5-fold CV
4. Generate predictions
5. Output result_{exp_id}.json with CV score
```

**Deliverables**:
- New module: `src/core/kse_codex.py`
- Updated: `src/core/kse.py`, `src/core/mcdu.py`
- Config updates
- Tests for KSE Codex integration

---

### Phase 2: PA Codex Integration (Weeks 3-4)

**Goal**: Replace programmatic analysis with AI-powered deep insights

**Tasks**:
1. Create `src/analysis/pa_codex.py`
   - Prompt builder for result analysis
   - Codex execution wrapper
   - Parse structured recommendations

2. Update `src/analysis/pa.py`
   - Add mode switch: programmatic vs Codex
   - Delegate to `pa_codex` when enabled
   - Maintain backward compatibility

3. Update `src/core/mcdu.py`
   - Collect comprehensive data for PA
   - Handle PA Codex execution
   - Extract structured recommendations
   - Pass to KSE for next iteration

4. Configuration
   - Add `execution_modes.pa: "codex"`
   - Add PA Codex settings

**Input to PA Codex**:
```markdown
# Performance Analysis Task - Iteration {N}

## Competition Context
- Name: {competition_name}
- Metric: {evaluation_metric}
- Current Best Score: {best_score_overall}

## Iteration {N} Results Summary
Total Experiments: {num_experiments}
Successful: {num_successful}
Failed: {num_failed}

## Detailed Results

### Experiment 1: {exp_id_1}
- Strategy: {strategy_name}
- Parameters: {parameters}
- Score: {score}
- Execution Time: {time}
- Key Logs:
  ```
  {relevant_log_excerpts}
  ```

### Experiment 2: {exp_id_2}
...

## Historical Context
- Iteration 0 Best: {score}
- Iteration 1 Best: {score}
- Overall Best: {score} (Experiment: {exp_id})

## Your Task
Perform deep analysis and provide:

1. Success Factor Analysis
   - What made successful experiments work?
   - Common patterns in high-scoring approaches?
   - Parameter sensitivity analysis?

2. Failure Analysis
   - Why did experiments fail?
   - Common error patterns?
   - Data/model mismatches?

3. Cross-Experiment Insights
   - Which features consistently help?
   - Which hyperparameters matter most?
   - Strategy comparison (GBM vs NN vs RF)?

4. Recommendations for Iteration {N+1}
   - Top 3 strategies to try next
   - Parameter ranges to explore
   - Approaches to avoid
   - Novel ideas based on patterns

Output: Detailed markdown analysis with structured recommendations section.
```

**Output from PA Codex**:
```markdown
# Performance Analysis - Iteration {N}

## Executive Summary
This iteration achieved a best score of 0.82 (Experiment iter2_exp2),
improving from 0.78 in the previous iteration (+5.1% improvement).

Key finding: Feature engineering significantly outperformed raw features.

## Success Factor Analysis

### Top Performer: iter2_exp2 (Score: 0.82)
- Strategy: Advanced Feature Engineering + LightGBM
- Success factors:
  1. Polynomial features captured non-linear relationships
  2. Target encoding reduced cardinality effectively
  3. Conservative learning rate (0.03) prevented overfitting
  4. Early stopping at 437 iterations was optimal

### Common Success Patterns
Across all successful experiments (n=5):
- Feature engineering present: 5/5
- Gradient boosting models: 4/5
- Cross-validation used: 5/5
- Learning rate < 0.05: 4/5

### Parameter Sensitivity
Most sensitive parameters:
1. learning_rate: ±0.02 causes ±0.03 score change
2. max_depth: Optimal at 6-8, degrades outside
3. Feature engineering: +0.04 score vs raw features

## Failure Analysis

### Failed Experiment: iter2_exp3 (Error)
- Strategy: Basic Neural Network
- Root cause: Insufficient preprocessing for NN
  * Log shows: "ValueError: NaN in input data"
  * Categorical features not encoded properly
- Recommendation: Add robust preprocessing for NN strategies

### Common Failure Patterns
- Neural networks: 2/2 failed (preprocessing issues)
- High learning rates (>0.1): 1/1 failed (divergence)
- Missing data handling: 2/3 experiments had warnings

## Cross-Experiment Insights

### Feature Importance Patterns
Analyzing logs from successful experiments:
1. Feature "Age" appears in top 5: 5/5 experiments
2. Feature "Fare" appears in top 5: 4/5 experiments
3. Engineered interaction "Age_Fare": +0.02 score

### Model Comparison
- LightGBM: 0.82 (best), 0.78 (avg) - consistent
- XGBoost: 0.79 (single attempt) - promising
- Neural Network: Failed (2 attempts) - needs work
- Random Forest: 0.75 (slow, underperforming)

### Hyperparameter Insights
Optimal ranges discovered:
- learning_rate: [0.02, 0.05]
- n_estimators: [500, 1000] with early stopping
- max_depth: [6, 8]
- num_leaves: [40, 60]

## Recommendations for Iteration {N+1}

### Top 3 Strategies to Try

1. **Ensemble of Top Models** (Priority: HIGH)
   - Blend best LightGBM (0.82) with XGBoost (0.79)
   - Weighted average or stacking
   - Expected score: 0.83-0.85

2. **Feature Engineering V2** (Priority: HIGH)
   - Build on successful polynomial features
   - Add: 3-way interactions for top features
   - Add: Binning of "Age" (categorical patterns in logs)
   - Expected score: 0.82-0.84

3. **XGBoost Optimization** (Priority: MEDIUM)
   - Previous XGBoost showed promise (0.79)
   - Try with successful feature engineering pipeline
   - Tune: max_depth, subsample, colsample_bytree
   - Expected score: 0.81-0.83

### Parameter Ranges to Explore
- learning_rate: [0.02, 0.04] (narrowed from [0.01, 0.05])
- max_depth: [6, 8] (confirmed optimal)
- New: subsample: [0.8, 1.0]
- New: colsample_bytree: [0.8, 1.0]

### Approaches to Avoid
1. Neural Networks without robust preprocessing
2. Learning rates > 0.1 (consistently diverge)
3. Random Forest (too slow, underperforms)
4. Shallow trees (max_depth < 4 underperform)

### Novel Ideas
1. **Time-based CV**: Logs suggest temporal patterns in data
2. **Feature selection**: Try dropping bottom 20% features
3. **AutoML ensemble**: Let multiple models vote
4. **Outlier handling**: Logs show extreme values in "Fare"

---

## Structured Recommendations (for KSE)

```json
{
  "recommended_strategies": [
    "EnsembleBlend_LightGBM_XGBoost",
    "FeatureEngV2_LightGBM",
    "XGBoost_Optimized"
  ],
  "parameter_ranges": {
    "learning_rate": [0.02, 0.04],
    "max_depth": [6, 8],
    "n_estimators": [500, 1000]
  },
  "avoid_strategies": [
    "BasicNN",
    "RandomForest"
  ],
  "key_insights": [
    "Feature engineering provides +0.04 score improvement",
    "Ensemble likely to reach 0.83-0.85",
    "Neural networks need preprocessing overhaul"
  ]
}
```
```

**Deliverables**:
- New module: `src/analysis/pa_codex.py`
- Updated: `src/analysis/pa.py`, `src/core/mcdu.py`
- Config updates
- Tests for PA Codex integration

---

### Phase 3: Integration & Testing (Week 5)

**Goal**: Wire end-to-end AI loop and validate

**Tasks**:
1. KSE ↔ PA Feedback Loop
   - PA outputs structured recommendations
   - KSE receives and incorporates them
   - Test multi-iteration learning

2. Artifact Management
   - Standardize markdown storage
   - KSE idea library: `experiments/kse_ideas/`
   - PA analysis archive: `experiments/pa_analysis/`

3. End-to-End Testing
   - Run 3-iteration loop with all Codex modes
   - Verify learning/improvement
   - Monitor costs and performance

4. Safety & Validation
   - Ensure WAA tasks forbid submissions
   - Validate all result files
   - Error handling for malformed AI outputs

**Deliverables**:
- Integrated system with all 3 Codex modes
- Test suite covering full loop
- Documentation updates
- Safety guardrails

---

### Phase 4: Optimization (Week 6+)

**Goal**: Production-ready, cost-efficient system

**Tasks**:
1. Performance
   - Parallel Codex calls where safe
   - Optimize prompt lengths
   - Cache repeated analyses

2. Cost Management
   - Token usage tracking per component
   - Budget enforcement
   - Cost estimation pre-run

3. Observability
   - Rich logging for all AI calls
   - Structured output tracking
   - Performance dashboards

4. Prompt Engineering
   - Iterate on prompts based on results
   - A/B test different approaches
   - Few-shot examples in prompts

**Deliverables**:
- Optimized, production-ready system
- Cost tracking and budgets
- Enhanced monitoring
- Refined prompts

---

## Configuration Evolution

### Current (WAA Only)
```json
{
  "execution_mode": "codex",
  "codex": {
    "enabled": true,
    "timeout": 3600,
    "max_retries": 2
  }
}
```

### Phase 1 (+ KSE)
```json
{
  "execution_modes": {
    "waa": "codex",
    "kse": "codex",
    "pa": "programmatic"
  },
  "codex": {
    "waa": {
      "timeout": 3600,
      "max_retries": 2
    },
    "kse": {
      "timeout": 600,
      "max_retries": 1,
      "hypotheses_per_iteration": 3
    }
  }
}
```

### Phase 2 (Full AI)
```json
{
  "execution_modes": {
    "waa": "codex",
    "kse": "codex",
    "pa": "codex"
  },
  "codex": {
    "waa": {
      "timeout": 3600,
      "max_retries": 2
    },
    "kse": {
      "timeout": 600,
      "max_retries": 1,
      "hypotheses_per_iteration": 3
    },
    "pa": {
      "timeout": 300,
      "max_retries": 1,
      "detailed_analysis": true
    }
  },
  "cost_controls": {
    "max_tokens_per_iteration": 500000,
    "alert_threshold": 400000
  }
}
```

---

## Expected Outcomes

### Quantitative Improvements
- **Strategy Diversity**: 3-4 predefined → 10+ AI-generated per iteration
- **Analysis Depth**: 5 metrics → 20+ insights per iteration
- **Learning Rate**: Minimal → Significant improvement per iteration
- **Score Improvement**: Linear → Accelerating improvement curve

### Qualitative Improvements
- **Creativity**: AI discovers non-obvious strategies
- **Adaptability**: System learns from failures effectively
- **Reasoning**: Transparent why-behind-strategies
- **Robustness**: Better error handling and recovery

---

## Risk Mitigation

### Technical Risks
1. **Codex Cost Overrun**
   - Mitigation: Token budgets, timeouts, monitoring

2. **Poor AI Output Quality**
   - Mitigation: Output validation, fallback to programmatic

3. **Parsing Failures**
   - Mitigation: Structured output formats, retry logic

### Design Risks
1. **Overfitting to Specific Competitions**
   - Mitigation: Test on diverse competition types

2. **AI Generates Invalid Strategies**
   - Mitigation: Validation layer, feasibility checks

3. **Feedback Loop Divergence**
   - Mitigation: Human-in-loop checkpoints, sanity checks

---

## Success Criteria

### Phase 1 (KSE Integration)
- [ ] KSE generates 3+ creative strategies per iteration
- [ ] Strategies are executable by WAA
- [ ] Strategies reference competition context appropriately
- [ ] Cost per KSE call < $0.50

### Phase 2 (PA Integration)
- [ ] PA generates detailed analysis (>500 words)
- [ ] PA extracts structured recommendations
- [ ] Recommendations used by KSE in next iteration
- [ ] Cost per PA call < $0.30

### Phase 3 (Full Integration)
- [ ] 3-iteration loop completes without errors
- [ ] Visible improvement in scores across iterations
- [ ] Total cost per iteration < $5.00
- [ ] All artifacts properly stored and logged

### Phase 4 (Production)
- [ ] System runs autonomously for 5+ iterations
- [ ] Achieves competitive score (top 50% of leaderboard)
- [ ] Cost tracking and budgets functional
- [ ] Complete documentation and tests

---

## Timeline Summary

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| Phase 1: KSE | 2 weeks | AI-powered strategy generation |
| Phase 2: PA | 2 weeks | AI-powered deep analysis |
| Phase 3: Integration | 1 week | End-to-end AI loop |
| Phase 4: Optimization | 2+ weeks | Production-ready system |

**Total**: ~7 weeks to full AI-powered system

---

## Next Immediate Steps

1. **Validate Current WAA Codex**
   ```bash
   uv run python tests/test_codex_integration.py
   ```

2. **Design KSE Prompt**
   - Draft prompt template
   - Define input data structure
   - Define output format

3. **Implement KSE Codex Module**
   - Create `src/core/kse_codex.py`
   - Build prompt builder
   - Add Codex execution
   - Parse and validate outputs

4. **Test KSE Integration**
   - Unit tests for prompt building
   - Integration test with real Codex
   - Validate output quality

5. **Wire into MCDU**
   - Add configuration flag
   - Update main loop
   - Test full flow

---

## Questions & Decisions Needed

### KSE Design
- [ ] How many hypotheses per iteration? (Recommend: 3-5)
- [ ] Should KSE generate in parallel or sequentially? (Recommend: Sequential with context)
- [ ] Should ideas include success probability estimates? (Recommend: Yes)
- [ ] Format for idea markdowns? (Recommend: Structured with rationale section)

### PA Design
- [ ] How much log data to include? (Recommend: Last 100 lines per experiment)
- [ ] Should PA score/rank experiments? (Recommend: Yes, with reasoning)
- [ ] Recommendation format? (Recommend: JSON + markdown explanation)
- [ ] Should PA suggest stopping early if plateau? (Recommend: Yes, advisory)

### Integration
- [ ] Should there be human review checkpoints? (Recommend: Optional flag)
- [ ] Maximum budget per iteration? (Recommend: Configurable, default $10)
- [ ] Logging verbosity for AI calls? (Recommend: High initially, tunable)
- [ ] Artifact retention policy? (Recommend: Keep all for learning)

---

## Resources Needed

### Development
- Codex CLI installed and configured
- API keys with sufficient quota
- Test competitions for validation

### Testing
- Sample competition data (Titanic, House Prices)
- Reference baselines for comparison
- Cost tracking spreadsheet

### Documentation
- Prompt templates
- Output format specifications
- Integration guides
- Troubleshooting playbook

---

This roadmap provides a clear path from the current state (WAA-only Codex) to the target state (full AI-powered autonomous system). Each phase builds incrementally, with clear deliverables and success criteria.

Let's build an intelligent Kaggle competitor!
