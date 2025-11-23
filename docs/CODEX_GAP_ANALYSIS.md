# Codex Integration Gap Analysis (KSE / WAA / PA)

## Target Workflow (per iteration)
- **KSE (once)**: AI (Codex) deeply reasons over crawl4ai data + prior results; generates multiple idea markdowns describing approach and rationale.
- **WAA (1–N in parallel)**: For each KSE markdown, create a worktree, drop the markdown inside, invoke Codex to execute the experiment (never submit).
- **PA (once)**: AI reads all WAA outputs/scores, performs thorough analysis, and feeds insights to the next KSE iteration.
- **Programmatic only**: Everything else (orchestration, submissions) runs without AI.
- **Logging**: All KSE/WAA/PA outputs saved as MD for humans and AIs.

## Current State (repo review)
- Execution modes: `simulation` (wca_simulator) or `codex` (Codex executor) controlled via `execution_mode` in config.
- KSE (`src/core/kse.py`): Generates random strategies/params; optionally pulls discussion strategies via crawler parser; writes a single task markdown per hypothesis; no Codex/AI invocation.
- WAA:
  - Simulator: `src/execution/wca_simulator.py` (now WAA) produces dummy results/logs (plain text, not MD).
  - Codex path: `src/execution/codex_launcher.py` + `src/utils/codex_executor.py` can run Codex for experiments; tasks come from KSE markdown; no guard against Kaggle submission inside Codex; output files are result JSON, DONE marker, submission CSV, log.
- PA (`src/analysis/pa.py`): Pure Python heuristic summary; no Codex/AI; writes summary markdown from code (not AI-authored).
- Orchestration (`src/execution/eo.py`, `src/core/mcdu.py`): Runs experiments per iteration; no Codex usage for KSE/PA; no per-idea MD storage beyond KSE task files; no AI log collation.
- Crawler use: `KIM` can parse competition info and discussions; outputs not plumbed into Codex for KSE/PA.
- Logging: Mix of text logs; no standardized MD logs for KSE/WAA/PA; WAA log filename `waa_{exp_id}.log` (not MD).

## Gaps vs. Target
- **KSE AI missing**: No Codex call for idea generation; ideas not iterative beyond random strategies; no rationale per idea; no idea markdown library.
- **PA AI missing**: No Codex-based deep analysis of WAA outputs/scores/logs; current PA is heuristic and shallow.
- **WAA mapping**: No automatic per-idea worktree creation tied to KSE idea markdowns; WAA task markdowns not derived from AI idea files; submission prevention not enforced in Codex prompts.
- **Data inputs to AIs**: Crawl4ai outputs, WAA logs/scores, PA summaries are not packaged and fed into KSE/PA prompts.
- **Logging format**: No MD logs for KSE/WAA/PA; existing logs are plain text or JSON; not centralized for human/AI review.
- **Iteration flow**: KSE/PA Codex calls not wired into the main loop; only WAA Codex execution is supported.
- **Result surfacing**: No structured handoff of PA insights to KSE; no storage of AI outputs for reuse next iteration.
- **Safety/controls**: No guardrails in Codex tasks to forbid Kaggle submissions; no separation between code generation and submission steps.
- **Config knobs**: No dedicated config for KSE/PA Codex settings, idea counts, or log paths; only WAA Codex config exists.
- **Metrics tracking**: WAA outputs are not normalized into a corpus PA can consume (e.g., consolidated MD with scores, errors, features tried).

## Suggested Next Steps (order of implementation)
1) Add KSE Codex pipeline: prompt template + idea MD generation + storage path + config toggles.  
2) Wire EO/MCDU to spawn WAAs per idea MD and drop each MD into its worktree.  
3) Add PA Codex pipeline: ingest WAA outputs/logs/scores into a Codex prompt; emit MD analysis per iteration; feed recommendations back to KSE.  
4) Standardize MD logging for KSE/WAA/PA and bundle iteration artifacts for reuse.  
5) Add safety clauses in WAA task templates to prohibit Kaggle submissions; enforce programmatic submission outside Codex.  
6) Extend config for KSE/PA Codex settings (model, timeouts, idea count, log dirs) and enforce programmatic-only steps elsewhere.  
7) Normalize WAA outputs into a summary file PA can consume (scores, params, errors, key logs).
