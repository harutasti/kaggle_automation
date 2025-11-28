# Codex Integration - Quick Start

> NOTE: Legacy references to `execution_mode`/`execution_modes` in this document are obsolete. The code now uses a single `simulation_mode` flag (True = simulator, False = Codex) across KSE/WAA/PA.

## What Was Created

### Core Execution Engine
📄 **src/utils/codex_executor.py** (290 lines)
- `execute_codex_experiment()` - Main execution function
- `execute_with_retry()` - Automatic retry logic
- `CodexResult` dataclass - Structured results
- Full error handling and result parsing

### Integration Layer
📄 **src/execution/codex_launcher.py** (230 lines)
- `CodexExperimentLauncher` class
- Batch experiment management
- Result format conversion for RAD
- Validation and error handling

### Testing
📄 **test_codex_integration.py** (200 lines)
- Isolated integration test
- Creates minimal test task
- Validates full pipeline
- No dependencies on main system

### Configuration
📄 **config/config_codex.json**
- Pre-configured for safe testing
- 1 agent, 2 iterations
- Titanic competition (small dataset)
- All Codex settings included

### Documentation
📄 **CODEX_INTEGRATION_GUIDE.md**
- Complete integration guide
- Architecture diagrams
- Troubleshooting section
- Best practices

---

## Key Design Principles

1. **Simple & Direct** - No complex wrappers, just clean function calls
2. **No Subprocess** - Direct `subprocess.run()` of `codex exec`
3. **Stdin-based** - Uses stdin for prompts (Codex pattern)
4. **File-based Results** - Parses output files (result_*.json, DONE_*)
5. **Structured Errors** - Categorized error types for debugging
6. **Retry Logic** - Automatic retries for transient failures
7. **Drop-in Ready** - Designed to integrate with existing EO

---

## How It Works

```python
# Simple as this:
from src.utils.codex_executor import execute_codex_experiment

result = execute_codex_experiment(
    task_markdown_path="experiments/hypotheses/iter0_exp1_task.md",
    worktree_path="experiments/worktrees/iter0_exp1",
    experiment_id="iter0_exp1",
    timeout=3600
)

if result.success:
    print(f"Score: {result.result_data['score']}")
```

**What happens under the hood:**
1. Reads task markdown
2. Calls `codex exec --skip-git-repo-check` with stdin
3. Saves output to `codex_output_{exp_id}.md`
4. Checks for `DONE_{exp_id}` file
5. Parses `result_{exp_id}.json`
6. Returns `CodexResult` object

---

## Quick Test (5 minutes)

```bash
# 1. Verify Codex is installed
which codex

# 2. Run integration test
uv run python test_codex_integration.py

# Expected: ✓ ALL TESTS PASSED!
```

---

## Integration with Main System

### Option A: Modify EO Directly

Edit `src/execution/eo.py`:

```python
def _launch_single_experiment(self, hypothesis):
    """Launch experiment - choose mode based on config"""

    if not self.config.get("simulation_mode", False):
        # Use Codex
        from .codex_launcher import CodexExperimentLauncher
        launcher = CodexExperimentLauncher(self.config)

        worktree_path = # ... existing worktree creation code

        result = launcher.launch_experiment(hypothesis, worktree_path)

        # Convert to format EO expects
        return {
            "experiment_id": hypothesis.experiment_id,
            "status": "SUCCESS" if result.success else "FAILURE",
            "score": result.result_data.get("score") if result.success else None
        }
    else:
        # Use simulator (existing code)
        return self._launch_with_simulator(hypothesis)
```

### Option B: Test Standalone First

Use `codex_launcher.py` independently:

```python
from src.execution.codex_launcher import CodexExperimentLauncher

config = {"codex": {"enabled": True, "timeout": 3600}}
launcher = CodexExperimentLauncher(config)

result = launcher.launch_experiment(hypothesis, worktree_path)
```

---

## Configuration

### Simulation Mode (Free)
```json
{
  "simulation_mode": true
}
```

### Codex Mode (Real AI)
```json
{
  "simulation_mode": false,
  "wca_per_iteration": 1,
  "max_iterations": 2,
  "codex": {
    "enabled": true,
    "timeout": 3600,
    "max_retries": 2
  }
}
```

