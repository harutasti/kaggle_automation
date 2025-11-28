# AutoKaggle Pipeline Inputs & Outputs (Verified from Code)

This document enumerates the inputs and outputs for each major step, citing the current code paths. No assumptions beyond the observed code are included.

## Entry: `main.py`
- **Inputs**: CLI flags `--config`, `--skip-confirmations` (`main.py` lines 18-38). Config JSON loaded from `config_file` (lines 39-47).
- **Outputs**:
  - Enriched `config` with `system_specs`, `skip_confirmations`, `experiment_run_dir`, `timestamp` (lines 49-81).
  - Directories created at start: `experiment_run_dir/{worktrees,results,hypotheses,analysis,kaggle_data,codex-responses/{KSE,WAA,PA}}` (`main.py` lines 83-95).
  - Instantiates `MasterControllerDecisionUnit` and calls `run_main_loop` (lines 95-104).

## Orchestration: `MasterControllerDecisionUnit.run_main_loop`
- **Inputs**:
  - Config including `kaggle_competition_name`, `max_iterations`, `wca_per_iteration`, stop conditions (`src/core/mcdu.py` lines 12-35).
  - User confirmation handler (`UserConfirmation`).
- **Outputs**:
  1) **Fetch competition info**: calls `KIM.get_competition_info()`; on success prints `Successfully fetched competition info for {competition_name}` (`mcdu.py` lines 62-81).
  2) **Download data**: `KIM.download_data_files(...)` (`mcdu.py` lines 83-88).
  3) **Pass dataset analysis**: `self.kse.set_dataset_analysis(...)` if available (`mcdu.py` lines 90-96).
 4) **Copy data for KSE**: `experiment_run_dir/kaggle_data` → `hypotheses/kaggle_data`; crawler output `kaggle_competitions/{competition}` → `hypotheses/crawler_data` (`mcdu.py` lines 98-110).
  5) Iterative loop calls:
     - `_generate_hypotheses_for_iteration()` → KSE (`mcdu.py` lines 123-133).
     - `eo.launch_experiments(...)` → returns launched map (`mcdu.py` lines 135-140).
     - `eo.check_running_experiments()` until completion (`mcdu.py` lines 142-156).
     - `rad.collect_result(...)` per finished experiment, then `rad.update_result_metadata(...)` (`mcdu.py` lines 146-155).
     - `pa.analyze_results(...)` (`mcdu.py` line 158).
     - `_update_overall_best(...)` (`mcdu.py` lines 160-183).
     - Cleanup via `eo.cleanup_worktree(...)` (`mcdu.py` lines 148-154, 200-211).
  6) **Final report** logs best score and optionally submits via `KIM.submit_predictions(...)` (`mcdu.py` lines 213-247).

## Competition Interface: `KaggleInterfaceManager`
- **Inputs**:
  - `kaggle_competition_name`, `experiment_run_dir`, `use_crawler`, `simulation_mode`, `analyze_dataset` (`src/core/kim.py` lines 16-48).
  - Kaggle credentials (required unless `simulation_mode` is true) (`kim.py` lines 34-48).
- **Outputs**:
  - `get_competition_info` returns `CompetitionInfo` with name, evaluation_metric, deadline, description_markdown, data_files (simulation mode returns placeholders) (`kim.py` lines 77-147).
  - `download_data_files` populates `experiment_run_dir/kaggle_data` with either crawler copies, Kaggle API downloads, or placeholder CSVs in simulation mode; updates `competition_info.data_files`; triggers dataset analysis if enabled (`kim.py` lines 155-236).
  - `get_dataset_analysis_placeholders` produces dataset stats for prompts via `DatasetAnalyzer` (not shown here but invoked at `kim.py` lines 196-198).
  - `submit_predictions` and `get_submission_score` provide submission/score handling; in simulation/dry-run they log and skip real API calls (`kim.py` lines 200-273, 275-297).

## Hypothesis Generation: `KnowledgeStrategyEngine`
- **Inputs**:
  - `CompetitionInfo`, `num_hypotheses`, optional `AnalysisResult`, prior `ExperimentResult`s; config for `simulation_mode`, prompts dir, `wca_per_iteration`, GPU allocator settings (`src/core/kse.py` lines 18-49).
  - Discussion strategies from crawler via `parse_discussion_strategies` (`kse.py` lines 88-115).
  - Dataset analysis placeholders set by `set_dataset_analysis` (`kse.py` lines 30-43).
- **Outputs**:
  - **Codex-enabled path** (`kse.py` `_generate_hypotheses_with_codex` and helpers, used when `simulation_mode` is false):
    - Creates iteration dir `hypotheses/iter{n}`; copies templates from `prompts/KSE` (`kse_codex_prompt.md`, `waa_common_template.md`, `waa_experiment_template.md`) and pre-fills `{{EXPERIMENT_ID}}` per experiment.
    - Builds prompt (fills `<<...>>` tokens with paths/iteration counts), saves `kse_prompt_iter{n}.md`, runs `codex exec --skip-git-repo-check --json` in the iteration dir (`execute_codex` mode KSE). If `{{...}}` placeholders remain, triggers `codex exec --skip-git-repo-check resume --last --json` with a list of missing placeholders.
    - After templates are filled (or dry-run stub fill), merges common + per-experiment templates with `prompts/WAA/waa_task_template.md` and GPU allocation text into `hypotheses/iter{n}/{exp_id}_task.md`.
    - Parses machine-readable block in each experiment template to set `strategy_name` and `parameters` on `ExperimentHypothesis`.
  - **Fallback**: `_generate_programmatic_hypotheses` writes tasks under `hypotheses/iter{n}` using `_generate_task_markdown` with dummy params (also used when Codex is disabled or fails).
  - Outputs: list of `ExperimentHypothesis` with `experiment_id`, `iteration`, `strategy_name`, `parameters`, `task_markdown_path` (pointing to `hypotheses/iter{n}/{exp_id}_task.md`).

