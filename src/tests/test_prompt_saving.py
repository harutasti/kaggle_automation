import os
import sys
import shutil
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

# Persistent output directory for example prompts
EXAMPLE_PROMPTS_DIR = Path(project_root) / "src" / "tests" / "example_prompts"


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


def test_generate_example_prompts_persistent():
    """
    Generate example prompts to a persistent directory for inspection.

    This test creates realistic example prompts in src/tests/example_prompts/
    so they can be reviewed and used as reference.
    """
    # Clean and create output directory
    if EXAMPLE_PROMPTS_DIR.exists():
        shutil.rmtree(EXAMPLE_PROMPTS_DIR)

    run_dir = EXAMPLE_PROMPTS_DIR / "experiments" / "demo_comp" / "20250101_000000"
    hypotheses_iter = run_dir / "hypotheses" / "iter0"
    worktrees_dir = run_dir / "worktrees"
    worktree_exp = worktrees_dir / "iter0_exp1_abc123"
    hypotheses_iter.mkdir(parents=True, exist_ok=True)
    worktree_exp.mkdir(parents=True, exist_ok=True)

    # KSE prompt with realistic content
    kse_prompt = """# AutoKaggle KSE: Initial Hypothesis Generation

## Competition Context

**Competition Name:** Titanic - Machine Learning from Disaster
**Competition Type:** Binary Classification
**Evaluation Metric:** Accuracy
**Submission Format:** PassengerId, Survived

### Dataset Echo-Back
- Training samples: 891 rows
- Test samples: 418 rows
- Features: 11 (5 numeric, 6 categorical)
- Target variable: Survived with distribution {0: 549, 1: 342}
- Missing data: Age (177), Cabin (687), Embarked (2)
- Class balance: 61.6% died, 38.4% survived

## Research Findings

### Web Search Discoveries
- Winning techniques: Feature engineering on Name (titles), family size groupings
- Recent advances: CatBoost handles categoricals well for this dataset
- Common pitfalls: Overfitting on small dataset, ignoring feature interactions

### Discussion Insights
1. Title extraction from Name is critical (Mr, Mrs, Miss, Master, etc.)
2. Family size (SibSp + Parch + 1) creates meaningful groups
3. Cabin deck letter extraction helps despite missing values
4. Age imputation strategy significantly impacts results

## Diversity Matrix

| Hypothesis | Model Family | Feature Philosophy | Complexity | Unique Element |
|------------|--------------|-------------------|------------|----------------|
| exp_1 | Linear | Minimalist | Simple | Baseline LogReg |
| exp_2 | Gradient Boosting | Domain-Driven | Medium | LightGBM + titles |
| exp_3 | Neural Network | Embedding-Based | Complex | TabNet |

Generate 3 diverse experiment hypotheses following the diversity matrix above.
"""

    kse_result = execute_kse_hypothesis_generation(
        prompt_content=kse_prompt,
        output_dir=hypotheses_iter,
        iteration=0,
        dry_run=True,
        logger=None,
    )
    assert kse_result.success

    # WAA prompt with realistic task
    waa_task = """# Experiment Blueprint for iter0_exp1_abc123

## Machine-Readable Summary
- experiment_id: iter0_exp1_abc123
- strategy_name: LightGBM with Domain Features
- primary_objective: Beat baseline with engineered features
- target_metric: accuracy
- validation_scheme: StratifiedKFold(5)
- expected_outcome: 0.82-0.85 accuracy
- complexity_level: Medium
- model_family: Gradient Boosting

## Hypothesis and Rationale

### Core Hypothesis
LightGBM with domain-engineered features (title extraction, family size groups,
cabin deck) will outperform baseline logistic regression by capturing non-linear
feature interactions while maintaining fast training time.

## Data Prep & Validation
- Load train.csv and test.csv
- Extract title from Name using regex
- Create FamilySize = SibSp + Parch + 1
- Extract Cabin deck (first letter) or 'Unknown'
- Impute Age using median by Title group
- Use StratifiedKFold(5, random_state=42)

## Modeling Plan
- Model: LightGBM with early stopping
- Loss: binary_logloss
- Hyperparameters to tune via Optuna (50 trials):
  - learning_rate: [0.01, 0.3]
  - num_leaves: [15, 63]
  - max_depth: [3, 12]
  - min_child_samples: [5, 100]
  - reg_alpha: [0.0, 1.0]
  - reg_lambda: [0.0, 1.0]

## WAA Guidance: Aggressive Execution
- Minimum Optuna trials: 50
- Must-try: feature importance analysis, SHAP values
- Quick wins: try removing low-importance features
- Freedom to deviate: can try CatBoost if LightGBM plateaus

## Deliverables
- result_iter0_exp1_abc123.json with CV score
- submission_iter0_exp1_abc123.csv with predictions
- DONE_iter0_exp1_abc123 completion marker
- waa_iter0_exp1_abc123.log with training logs
"""

    task_md = worktree_exp / "iter0_exp1_abc123_task.md"
    task_md.write_text(waa_task, encoding="utf-8")

    waa_result = execute_codex_experiment(
        task_markdown_path=task_md,
        worktree_path=worktree_exp,
        experiment_id="iter0_exp1_abc123",
        dry_run=True,
        logger=None,
    )
    assert waa_result.success

    # PA prompt with realistic analysis request
    pa_prompt = """# Performance Analysis - Iteration 0

## Your Role
You are a THIRD-PARTY AUDITOR analyzing experiment results. Your analysis directly
impacts the next iteration's success. Be thorough, objective, and actionable.

## Experiment Results

| Exp ID | Strategy | CV Score | Train Score | Gap | Runtime |
|--------|----------|----------|-------------|-----|---------|
| iter0_exp1_abc123 | LightGBM + Domain Features | 0.8372 | 0.8891 | 5.19% | 12min |
| iter0_exp2_def456 | Baseline LogReg | 0.7923 | 0.8012 | 0.89% | 1min |
| iter0_exp3_ghi789 | TabNet | 0.8156 | 0.9234 | 10.78% | 45min |

## Analysis Requirements

### MACRO Analysis (Strategic View)
- Which model families showed promise?
- What is the overall trajectory?
- Are we exploring enough diversity?

### MICRO Analysis (Tactical View)
- Why did LightGBM outperform others?
- Why is TabNet overfitting severely?
- What specific features drove performance?

### WHY Analysis (Root Cause)
- For each finding, explain the MECHANISM
- Don't just state "X worked better" - explain WHY

### ACTION ITEMS FOR KSE
Provide concrete recommendations:
- MUST DO: High-confidence improvements
- SHOULD DO: Promising explorations
- MUST NOT DO: Approaches to avoid

Create analysis_iter0.md and pa_summary_iter0.json with your findings.
"""

    pa_result = execute_pa_analysis(
        results_data=pa_prompt,
        iteration=0,
        output_dir=worktrees_dir,
        dry_run=True,
        resume_prompt=pa_prompt,
        run_label="first_run",
        logger=None,
    )
    assert pa_result.success

    # Verify files were created
    prompts_dir = run_dir / "prompts"
    assert (prompts_dir / "KSE" / "iter0" / "iter0_prompt.md").exists()
    assert (prompts_dir / "WAA" / "iter0" / "iter0_exp1_abc123.md").exists()
    assert (prompts_dir / "PA" / "iter0" / "iter0_first_run.md").exists()

    print(f"\n{'='*60}")
    print(f"Example prompts saved to: {EXAMPLE_PROMPTS_DIR}")
    print(f"{'='*60}")
    print(f"\nGenerated files:")
    for p in sorted(prompts_dir.rglob("*.md")):
        print(f"  - {p.relative_to(EXAMPLE_PROMPTS_DIR)}")
