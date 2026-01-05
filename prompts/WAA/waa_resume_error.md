# AutoKaggle Resume (Background Run Error)

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
1) Diagnose the failure using logs and artifacts.
2) Update `experiment-status.yaml` with:
   - status: ERROR
   - message: clear description of the error
   - error_type and recovery_suggestion
3) Create `DONE_{{EXPERIMENT_ID}}` with "FAILURE: <reason>".

IMPORTANT: Exit immediately after completing the above.