## Experiment Orchestration: `ExperimentOrchestrator.launch_experiments`
- **Inputs**:
  - `hypotheses` list; config for `experiment_run_dir`, `simulation_mode`, GPU allocator, `experiment_pyproject_path`, uv lock, etc. (`src/execution/eo.py` lines 20-39, 156-236).
- **Outputs** (simulation vs codex):
  - Creates git worktrees per experiment, copies `kaggle_data`, `pyproject.toml`, `uv.lock`, ensures `uv` is installed, runs `uv sync`, writes `experiment-status.yaml`, saves hypothesis metadata (`eo.py` lines 166-255).
  - In codex mode (`simulation_mode` false): `_launch_codex_experiment` starts `codex exec --json` with task markdown/hardware env; otherwise runs `wca_simulator.py` (`eo.py` lines 262-295).
  - Returns dict of launched/failed IDs (`eo.py` lines 250-273).

### Experiment Execution (WAA simulator)
- **Inputs**: `--worktree-path`, `--task-markdown-path`, `--experiment-id` (`src/execution/wca_simulator.py` lines 135-162).
- **Outputs**: Writes `waa_{exp_id}.log`, `result_{exp_id}.json` with score/timestamps, `submission_{exp_id}.csv`, `model_{exp_id}.pkl`, `DONE_{exp_id}` status, optional `ERROR_{exp_id}.log` (`wca_simulator.py` lines 14-126).

### Codex WAA path
- **Inputs**: Task markdown, worktree path, experiment_id, codex_responses_dir, timeout (`execute_codex_experiment` in `src/utils/codex_executor.py` lines 29-109).
- **Outputs**: Saves Codex stdout to `codex_output_{exp_id}.md` (or JSONL), expects `result_{exp_id}.json`, `DONE_{exp_id}`, `submission_{exp_id}.csv`, `waa_{exp_id}.log`; returns `CodexResult` with parsed score (`codex_executor.py` lines 92-151, 191-270).

## Result Aggregation: `ResultAggregatorDatabase.collect_result`
- **Inputs**: `exp_id`, `worktree_path` (`src/analysis/rad.py` lines 61-155).
- **Outputs**:
  - Reads `DONE_{exp_id}`, `result_{exp_id}.json`, `waa_{exp_id}.log`, optional `ERROR_{exp_id}.log`.
  - Copies log and outputs (`submission_{exp_id}.csv`, `model_{exp_id}.pkl`, other submission/prediction patterns) into `results/{exp_id}/...` (`rad.py` lines 79-134).
  - Creates `ExperimentResult` with iteration/strategy/parameters (updated via `update_result_metadata`), start/end times, score, result_files, log_path, status, error_message; persists `results_manifest.json` (`rad.py` lines 136-188).

## Performance Analysis: `PerformanceAnalyzer.analyze_results`
- **Inputs**: `iteration`, list of `ExperimentResult`s, optional official scores (`src/analysis/pa.py` lines 14-89).
- **Outputs**:
  - Computes best score/experiment, basic stats, recommendations (successful + non-failing strategies), writes markdown report `analysis_iter_{iteration}.md` (`pa.py` lines 29-88).
  - Returns `AnalysisResult` (iteration, summary_markdown, best_score, best_experiment_id, improvement_trend placeholder, recommended_strategies).
  - If `simulation_mode` is false, calls `execute_codex` (mode PA) to produce `analysis_iter{n}.md` and `pa_summary_iter{n}.json` (`pa.py` lines 85-152; `codex_executor.py` lines 571-666).

## Submission/Scoring Hooks
- **Intermediate submissions per iteration**: `MasterControllerDecisionUnit` calls `user_confirm.confirm_iteration_submissions` then `KIM.submit_predictions` and `KIM.get_submission_score` for each successful experiment (`mcdu.py` lines 136-158).
- **Final submission**: `_final_reporting` optionally submits best experiment after confirmation (`mcdu.py` lines 213-247).

## Logging & Status Artifacts
- User confirmations and statuses via `UserConfirmation` (auto-confirmable) (`user_interaction.py`).
- Session tracking via `experiment-status.yaml` managed by `SessionManager` for long runs (`src/execution/session_manager.py`).
- Codex JSONL outputs stored under `experiment_run_dir/codex-responses/{KSE,WAA,PA}` when Codex runs (`codex_executor.py` save blocks).

## Data Flow Summary
1) **Main** loads config/flags → sets run dirs.
2) **KIM** fetches competition info → downloads/analyzes data → dataset placeholders.
3) **KSE** builds prompts → Codex (or fallback) generates hypotheses + task markdown.
4) **EO** prepares worktrees/env → launches WAA (sim or Codex) → produces DONE/result/submission/log/model.
5) **RAD** copies artifacts to results store → builds/persists `ExperimentResult`.
6) **PA** summarizes iteration → `AnalysisResult` → feeds next KSE call.
7) **MCDU** tracks best, submits (simulated in dry-run), cleans up worktrees, stops on thresholds → final report.
