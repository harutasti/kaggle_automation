import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.utils.codex_executor import (
    execute_kse_hypothesis_generation,
    execute_pa_analysis,
    execute_codex_experiment,
)


def test_prompts_are_saved_for_kse_waa_pa():
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "experiments" / "demo_comp" / "20250101_000000"
        # Create run structure
        hypotheses_iter = run_dir / "hypotheses" / "iter0"
        worktrees_dir = run_dir / "worktrees"
        worktree_exp = worktrees_dir / "iter0_exp1_abc123"
        hypotheses_iter.mkdir(parents=True, exist_ok=True)
        worktree_exp.mkdir(parents=True, exist_ok=True)

        # KSE prompt save (first run)
        kse_result = execute_kse_hypothesis_generation(
            prompt_content="KSE_PROMPT_CONTENT",
            output_dir=hypotheses_iter,
            iteration=0,
            dry_run=True,
            logger=None,
        )
        assert kse_result.success
        kse_saved = run_dir / "prompts" / "KSE" / "iter0" / "iter0_prompt.md"
        assert kse_saved.exists(), "KSE prompt was not saved"
        assert "KSE_PROMPT_CONTENT" in kse_saved.read_text()

        # WAA prompt save
        task_md = worktree_exp / "iter0_exp1_abc123_task.md"
        task_md.write_text("# dummy task", encoding="utf-8")
        waa_result = execute_codex_experiment(
            task_markdown_path=task_md,
            worktree_path=worktree_exp,
            experiment_id="iter0_exp1_abc123",
            dry_run=True,
            logger=None,
        )
        assert waa_result.success
        waa_saved = run_dir / "prompts" / "WAA" / "iter0" / "iter0_exp1_abc123.md"
        assert waa_saved.exists(), "WAA prompt was not saved"
        assert "Your Task:" in waa_saved.read_text()

        # PA prompt save (resume style)
        worktrees_dir.mkdir(parents=True, exist_ok=True)
        pa_result = execute_pa_analysis(
            results_data="PA_PROMPT_CONTENT",
            iteration=1,
            output_dir=worktrees_dir,
            dry_run=True,
            resume_prompt="PA_RESUME_PROMPT",
            run_label="resume",
            logger=None,
        )
        assert pa_result.success
        pa_saved = run_dir / "prompts" / "PA" / "iter1" / "iter1_resume.md"
        assert pa_saved.exists(), "PA prompt was not saved"
        assert "PA_RESUME_PROMPT" in pa_saved.read_text()
