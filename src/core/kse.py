import os
import uuid
import random
import json
import re
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from .base_component import BaseComponent
from ..data_models import (
    CompetitionInfo, ExperimentHypothesis, ExperimentResult, AnalysisResult,
    ContinuationHypothesis, ExperimentDecision, ExperimentDecisionType
)
from ..utils.file_utils import write_markdown, ensure_dir
from ..utils.crawler_parser import parse_discussion_strategies
from ..utils.dataset_analyzer import DatasetAnalyzer
from ..utils.system_specs import SystemSpecsDetector
from ..utils.codex_executor import CodexMode, execute_codex, CodexResult
from ..utils.gpu_allocator import GPUAllocator
from ..utils.dry_run import stable_hash_int, write_jsonl_agent_message

class KnowledgeStrategyEngine(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.strategies = ["SimpleGBM", "FeatureEngV1_LGBM", "BasicNN", "RandomForest_HyperOpt"]
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.hypothesis_dir = os.path.join(self.experiment_run_dir, "hypotheses")
        self.simulation_mode = config.get("simulation_mode", False)
        ensure_dir(self.hypothesis_dir)

        self.competition_name = config.get("kaggle_competition_name")
        self.use_crawler = config.get("use_crawler", True)
        self.discussion_strategies: List[Dict[str, Any]] = []

        # Initialize new components
        self.system_specs_detector = SystemSpecsDetector()
        self.system_specs = None  # Will be populated on first use
        self.dataset_analyzer = None  # Will be initialized when needed
        self.dataset_analysis = None  # Cache for dataset analysis

        # Dry-run (simulation_mode) still exercises the template pipeline, but must not call Codex.
        # Treat "use_codex_for_generation" as "use the template pipeline" rather than "invoke Codex CLI".
        self.use_codex_for_generation = True
        self._codex_cli_enabled = not self.simulation_mode
        self.codex_timeout = config.get("kse_codex_timeout", 600)

        # Prompts directory for loading template files
        self.prompts_dir = config.get("prompts_dir", "prompts")

        # GPU allocator for parallel WAA resource management
        self.gpu_allocator = GPUAllocator(config)

        # Number of WAAs per iteration (for GPU allocation calculations)
        self.wca_per_iteration = config.get("wca_per_iteration", 3)

    def set_dataset_analysis(self, analysis: Optional[Dict[str, Any]]) -> None:
        """
        Set the dataset analysis from an external source (e.g., KIM).

        This allows reusing the analysis that KIM already performed,
        avoiding duplicate work and ensuring consistency.

        Args:
            analysis: Dataset analysis dictionary from KIM.get_dataset_analysis()
        """
        if analysis:
            self.dataset_analysis = analysis
            self.logger.info("Dataset analysis received from KIM")
        else:
            self.logger.debug("No dataset analysis provided, will analyze on demand")

    def _get_system_specs(self) -> Dict[str, Any]:
        """Get system specifications, caching the result."""
        if self.system_specs is None:
            self.logger.info("Detecting system specifications...")
            self.system_specs = self.system_specs_detector.get_specs()
            self.logger.info(f"System: {self.system_specs['cpu']['compute_type']} CPU, "
                           f"{self.system_specs['memory']['memory_class']}, "
                           f"GPU: {self.system_specs['gpu']['available']}")
        return self.system_specs_detector.get_prompt_placeholders()

    def _get_dataset_analysis(self, competition_info: CompetitionInfo) -> Dict[str, Any]:
        """Get dataset analysis, caching the result."""
        if self.dataset_analysis is None:
            self.logger.info("Analyzing competition dataset...")
            # Initialize dataset analyzer with competition data directory
            data_dir = os.path.join("kaggle_competitions", self.competition_name, "data")
            if os.path.exists(data_dir):
                self.dataset_analyzer = DatasetAnalyzer(self.competition_name, data_dir)
                self.dataset_analysis = self.dataset_analyzer.get_prompt_placeholders()
                self.logger.info(f"Dataset: {self.dataset_analysis.get('train_size', 0)} train samples, "
                               f"{self.dataset_analysis.get('feature_count', 0)} features")
            else:
                self.logger.warning(f"Data directory not found: {data_dir}")
                self.dataset_analysis = self._get_default_dataset_placeholders()
        return self.dataset_analysis

    def _get_default_dataset_placeholders(self) -> Dict[str, Any]:
        """Return default dataset placeholders when analysis isn't possible."""
        return {
            "train_size": "[ASSUMED: 1000]",
            "test_size": "[ASSUMED: 500]",
            "feature_count": "[ASSUMED: 20]",
            "numeric_count": "[ASSUMED: 10]",
            "categorical_count": "[ASSUMED: 10]",
            "target_variable": "[ASSUMED: target]",
            "competition_type": "[ASSUMED: classification]",
            "target_distribution": "[ASSUMED: balanced]",
            "class_distribution": "[ASSUMED: balanced]",
            "missing_data_summary": "[ASSUMED: no missing data]",
            "unique_characteristics": "[ASSUMED: standard tabular dataset]",
            "temporal_or_cross_sectional": "[ASSUMED: cross-sectional]"
        }

    def _get_community_insights(self) -> Dict[str, Any]:
        """Get community insights from discussions."""
        insights = {
            "winning_approaches": [],
            "benchmarks": {},
            "common_pitfalls": [],
            "recommended_techniques": [],
            "domain_knowledge": "[ASSUMED: No specific domain knowledge]",
            "ceiling_score": 0.95
        }

        if self.discussion_strategies:
            # Extract insights from discussion strategies
            for strategy in self.discussion_strategies:
                if strategy.get('description'):
                    insights["winning_approaches"].append(strategy['description'][:200])
                if strategy.get('algorithm'):
                    insights["recommended_techniques"].append(strategy['algorithm'])

            # Add benchmark scores if available
            for strategy in self.discussion_strategies:
                if strategy.get('score'):
                    insights["benchmarks"][strategy['strategy_name']] = strategy['score']

        return insights

    def _load_discussion_strategies(self):
        """Load strategies from crawler discussion data"""
        if self.use_crawler and self.competition_name:
            self.discussion_strategies = parse_discussion_strategies(self.competition_name)
            if self.discussion_strategies:
                self.logger.info(f"Loaded {len(self.discussion_strategies)} strategies from discussions")
                # Add discovered strategies to our list
                for strategy in self.discussion_strategies:
                    strategy_name = strategy['strategy_name']
                    # Normalize algorithm names to our format
                    if strategy_name.lower() in ['xgboost', 'lightgbm', 'catboost']:
                        formatted_name = f"{strategy_name}_FromDiscussion"
                        if formatted_name not in self.strategies:
                            self.strategies.append(formatted_name)
                            self.logger.info(f"Added strategy from discussions: {formatted_name}")
                    elif 'neural' in strategy_name.lower() or 'nn' in strategy_name.lower():
                        if "AdvancedNN" not in self.strategies:
                            self.strategies.append("AdvancedNN")
                    elif 'ensemble' in strategy_name.lower() or 'blend' in strategy_name.lower():
                        if "EnsembleBlend" not in self.strategies:
                            self.strategies.append("EnsembleBlend")

    def _get_kse_template_paths(self) -> Dict[str, Path]:
        """Return paths to KSE instruction and template files."""
        base_dir = Path(self.prompts_dir) if self.prompts_dir else Path("prompts")
        kse_dir = base_dir / "KSE"

        instruction = kse_dir / "kse_codex_prompt.md"
        common = kse_dir / "waa_common_template.md"
        experiment = kse_dir / "waa_experiment_template.md"

        for path in [instruction, common, experiment]:
            if not path.exists():
                raise FileNotFoundError(f"KSE template missing: {path}")

        return {
            "instruction": instruction,
            "common": common,
            "experiment": experiment
        }

    def _prepare_iteration_directory(self, iteration: int) -> Path:
        """Create and return the iteration-specific hypothesis directory."""
        iteration_dir = Path(self.hypothesis_dir) / f"iter{iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        return iteration_dir

    def _build_experiment_ids(self, iteration: int, num_hypotheses: int) -> List[str]:
        """Generate experiment identifiers for this iteration."""
        exp_ids = []
        for i in range(num_hypotheses):
            exp_ids.append(f"iter{iteration}_exp{i+1}_{uuid.uuid4().hex[:6]}")
        return exp_ids

    def _build_experiment_ids_for_slots(self, iteration: int, slot_numbers: List[int]) -> List[str]:
        """
        Generate experiment identifiers for specific WAA slot numbers.

        Slot numbers are 1-based (exp1, exp2, ...), matching the WAA/GPU allocator conventions.
        """
        return [f"iter{iteration}_exp{slot}_{uuid.uuid4().hex[:6]}" for slot in slot_numbers]

    @staticmethod
    def _extract_exp_slot_number(exp_id: str) -> Optional[int]:
        """Extract 1-based exp slot number from an experiment identifier."""
        match = re.search(r"_exp(\d+)_", exp_id)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _prepare_iteration_templates(self, iteration: int, exp_ids: List[str]) -> Dict[str, Any]:
        """
        Copy KSE templates into the iteration directory and pre-fill experiment IDs.

        Returns a dict with iteration_dir, instruction_path, common_path, experiment_paths.
        """
        template_paths = self._get_kse_template_paths()
        iteration_dir = self._prepare_iteration_directory(iteration)

        # Common template
        common_target = iteration_dir / "waa_common_filled.md"
        common_target.write_text(template_paths["common"].read_text(encoding="utf-8"), encoding="utf-8")

        # Experiment templates (one per experiment)
        experiment_template_raw = template_paths["experiment"].read_text(encoding="utf-8")
        experiment_paths: List[Path] = []
        for exp_id in exp_ids:
            exp_content = experiment_template_raw.replace("{{EXPERIMENT_ID}}", exp_id)
            exp_target = iteration_dir / f"{exp_id}_plan.md"
            exp_target.write_text(exp_content, encoding="utf-8")
            experiment_paths.append(exp_target)

        return {
            "iteration_dir": iteration_dir,
            "instruction_path": template_paths["instruction"],
            "common_path": common_target,
            "experiment_paths": experiment_paths
        }

    def _get_data_paths_relative(self, iteration_dir: Path) -> Dict[str, str]:
        """Return relative paths for kaggle and crawler data for prompt inclusion."""
        kaggle_data_dir = Path(self.hypothesis_dir) / "kaggle_data"
        crawler_data_dir = Path(self.hypothesis_dir) / "crawler_data"

        kaggle_rel = os.path.relpath(kaggle_data_dir, iteration_dir) if kaggle_data_dir.exists() else "not available"
        crawler_rel = os.path.relpath(crawler_data_dir, iteration_dir) if crawler_data_dir.exists() else "not available"

        return {"kaggle": kaggle_rel, "crawler": crawler_rel}

    def _compose_system_context(self,
                                competition_info: CompetitionInfo,
                                num_hypotheses: int,
                                analysis_result: Optional[AnalysisResult],
                                previous_results: Optional[List[ExperimentResult]]) -> str:
        """Build a compact system context block appended to the KSE prompt."""
        dataset_analysis = self._get_dataset_analysis(competition_info)
        system_specs = self._get_system_specs()

        context_lines = [
            f"- evaluation_metric: {competition_info.evaluation_metric}",
            f"- data_files: {', '.join(competition_info.data_files)}",
            f"- dataset quick stats: train_size={dataset_analysis.get('train_size')}, features={dataset_analysis.get('feature_count')}, target={dataset_analysis.get('target_variable')}",
            f"- system: GPU available={system_specs.get('gpu_available', 'Unknown')}, memory={system_specs.get('memory_gb', 'Unknown')} GB",
            f"- planned experiments this iteration: {num_hypotheses}"
        ]

        if analysis_result:
            context_lines.append(
                f"- previous best score: {analysis_result.best_score} (exp_id={analysis_result.best_experiment_id})"
            )

        if previous_results:
            # Show up to three recent results for guidance
            recent = previous_results[-3:]
            for res in recent:
                context_lines.append(
                    f"- prior result: {res.experiment_id} | {res.strategy_name} | score={res.score}"
                )

        return "\n\n## System-provided quick context\n" + "\n".join(context_lines)

    def _format_waa_results(self,
                            previous_results: Optional[List[ExperimentResult]],
                            official_scores: Optional[Dict[str, float]],
                            current_iteration: int) -> str:
        """Format WAA results (with official scores) for prompt embedding."""
        if not previous_results:
            return "No WAA results available yet."

        latest_iter = current_iteration - 1 if current_iteration > 0 else 0
        iter_results = [r for r in previous_results if r.iteration == latest_iter] or previous_results
        lines = []
        for r in iter_results:
            official = None
            if official_scores:
                official = official_scores.get(r.experiment_id)
            official_str = f"{official:.4f}" if official is not None else "N/A"
            score_str = f"{r.score:.4f}" if r.score is not None else "N/A"
            lines.append(
                f"- {r.experiment_id} | strategy={r.strategy_name} | cv_score={score_str} | official_score={official_str} | status={r.status}"
            )
        return "\n".join(lines) if lines else "No WAA results available yet."

    def _load_pa_analysis_markdown(self, current_iteration: int) -> str:
        """Load the most recent PA analysis markdown for context."""
        if current_iteration <= 0:
            return "No PA analysis yet."
        analysis_path = Path(self.experiment_run_dir) / "analysis" / f"analysis_iter_{current_iteration - 1}.md"
        if analysis_path.exists():
            try:
                return analysis_path.read_text(encoding="utf-8")
            except Exception:
                return "PA analysis could not be read."
        return "PA analysis not found for previous iteration."

    def generate_initial_hypotheses(self, competition_info: CompetitionInfo, num_hypotheses: int) -> List[ExperimentHypothesis]:
        """Generate initial experiment hypotheses."""
        method_name = "generate_initial_hypotheses"
        self._log_start(method_name, num_hypotheses=num_hypotheses)

        # Load strategies from discussion insights
        self._load_discussion_strategies()

        if self.use_codex_for_generation:
            # Use Codex with external prompts for hypothesis generation
            hypotheses = self._generate_hypotheses_with_codex(
                competition_info, num_hypotheses, iteration=0, is_initial=True, official_scores=None
            )
        else:
            # Fallback to original programmatic generation
            hypotheses = []
            iteration_dir = Path(self.hypothesis_dir) / "iter0"
            iteration_dir.mkdir(parents=True, exist_ok=True)
            for i in range(num_hypotheses):
                exp_id = f"iter0_exp{i+1}_{uuid.uuid4().hex[:6]}"
                strategy = random.choice(self.strategies)
                params = self._get_dummy_params(strategy)
                task_md_path = iteration_dir / f"{exp_id}_task.md"

                task_markdown = self._generate_task_markdown(exp_id, 0, strategy, params, competition_info, num_hypotheses)
                write_markdown(task_markdown, str(task_md_path))

                hypothesis = ExperimentHypothesis(
                    experiment_id=exp_id,
                    iteration=0,
                    strategy_name=strategy,
                    parameters=params,
                    task_markdown_path=str(task_md_path)
                )
                hypotheses.append(hypothesis)
                self.logger.debug(f"Generated hypothesis: {exp_id} ({strategy})")

        self._log_end(method_name, result=f"Generated {len(hypotheses)} hypotheses")
        return hypotheses

    def _generate_hypotheses_with_codex(self,
                                       competition_info: CompetitionInfo,
                                       num_hypotheses: int,
                                       iteration: int,
                                       is_initial: bool = True,
                                       analysis_result: Optional[AnalysisResult] = None,
                                       previous_results: Optional[List[ExperimentResult]] = None,
                                       official_scores: Optional[Dict[str, float]] = None,
                                       exp_ids: Optional[List[str]] = None,
                                       total_waas: Optional[int] = None) -> List[ExperimentHypothesis]:
        """Generate hypotheses using Codex with the new A/B template pipeline."""
        self.logger.info(f"Generating hypotheses using Codex for iteration {iteration}")

        # Prepare iteration workspace and template files
        if exp_ids is None:
            exp_ids = self._build_experiment_ids(iteration, num_hypotheses)
        else:
            num_hypotheses = len(exp_ids)
        if total_waas is None:
            total_waas = num_hypotheses
        template_info = self._prepare_iteration_templates(iteration, exp_ids)
        iteration_dir: Path = template_info["iteration_dir"]

        # Build Codex prompt that instructs filling common + experiment templates
        filled_prompt = self._build_kse_prompt(
            competition_info=competition_info,
            num_hypotheses=num_hypotheses,
            iteration=iteration,
            template_info=template_info,
            analysis_result=analysis_result,
            previous_results=previous_results,
            official_scores=official_scores
        )

        # Save filled prompt for debugging
        prompt_path = iteration_dir / f"kse_prompt_iter{iteration}.md"
        prompt_path.write_text(filled_prompt, encoding="utf-8")
        self.logger.info(f"Saved filled prompt to {prompt_path}")

        # Execute Codex to fill templates
        codex_responses_dir = os.path.join(self.experiment_run_dir, "codex-responses")
        if self.simulation_mode:
            # Dry-run: deterministically "fill" templates locally, leaving some placeholders
            # so that the resume-fill path is exercised.
            self._dry_run_fill_templates(
                iteration=iteration,
                competition_info=competition_info,
                exp_ids=exp_ids,
                common_path=template_info["common_path"],
                experiment_paths=template_info["experiment_paths"],
                attempt=0,
            )
            # Emit a minimal Codex-like JSONL response for parity with real runs.
            write_jsonl_agent_message(
                Path(codex_responses_dir) / "KSE" / f"response-{iteration}-{'initial' if iteration == 0 else 'resume'}.jsonl",
                f"DRY-RUN: simulated KSE template fill (iteration={iteration}, attempt=0)."
            )
            codex_result = CodexResult(success=True, mode=CodexMode.KSE, execution_time=0.0)
        else:
            try:
                use_resume = iteration > 0
                run_label = "initial" if iteration == 0 else "resume"
                resume_prompt = filled_prompt if use_resume else None
                codex_result = execute_codex(
                    mode=CodexMode.KSE,
                    prompt_content=filled_prompt,
                    output_dir=str(iteration_dir),
                    iteration=iteration,
                    codex_responses_dir=codex_responses_dir,
                    timeout=self.codex_timeout,
                    logger=self.logger,
                    resume_prompt=resume_prompt,
                    run_label=run_label,
                    live_view_config=self.config
                )
            except Exception as e:
                self.logger.error(f"Error calling Codex for KSE: {e}")
                codex_result = CodexResult(
                    success=False,
                    mode=CodexMode.KSE,
                    execution_time=0.0,
                    error=str(e)
                )

        if not codex_result.success:
            self.logger.warning(f"Codex execution failed: {codex_result.error}")
            self.logger.warning("Falling back to programmatic generation")
            return self._generate_programmatic_hypotheses(
                iteration, num_hypotheses, competition_info, previous_results, exp_ids=exp_ids, total_waas=total_waas
            )

        # Check placeholders and optionally trigger resume to complete them
        placeholder_map = self._find_remaining_placeholders(
            [template_info["common_path"]] + template_info["experiment_paths"]
        )

        if placeholder_map:
            placeholder_map = self._resolve_placeholders_with_resume(
                iteration=iteration,
                iteration_dir=iteration_dir,
                template_paths=[template_info["common_path"]] + template_info["experiment_paths"],
                codex_responses_dir=codex_responses_dir
            )

        if placeholder_map:
            self.logger.warning(f"Placeholders remain after Codex runs: {placeholder_map}")
            self.logger.warning("Falling back to programmatic generation")
            return self._generate_programmatic_hypotheses(
                iteration, num_hypotheses, competition_info, previous_results, exp_ids=exp_ids, total_waas=total_waas
            )

        # Build final hypotheses and WAA task markdowns from filled templates
        hypotheses = self._create_hypotheses_from_templates(
            iteration=iteration,
            exp_ids=exp_ids,
            common_path=template_info["common_path"],
            experiment_paths=template_info["experiment_paths"],
            competition_info=competition_info,
            total_waas=total_waas
        )

        self.logger.info(f"Successfully prepared {len(hypotheses)} hypotheses from filled templates")
        return hypotheses

    def _dry_run_fill_templates(
        self,
        iteration: int,
        competition_info: CompetitionInfo,
        exp_ids: List[str],
        common_path: Path,
        experiment_paths: List[Path],
        attempt: int,
    ) -> None:
        """
        Deterministically fill KSE templates without calling Codex.

        attempt=0 intentionally leaves some placeholders so that the resume-fill
        path is exercised. attempt>=1 fills all remaining placeholders.
        """
        # Fill common template
        common_text = Path(common_path).read_text(encoding="utf-8")
        common_text = self._dry_run_fill_text(
            text=common_text,
            key=f"{competition_info.name}:{iteration}:common:{attempt}",
            attempt=attempt,
            fixed={
                "COMPETITION_NAME": competition_info.name,
                "EVALUATION_METRIC": competition_info.evaluation_metric,
                "METRIC_DIRECTION": "higher" if getattr(competition_info, "higher_is_better", True) else "lower",
                "METRIC_DIRECTION_EXPLANATION": "higher is better" if getattr(competition_info, "higher_is_better", True) else "lower is better",
            },
            protect={"COMPETITION_NAME", "EVALUATION_METRIC", "METRIC_DIRECTION", "METRIC_DIRECTION_EXPLANATION"},
        )
        Path(common_path).write_text(common_text, encoding="utf-8")

        # Fill per-experiment templates
        for exp_id, exp_path in zip(exp_ids, experiment_paths):
            strategy, params = self._dry_run_strategy_and_params(exp_id)
            exp_text = Path(exp_path).read_text(encoding="utf-8")
            exp_text = self._dry_run_fill_text(
                text=exp_text,
                key=f"{competition_info.name}:{iteration}:{exp_id}:{attempt}",
                attempt=attempt,
                fixed={
                    "EXPERIMENT_ID": exp_id,
                    "STRATEGY_NAME": strategy,
                    "PARAMETERS_JSON": json.dumps(params, indent=2),
                    "TARGET_METRIC": competition_info.evaluation_metric,
                    "METRIC_DIRECTION": "higher" if getattr(competition_info, "higher_is_better", True) else "lower",
                    "METRIC_DIRECTION_EXPLANATION": "higher is better" if getattr(competition_info, "higher_is_better", True) else "lower is better",
                },
                protect={"EXPERIMENT_ID", "STRATEGY_NAME", "PARAMETERS_JSON", "TARGET_METRIC", "METRIC_DIRECTION", "METRIC_DIRECTION_EXPLANATION"},
            )
            Path(exp_path).write_text(exp_text, encoding="utf-8")

    def _dry_run_strategy_and_params(self, exp_id: str) -> tuple[str, Dict[str, Any]]:
        """Deterministically derive a strategy + params from exp_id."""
        # Keep in sync with the strategies list for diversity coverage.
        strategies = [
            "LightGBM_Optuna",
            "XGBoost_Baseline",
            "CatBoost_Categorical",
            "RandomForest_Quick",
            "LinearModel_FeatureEng",
        ]
        strategy = strategies[stable_hash_int(f"{exp_id}:strategy") % len(strategies)]

        # Deterministic but plausible params (not actually used by the simulator).
        def u(suffix: str, low: float, high: float) -> float:
            n = stable_hash_int(f"{exp_id}:{suffix}") % 1_000_000
            return low + (high - low) * (n / 1_000_000.0)

        if "LightGBM" in strategy:
            params = {
                "learning_rate": round(u("lr", 0.005, 0.2), 5),
                "n_estimators": int(50 + (stable_hash_int(f"{exp_id}:n_est") % 950)),
                "num_leaves": int(16 + (stable_hash_int(f"{exp_id}:leaves") % 240)),
            }
        elif "XGBoost" in strategy:
            params = {
                "eta": round(u("eta", 0.01, 0.3), 5),
                "max_depth": int(3 + (stable_hash_int(f"{exp_id}:depth") % 8)),
                "subsample": round(u("subsample", 0.6, 1.0), 3),
            }
        elif "CatBoost" in strategy:
            params = {
                "learning_rate": round(u("lr", 0.01, 0.2), 5),
                "depth": int(4 + (stable_hash_int(f"{exp_id}:depth") % 8)),
                "iterations": int(200 + (stable_hash_int(f"{exp_id}:iters") % 800)),
            }
        elif "RandomForest" in strategy:
            params = {
                "n_estimators": int(100 + (stable_hash_int(f"{exp_id}:rf_n") % 900)),
                "max_depth": int(3 + (stable_hash_int(f"{exp_id}:rf_d") % 20)),
            }
        else:
            params = {
                "alpha": round(u("alpha", 1e-4, 10.0), 6),
                "feature_set": "basic",
            }

        return strategy, params

    def _dry_run_fill_text(
        self,
        text: str,
        key: str,
        attempt: int,
        fixed: Dict[str, str],
        protect: set[str],
    ) -> str:
        """
        Replace {{PLACEHOLDER}} tokens with deterministic values.

        attempt=0 leaves a small subset of placeholders (excluding `protect`) so the resume path runs.
        attempt>=1 fills all remaining placeholders.
        """
        placeholders = sorted(set(re.findall(r"\{\{([^{}]+)\}\}", text)))
        if not placeholders:
            return text

        for ph in placeholders:
            ph_key = ph.strip()
            if ph_key in fixed:
                text = text.replace(f"{{{{{ph}}}}}", str(fixed[ph_key]))
                continue

            # Leave some placeholders on the first pass (deterministically) to exercise resume fill.
            if attempt == 0 and ph_key not in protect:
                # Keep ~15% as unresolved.
                if stable_hash_int(f"{key}:{ph_key}") % 20 == 0:
                    continue

            # Generic default replacement
            replacement = f"DRY_RUN_{ph_key}"
            text = text.replace(f"{{{{{ph}}}}}", replacement)

        return text

    def _build_kse_prompt(self,
                          competition_info: CompetitionInfo,
                          num_hypotheses: int,
                          iteration: int,
                          template_info: Dict[str, Any],
                          analysis_result: Optional[AnalysisResult],
                          previous_results: Optional[List[ExperimentResult]],
                          official_scores: Optional[Dict[str, float]] = None) -> str:
        """Build the Codex instruction prompt for KSE based on the iteration-specific template."""
        # Choose prompt template: first run vs resume
        prompts_dir = Path(self.prompts_dir) if self.prompts_dir else Path("prompts")
        if iteration == 0:
            instruction_path = prompts_dir / "KSE" / "kse_prompt_first_run.md"
        else:
            instruction_path = prompts_dir / "KSE" / "kse_prompt_resume.md"

        if not instruction_path.exists():
            # Fallback to legacy prompt if new templates are missing
            instruction_path = template_info["instruction_path"]

        prompt_template = instruction_path.read_text(encoding="utf-8")

        data_paths = self._get_data_paths_relative(template_info["iteration_dir"])
        common_rel = os.path.relpath(template_info["common_path"], template_info["iteration_dir"])
        experiment_rel_lines = "\n- " + "\n- ".join(
            f"{os.path.relpath(path, template_info['iteration_dir'])}"
            for path in template_info["experiment_paths"]
        )
        experiment_paths_block = experiment_rel_lines if experiment_rel_lines.strip() else ""

        kaggle_path_label = (
            f"{data_paths['kaggle']} (Kaggle API data)" if data_paths["kaggle"] != "not available" else "not available"
        )
        crawler_path_label = (
            f"{data_paths['crawler']} (crawler outputs)" if data_paths["crawler"] != "not available" else "not available"
        )

        context_block = "\n".join([
            f"- Competition name: {competition_info.name or 'Unknown competition'}",
            f"- Iteration: {iteration}",
            f"- Number of experiments: {num_hypotheses}",
            f"- Data sources: {kaggle_path_label}",
            f"- Crawler sources: {crawler_path_label}",
            f"- Common template: {common_rel}",
            f"- Experiment templates:\n{experiment_paths_block}"
        ])

        waa_results_block = self._format_waa_results(previous_results, official_scores, iteration)
        pa_analysis_block = self._load_pa_analysis_markdown(iteration)

        replacements = {
            "<<CONTEXT_BLOCK>>": context_block,
            "<<WAA_RESULTS>>": waa_results_block,
            "<<PA_ANALYSIS>>": pa_analysis_block
        }

        prompt = prompt_template
        for token, value in replacements.items():
            prompt = prompt.replace(token, value)

        prompt += self._compose_system_context(
            competition_info=competition_info,
            num_hypotheses=num_hypotheses,
            analysis_result=analysis_result,
            previous_results=previous_results
        )

        return prompt

    def _find_remaining_placeholders(self, paths: List[Path]) -> Dict[str, List[str]]:
        """Return remaining {{placeholders}} in the given files."""
        placeholder_map: Dict[str, List[str]] = {}
        for path in paths:
            try:
                content = Path(path).read_text(encoding="utf-8")
            except Exception as e:
                self.logger.warning(f"Failed to read template {path}: {e}")
                continue
            matches = re.findall(r"\{\{([^{}]+)\}\}", content)
            if matches:
                placeholder_map[str(path)] = sorted(set(m.strip() for m in matches))
        return placeholder_map

    def _resolve_placeholders_with_resume(self,
                                          iteration: int,
                                          iteration_dir: Path,
                                          template_paths: List[Path],
                                          codex_responses_dir: str | None) -> Dict[str, List[str]]:
        """Run Codex resume to fill any remaining placeholders."""
        remaining = self._find_remaining_placeholders(template_paths)
        max_attempts = self.config.get("kse_resume_attempts", 2)
        attempt = 0

        while remaining and attempt < max_attempts:
            missing_lines = []
            for file_path, placeholders in remaining.items():
                rel_path = os.path.relpath(file_path, iteration_dir)
                missing_lines.append(f"- {rel_path}: {', '.join(placeholders)}")

            resume_prompt = (
                "Some placeholders are still empty. Fill ONLY the missing placeholders listed below, "
                "without altering already completed content. Remove every `{{...}}` token.\n"
                "Placeholders to fill:\n" + "\n".join(missing_lines)
            )

            if self.simulation_mode:
                # Dry-run: fill remaining placeholders locally and emit a Codex-like JSONL trace.
                # attempt+1 corresponds to "resume1", "resume2", ...
                run_label = f"resume{attempt+1}"
                for path in template_paths:
                    content = Path(path).read_text(encoding="utf-8")
                    content = self._dry_run_fill_text(
                        text=content,
                        key=f"{iteration}:{path}:{run_label}",
                        attempt=attempt + 1,
                        fixed={},
                        protect=set(),
                    )
                    Path(path).write_text(content, encoding="utf-8")

                if codex_responses_dir:
                    write_jsonl_agent_message(
                        Path(codex_responses_dir) / "KSE" / f"response-{iteration}-{run_label}.jsonl",
                        f"DRY-RUN: simulated KSE resume fill (iteration={iteration}, attempt={attempt+1}).\n\n{resume_prompt}"
                    )
            else:
                execute_codex(
                    mode=CodexMode.KSE,
                    prompt_content=resume_prompt,
                    output_dir=str(iteration_dir),
                    iteration=iteration,
                    codex_responses_dir=codex_responses_dir,
                    timeout=self.codex_timeout,
                    logger=self.logger,
                    resume_prompt=resume_prompt,
                    run_label=f"resume{attempt+1}",
                    live_view_config=self.config
                )

            remaining = self._find_remaining_placeholders(template_paths)
            attempt += 1

        return remaining

    def _create_hypotheses_from_templates(self,
                                          iteration: int,
                                          exp_ids: List[str],
                                          common_path: Path,
                                          experiment_paths: List[Path],
                                          competition_info: CompetitionInfo,
                                          total_waas: int) -> List[ExperimentHypothesis]:
        """Assemble final WAA prompts and ExperimentHypothesis objects from filled templates."""
        common_content = Path(common_path).read_text(encoding="utf-8")
        hypotheses: List[ExperimentHypothesis] = []

        for exp_id, exp_path in zip(exp_ids, experiment_paths):
            experiment_content = Path(exp_path).read_text(encoding="utf-8")
            strategy, params = self._extract_strategy_and_params_from_template(experiment_content, exp_id)

            task_content = self._compose_task_content_from_templates(common_content, experiment_content, exp_id)

            # Wrap in unified WAA template
            template = self._load_waa_template()
            gpu_section = self._get_gpu_instructions_section(exp_id, total_waas)
            task_markdown = template.format(
                gpu_allocation_section=gpu_section,
                task_content=task_content,
                exp_id=exp_id
            )

            task_md_path = Path(self.hypothesis_dir) / f"iter{iteration}" / f"{exp_id}_task.md"
            task_md_path.parent.mkdir(parents=True, exist_ok=True)
            task_md_path.write_text(task_markdown, encoding="utf-8")

            hypotheses.append(
                ExperimentHypothesis(
                    experiment_id=exp_id,
                    iteration=iteration,
                    strategy_name=strategy,
                    parameters=params,
                    task_markdown_path=str(task_md_path)
                )
            )

        return hypotheses

    def _extract_strategy_and_params_from_template(self, content: str, exp_id: str) -> tuple[str, Dict[str, Any]]:
        """Parse strategy name and parameters JSON block from a filled experiment template."""
        strategy = f"Strategy_{exp_id}"
        strategy_match = re.search(r"strategy_name:\s*(.+)", content, re.IGNORECASE)
        if strategy_match:
            strategy = strategy_match.group(1).strip()

        params: Dict[str, Any] = {}
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            try:
                params = json.loads(json_match.group(1))
            except Exception as e:
                self.logger.warning(f"Failed to parse parameters JSON for {exp_id}: {e}")

        return strategy, params

    def _compose_task_content_from_templates(self, common_content: str, experiment_content: str, exp_id: str) -> str:
        """Combine common and per-experiment templates into WAA task content."""
        execution_notes = (
            f"\n## Execution Checklist\n"
            f"- Follow the experiment blueprint above precisely for {exp_id}.\n"
            f"- Produce `result_{exp_id}.json` with the validation metric.\n"
            f"- Produce `submission_{exp_id}.csv` in the competition format.\n"
            f"- Log key steps and metrics to `waa_{exp_id}.log`.\n"
            f"- Create `DONE_{exp_id}` when all outputs are ready.\n"
        )

        return (
            f"# Experiment Task: {exp_id}\n\n"
            f"## Competition-Wide Plan\n{common_content}\n\n"
            f"## Experiment Plan\n{experiment_content}\n"
            f"{execution_notes}"
        )

    def _generate_programmatic_hypotheses(self,
                                          iteration: int,
                                          num_hypotheses: int,
                                          competition_info: CompetitionInfo,
                                          previous_results: Optional[List[ExperimentResult]],
                                          exp_ids: Optional[List[str]] = None,
                                          total_waas: Optional[int] = None) -> List[ExperimentHypothesis]:
        """Fallback hypothesis generation without Codex."""
        iteration_dir = Path(self.hypothesis_dir) / f"iter{iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        hypotheses = []

        if exp_ids is None:
            exp_ids = [f"iter{iteration}_exp{i+1}_{uuid.uuid4().hex[:6]}" for i in range(num_hypotheses)]
        else:
            num_hypotheses = len(exp_ids)
        if total_waas is None:
            total_waas = num_hypotheses

        for exp_id in exp_ids:
            strategy = random.choice(self.strategies)
            params = self._get_dummy_params(strategy, previous_results)
            task_md_path = iteration_dir / f"{exp_id}_task.md"

            task_markdown = self._generate_task_markdown(exp_id, iteration, strategy, params, competition_info, total_waas)
            write_markdown(task_markdown, str(task_md_path))

            hypothesis = ExperimentHypothesis(
                experiment_id=exp_id,
                iteration=iteration,
                strategy_name=strategy,
                parameters=params,
                task_markdown_path=str(task_md_path)
            )
            hypotheses.append(hypothesis)

        return hypotheses

    def _prepare_iteration_results(self, previous_results: Optional[List[ExperimentResult]]) -> Dict[str, Any]:
        """Prepare iteration results for prompt filling."""
        if not previous_results:
            return {"experiments": [], "best_experiment": {}, "worst_experiment": {}}

        # Find best and worst experiments
        valid_results = [r for r in previous_results if r.score is not None]
        if valid_results:
            best_result = max(valid_results, key=lambda r: r.score)
            worst_result = min(valid_results, key=lambda r: r.score)
            scores = [r.score for r in valid_results]

            return {
                "experiments": [
                    {
                        "id": r.experiment_id,
                        "strategy": r.strategy_name,
                        "validation_score": r.score,
                        "runtime_minutes": r.execution_time_seconds / 60 if r.execution_time_seconds else 0,
                        "status": r.status,
                        "train_val_gap": 0  # Would need to calculate from logs
                    }
                    for r in previous_results
                ],
                "best_experiment": {
                    "id": best_result.experiment_id,
                    "strategy": best_result.strategy_name,
                    "score": best_result.score,
                    "runtime_minutes": best_result.execution_time_seconds / 60 if best_result.execution_time_seconds else 0
                },
                "worst_experiment": {
                    "id": worst_result.experiment_id,
                    "strategy": worst_result.strategy_name,
                    "score": worst_result.score
                },
                "mean_score": sum(scores) / len(scores),
                "std_score": 0,  # Would need numpy for std
                "min_score": min(scores),
                "max_score": max(scores),
                "success_rate": len(valid_results) / len(previous_results) * 100 if previous_results else 0,
                "cv_scheme": "StratifiedKFold(5)"
            }

        return {"experiments": [], "best_experiment": {}, "worst_experiment": {}}

    def _prepare_pa_analysis(self, analysis_result: Optional[AnalysisResult]) -> Dict[str, Any]:
        """Prepare PA analysis for prompt filling."""
        if not analysis_result:
            return {
                "success_patterns": [],
                "failure_patterns": [],
                "feature_importance": [],
                "high_priority": [],
                "medium_priority": [],
                "experimental": [],
                "avoid": [],
                "unresolved_questions": [],
                "summary": "No analysis available yet."
            }

        return {
            "success_patterns": getattr(analysis_result, 'success_patterns', []),
            "failure_patterns": getattr(analysis_result, 'failure_patterns', []),
            "feature_importance": getattr(analysis_result, 'feature_importance', []),
            "high_priority": analysis_result.recommended_strategies if analysis_result.recommended_strategies else [],
            "medium_priority": [],
            "experimental": [],
            "avoid": getattr(analysis_result, 'strategies_to_avoid', []),
            "unresolved_questions": getattr(analysis_result, 'unresolved_questions', []),
            "summary": analysis_result.summary_markdown if analysis_result.summary_markdown else "Analysis complete."
        }

    def generate_next_hypotheses(self,
                                 competition_info: CompetitionInfo,
                                 current_iteration: int,
                                 num_hypotheses: int,
                                 analysis_result: Optional[AnalysisResult],
                                 previous_results: List[ExperimentResult],
                                 official_scores: Optional[Dict[str, float]] = None) -> List[ExperimentHypothesis]:
        """Generate the next set of hypotheses based on analysis and past results."""
        method_name = "generate_next_hypotheses"
        self._log_start(method_name, iteration=current_iteration, num_hypotheses=num_hypotheses)

        if self.use_codex_for_generation:
            # Use Codex with external prompts for hypothesis generation
            hypotheses = self._generate_hypotheses_with_codex(
                competition_info, num_hypotheses, iteration=current_iteration,
                is_initial=False, analysis_result=analysis_result, previous_results=previous_results,
                official_scores=official_scores
            )
        else:
            # Fallback to original programmatic generation
            hypotheses = []
            iteration_dir = Path(self.hypothesis_dir) / f"iter{current_iteration}"
            iteration_dir.mkdir(parents=True, exist_ok=True)

            # Choose strategies based on analysis/history (simulation uses random + tweaks)
            possible_strategies = self.strategies[:]  # Make a copy
            if analysis_result and analysis_result.recommended_strategies:
                # Prioritize recommended strategies
                possible_strategies = analysis_result.recommended_strategies + [s for s in self.strategies if s not in analysis_result.recommended_strategies]
                self.logger.info(f"Prioritizing recommended strategies: {analysis_result.recommended_strategies}")

            if previous_results:
                 # Could generate hypotheses that fine-tune successful strategies (omitted)
                 pass

            for i in range(num_hypotheses):
                exp_id = f"iter{current_iteration}_exp{i+1}_{uuid.uuid4().hex[:6]}"
                # Select strategy (prioritize recommendations; otherwise rotate)
                strategy = possible_strategies[i % len(possible_strategies)]
                params = self._get_dummy_params(strategy, previous_results)  # Could adjust params using past results
                task_md_path = iteration_dir / f"{exp_id}_task.md"

                task_markdown = self._generate_task_markdown(exp_id, current_iteration, strategy, params, competition_info, num_hypotheses)
                write_markdown(task_markdown, str(task_md_path))

                hypothesis = ExperimentHypothesis(
                    experiment_id=exp_id,
                    iteration=current_iteration,
                    strategy_name=strategy,
                    parameters=params,
                    task_markdown_path=str(task_md_path)
                )
                hypotheses.append(hypothesis)
                self.logger.debug(f"Generated hypothesis: {exp_id} ({strategy})")

        self._log_end(method_name, result=f"Generated {len(hypotheses)} hypotheses")
        return hypotheses

    def _load_waa_template(self) -> str:
        """Load the unified WAA task template."""
        # First try the configured prompts_dir (may be absolute or relative)
        template_path = os.path.join(self.prompts_dir, "WAA", "waa_task_template.md")
        if os.path.exists(template_path):
            with open(template_path, 'r') as f:
                return f.read()

        # Fallback: use absolute path relative to this source file
        # This ensures the template is found regardless of working directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(base_dir))  # Go up from src/core/ to project root
        absolute_template_path = os.path.join(project_root, "prompts", "WAA", "waa_task_template.md")

        if os.path.exists(absolute_template_path):
            self.logger.debug(f"Using absolute template path: {absolute_template_path}")
            with open(absolute_template_path, 'r') as f:
                return f.read()

        raise FileNotFoundError(
            f"WAA template not found at:\n"
            f"  - {template_path}\n"
            f"  - {absolute_template_path}"
        )

    def _generate_task_content(self, exp_id: str, iteration: int, strategy: str,
                               params: dict, comp_info: CompetitionInfo,
                               hypothesis_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate the task-specific content section for WAA prompts.

        Args:
            exp_id: Experiment identifier
            iteration: Current iteration number
            strategy: Strategy name
            params: Model/experiment parameters
            comp_info: Competition information
            hypothesis_data: Optional hypothesis data from Codex (if using Codex-generated hypotheses)

        Returns:
            Task-specific markdown content (without UV/GPU/status sections)
        """
        if hypothesis_data:
            # Generate task content from Codex-generated hypothesis
            task_md = f"# Experiment Task: {exp_id}\n\n"
            task_md += f"## Competition: {comp_info.name}\n"
            task_md += f"## Iteration: {iteration}\n"
            task_md += f"## Strategy: {strategy}\n\n"

            # Add hypothesis details from Codex
            if hypothesis_data.get("description"):
                task_md += f"### Hypothesis\n{hypothesis_data['description']}\n\n"

            if hypothesis_data.get("approach"):
                task_md += f"### Approach\n{hypothesis_data['approach']}\n\n"

            task_md += f"### Parameters\n```json\n{json.dumps(params, indent=2)}\n```\n\n"

            # Implementation steps
            task_md += f"### Implementation Steps\n"
            if hypothesis_data.get("steps"):
                for i, step in enumerate(hypothesis_data["steps"], 1):
                    task_md += f"{i}. {step}\n"
            else:
                # Default steps
                task_md += f"1. Load data from `{comp_info.data_files}`\n"
                task_md += f"2. Implement {strategy} with specified parameters\n"
                task_md += f"3. Train model using cross-validation\n"
                task_md += f"4. Generate predictions on test set\n"
                task_md += f"5. Save results to `result_{exp_id}.json`\n"

            task_md += f"\n### Expected Output\n"
            task_md += f"- Model file: `model_{exp_id}.pkl`\n"
            task_md += f"- Predictions: `submission_{exp_id}.csv`\n"
            task_md += f"- Results JSON: `result_{exp_id}.json` containing:\n"
            task_md += f"  - validation_score\n"
            task_md += f"  - feature_importance (if applicable)\n"
            task_md += f"  - runtime_seconds\n"
            task_md += f"  - parameters_used\n"

            task_md += f"\n### Success Criteria\n"
            task_md += f"- Model trains without errors\n"
            task_md += f"- Validation score is computed\n"
            task_md += f"- Submission file is in correct format\n"
            task_md += f"- Results are saved to JSON\n"
            task_md += f"- Completion marker created: `DONE_{exp_id}`\n"

            return task_md

        else:
            # Generate task content from programmatic generation
            # Find relevant discussion insights for this strategy
            relevant_insights = []
            if self.discussion_strategies:
                for disc_strategy in self.discussion_strategies:
                    if any(keyword in strategy.lower() for keyword in disc_strategy['strategy_name'].lower().split()):
                        relevant_insights.append(disc_strategy['description'])

            task_md = f"""# Experiment Task: {exp_id}

**Iteration:** {iteration}
**Strategy:** {strategy}
**Competition:** {comp_info.name} ({comp_info.evaluation_metric})

## Parameters
```json
{json.dumps(params, indent=2)}
```

{f'''## Community Insights
Based on discussion analysis, here are relevant insights for this strategy:
{chr(10).join(f"- {{insight}}" for insight in relevant_insights[:3])}
''' if relevant_insights else ''}

## Instructions for AI Agent (WAA)

1.  **Understand the Goal:** The primary goal is to train a model using the '{strategy}' approach with the specified parameters and evaluate it using the '{comp_info.evaluation_metric}' metric.
2.  **Load Data:** Load the necessary data files: {', '.join(comp_info.data_files)}. Assume they are available in the standard data directory relative to the worktree root.
3.  **Preprocessing/Feature Engineering:** Apply preprocessing steps suitable for the '{strategy}'. If the strategy includes 'FeatureEng', implement the corresponding feature engineering logic. Use features specified in parameters if available (e.g., `feature_set`).
4.  **Model Training:**
    *   Instantiate the model based on the '{strategy}' (e.g., LightGBM, RandomForest, a simple Keras/PyTorch NN).
    *   Use the provided `parameters` for model initialization and training (e.g., learning rate, number of estimators, epochs, layers).
    *   Train the model on the training data. Implement cross-validation if appropriate for the strategy.
5.  **Prediction & Evaluation:**
    *   Generate predictions on a validation set (or via CV).
    *   Calculate the score using the '{comp_info.evaluation_metric}' metric.
    *   Generate predictions on the test set.
6.  **Output Generation:**
    *   Save the trained model (optional, if needed later).
    *   Save the validation/CV score to `result_{exp_id}.json` in the worktree root (format: `{{"score": <score_value>}}`).
    *   Save the test predictions to `submission_{exp_id}.csv` in the format required by the competition.
    *   Log key steps and results to `waa_{exp_id}.log`.
7.  **Final Step:** Create a file named `DONE_{exp_id}` in the worktree root to signal completion.

**Important:** Ensure all file paths for output are relative to the root of this Git worktree. Use the provided `experiment_id` (`{exp_id}`) in filenames.
"""
            return task_md.strip()

    def _get_dummy_params(self, strategy: str, previous_results: Optional[List[ExperimentResult]] = None) -> dict:
        """Generate placeholder parameters based on strategy."""
        if "GBM" in strategy or "LightGBM" in strategy:
            lr = random.uniform(0.01, 0.1)
            n_estimators = random.randint(100, 1000)
            # Could bias toward parameters from strong past results
            return {"learning_rate": round(lr, 4), "n_estimators": n_estimators, "feature_set": "basic"}
        elif "XGBoost" in strategy:
            return {"learning_rate": round(random.uniform(0.01, 0.3), 4), 
                    "n_estimators": random.randint(100, 1000),
                    "max_depth": random.randint(3, 10),
                    "subsample": round(random.uniform(0.6, 1.0), 2)}
        elif "CatBoost" in strategy:
            return {"learning_rate": round(random.uniform(0.01, 0.1), 4),
                    "iterations": random.randint(100, 1000),
                    "depth": random.randint(4, 10)}
        elif "NN" in strategy:
            if "Advanced" in strategy:
                return {"layers": [128, 64, 32], "dropout": round(random.uniform(0.2, 0.5), 2), 
                        "epochs": random.randint(20, 100), "batch_size": random.choice([32, 64, 128])}
            else:
                return {"layers": [64, 32], "dropout": round(random.uniform(0.1, 0.5), 2), "epochs": random.randint(10, 50)}
        elif "RandomForest" in strategy:
            return {"n_estimators": random.randint(50, 500), "max_depth": random.choice([None, 5, 10, 20])}
        elif "Ensemble" in strategy:
            return {"models": ["LightGBM", "XGBoost", "CatBoost"], 
                    "blend_method": random.choice(["weighted", "stacking", "voting"])}
        else:
            return {"param1": "dummy", "param2": random.randint(1, 10)}

    def _generate_task_markdown_from_hypothesis(self, exp_id: str, iteration: int, strategy: str,
                                               params: dict, comp_info: CompetitionInfo,
                                               hypothesis_data: Dict[str, Any],
                                               total_waas: Optional[int] = None) -> str:
        """Generate task markdown from Codex-generated hypothesis using unified template."""
        # Load unified template
        template = self._load_waa_template()

        # Generate dynamic sections
        gpu_section = self._get_gpu_instructions_section(exp_id, total_waas)
        task_content = self._generate_task_content(exp_id, iteration, strategy, params, comp_info, hypothesis_data)

        # Fill template placeholders (including exp_id for status management instructions)
        return template.format(
            gpu_allocation_section=gpu_section,
            task_content=task_content,
            exp_id=exp_id
        )

    def _generate_task_markdown(self, exp_id: str, iteration: int, strategy: str, params: dict,
                                comp_info: CompetitionInfo, total_waas: Optional[int] = None) -> str:
        """Generate task markdown for the WAA using unified template."""
        # Load unified template
        template = self._load_waa_template()

        # Generate dynamic sections
        gpu_section = self._get_gpu_instructions_section(exp_id, total_waas)
        task_content = self._generate_task_content(exp_id, iteration, strategy, params, comp_info)

        # Fill template placeholders (including exp_id for status management instructions)
        return template.format(
            gpu_allocation_section=gpu_section,
            task_content=task_content,
            exp_id=exp_id
        )

    def _get_gpu_instructions_section(self, exp_id: str, total_waas: Optional[int] = None) -> str:
        """
        Return GPU allocation instructions for WAA prompts.

        Args:
            exp_id: Experiment ID (e.g., "iter0_exp2_abc123")
            total_waas: Total number of parallel WAAs. If None, uses wca_per_iteration config.

        Returns:
            GPU allocation instructions as a string
        """
        if total_waas is None:
            total_waas = self.wca_per_iteration

        # Get GPU allocation for this WAA
        waa_index = GPUAllocator.parse_waa_index(exp_id)
        allocation = self.gpu_allocator.allocate(waa_index, total_waas)

        # The allocator generates complete, context-aware instructions
        return allocation.prompt_instructions

    # ========== Evolution Hypothesis Generation ==========

    def generate_evolution_hypotheses(
        self,
        competition_info: CompetitionInfo,
        current_iteration: int,
        num_hypotheses: int,
        analysis_result: AnalysisResult,
        previous_results: List[ExperimentResult],
        persistent_experiments: Dict[str, str],  # {exp_id: worktree_path}
        official_scores: Optional[Dict[str, float]] = None
    ) -> Tuple[List[ContinuationHypothesis], List[ExperimentHypothesis]]:
        """
        Generate evolution hypotheses based on PA decisions.

        Separates experiments into:
        - ContinuationHypothesis: For experiments marked CONTINUE (reuse existing worktree)
        - ExperimentHypothesis: For freed slots from TERMINATE decisions (new worktree)

        Args:
            competition_info: Competition information
            current_iteration: Current iteration number
            num_hypotheses: Total number of experiments to run (maintain configured count)
            analysis_result: AnalysisResult with experiment_decisions populated
            previous_results: List of previous experiment results
            persistent_experiments: Dict mapping experiment_id to worktree_path
            official_scores: Optional official scores

        Returns:
            Tuple of (continuation_hypotheses, new_hypotheses)
        """
        method_name = "generate_evolution_hypotheses"
        self._log_start(method_name, iteration=current_iteration, num_hypotheses=num_hypotheses)

        continuation_hypotheses: List[ContinuationHypothesis] = []
        new_hypotheses: List[ExperimentHypothesis] = []

        # Get decisions from analysis
        decisions = analysis_result.experiment_decisions
        if not decisions:
            self.logger.warning("No evolution decisions found, falling back to standard hypothesis generation")
            new_hypotheses = self.generate_next_hypotheses(
                competition_info, current_iteration, num_hypotheses,
                analysis_result, previous_results, official_scores
            )
            return continuation_hypotheses, new_hypotheses

        # Separate CONTINUE and TERMINATE decisions
        continue_decisions = [d for d in decisions if d.decision == ExperimentDecisionType.CONTINUE]
        terminate_decisions = [d for d in decisions if d.decision == ExperimentDecisionType.TERMINATE]

        self.logger.info(
            f"Evolution: {len(continue_decisions)} CONTINUE, {len(terminate_decisions)} TERMINATE"
        )

        # Create continuation hypotheses for CONTINUE decisions
        occupied_slots: set[int] = set()
        for decision in continue_decisions:
            exp_id = decision.experiment_id
            worktree_path = persistent_experiments.get(exp_id)

            if not worktree_path:
                self.logger.warning(f"No worktree found for {exp_id}, treating as TERMINATE")
                terminate_decisions.append(decision)
                continue

            # Record the slot (expN) occupied by this continued worktree so that new hypotheses
            # can be generated for the freed slots without colliding on GPU/WAA allocation.
            worktree_id = os.path.basename(os.path.normpath(worktree_path))
            slot_num = self._extract_exp_slot_number(worktree_id) or self._extract_exp_slot_number(exp_id)
            if slot_num is None:
                # As a last resort, try to infer from any key that maps to the same worktree.
                for key, path in persistent_experiments.items():
                    if path == worktree_path:
                        slot_num = self._extract_exp_slot_number(key)
                        if slot_num is not None:
                            break
            if slot_num is not None:
                occupied_slots.add(slot_num)
            else:
                self.logger.warning(
                    f"Could not infer exp slot number for continued experiment {exp_id} "
                    f"(worktree={worktree_path}); GPU allocation may be degraded."
                )

            # Find the previous result for this experiment
            prev_result = next((r for r in previous_results if r.experiment_id == exp_id), None)
            if not prev_result:
                self.logger.warning(f"No previous result found for {exp_id}")
                continue

            continuation = self._create_continuation_hypothesis(
                decision=decision,
                iteration=current_iteration,
                worktree_path=worktree_path,
                prev_result=prev_result,
                competition_info=competition_info,
                total_waas=num_hypotheses
            )
            continuation_hypotheses.append(continuation)

        # Determine which WAA slots are free this iteration.
        all_slots = list(range(1, num_hypotheses + 1))
        free_slots = [s for s in all_slots if s not in occupied_slots]
        self.logger.info(f"Creating {len(free_slots)} new hypotheses for freed slots: {free_slots}")

        if free_slots:
            # Generate new hypotheses for freed slots
            # Include context about what was terminated and why
            terminated_context = self._build_termination_context(terminate_decisions)

            new_hypotheses = self._generate_new_hypotheses_for_slots(
                competition_info=competition_info,
                current_iteration=current_iteration,
                slot_numbers=free_slots,
                analysis_result=analysis_result,
                previous_results=previous_results,
                official_scores=official_scores,
                terminated_context=terminated_context,
                total_waas=num_hypotheses
            )

        self._log_end(
            method_name,
            result=f"{len(continuation_hypotheses)} continuations, {len(new_hypotheses)} new"
        )
        return continuation_hypotheses, new_hypotheses

    def _create_continuation_hypothesis(
        self,
        decision: ExperimentDecision,
        iteration: int,
        worktree_path: str,
        prev_result: ExperimentResult,
        competition_info: CompetitionInfo,
        total_waas: int
    ) -> ContinuationHypothesis:
        """
        Create a ContinuationHypothesis from a CONTINUE decision.

        Args:
            decision: The CONTINUE decision from PA
            iteration: Current iteration number
            worktree_path: Path to existing worktree
            prev_result: Previous experiment result
            competition_info: Competition information
            total_waas: Total number of WAAs running in parallel

        Returns:
            ContinuationHypothesis object
        """
        exp_id = decision.experiment_id
        worktree_id = os.path.basename(os.path.normpath(worktree_path))
        slot_num = self._extract_exp_slot_number(worktree_id) or self._extract_exp_slot_number(exp_id)
        if slot_num is None:
            self.logger.warning(
                f"Could not infer exp slot number for continuation parent={exp_id} "
                f"(worktree={worktree_path}); defaulting to exp1."
            )
            slot_num = 1

        # Preserve the parent worktree suffix for stable lineage naming across iterations.
        suffix = worktree_id.split("_")[-1] if worktree_id else exp_id.split("_")[-1]
        continuation_id = f"iter{iteration}_exp{slot_num}_cont_{suffix}"

        # Generate continuation task markdown
        task_markdown = self._generate_continuation_task_markdown(
            decision=decision,
            continuation_id=continuation_id,
            prev_result=prev_result,
            competition_info=competition_info,
            total_waas=total_waas
        )

        # Save task markdown
        task_md_path = Path(self.hypothesis_dir) / f"iter{iteration}" / f"{continuation_id}_task.md"
        task_md_path.parent.mkdir(parents=True, exist_ok=True)
        task_md_path.write_text(task_markdown, encoding="utf-8")

        return ContinuationHypothesis(
            experiment_id=exp_id,  # Original ID preserved
            continuation_id=continuation_id,
            iteration=iteration,
            original_strategy_name=prev_result.strategy_name,
            improvement_instructions=decision.improvement_instructions or "",
            new_parameters=prev_result.parameters or {},
            worktree_path=worktree_path,
            task_markdown_path=str(task_md_path),
            parent_score=prev_result.score or 0.0
        )

    def _generate_continuation_task_markdown(
        self,
        decision: ExperimentDecision,
        continuation_id: str,
        prev_result: ExperimentResult,
        competition_info: CompetitionInfo,
        total_waas: int
    ) -> str:
        """
        Generate task markdown for a continuation experiment.

        This provides context about the parent experiment and PA's improvement instructions.
        """
        # Load continuation template if available
        template_path = Path(self.prompts_dir) / "KSE" / "kse_continuation_template.md"

        if template_path.exists():
            template = template_path.read_text(encoding="utf-8")
            # Fill placeholders
            filled = template.replace("{{CONTINUATION_ID}}", continuation_id)
            filled = filled.replace("{{ORIGINAL_EXP_ID}}", decision.experiment_id)
            filled = filled.replace("{{ORIGINAL_STRATEGY}}", prev_result.strategy_name)
            filled = filled.replace("{{PARENT_SCORE}}", f"{prev_result.score:.4f}" if prev_result.score else "N/A")
            filled = filled.replace("{{IMPROVEMENT_INSTRUCTIONS}}", decision.improvement_instructions or "No specific instructions")
            filled = filled.replace("{{REASONING}}", decision.reasoning)
            filled = filled.replace("{{POTENTIAL_CEILING}}", f"{decision.potential_ceiling:.4f}" if decision.potential_ceiling else "Unknown")
            filled = filled.replace("{{COMPETITION_NAME}}", competition_info.name)
            filled = filled.replace("{{EVALUATION_METRIC}}", competition_info.evaluation_metric)

            # Wrap with WAA template
            waa_template = self._load_waa_template()
            gpu_section = self._get_gpu_instructions_section(continuation_id, total_waas)
            return waa_template.format(
                gpu_allocation_section=gpu_section,
                task_content=filled,
                exp_id=continuation_id
            )
        else:
            # Generate inline continuation task
            return self._generate_inline_continuation_task(
                decision=decision,
                continuation_id=continuation_id,
                prev_result=prev_result,
                competition_info=competition_info,
                total_waas=total_waas
            )

    def _generate_inline_continuation_task(
        self,
        decision: ExperimentDecision,
        continuation_id: str,
        prev_result: ExperimentResult,
        competition_info: CompetitionInfo,
        total_waas: int
    ) -> str:
        """Generate continuation task markdown without external template."""
        task_content = f"""# Continuation Experiment: {continuation_id}

## Context: Building on Previous Success

This is a **CONTINUATION** of experiment `{decision.experiment_id}`.

### Parent Experiment Summary
- **Original Strategy:** {prev_result.strategy_name}
- **Previous Score:** {prev_result.score:.4f if prev_result.score else 'N/A'}
- **Potential Ceiling:** {decision.potential_ceiling:.4f if decision.potential_ceiling else 'Unknown'}

### Why Continuing This Experiment
{decision.reasoning}

---

## PA's Improvement Instructions (FOLLOW THESE)

{decision.improvement_instructions or 'No specific instructions provided - use your judgment to improve.'}

---

## Your Task

1. **Review** the existing code and results in this worktree
2. **Implement** the improvements specified above
3. **Do NOT** start from scratch - build on what exists
4. **Maintain** the same CV scheme for comparability
5. **Document** what changes you made and why

## Expected Outputs

- `result_{continuation_id}.json` with the new validation score
- `submission_{continuation_id}.csv` in competition format
- `waa_{continuation_id}.log` with implementation details
- `DONE_{continuation_id}` marker when complete

## Success Criteria

- Score improves from {prev_result.score:.4f if prev_result.score else 'baseline'}
- Changes are well-documented
- Implementation follows PA's instructions
- Outputs are correctly formatted

---

**Competition:** {competition_info.name}
**Metric:** {competition_info.evaluation_metric}
"""

        # Wrap with WAA template
        waa_template = self._load_waa_template()
        gpu_section = self._get_gpu_instructions_section(continuation_id, total_waas)
        return waa_template.format(
            gpu_allocation_section=gpu_section,
            task_content=task_content,
            exp_id=continuation_id
        )

    def _build_termination_context(self, terminate_decisions: List[ExperimentDecision]) -> str:
        """Build context about terminated experiments for new hypothesis generation."""
        if not terminate_decisions:
            return "No experiments were terminated."

        lines = ["## Terminated Experiments (Do NOT repeat these approaches)\n"]
        for decision in terminate_decisions:
            lines.append(f"### {decision.experiment_id}")
            lines.append(f"- **Reason:** {decision.termination_reason or decision.reasoning}")
            lines.append(f"- **Confidence:** {decision.confidence:.2f}")
            lines.append("")

        lines.append("\n**Important:** Generate NEW approaches that avoid the pitfalls above.")
        return "\n".join(lines)

    def _generate_new_hypotheses_for_slots(
        self,
        competition_info: CompetitionInfo,
        current_iteration: int,
        slot_numbers: List[int],
        analysis_result: AnalysisResult,
        previous_results: List[ExperimentResult],
        official_scores: Optional[Dict[str, float]],
        terminated_context: str,
        total_waas: int
    ) -> List[ExperimentHypothesis]:
        """
        Generate new hypotheses for slots freed by TERMINATE decisions.

        Includes context about what was terminated to avoid repeating failures.
        """
        self.logger.info(f"Generating {len(slot_numbers)} new hypotheses for freed slots: {slot_numbers}")

        exp_ids = self._build_experiment_ids_for_slots(current_iteration, slot_numbers)

        if self.use_codex_for_generation:
            # Use Codex with termination context
            return self._generate_hypotheses_with_codex(
                competition_info=competition_info,
                num_hypotheses=len(exp_ids),
                iteration=current_iteration,
                is_initial=False,
                analysis_result=analysis_result,
                previous_results=previous_results,
                official_scores=official_scores,
                exp_ids=exp_ids,
                total_waas=total_waas
            )
        else:
            # Fallback to programmatic generation
            return self._generate_programmatic_hypotheses(
                iteration=current_iteration,
                num_hypotheses=len(exp_ids),
                competition_info=competition_info,
                previous_results=previous_results,
                exp_ids=exp_ids,
                total_waas=total_waas
            )
