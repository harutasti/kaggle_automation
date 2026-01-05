# Competition-Wide Context (Filled by KSE)

## Overview
- Competition: {{COMPETITION_NAME}}
- Goal / objective: {{COMPETITION_OBJECTIVE}}
- Evaluation metric: {{EVALUATION_METRIC}}
- Metric direction: {{METRIC_DIRECTION}} ({{METRIC_DIRECTION_EXPLANATION}})
- Key deadlines or iteration cadence: {{DEADLINES_AND_CADENCE}}

## Rules and Submission Requirements
- Submission format (file name, required columns, ordering): {{SUBMISSION_FORMAT}}
- External data / pretraining policy: {{EXTERNAL_DATA_POLICY}}
- Hardware/runtime limits or notebook constraints: {{HARDWARE_LIMITS}}
- Disallowed techniques or pitfalls called out by organizers: {{DISALLOWED_ITEMS}}
- Mandatory validation rule: Use official constraints/geometry; proxies may only prune and must be rechecked before DONE

## Data / Problem Summary
- Primary files and shapes: {{TRAINING_FILES}}
- Target or objective definition: {{TARGET_AND_TYPE}}
- Data types / structure (numeric/categorical/text/graph/etc.): {{FEATURE_TYPES}}
- Missing data and quality issues: {{MISSING_DATA}}
- Feasibility constraints / invalid solution risks: {{LEAKAGE_AND_SPLITS}}
- Balance or distribution observations: {{CLASS_BALANCE}}

---

## Research Findings Summary (NEW - Filled by KSE)

### Web Search Discoveries
{{WEB_SEARCH_FINDINGS}}

Key techniques discovered:
1. {{TECHNIQUE_1}}: {{TECHNIQUE_1_DESCRIPTION}} (Expected Impact: {{TECHNIQUE_1_IMPACT}})
2. {{TECHNIQUE_2}}: {{TECHNIQUE_2_DESCRIPTION}} (Expected Impact: {{TECHNIQUE_2_IMPACT}})
3. {{TECHNIQUE_3}}: {{TECHNIQUE_3_DESCRIPTION}} (Expected Impact: {{TECHNIQUE_3_IMPACT}})

### Discussion/Notebook Insights
{{DISCUSSION_INSIGHTS}}

Top insights extracted:
1. {{INSIGHT_1}}
2. {{INSIGHT_2}}
3. {{INSIGHT_3}}
4. {{INSIGHT_4}}
5. {{INSIGHT_5}}

### Pitfalls to Avoid
{{PITFALLS_LIST}}

### Cutting-Edge Techniques Worth Considering
{{CUTTING_EDGE_TECHNIQUES}}

---

## Global Evaluation & Experiment Expectations
- Preferred evaluation scheme and justification: {{VALIDATION_SCHEME}}
- Data handling notes (splits, leakage controls, feasibility checks): {{DATA_HANDLING_NOTES}}
- Baseline/benchmark references (public LB baselines, starter notebooks): {{BASELINES_AND_REFERENCES}}
- Expected score ceiling or target ranges: {{EXPECTED_SCORE_RANGE}}
- Reproducibility and random seed policy: {{REPRODUCIBILITY_POLICY}}

## Operational Constraints for WAAs
- Time and GPU/CPU budget guidance: {{RESOURCE_BUDGET}}
- Checkpointing and intermediate artifacts to persist: {{CHECKPOINT_GUIDANCE}}
- Logging expectations (what to record in `waa_{exp_id}.log`): {{LOGGING_EXPECTATIONS}}
- Mandatory outputs (result JSON, submission CSV, DONE marker): {{OUTPUT_REQUIREMENTS}}

---

## Hypothesis Diversity Requirements (NEW)

This iteration's experiments MUST collectively cover:

### Heuristic Families Assigned
{{MODEL_FAMILIES_LIST}}

### Operator / Move Strategies Assigned
{{FEATURE_STRATEGIES_LIST}}

### Complexity Distribution
{{COMPLEXITY_DISTRIBUTION}}

### Diversity Matrix
| Experiment ID | Heuristic Family | Operator Strategy | Complexity | Unique Element |
|---------------|------------------|-------------------|------------|----------------|
{{DIVERSITY_MATRIX_ROWS}}

**Note**: Each WAA should verify their experiment differs from others in at least 2 dimensions.

---

## Risks, Open Questions, and Fallbacks
- High-risk areas to monitor: {{HIGH_RISK_AREAS}}
- Open questions to answer in future iterations: {{OPEN_QUESTIONS}}
- Recommended simplifications if constraints bite: {{FALLBACK_PATHS}}

---

## Evolution Summary (For Resume Iterations)

### Changes from Previous Iteration
{{EVOLUTION_CHANGES}}

### Approaches Killed and Why
{{KILLED_APPROACHES}}

### New Approaches Added and Why
{{NEW_APPROACHES}}

### Current Trajectory Assessment
{{TRAJECTORY_ASSESSMENT}}
