import os
import json
import datetime
from typing import List, Dict, Optional

from ..core.base_component import BaseComponent
from ..data_models import ExperimentResult, ExperimentHypothesis
from ..utils.file_utils import ensure_dir, read_json, copy_file, move_file, write_json, read_markdown

class ResultAggregatorDatabase(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.results_base_dir = os.path.join(config.get("experiments_base_dir", "./experiments"), "results")
        self.manifest_file = os.path.join(self.results_base_dir, "results_manifest.json")
        ensure_dir(self.results_base_dir)
        self.results_cache: Dict[str, ExperimentResult] = self._load_manifest()

    def _load_manifest(self) -> Dict[str, ExperimentResult]:
        """マニフェストファイルから結果をロード"""
        manifest_data = read_json(self.manifest_file)
        cache = {}
        if manifest_data:
            # JSONからExperimentResultオブジェクトに変換（簡易版）
            # 本格的にはdataclasses-jsonなどを使うと良い
            for exp_id, data in manifest_data.items():
                 try:
                     # 日付時刻文字列をdatetimeオブジェクトに変換
                     data['start_time'] = datetime.datetime.fromisoformat(data['start_time']) if data.get('start_time') else None
                     data['end_time'] = datetime.datetime.fromisoformat(data['end_time']) if data.get('end_time') else None
                     # execution_time_seconds がない場合やNoneの場合の処理
                     if 'execution_time_seconds' not in data or data['execution_time_seconds'] is None:
                         if data.get('start_time') and data.get('end_time'):
                            data['execution_time_seconds'] = (data['end_time'] - data['start_time']).total_seconds()
                         else:
                            data['execution_time_seconds'] = 0.0 # または適切なデフォルト値

                     cache[exp_id] = ExperimentResult(**data)
                 except Exception as e:
                     self.logger.error(f"Error loading result data for {exp_id} from manifest: {e}")
            self.logger.info(f"Loaded {len(cache)} results from manifest.")
        else:
             self.logger.info("Manifest file not found or empty. Starting with empty cache.")
        return cache

    def _save_manifest(self):
        """現在の結果キャッシュをマニフェストファイルに保存"""
        # ExperimentResultオブジェクトをJSONシリアライズ可能な辞書に変換（簡易版）
        serializable_data = {}
        for exp_id, result in self.results_cache.items():
            data = result.__dict__.copy()
            data['start_time'] = result.start_time.isoformat() if result.start_time else None
            data['end_time'] = result.end_time.isoformat() if result.end_time else None
            serializable_data[exp_id] = data

        write_json(serializable_data, self.manifest_file)

    def collect_result(self, exp_id: str, worktree_path: str) -> Optional[ExperimentResult]:
        """指定されたWorktreeから実験結果を収集し、DB（ファイル）に保存"""
        method_name = "collect_result"
        self._log_start(method_name, exp_id=exp_id, worktree_path=worktree_path)

        if not os.path.exists(worktree_path):
             self.logger.error(f"Worktree path does not exist: {worktree_path}")
             return None

        done_file_path = os.path.join(worktree_path, f"DONE_{exp_id}")
        result_json_path = os.path.join(worktree_path, f"result_{exp_id}.json")
        wca_log_path = os.path.join(worktree_path, f"wca_{exp_id}.log")
        error_log_path = os.path.join(worktree_path, f"ERROR_{exp_id}.log") # WCAが異常終了した場合

        status = "UNKNOWN"
        if os.path.exists(done_file_path):
             with open(done_file_path, 'r') as f:
                 status = f.read().strip()
        else:
             self.logger.warning(f"DONE file not found for {exp_id}. Assuming failure.")
             status = "FAILURE_NO_DONE_FILE"


        result_data = read_json(result_json_path)
        score = result_data.get("score") if result_data else None
        error_message = None
        if status != "SUCCESS":
             if os.path.exists(error_log_path):
                  error_message = read_markdown(error_log_path) # エラーログの内容を読む
             elif status == "UNEXPECTED_FAILURE":
                  error_message = "WCA process terminated unexpectedly."
             elif status == "FAILURE_NO_DONE_FILE":
                  error_message = "DONE file was not created."
             else: # status == "FAILURE" from DONE file
                  # WCAログからエラーを探すことも可能（今回は省略）
                  error_message = "Simulated WCA failure or error during execution."


        # 結果ファイルのリストアップとコピー
        collected_files_relative = [] # results_dir基準の相対パス
        exp_result_dir = os.path.join(self.results_base_dir, exp_id)
        ensure_dir(exp_result_dir)

        # WCAログは必ずコピー
        collected_log_path_relative = os.path.join(exp_id, os.path.basename(wca_log_path))
        collected_log_path_absolute = os.path.join(self.results_base_dir, collected_log_path_relative)
        if os.path.exists(wca_log_path):
            copy_file(wca_log_path, collected_log_path_absolute)
        else:
             self.logger.warning(f"WCA log file not found: {wca_log_path}")
             collected_log_path_relative = None # ログが見つからない場合

        # その他の生成された可能性のあるファイル (submission, modelなど)
        potential_files = [f"submission_{exp_id}.csv", f"model_{exp_id}.pkl"] # 他にもあれば追加
        for fname in potential_files:
            src_path = os.path.join(worktree_path, fname)
            if os.path.exists(src_path):
                dst_relative = os.path.join(exp_id, fname)
                dst_absolute = os.path.join(self.results_base_dir, dst_relative)
                copy_file(src_path, dst_absolute)
                collected_files_relative.append(dst_relative)

        # ExperimentResultオブジェクト作成 (開始/終了時間は仮)
        # TODO: KSEから仮説情報を取得してiteration, strategy_name, parametersを埋める必要あり
        #       現状ではこれらの情報はWorktree内にはないので、MCDUから渡すか、
        #       exp_idから復元する仕組みが必要。ここではダミー値を入れる。
        dummy_start = datetime.datetime.now() - datetime.timedelta(minutes=1)
        dummy_end = datetime.datetime.now()
        dummy_duration = (dummy_end-dummy_start).total_seconds()

        result = ExperimentResult(
            experiment_id=exp_id,
            iteration=-1, # 要取得
            strategy_name="Unknown", # 要取得
            parameters={}, # 要取得
            start_time=dummy_start, # WCAシミュレータ内で記録・保存すべき
            end_time=dummy_end,     # WCAシミュレータ内で記録・保存すべき
            execution_time_seconds=dummy_duration, # WCAシミュレータ内で計算・保存すべき
            score=score,
            result_files=collected_files_relative,
            log_path=collected_log_path_relative if collected_log_path_relative else "log_not_found",
            status=status,
            error_message=error_message
        )

        self.results_cache[exp_id] = result
        self._save_manifest() # 結果をファイルに永続化

        self.logger.info(f"Collected result for {exp_id}. Status: {status}, Score: {score}")
        self._log_end(method_name, result=result)
        return result

    def get_result(self, exp_id: str) -> Optional[ExperimentResult]:
        """指定された実験IDの結果を取得"""
        return self.results_cache.get(exp_id)

    def get_all_results(self) -> List[ExperimentResult]:
        """すべての実験結果を取得"""
        return list(self.results_cache.values())

    def get_results_by_iteration(self, iteration: int) -> List[ExperimentResult]:
        """指定されたイテレーションの実験結果を取得"""
        return [res for res in self.results_cache.values() if res.iteration == iteration]

    def update_result_metadata(self, exp_id: str, hypothesis: ExperimentHypothesis):
        """収集後、仮説情報を使って結果のメタデータを更新する"""
        if exp_id in self.results_cache:
            result = self.results_cache[exp_id]
            result.iteration = hypothesis.iteration
            result.strategy_name = hypothesis.strategy_name
            result.parameters = hypothesis.parameters
            # TODO: WCAが開始/終了時間/実行時間を記録・保存するように変更した場合、
            #       ここでその情報をresult_{exp_id}.jsonから読み込んで設定する
            self._save_manifest()
            self.logger.info(f"Updated metadata for result {exp_id}")
        else:
             self.logger.warning(f"Cannot update metadata. Result not found for {exp_id}")