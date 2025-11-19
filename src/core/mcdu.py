import os
import time
import json
from typing import Dict, List, Optional

from .base_component import BaseComponent
from .kim import KaggleInterfaceManager
from .kse import KnowledgeStrategyEngine
from ..execution.eo import ExperimentOrchestrator
from ..analysis.rad import ResultAggregatorDatabase
from ..analysis.pa import PerformanceAnalyzer
from ..data_models import CompetitionInfo, ExperimentHypothesis, ExperimentResult, AnalysisResult

class MasterControllerDecisionUnit(BaseComponent):
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        super().__init__(self.config) # BaseComponentの初期化

        # コンポーネントの初期化
        self.kim = KaggleInterfaceManager(self.config)
        self.kse = KnowledgeStrategyEngine(self.config)
        self.eo = ExperimentOrchestrator(self.config)
        self.rad = ResultAggregatorDatabase(self.config)
        self.pa = PerformanceAnalyzer(self.config)

        # 状態変数
        self.current_iteration = 0
        self.max_iterations = self.config.get("max_iterations", 5)
        self.wca_per_iteration = self.config.get("wca_per_iteration", 3)
        self.competition_info: Optional[CompetitionInfo] = None
        self.all_results: Dict[int, List[ExperimentResult]] = {} # {iteration: [results]}
        self.best_score_overall: Optional[float] = None
        self.best_experiment_id_overall: Optional[str] = None
        self.iterations_without_improvement = 0
        self.stop_reason: Optional[str] = None

        # 停止条件の設定読み込み
        stop_config = self.config.get("stop_condition", {})
        self.score_threshold = stop_config.get("score_threshold")
        self.no_improvement_threshold = stop_config.get("no_improvement_iterations", 3)


    def _load_config(self, config_path: str) -> dict:
        """設定ファイルをロード"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"Configuration loaded from {config_path}") # logger初期化前なのでprint
            return config
        except FileNotFoundError:
            print(f"Error: Configuration file not found at {config_path}")
            raise
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {config_path}")
            raise
        except Exception as e:
            print(f"Error loading configuration: {e}")
            raise

    def run_main_loop(self):
        """メインの実行ループ"""
        self._log_start("run_main_loop")

        # 1. 初期化：コンペ情報取得＆データダウンロード
        self.competition_info = self.kim.get_competition_info()
        if not self.competition_info:
            self.logger.critical("Failed to get competition info. Exiting.")
            return
        if not self.kim.download_data_files(self.competition_info):
             self.logger.warning("Failed to download/verify data files. Continuing, but WCA might fail.")
             # ここで停止する判断もあり

        # 2. メインループ
        while not self._should_stop():
            self.logger.info(f"--- Starting Iteration {self.current_iteration} ---")

            # 2a. 仮説生成
            hypotheses = self._generate_hypotheses_for_iteration()
            if not hypotheses:
                 self.logger.warning(f"No hypotheses generated for iteration {self.current_iteration}. Stopping.")
                 self.stop_reason = "Hypothesis generation failed"
                 break

            # 2b. 実験実行開始
            launched_ids = self.eo.launch_experiments(hypotheses)
            if not launched_ids:
                 self.logger.warning(f"No experiments were launched for iteration {self.current_iteration}. Stopping.")
                 self.stop_reason = "Experiment launch failed"
                 break

            running_experiments = set(launched_ids)
            hypotheses_map = {h.experiment_id: h for h in hypotheses} # IDから仮説を引けるように

            # 2c. 実験完了待ち＆結果収集
            iteration_results = []
            while running_experiments:
                time.sleep(10) # 10秒ごとにチェック
                completed_ids = self.eo.check_running_experiments()
                newly_completed = running_experiments.intersection(completed_ids)

                if newly_completed:
                     self.logger.info(f"Experiments completed: {list(newly_completed)}")
                     for exp_id in newly_completed:
                         worktree_path = self.eo.get_worktree_path(exp_id)
                         result = self.rad.collect_result(exp_id, worktree_path)
                         if result:
                              # RADに収集させた後、仮説情報でメタデータを更新
                              if exp_id in hypotheses_map:
                                   self.rad.update_result_metadata(exp_id, hypotheses_map[exp_id])
                                   result = self.rad.get_result(exp_id) # 更新後の結果を再取得
                                   iteration_results.append(result)
                              else:
                                   self.logger.error(f"Hypothesis not found for completed experiment {exp_id}!")
                         else:
                              self.logger.error(f"Failed to collect result for {exp_id}")

                         # Worktreeのクリーンアップ
                         self.eo.cleanup_worktree(exp_id, worktree_path)

                     running_experiments -= newly_completed
                     self.logger.info(f"Remaining experiments in iteration: {len(running_experiments)}")

            self.all_results[self.current_iteration] = iteration_results

            # 2d. パフォーマンス分析
            analysis_result = self.pa.analyze_results(self.current_iteration, iteration_results)

            # 2e. 全体のベストスコア更新と改善チェック
            self._update_overall_best(analysis_result)

            self.current_iteration += 1
            self.logger.info(f"--- Finished Iteration {self.current_iteration - 1} ---")
            # ループ終了条件チェックは次回のループ開始時に _should_stop で行われる

        # 3. 終了処理
        self.logger.info("Main loop finished.")
        self._final_reporting()
        self._log_end("run_main_loop")

    def _should_stop(self) -> bool:
        """ループを停止すべきか判断する"""
        if self.stop_reason:
             self.logger.info(f"Stopping loop. Reason: {self.stop_reason}")
             return True

        if self.current_iteration >= self.max_iterations:
            self.stop_reason = f"Reached max iterations ({self.max_iterations})"
            self.logger.info(self.stop_reason)
            return True

        if self.score_threshold and self.best_score_overall and self.best_score_overall >= self.score_threshold:
            self.stop_reason = f"Achieved score threshold ({self.score_threshold}) with score {self.best_score_overall:.4f}"
            self.logger.info(self.stop_reason)
            return True

        if self.iterations_without_improvement >= self.no_improvement_threshold:
             self.stop_reason = f"No improvement in best score for {self.no_improvement_threshold} iterations."
             self.logger.info(self.stop_reason)
             return True

        # TODO: 予算や残り時間などの条件も追加可能

        return False

    def _generate_hypotheses_for_iteration(self) -> List[ExperimentHypothesis]:
        """現在のイテレーションのための仮説を生成する"""
        if self.current_iteration == 0:
            return self.kse.generate_initial_hypotheses(self.competition_info, self.wca_per_iteration)
        else:
            # 前回の分析結果と全結果履歴を渡す
            last_iteration = self.current_iteration - 1
            last_analysis = self.pa.analyze_results(last_iteration, self.all_results.get(last_iteration, [])) # 再分析？or 保存したものを利用
            all_past_results = [res for iter_res in self.all_results.values() for res in iter_res]
            return self.kse.generate_next_hypotheses(self.competition_info,
                                                      self.current_iteration,
                                                      self.wca_per_iteration,
                                                      last_analysis,
                                                      all_past_results)

    def _update_overall_best(self, analysis_result: AnalysisResult):
        """分析結果に基づき、全体のベストスコアを更新し、改善がなかった回数をカウント"""
        current_best_iter_score = analysis_result.best_score
        initial_best_score = self.best_score_overall

        if current_best_iter_score is not None:
            if self.best_score_overall is None or current_best_iter_score > self.best_score_overall:
                self.best_score_overall = current_best_iter_score
                self.best_experiment_id_overall = analysis_result.best_experiment_id
                self.iterations_without_improvement = 0 # 改善したのでリセット
                self.logger.info(f"New overall best score: {self.best_score_overall:.4f} (Exp ID: {self.best_experiment_id_overall})")
            else:
                 # スコアが同じか低い場合
                 if initial_best_score is not None: # 初回イテレーションでない場合
                     self.iterations_without_improvement += 1
                     self.logger.info(f"Best score did not improve. Iterations without improvement: {self.iterations_without_improvement}")
        else:
             # 今回のイテレーションで有効なスコアがなかった場合
             if initial_best_score is not None: # 初回イテレーションでない場合
                 self.iterations_without_improvement += 1
                 self.logger.info(f"No valid score in this iteration. Iterations without improvement: {self.iterations_without_improvement}")


    def _final_reporting(self):
        """最終結果のレポート"""
        self.logger.info("--- Final Report ---")
        if self.best_score_overall is not None:
            self.logger.info(f"Overall Best Score: {self.best_score_overall:.4f}")
            self.logger.info(f"Best Experiment ID: {self.best_experiment_id_overall}")
            # 最良の結果の詳細を表示 (RADから取得)
            best_result = self.rad.get_result(self.best_experiment_id_overall)
            if best_result:
                 self.logger.info(f"Best Result Details: {best_result}")
                 # ここで提出処理を呼び出す (今回はログ出力のみ)
                 submission_file = next((f for f in best_result.result_files if 'submission' in f), None)
                 if submission_file:
                      submission_path_absolute = os.path.join(self.rad.results_base_dir, submission_file)
                      self.logger.info(f"Simulating submission of: {submission_path_absolute}")
                      self.kim.submit_predictions(submission_path_absolute, f"Final submission based on {self.best_experiment_id_overall}")
                 else:
                      self.logger.warning("Submission file not found for the best experiment.")

        else:
            self.logger.info("No successful experiments were completed.")
        self.logger.info(f"Stopped due to: {self.stop_reason}")
        self.logger.info(f"Total iterations: {self.current_iteration}")
