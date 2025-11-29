## CRITICAL: Python Environment Requirements

**YOU MUST FOLLOW THESE INSTRUCTIONS EXACTLY:**

1. **Use the current virtual environment** - DO NOT create a new virtual environment
2. **Install packages with `uv add <package-name>`** - NEVER use `pip install`
3. **Run scripts with `uv run xxx.py`** - NEVER use `python xxx.py`

Examples:
- To install a package: `uv add torch`
- To run a script: `uv run train.py`
- To run with arguments: `uv run train.py --epochs 10`

**VIOLATION OF THESE RULES WILL CAUSE EXPERIMENT FAILURE.**

{gpu_allocation_section}

## CRITICAL: Experiment Status Management

You MUST maintain `experiment-status.yaml` to communicate your progress. This file allows the system to track long-running training jobs and automatically resume your session when training completes. Status updates are mandatory and must be written with real ISO timestamps (no placeholders or shell literals).

### Status Values

| Status | When to Use | Action After Setting |
|--------|-------------|---------------------|
| **IDLE** | Default. Short operations (<10 min): data loading, preprocessing, quick inference | Continue working normally |
| **RUNNING** | Long operations (>10 min): model training, large inference, hyperparameter search | **EXIT IMMEDIATELY** |
| **COMPLETE** | ALL work done successfully, all outputs saved | **EXIT IMMEDIATELY** |
| **ERROR** | Unrecoverable error, human intervention needed | **EXIT IMMEDIATELY** |

### How to Update Status

Append to `experiment-status.yaml` using YAML format. Use a real timestamp (example below uses `date` to generate ISO time):

```bash
timestamp=$(date --iso-8601=seconds)
cat >> experiment-status.yaml <<EOF
  - timestamp: "$timestamp"
    status: RUNNING
    message: "Starting long training"
EOF
```

### CRITICAL RULES

1. **IDLE is the default**: Keep this status for short operations. You can work normally.

2. **Before long training (>10 minutes)**:
   - Set status to RUNNING with a descriptive message (use the command pattern above)
   - Start training in the background using `nohup`
   - **EXIT THE SESSION IMMEDIATELY** - do NOT wait for training

3. **After setting RUNNING**: You MUST exit. The system monitors GPU/CPU utilization and will automatically resume your session when training appears complete (utilization drops and no model files are being written).

4. **COMPLETE can only be used once**: Only set this when ALL of the following are ready:
   - `result_{exp_id}.json` with validation score
   - `submission_{exp_id}.csv` with predictions
   - `DONE_{exp_id}` completion marker
   - Update `experiment-status.yaml` with status COMPLETE and the validation score message using a real timestamp:

```bash
timestamp=$(date --iso-8601=seconds)
cat >> experiment-status.yaml <<EOF
  - timestamp: "$timestamp"
    status: COMPLETE
    message: "Training complete. Validation score: <PUT SCORE HERE>"
    output_files:
      - "result_{exp_id}.json"
      - "submission_{exp_id}.csv"
      - "DONE_{exp_id}"
EOF
```

5. **ERROR must explain the problem**: Include what went wrong and potential solutions.

### Example: Long Training Workflow

```bash
# 1. Analyze data and prepare features (IDLE status is fine)
uv run prepare_features.py

# 2. Before starting long training, update status
cat >> experiment-status.yaml << 'EOF'
  - timestamp: "2024-01-15T10:30:00"
    status: RUNNING
    message: "Starting XGBoost training with 500 trees, expected ~2 hours"
EOF

# 3. Start training in background so it continues after session ends
nohup uv run train.py > training.log 2>&1 &

# 4. EXIT NOW - do not wait for training to complete!
# The system will automatically resume when training finishes.
```

### Example: Quick Operations (No Status Change Needed)

```bash
# These are fast operations - just keep IDLE status and work normally
uv run load_data.py           # Data loading - usually < 1 min
uv run feature_engineering.py  # Feature prep - usually < 5 min
uv run quick_inference.py      # Small model inference - usually < 2 min
```

### Example: Session Resume (After Training Completes)

When the system detects training is complete (low GPU/CPU utilization, no file writes), it will resume your session. You should then:

```bash
# 1. Check if training was successful
if [ -f "model.pkl" ] && [ -f "training.log" ]; then
    # Check log for completion
    tail -20 training.log

    # 2. Run inference and create submission
    uv run inference.py

    # 3. Update status to COMPLETE
    cat >> experiment-status.yaml << 'EOF'
  - timestamp: "2025-01-15T12:45:00"
    status: COMPLETE
    message: "Training complete. Validation score: 0.8532"
EOF

    # 4. Create completion marker
    echo "SUCCESS" > DONE_{exp_id}
else
    # Training failed
    cat >> experiment-status.yaml << 'EOF'
  - timestamp: "2025-01-15T12:45:00"
    status: ERROR
    message: "Training failed - model file not created"
    error_type: "TRAINING_FAILURE"
    recovery_suggestion: "Check training.log for errors, possibly reduce model complexity"
EOF

    echo "FAILURE" > DONE_{exp_id}
fi
```

### Status File Format Reference

```yaml
experiment_id: "iter0_exp1_abc123"
created_at: "2025-01-15T10:00:00"
statuses:
  - timestamp: "2025-01-15T10:00:00"
    status: IDLE
    message: "Initial state"

  - timestamp: "2025-01-15T10:30:00"
    status: RUNNING
    message: "Starting XGBoost training"
    expected_duration_minutes: 120

  - timestamp: "2025-01-15T12:45:00"
    status: COMPLETE
    message: "Training complete. Score: 0.8532"
    output_files:
      - "model.pkl"
      - "submission.csv"
```

**REMEMBER**: Setting RUNNING or COMPLETE means you MUST exit the session immediately!

---

{task_content}

## Outputs & Files (MANDATORY)

- `result_{exp_id}.json` with a top-level `score` field (float) representing the primary CV metric, plus any detailed metrics.
- `submission_{exp_id}.csv` (exact name) with predictions in competition format.
- Log key steps to root-level `waa_{exp_id}.log` (copy here if generated elsewhere).
- Update `experiment-status.yaml` with RUNNING/COMPLETE entries (real ISO timestamps) and then create `DONE_{exp_id}` once all outputs are ready.
