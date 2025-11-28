# Codex Integration Guide

> NOTE: References to `execution_mode`/`execution_modes` in this guide are legacy. The current code uses a single `simulation_mode` flag (True = simulator, False = Codex) for all components.

This guide explains how to use the new Codex integration for AutoKaggler.

## Overview

The Codex integration allows AutoKaggler to use real AI agents (via Anthropic's Codex CLI) instead of the simulation mode. This enables actual ML experiments on Kaggle competitions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         MCDU (Main Loop)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              KSE (Knowledge Strategy Engine)                 │
│  Generates: experiments/hypotheses/{exp_id}_task.md          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│           EO (Experiment Orchestrator)                       │
│  Creates: Git worktrees for isolated execution               │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
        Simulation Mode          Codex Mode (NEW!)
                │                       │
                ▼                       ▼
    ┌───────────────────┐   ┌──────────────────────┐
    │ wca_simulator.py  │   │ codex_launcher.py    │
    │  (Mock Results)   │   │   ↓                  │
    └───────────────────┘   │ codex_executor.py    │
                            │   ↓                  │
                            │ codex exec           │
                            │  (Real AI)           │
                            └──────────────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │  Result Files:        │
                        │  - result_{id}.json   │
                        │  - DONE_{id}          │
                        │  - submission_{id}.csv│
                        └───────────────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │  RAD (Result Agg.)    │
                        │  Collects & stores    │
                        └───────────────────────┘
```

## Components

### 1. `src/utils/codex_executor.py`

**Purpose**: Core execution engine for Codex.

**Key Functions**:
- `execute_codex_experiment()` - Single experiment execution
- `execute_with_retry()` - Execution with automatic retry logic
- `CodexResult` - Structured result dataclass

**What it does**:
1. Reads task markdown file
2. Calls `codex exec` with stdin input
3. Saves output to `codex_output_{exp_id}.md`
4. Parses result files (result_*.json, DONE_*)
5. Returns structured CodexResult

**Usage**:
```python
from src.utils.codex_executor import execute_codex_experiment

result = execute_codex_experiment(
    task_markdown_path="experiments/hypotheses/iter0_exp1_task.md",
    worktree_path="experiments/worktrees/iter0_exp1",
    experiment_id="iter0_exp1",
    timeout=3600
)

if result.success:
    print(f"Score: {result.result_data['score']}")
else:
    print(f"Error: {result.error}")
```

### 2. `src/execution/codex_launcher.py`

**Purpose**: Integration layer between EO and Codex executor.

**Key Class**: `CodexExperimentLauncher`

**What it does**:
1. Validates Codex CLI is available
2. Manages experiment launches
3. Converts results to format expected by RAD
4. Handles batch execution (future: parallel)

**Usage**:
```python
from src.execution.codex_launcher import CodexExperimentLauncher

launcher = CodexExperimentLauncher(config)

result = launcher.launch_experiment(
    hypothesis=experiment_hypothesis,
    worktree_path=worktree_path
)
```

### 3. Configuration

**File**: `config/config_codex.json`

**Key Settings**:
```json
{
  "simulation_mode": false,        // Disable simulator
  "wca_per_iteration": 1,         // Start with 1 agent
  "max_iterations": 2,            // Start with 2 iterations

  "codex": {
    "enabled": true,
    "timeout": 3600,               // 1 hour per experiment
    "max_retries": 2,              // Retry failed experiments
    "track_usage": true            // Track execution stats
  }
}
```

## Installation

### Prerequisites

1. **Install Codex CLI**:
   ```bash
   # Install Codex (follow official instructions)
   # Ensure it's in your PATH
   which codex  # Should show path to codex binary
   ```

2. **Set API Key** (if required):
   ```bash
   export ANTHROPIC_API_KEY="your-api-key"
   ```

3. **Verify Installation**:
   ```bash
   codex --version
   ```

## Testing

### Step 1: Run Integration Test

```bash
# Test Codex integration in isolation
uv run python test_codex_integration.py
```

**Expected Output**:
```
==============================================================
Codex Integration Test
==============================================================

✓ Created test task: /tmp/codex_test_xyz/test_exp_simple_task.md

==============================================================
TEST 1: Basic Execution
==============================================================

Result:
  Success: True
  Execution Time: 12.34s
  Score: 0.85

✓ TEST 1 PASSED - Codex executed successfully!

==============================================================
ALL TESTS PASSED!
==============================================================
```

### Step 2: Test with Single Experiment

```bash
# Copy Codex config
cp config/config_codex.json config/config.json

# Run AutoKaggler
uv run python main.py
```

**Monitor**:
```bash
# Watch logs in real-time
tail -f logs/auto_kaggle.log

# Check experiment outputs
ls -la experiments/worktrees/*/codex_output_*.md
ls -la experiments/worktrees/*/result_*.json
```

### Step 3: Verify Results

```bash
# Check results database
cat experiments/results/manifest.json | jq '.experiments[] | select(.status=="SUCCESS")'

# View analysis
cat experiments/analysis/analysis_iter_0.md
```

## Usage

### Basic Usage

1. **Configure for Codex**:
   ```bash
   cp config/config_codex.json config/config.json
   ```

2. **Run**:
   ```bash
   uv run python main.py
   ```

3. **Monitor Progress**:
   - Logs: `logs/auto_kaggle.log`
   - Codex outputs: `experiments/worktrees/*/codex_output_*.md`
   - Results: `experiments/results/*/result_*.json`

### Testing Different Competitions

Edit `config/config.json`:

```json
{
  "kaggle_competition_name": "titanic",  // or "house-prices-advanced-regression-techniques"
  "wca_per_iteration": 1,
  "max_iterations": 2
}
```

**Recommended test competitions**:
1. **titanic** - Binary classification, small dataset
2. **house-prices-advanced-regression-techniques** - Regression, clean data
3. **digit-recognizer** - Image classification (MNIST)

### Scaling Up

Once validated with 1 agent:

```json
{
  "wca_per_iteration": 3,     // Increase to 3 parallel agents
  "max_iterations": 5,        // Run more iterations
  "codex": {
    "timeout": 7200           // Increase timeout if needed
  }
}
```

## Troubleshooting

### Codex Not Found

**Error**: `Codex CLI not found. Please install it first.`

**Solution**:
```bash
# Verify installation
which codex

# Add to PATH if needed
export PATH="/path/to/codex:$PATH"
```

### Timeout Errors

**Error**: `Execution timed out after 3600s`

**Solutions**:
1. Increase timeout in config:
   ```json
   {"codex": {"timeout": 7200}}
   ```

2. Use simpler competition (smaller dataset)

3. Simplify strategy (less feature engineering)

### Missing Result Files

**Error**: `Result file not created`

**Check**:
1. Codex output: `cat experiments/worktrees/*/codex_output_*.md`
2. Look for errors in output
3. Verify task markdown is clear

**Common causes**:
- Task instructions unclear
- Data files not found
- Model training failed
- Insufficient time (timeout)

### Incomplete Experiments

**Error**: `Experiment did not complete (DONE file not created)`

**Check**:
- Codex may have partially completed
- Look for error messages in output
- Verify all required files exist in worktree

## Cost Management

### Token Usage Tracking

Codex tracks usage in: `experiments/codex_usage.json`

```json
{
  "total_experiments": 15,
  "total_time": 5432.1,
  "average_time": 362.1,
  "successes": 12,
  "failures": 3
}
```

### Budget Control

**Recommendations**:
1. Start small: 1 agent, 2 iterations
2. Use simple competitions (Titanic)
3. Set aggressive timeouts initially
4. Monitor usage after each run
5. Scale up gradually

**Estimated costs** (rough):
- 1 experiment: ~5-15 minutes, varies by complexity
- Simple competition (Titanic): Fast, low cost
- Complex competition (images): Slow, high cost

## Switching Between Modes

### Simulation Mode (No Cost)

```json
{
  "simulation_mode": true
}
```

### Codex Mode (Real AI)

```json
{
  "simulation_mode": false,
  "codex": {"enabled": true}
}
```

## Integration with EO

To integrate with Experiment Orchestrator:

```python
# src/execution/eo.py

def _launch_experiment(self, hypothesis):
    if not self.config.get("simulation_mode", False):
        return self._launch_with_codex(hypothesis)
    else:
        return self._launch_with_simulator(hypothesis)

def _launch_with_codex(self, hypothesis):
    from .codex_launcher import CodexExperimentLauncher

    launcher = CodexExperimentLauncher(self.config)
    worktree_path = self._get_worktree_path(hypothesis.experiment_id)

    result = launcher.launch_experiment(hypothesis, worktree_path)

    return {
        "experiment_id": hypothesis.experiment_id,
        "status": "SUCCESS" if result.success else "FAILURE",
        "score": result.result_data.get("score") if result.success else None
    }
```

## Output Files

For each experiment, Codex creates:

1. **codex_output_{exp_id}.md**
   - Raw output from Codex execution
   - Includes all tool calls, reasoning, code
   - Useful for debugging

2. **result_{exp_id}.json**
   - Required format: `{"score": <value>}`
   - Optional: Additional metrics, metadata
   - Created by Codex based on task instructions

3. **DONE_{exp_id}**
   - Empty completion signal file
   - Indicates experiment finished successfully

4. **submission_{exp_id}.csv**
   - Competition submission format
   - Predictions for test set
   - Optional but recommended

## Best Practices

1. **Start Small**: 1 agent, 2 iterations, simple competition
2. **Monitor First Run**: Watch logs and outputs closely
3. **Verify Results**: Check that scores make sense
4. **Iterate**: Gradually increase complexity
5. **Track Costs**: Monitor execution times and adjust timeouts
6. **Use Simulation First**: Test workflow logic without cost
7. **Clear Instructions**: Make task markdown as clear as possible
8. **Handle Failures**: Expect ~20% failure rate initially

## Next Steps

After successful integration:

1. **Add Parallel Execution**: Implement true parallel launches
2. **Better Monitoring**: Real-time progress tracking
3. **Cost Estimation**: Pre-flight cost estimates
4. **Session Management**: Reuse context across experiments
5. **Tool Restrictions**: Fine-grained control over Codex tools
6. **Result Validation**: Automatic sanity checks on outputs

## Support

For issues:
1. Check `logs/auto_kaggle.log`
2. Review Codex output files
3. Run `test_codex_integration.py`
4. Verify Codex CLI works standalone
5. Check configuration syntax

## Example End-to-End Flow

```bash
# 1. Install and verify Codex
which codex

# 2. Run integration test
uv run python test_codex_integration.py

# 3. Configure for Codex
cp config/config_codex.json config/config.json

# 4. Run AutoKaggler
uv run python main.py

# 5. Monitor progress
tail -f logs/auto_kaggle.log

# 6. Check results
cat experiments/results/manifest.json | jq '.experiments[] | select(.status=="SUCCESS")'

# 7. Review analysis
cat experiments/analysis/analysis_iter_0.md
```

Success! You now have real AI agents competing in Kaggle competitions!
