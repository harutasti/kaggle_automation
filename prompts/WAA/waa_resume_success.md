# AutoKaggle Resume (Background Training Completed)

Experiment ID: {{EXPERIMENT_ID}}
Worktree: {{WORKTREE_PATH}}
Exit Code: {{EXIT_CODE}}

Background process summary:
{{BACKGROUND_PROCESSES}}

Training Log (last 10KB):
```
{{TRAINING_LOG_TAIL}}
```

Your Task:
1) Verify that training finished successfully (check logs, model artifacts, metrics).
2) If training succeeded:
   - Create `result_{{EXPERIMENT_ID}}.json` with the score
   - Create `submission_{{EXPERIMENT_ID}}.csv` in competition format
   - Update `experiment-status.yaml` with COMPLETE and the score
   - Create `DONE_{{EXPERIMENT_ID}}` with "SUCCESS"
3) If training failed unexpectedly:
   - Update `experiment-status.yaml` with ERROR details
   - Create `DONE_{{EXPERIMENT_ID}}` with "FAILURE: <reason>"

IMPORTANT: Exit immediately after completing the above.
