# AutoKaggle (AutoKaggler) — Multi-Agent Kaggle Automation

AutoKaggle is an experiment-orchestration system that **simulates autonomous Kaggle participation** using multiple AI “worker” agents running in parallel, plus an “analysis” agent that decides what to try next.

At a high level it:
1. Fetches competition metadata + data (Kaggle API and/or crawler)
2. Uses an LLM to generate diverse experiment hypotheses (KSE)
3. Executes experiments in isolated **Git worktrees** (WAA/EO)
4. Aggregates artifacts + scores (RAD)
5. Uses an LLM to analyze results and decide **CONTINUE vs TERMINATE** (PA)
6. Iterates until stop conditions are met (MCDU)

> Safety / compliance note: This repo automates submissions and code generation. You are responsible for complying with Kaggle competition rules (including rule acceptance) and for any LLM usage costs.

---

## Current Repository Layout

```
.
├── main.py                      # Entry point (creates timestamped run dir, starts MCDU)
├── config/
│   ├── config.json              # Default run config (titanic)
│   ├── config-house.json        # Example config (house prices)
│   ├── config-space.json        # Example config (spaceship titanic)
│   └── experiment_pyproject.toml# Dependencies for per-experiment worktrees (uv sync)
├── prompts/
│   ├── KSE/                     # Hypothesis generation templates
│   ├── PA/                      # Analysis + evolution decision templates
│   └── WAA/                     # Worker task template (UV rules, status file contract, etc.)
└── src/
    ├── core/                    # MCDU, KIM, KSE
    ├── execution/               # EO, Codex launch/resume, session management
    ├── analysis/                # RAD + PA
    ├── kaggle_crawler/          # crawl_kaggle_competition.py (crawl4ai + Playwright)
    ├── utils/                   # logging, dataset analysis, GPU allocation, parsers, etc.
    └── tests/                   # Standalone test scripts (not a formal test harness)
```

---

## Architecture (Big Picture → Micro)

### Control Flow (MCDU)
`src/core/mcdu.py` (`MasterControllerDecisionUnit`) runs the main loop:

- **Iteration 0**
  - KIM fetches competition info + downloads data
  - KSE generates `wca_per_iteration` hypotheses (task markdown files)
  - EO launches WAAs (one per hypothesis) in separate Git worktrees
  - RAD collects `result_*.json`, `submission_*.csv`, logs, models, JSONL traces
  - (Optional) submit successful experiments to Kaggle for official scores
  - PA analyzes results and produces explicit **evolution decisions**

- **Iteration > 0 (Evolution Mode)**
  - PA decisions decide which experiments **CONTINUE** (reuse the same worktree) vs **TERMINATE** (cleanup + free a slot)
  - KSE generates:
    - Continuation tasks for CONTINUE experiments
    - New hypotheses for freed slots
  - EO launches continuations and new experiments, and the loop repeats

Stop conditions live in config (`max_iterations`, `stop_condition.score_threshold`, `stop_condition.no_improvement_iterations`).

### Components

- **KIM** (`src/core/kim.py`) — Kaggle Interface Manager
  - Reads competition metadata via crawler output first (if enabled), else Kaggle API
  - Downloads competition data (crawler output if present, else Kaggle API)
  - Optionally analyzes datasets for prompt placeholders
  - Submits predictions and polls for official scores

- **KSE** (`src/core/kse.py`) — Knowledge Strategy Engine
  - Uses templates in `prompts/KSE/` to instruct Codex/LLM to generate **diverse** hypotheses
  - Generates WAA task markdown using `prompts/WAA/waa_task_template.md`
  - Injects hardware guidance (GPU allocation) and strict **uv** usage rules into worker tasks

- **EO** (`src/execution/eo.py`) — Experiment Orchestrator
  - Creates one Git worktree per experiment (`git worktree add -b exp/<exp_id> ...`)
  - Copies data + templates into worktrees
  - Copies `config/experiment_pyproject.toml` → `<worktree>/pyproject.toml` and runs `uv sync`
  - Launches either:
    - **Codex mode**: `codex exec --json ...`
    - **Simulation mode**: `src/execution/wca_simulator.py`
  - Monitors completion using DONE files and/or `experiment-status.yaml`, and can trigger `codex resume --last`

- **RAD** (`src/analysis/rad.py`) — Result Aggregator Database
  - Collects artifacts from worktrees into `results/`
  - Maintains `results/results_manifest.json`
  - Extracts a numeric score from multiple common JSON patterns (not only `score`)

