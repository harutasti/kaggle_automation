# Continuation Experiment: {{CONTINUATION_ID}}

## Context: Building on Previous Success

This is a **CONTINUATION** of experiment `{{ORIGINAL_EXP_ID}}`.

You are resuming an experiment that showed promise. Your job is to **improve** it based on PA's analysis, NOT start from scratch.

---

## Parent Experiment Summary

| Field | Value |
|-------|-------|
| Original Experiment ID | {{ORIGINAL_EXP_ID}} |
| Strategy | {{ORIGINAL_STRATEGY}} |
| Previous Score | {{PARENT_SCORE}} |
| Potential Ceiling | {{POTENTIAL_CEILING}} |
| Competition | {{COMPETITION_NAME}} |
| Metric | {{EVALUATION_METRIC}} |

### Why This Experiment is Continuing

{{REASONING}}

---

## PA's Improvement Instructions (MANDATORY)

**You MUST implement these improvements:**

{{IMPROVEMENT_INSTRUCTIONS}}

---

## Your Task

### Step 1: Review Existing Work
- Examine the code files in this worktree
- Understand what was implemented previously
- Note what worked well and what didn't

### Step 2: Implement Improvements
- Follow PA's improvement instructions above
- Make targeted changes, not wholesale rewrites
- Keep the same validation scheme for score comparability

### Step 3: Validate Changes
- Run the updated model with cross-validation
- Compare new score to previous score ({{PARENT_SCORE}})
- Ensure the implementation is complete and correct

### Step 4: Document Changes
- Log what you changed and why in your output
- Include before/after comparison
- Note any unexpected findings

---

## Implementation Guidelines

### DO:
- Build on existing code
- Make incremental improvements
- Keep the same CV folds for comparability
- Follow PA's specific instructions
- Document your changes clearly

### DO NOT:
- Start from scratch
- Change the fundamental approach without reason
- Use a different CV scheme
- Ignore PA's improvement instructions
- Make changes beyond what's necessary

---

## Expected Outputs

All outputs should use the CONTINUATION ID: `{{CONTINUATION_ID}}`

1. **Results JSON:** `result_{{CONTINUATION_ID}}.json`
   ```json
   {
     "score": <new_validation_score>,
     "parent_score": {{PARENT_SCORE}},
     "improvement": <score_difference>,
     "changes_made": ["list", "of", "changes"],
     "runtime_seconds": <execution_time>
   }
   ```

2. **Submission CSV:** `submission_{{CONTINUATION_ID}}.csv`
   - Must be in competition format
   - Generated from the improved model

3. **Log File:** `waa_{{CONTINUATION_ID}}.log`
   - Document all changes made
   - Include reasoning for each change
   - Note any issues encountered

4. **Completion Marker:** `DONE_{{CONTINUATION_ID}}`
   - Create this file only when ALL outputs are ready

---

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Score Improvement | > {{PARENT_SCORE}} |
| PA Instructions | All implemented |
| Documentation | Changes clearly logged |
| Output Files | All present and valid |
| Comparability | Same CV scheme used |

---

## Common Pitfalls to Avoid

1. **Temptation to Rewrite:** Don't throw away working code. Make targeted improvements.

2. **Changing CV Scheme:** Keep the same validation setup so scores are comparable.

3. **Ignoring PA Instructions:** PA's analysis is based on experiment results. Follow its guidance.

4. **Over-Engineering:** Implement what's asked, not more. Save new ideas for new experiments.

5. **Missing Documentation:** Future iterations depend on understanding what changed.

---

**Remember:** This experiment was continued because it showed promise. Your job is to unlock that potential through targeted improvements, not to reinvent the wheel.
