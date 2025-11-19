import os
import sys
import json
import time
import random
import argparse
import logging
from datetime import datetime, timedelta

# Add project root to sys.path to fix imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from src.utils.file_utils import ensure_dir, write_json, read_markdown

def setup_wca_logger(log_file: str, level: str = "INFO"):
    """WCA用ロガーのセットアップ"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    log_level = level_map.get(level, logging.INFO)
    
    logger = logging.getLogger('AutoKaggle.WCA')
    logger.setLevel(log_level)
    
    # 既存のハンドラをすべて削除
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # ファイルハンドラ
    file_handler = logging.FileHandler(log_file)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # コンソールハンドラ（親のコンソールが出力する場合は不要かも）
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    return logger

def run_wca_simulation(args):
    """WCAシミュレータのメイン処理"""
    # ロガー設定
    log_file = os.path.join(args.worktree_path, f"wca_{args.experiment_id}.log")
    logger = setup_wca_logger(log_file, args.log_level)
    logger.info(f"WCA Simulator started for experiment {args.experiment_id}")
    
    try:
        # 開始時間記録
        start_time = datetime.now()
        logger.info(f"Start time: {start_time}")
        
        # タスク指示ファイルを読み込み
        logger.info(f"Reading task instructions from {args.task_markdown_path}")
        task_instructions = read_markdown(args.task_markdown_path)
        if not task_instructions:
            raise Exception(f"Failed to read task instructions from {args.task_markdown_path}")
        
        # タスク指示をログに記録（実際のClaudeなら理解する）
        logger.info(f"Task Instructions Summary: {args.task_markdown_path} (length: {len(task_instructions)} chars)")
        
        # 作業時間のシミュレーション
        work_duration = random.randint(5, 15)  # 5～15秒のランダムな時間
        logger.info(f"Simulating work for {work_duration} seconds...")
        time.sleep(work_duration)
        
        # スコア生成（スコアなし、失敗のシミュレーションもたまに行う）
        failure_chance = 0.2  # 20%の確率で失敗
        will_fail = random.random() < failure_chance
        
        if will_fail:
            # 失敗のシミュレーション
            logger.error("Simulated failure occurred while processing the task.")
            with open(os.path.join(args.worktree_path, f"ERROR_{args.experiment_id}.log"), 'w') as f:
                f.write(f"Simulated error at {datetime.now()}\n\nThis is a simulated error for testing the failure handling.")
            
            status = "FAILURE"
            score = None
        else:
            # 成功のシミュレーション
            score = random.uniform(0.6, 0.99)  # 0.6～0.99のランダムなスコア
            logger.info(f"Task completed successfully with score: {score:.4f}")
            status = "SUCCESS"
            
            # result JSONファイル作成
            result_data = {
                "score": score,
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat()
            }
            result_file = os.path.join(args.worktree_path, f"result_{args.experiment_id}.json")
            write_json(result_data, result_file)
            logger.info(f"Saved result to {result_file}")
            
            # ダミーのsubmissionファイル作成
            submission_file = os.path.join(args.worktree_path, f"submission_{args.experiment_id}.csv")
            with open(submission_file, 'w') as f:
                f.write(f"id,target\n1,0.{random.randint(1, 9)}\n2,0.{random.randint(1, 9)}")
            logger.info(f"Created dummy submission file at {submission_file}")
            
            # ダミーのモデルファイル作成
            model_file = os.path.join(args.worktree_path, f"model_{args.experiment_id}.pkl")
            with open(model_file, 'w') as f:
                f.write("This is a dummy model file.")
            logger.info(f"Created dummy model file at {model_file}")
        
        # 終了時間記録
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        logger.info(f"End time: {end_time}")
        logger.info(f"Execution time: {execution_time:.2f} seconds")
        
        # 完了ファイル作成
        done_file = os.path.join(args.worktree_path, f"DONE_{args.experiment_id}")
        with open(done_file, 'w') as f:
            f.write(status)
        logger.info(f"Created DONE file with status: {status}")
        
        logger.info(f"WCA Simulator completed for experiment {args.experiment_id}")
        return 0
    
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        # エラーログ作成
        error_file = os.path.join(args.worktree_path, f"ERROR_{args.experiment_id}.log")
        import traceback
        with open(error_file, 'w') as f:
            f.write(f"Error at {datetime.now()}\n\n{str(e)}\n\n{traceback.format_exc()}")
        
        # 完了ファイル作成（失敗状態）
        done_file = os.path.join(args.worktree_path, f"DONE_{args.experiment_id}")
        with open(done_file, 'w') as f:
            f.write("FAILURE")
        
        logger.error(f"WCA Simulator failed for experiment {args.experiment_id}")
        return 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Worker Claude Agent Simulator')
    parser.add_argument('--worktree-path', required=True, help='Path to the git worktree for this experiment')
    parser.add_argument('--task-markdown-path', required=True, help='Path to the task markdown file')
    parser.add_argument('--experiment-id', required=True, help='Unique ID for this experiment')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Logging level')
    
    args = parser.parse_args()
    
    # ディレクトリが存在することを確認
    if not os.path.exists(args.worktree_path):
        print(f"Error: Worktree path does not exist: {args.worktree_path}")
        sys.exit(1)
    
    if not os.path.exists(args.task_markdown_path):
        print(f"Error: Task markdown file does not exist: {args.task_markdown_path}")
        sys.exit(1)
    
    sys.exit(run_wca_simulation(args))