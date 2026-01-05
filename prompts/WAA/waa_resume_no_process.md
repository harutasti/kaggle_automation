# AutoKaggle Resume (No Background Process Found)

Experiment ID: {{EXPERIMENT_ID}}
Worktree: {{WORKTREE_PATH}}
Exit Code: {{EXIT_CODE}}

Run Log (last 10KB):
```
{{TRAINING_LOG_TAIL}}
```

Your Task:
1) Determine the actual state of the run (check logs, artifacts, status file).
2) If the run already finished:
   - Create `result_{{EXPERIMENT_ID}}.json` with the score
   - Create `submission_{{EXPERIMENT_ID}}.csv`
   - Validate the submission with official constraints (use `src/tools/validate_submission.py` if available)
   - If validation fails, mark FAILURE instead of SUCCESS and record the reason
   - Update `experiment-status.yaml` with COMPLETE and the score
   - Create `DONE_{{EXPERIMENT_ID}}` with "SUCCESS"
3) If nothing ran or it failed:
   - Update `experiment-status.yaml` with ERROR details
   - Create `DONE_{{EXPERIMENT_ID}}` with "FAILURE: <reason>"

IMPORTANT: Exit immediately after completing the above.
