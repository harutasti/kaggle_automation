# AutoKaggle Resume (Background Run Completed)

Experiment ID: {{EXPERIMENT_ID}}
Worktree: {{WORKTREE_PATH}}
Exit Code: {{EXIT_CODE}}

Background process summary:
{{BACKGROUND_PROCESSES}}

Run Log (last 10KB):
```
{{TRAINING_LOG_TAIL}}
```

Your Task:
1) Verify that the run finished successfully (check logs, artifacts, metrics).
2) If the run succeeded:
   - Create `result_{{EXPERIMENT_ID}}.json` with the score
   - Create `submission_{{EXPERIMENT_ID}}.csv` in competition format
   - Validate the submission with official constraints (use `src/tools/validate_submission.py` if available)
   - If validation fails, mark FAILURE instead of SUCCESS and record the reason
   - Update `experiment-status.yaml` with COMPLETE and the score
   - Create `DONE_{{EXPERIMENT_ID}}` with "SUCCESS"
3) If the run failed unexpectedly:
   - Update `experiment-status.yaml` with ERROR details
   - Create `DONE_{{EXPERIMENT_ID}}` with "FAILURE: <reason>"

IMPORTANT: Exit immediately after completing the above.