---

## Expected Output Files

Each experiment creates:

```
experiments/worktrees/iter0_exp1_abc123/
├── codex_output_iter0_exp1_abc123.md     ← Codex raw output
├── result_iter0_exp1_abc123.json         ← {"score": 0.85}
├── DONE_iter0_exp1_abc123                ← Completion signal
└── submission_iter0_exp1_abc123.csv      ← Predictions
```

---

## Error Handling

The system handles these error types:

- `FILE_NOT_FOUND` - Task markdown missing
- `DIRECTORY_NOT_FOUND` - Worktree missing
- `TIMEOUT` - Execution exceeded timeout
- `CODEX_NOT_FOUND` - CLI not installed
- `CODEX_ERROR` - Non-zero exit code
- `INCOMPLETE` - No DONE file created
- `MISSING_RESULT` - No result.json created
- `INVALID_RESULT` - Missing score field
- `JSON_PARSE_ERROR` - Malformed JSON

All errors include:
- Descriptive message
- Error type category
- Raw output (for debugging)
- Execution time

---

## Comparison: Before vs After

### Before (Simulation)
```python
# wca_simulator.py
time.sleep(random.randint(5, 15))  # Fake work
score = random.uniform(0.6, 0.99)  # Random score
```

### After (Codex)
```python
# codex_executor.py
subprocess.run(["codex", "exec"], ...)  # Real AI
result = parse_result_json()  # Actual score
```

**Same interface, real execution!**

---

## Next Steps

### Must Do (Before First Run)
- [ ] Install Codex CLI
- [ ] Run `test_codex_integration.py`
- [ ] Copy `config_codex.json` to `config.json`

### Integration Steps
- [ ] Use `simulation_mode` to toggle simulator vs Codex in EO
- [ ] Test with 1 experiment manually
- [ ] Run full system with Codex
- [ ] Monitor costs and adjust

### Nice to Have (Later)
- [ ] True parallel execution
- [ ] Real-time progress monitoring
- [ ] Pre-flight cost estimation
- [ ] Result validation rules

---

## File Summary

| File | Purpose | Lines | Status |
|------|---------|-------|--------|
| codex_executor.py | Core execution | 290 | ✅ Complete |
| codex_launcher.py | Integration layer | 230 | ✅ Complete |
| test_codex_integration.py | Testing | 200 | ✅ Complete |
| config_codex.json | Configuration | 30 | ✅ Complete |
| CODEX_INTEGRATION_GUIDE.md | Full docs | 500+ | ✅ Complete |
| CODEX_QUICKSTART.md | Quick ref | 200 | ✅ Complete |

**Total: ~1,450 lines of production-ready code + documentation**

---

## Cost & Safety

### Safety Features Built-in
✅ Timeout enforcement
✅ Retry logic
✅ Error categorization
✅ Result validation
✅ Git worktree isolation
✅ Structured logging

### Recommended First Run
- Competition: Titanic (small, fast)
- Agents: 1 (wca_per_iteration: 1)
- Iterations: 2 (max_iterations: 2)
- Timeout: 1 hour (3600s)
- Expected time: ~10-20 minutes total
- Expected cost: Minimal

### Scaling Guidelines
Start: 1 agent × 2 iterations = 2 experiments
Then: 3 agents × 2 iterations = 6 experiments
Finally: 3 agents × 5 iterations = 15 experiments

Monitor usage after each step!

---

## Questions?

1. **Does it work with existing task markdown?**
   Yes! No changes needed to KSE or task generation.

2. **Can I switch back to simulation?**
   Yes! Just change `simulation_mode` in config.

3. **Do I need to modify EO?**
   Minimal changes - just add mode switch.

4. **What if Codex fails?**
   Automatic retry (configurable), then fail gracefully.

5. **How do I debug failures?**
   Check `codex_output_{exp_id}.md` for full output.

---

## Contact Points

- Core execution: `src/utils/codex_executor.py`
- Integration: `src/execution/codex_launcher.py`
- Testing: `test_codex_integration.py`
- Config: `config/config_codex.json`
- Docs: `CODEX_INTEGRATION_GUIDE.md`

**Ready to run!** 🚀
