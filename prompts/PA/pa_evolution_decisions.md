---

## CRITICAL: Evolution Decisions Required

After your analysis, you MUST provide explicit **CONTINUE** or **TERMINATE** decisions for each experiment.
These decisions determine whether experiments persist to the next iteration or are archived.

### Experiments Requiring Decisions:
<<EXPERIMENT_IDS>>

---

## Decision Criteria

### CONTINUE if ANY of these apply:
- **Competitive Score**: Within 5% of the best score in this iteration
- **Clear Improvement Path**: You can identify specific, actionable improvements
- **Diversity Value**: The approach is orthogonal to other experiments (different heuristic family, operator set)
- **Promising Trajectory**: Showed improvement from previous iteration (if applicable)
- **Fixable Issues**: Problems identified are parameter/implementation issues, not fundamental approach flaws

### TERMINATE if ANY of these apply:
- **Significantly Worse**: Score is >10% below the best with no clear fix
- **Fundamental Limitations**: The approach is inherently unsuited for this problem type
- **Redundancy**: A similar or better approach already exists in other experiments
- **Repeated Failure**: Failed to improve across multiple iterations
- **Resource Inefficiency**: Takes significantly longer with no score benefit

---

## Output Format (MANDATORY)

You MUST output decisions in this EXACT YAML format at the end of your analysis:

```yaml
decisions:
  - experiment_id: "<exact experiment ID>"
    decision: CONTINUE
    confidence: 0.85
    reasoning: "Concise explanation of why continuing"
    improvement_instructions: |
      1. Specific first improvement (e.g., "Increase SA start temperature from 1.0 to 2.0")
      2. Specific second improvement (e.g., "Add 2-opt move to local search neighborhood")
      3. Additional improvements as needed
    potential_ceiling: 0.82
    priority_rank: 1

  - experiment_id: "<exact experiment ID>"
    decision: TERMINATE
    confidence: 0.90
    reasoning: "Concise explanation of why terminating"
    termination_reason: "Specific reason (e.g., 'Greedy-only construction stalls far from feasible optimum')"
    priority_rank: 3

summary:
  continue_count: <number of CONTINUE decisions>
  terminate_count: <number of TERMINATE decisions>
  new_slots: <same as terminate_count>
```

---

## Field Requirements

### For ALL decisions:
- `experiment_id`: EXACT ID from the list above (copy-paste to avoid typos)
- `decision`: Must be exactly "CONTINUE" or "TERMINATE"
- `confidence`: Float between 0.0 and 1.0 (higher = more certain)
- `reasoning`: Brief explanation (1-2 sentences)
- `priority_rank`: Integer ranking (1 = highest priority experiment)

### For CONTINUE decisions (REQUIRED):
- `improvement_instructions`: Multi-line string with numbered, specific improvements
  - Must include at least 2 concrete improvements
  - Be specific: operators, parameters, schedules by name
  - Format as numbered list for clarity
- `potential_ceiling`: Estimated maximum achievable score with improvements

### For TERMINATE decisions (REQUIRED):
- `termination_reason`: Specific reason explaining the fundamental issue
  - Not just "poor performance" - explain WHY it can't improve

---

## Decision Prioritization Guidelines

When ranking experiments (priority_rank):

1. **Rank 1-2**: Best performing experiments with clear improvement paths
2. **Middle ranks**: Experiments with potential but more uncertainty
3. **Lowest ranks**: Experiments to terminate

### Diversity Consideration:
- Don't terminate ALL experiments of a particular heuristic family unless they ALL failed
- Maintain at least 2 different approaches among CONTINUE decisions if possible
- Consider keeping one "exploration" experiment even if not top-performing

---

## Common Mistakes to Avoid

1. **Missing experiment IDs**: Every experiment in the list MUST have a decision
2. **Vague improvement instructions**: "Try better parameters" is NOT acceptable
3. **Missing improvement_instructions for CONTINUE**: This field is REQUIRED
4. **Invalid YAML syntax**: Use proper indentation (2 spaces), quotes for strings with special chars
5. **Confidence outside 0-1**: Must be between 0.0 and 1.0

---

## Example Output

```yaml
decisions:
  - experiment_id: "iter1_exp1_a4ecbd"
    decision: CONTINUE
    confidence: 0.85
    reasoning: "Best score with room for schedule tuning"
    improvement_instructions: |
      1. Increase SA start temperature from 1.0 to 2.5 and slow the cooling rate
      2. Add a 2-opt neighborhood with incremental scoring
      3. Add a restart after 1,000 no-improve iterations
    potential_ceiling: 0.86
    priority_rank: 1

  - experiment_id: "iter1_exp2_b7f912"
    decision: CONTINUE
    confidence: 0.70
    reasoning: "Hybrid approach adds diversity, but needs stronger perturbation"
    improvement_instructions: |
      1. Increase perturbation size in ILS from 2 swaps to 5 swaps
      2. Add tabu list length sweep [5, 10, 20]
      3. Use multi-start with 5 randomized seeds
    potential_ceiling: 0.84
    priority_rank: 2

  - experiment_id: "iter1_exp3_c3d456"
    decision: TERMINATE
    confidence: 0.90
    reasoning: "Pure greedy stalls far from competitive scores"
    termination_reason: "Greedy-only construction cannot recover from early suboptimal choices without local search."
    priority_rank: 3

summary:
  continue_count: 2
  terminate_count: 1
  new_slots: 1
```

---

**REMINDER**: Your decisions directly impact the next iteration. CONTINUE experiments will resume with your improvement instructions. TERMINATE experiments will be archived and replaced with new hypotheses. Be thoughtful and specific.