- **PA** (`src/analysis/pa.py`) — Performance Analyzer
  - Computes best scores/trends (supports higher-is-better vs lower-is-better)
  - (Optional) uses Codex/LLM to generate deeper analysis and **CONTINUE/TERMINATE** decisions

---

## Prerequisites

- Python `>=3.12` (repo includes `.python-version`)
- Git (required: this system uses Git worktrees)
- `uv` (used both by the controller and by each experiment worktree)
- `tmux` (**required**) — used to open a separate terminal window per Codex/WAA for live JSONL logs
- Kaggle credentials (`kaggle.json`) for real competition data download (required even in `simulation_mode=true`; submissions only happen in real mode)
- Codex CLI (`codex`) in PATH if `simulation_mode=false`
- Playwright browsers if `use_crawler=true` (crawler uses `crawl4ai` + Playwright)

---

## Setup

### 0) Install system dependencies (tmux)

`tmux` is an OS-level package (it is **not** installed via `pyproject.toml` / `uv sync`).

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y tmux
```

macOS (Homebrew):

```bash
brew install tmux
```

### 1) Install controller dependencies

```bash
uv sync
```

### 2) Kaggle credentials (recommended)

Place your `kaggle.json` either:
- at repo root (`./kaggle.json`) — `KIM` will auto-use it, or
- at `~/.kaggle/kaggle.json`

If submissions fail with a 403, you likely need to **accept competition rules** in the Kaggle web UI first.

### 3) Playwright (crawler)

If you use the crawler (`use_crawler=true`), install browsers:

```bash
uv run python -m playwright install chromium
```

You can also run a quick crawler health check:

```bash
uv run crawl4ai-doctor
```

### 4) Preflight checks (automatic)

`main.py` runs a preflight step and will **exit early with a helpful message** if any required tool/credential is missing (e.g., `tmux`, `codex`, `kaggle.json`, Playwright/Chromium, `crawl4ai-doctor`).

---

## Live Codex Logs (Separate tmux windows)

AutoKaggle can stream each WAA’s `codex exec --json` output to a JSONL file and open a **separate tmux window per WAA** to render it live with colors.

Requirements:
- `tmux` installed
- Run AutoKaggle *inside* tmux (so `$TMUX` is set), e.g. `tmux new -s autokaggle`

Enable via config:

```json
{
  "codex_live_view": {
    "enabled": true,
    "backend": "tmux",
    "viewer_timestamps": true,
    "viewer_idle_exit_seconds": 3.0
  }
}
```

Notes:
- The main terminal stays clean: Codex JSONL output is written to `codex_output_<exp_id>.jsonl` in each worktree.
- The tmux window auto-closes after Codex ends (or when the PID ends and the viewer is idle).
- To disable: set `"enabled": false` or `"backend": "none"`.

## Configuration

Configs are JSON files in `config/`. The most important keys:

- `kaggle_competition_name`: Kaggle competition slug (e.g., `titanic`)
- `max_iterations`: max loop iterations
- `wca_per_iteration`: number of parallel worker agents (WAAs)
- `stop_condition`:
  - `score_threshold` (optional)
  - `no_improvement_iterations`
- `simulation_mode`: if `true`, avoids **Codex calls only** and uses the simulator for WAAs; Kaggle API + crawler/data download still run (submissions are disabled)
- `use_crawler`: whether to crawl Kaggle pages/discussions with Playwright
- `experiment_pyproject_path`: per-experiment dependency spec copied into each worktree
- `kaggle_score_wait_timeout_seconds`: how long to poll Kaggle for official scores after submissions
- `kaggle_score_poll_interval_seconds`: polling interval for checking submission scores

Example:

```json
{
  "kaggle_competition_name": "titanic",
  "max_iterations": 3,
  "wca_per_iteration": 3,
  "stop_condition": { "no_improvement_iterations": 2 },
  "simulation_mode": true,
  "use_crawler": true,
  "analyze_dataset": true
}
```

---

## Simulation Mode (Dry-Run) vs Real Mode

`simulation_mode=true` is designed to verify that **everything other than Codex works end-to-end**, including crawling/downloading data, worktrees, `uv sync`, status/resume, RAD aggregation, PA evolution decisions, and archival.

### What’s the same

- **Kaggle API auth + data download** still runs (and fails fast if credentials are missing/invalid)
- **Crawler** still runs when `use_crawler=true` (Playwright required)
- **Git worktrees** are created/reused the same way
- **Per-worktree `uv sync`** still runs (heavy step is intentionally preserved)
- **RAD** still collects outputs into `results/` and updates `results_manifest.json`
- **PA** still writes `analysis/analysis_iter_<n>.md` and produces evolution decisions (CONTINUE/TERMINATE), driving continuation + archival

### What’s different (by component)

- **KIM (KaggleInterfaceManager)**:
  - Real: can submit predictions + poll for official scores
  - Dry-run: **never submits** (and therefore no official-score polling); everything else stays real (crawler/API/download/analysis)
- **MCDU (MasterControllerDecisionUnit)**:
  - Real: can submit successful iterations + optionally submit final best
  - Dry-run: skips all Kaggle submissions (iteration + final); run loop/polling is kept fast so the simulator can progress quickly
- **KSE (KnowledgeStrategyEngine)**:
  - Real: fills KSE templates by invoking Codex
  - Dry-run: fills the same templates locally, intentionally leaving some `{{...}}` placeholders and then doing a “resume fill” pass; writes Codex-like JSONL traces under `codex-responses/KSE/`
- **EO/WAA (ExperimentOrchestrator / Worker Agents)**:
  - Real: launches `codex exec --json ...` and may trigger `codex resume --last`
  - Dry-run: launches `src/execution/wca_simulator.py` inside each worktree (`uv run ...`) and triggers simulator `--resume` when the training marker appears; simulator injects deterministic failures while guaranteeing at least one SUCCESS per iteration
- **PA (PerformanceAnalyzer)**:
  - Real: can use Codex for deeper analysis + decisions
  - Dry-run: generates Codex-like decision text and intentionally fails validation on the first pass so the existing parse/validate/retry loop is exercised; writes Codex-like JSONL traces under `codex-responses/PA/`

---

## Running

```bash
# Default config
uv run python main.py

# Pick a config
uv run python main.py -c config/config-house.json

# Non-interactive (skips confirmation prompts)
uv run python main.py -c config/config.json -y
```

Notes:
- Run from a Git repo root (the program exits if `.git` is missing).
- In real mode (`simulation_mode=false`), WAAs require the `codex` CLI to be installed.
- In simulation mode (`simulation_mode=true`), Kaggle credentials are still required (data download is real), but submissions are disabled.

---

## Output Layout (per run)

Each run writes to a timestamped directory:

`<experiments_base_dir>/<competition>/<YYYYmmdd_HHMMSS>/`

Subdirectories created by `main.py`:

- `worktrees/` — isolated Git worktrees (one per experiment)
- `hypotheses/` — KSE templates, filled hypotheses, and generated WAA task markdown
- `results/` — collected artifacts and `results_manifest.json`
- `analysis/` — PA markdown reports (`analysis_iter_<n>.md`)
- `kaggle_data/` — downloaded competition data for this run
- `codex-responses/` — JSONL output logs for KSE/WAA/PA

`src/utils/codex_executor.py` also persists the *exact prompts used* under:
- `<run_dir>/prompts/KSE/`, `<run_dir>/prompts/WAA/`, `<run_dir>/prompts/PA/`

---

## Crawler (manual)

You can crawl competition pages/discussions explicitly:

```bash
uv run python src/kaggle_crawler/crawl_kaggle_competition.py <competition_slug> --max-discussions 20
```

Crawler output goes to `kaggle_competitions/<competition_slug>/` and is reused by KIM/KSE/EO when present.

---

## Troubleshooting

- **“Not a Git repository”**: run `git init` (and ensure you have at least one commit).
- **Kaggle submission 403 / rules not accepted**: open the competition page and accept rules, then rerun.
- **`codex` not found**: install the Codex CLI or use `simulation_mode=true`.
- **Crawler fails**: ensure Playwright browsers are installed; Kaggle may rate-limit scraping.
- **Disk usage grows fast**: each worktree gets a copy of `kaggle_data/` (large competitions can be heavy).

---

## Where to Look Next

- Main loop + evolution: `src/core/mcdu.py`
- Kaggle integration + dataset analysis: `src/core/kim.py`, `src/utils/dataset_analyzer.py`
- Hypothesis generation + prompt templates: `src/core/kse.py`, `prompts/KSE/`
- Worktree execution + resume: `src/execution/eo.py`, `src/execution/session_manager.py`
- Result aggregation + scoring: `src/analysis/rad.py`
- Analysis + evolution decisions: `src/analysis/pa.py`, `prompts/PA/`
