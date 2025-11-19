import logging
import datetime
import os
import zipfile
import subprocess
import sys
import json
from typing import Optional, List, Dict, Any

from .base_component import BaseComponent
from ..data_models import CompetitionInfo
from ..utils.file_utils import ensure_dir, write_json, read_json
from ..utils.crawler_parser import parse_competition_info
from ..utils.claude_code_wrapper import ClaudeCodeWrapper

class KaggleInterfaceManager(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.competition_name = config.get("kaggle_competition_name", "dummy-competition")
        self.download_dir = os.path.join(config.get("experiments_base_dir", "./experiments"), "kaggle_data")
        ensure_dir(self.download_dir)
        self.api = self._authenticate_kaggle()
        self.simulation_mode = config.get("simulation_mode", False)
        self.use_crawler = config.get("use_crawler", True)  # Default to using crawler
        self.crawler_output_dir = "kaggle_competitions"
        self.max_discussions = config.get("max_discussions", 20)

    def _authenticate_kaggle(self):
        """Kaggle APIの認証を行う"""
        try:
            # Import here to avoid authentication at module import time
            from kaggle.api.kaggle_api_extended import KaggleApi
            api = KaggleApi()
            api.authenticate()
            self.logger.info("Kaggle API authenticated successfully.")
            return api
        except ImportError:
            self.logger.error("Could not import Kaggle API. Try 'uv add kaggle'.")
            return None
        except Exception as e:
            self.logger.error(f"Kaggle API authentication failed: {e}")
            self.logger.warning("Falling back to simulation mode.")
            return None
    
    def _run_crawler(self, force: bool = False) -> bool:
        """Run kaggle_crawler to fetch competition data"""
        try:
            crawler_script = os.path.join("src", "kaggle_crawler", "crawl_kaggle_competition.py")
            if not os.path.exists(crawler_script):
                self.logger.error(f"Crawler script not found: {crawler_script}")
                return False
            
            cmd = [sys.executable, crawler_script, self.competition_name, 
                   f"--max-discussions", str(self.max_discussions)]
            if force:
                cmd.append("--force")
            
            self.logger.info(f"Running kaggle_crawler for competition: {self.competition_name}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Crawler failed: {result.stderr}")
                return False
            
            self.logger.info("Crawler completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error running crawler: {e}")
            return False

    def _run_claude_analysis(self, competition_path: str) -> Optional[Dict[str, Any]]:
        """Run Claude Code to analyze competition data"""
        try:
            # Check if Claude Code is enabled
            claude_config = self.config.get("claude_code", {})
            if not claude_config.get("enabled", False):
                self.logger.info("Claude Code is not enabled, skipping analysis")
                return None
            
            # Initialize Claude Code wrapper
            wrapper = ClaudeCodeWrapper(self.config)
            
            # Create a focused prompt that avoids hanging
            simple_prompt = f"""Analyze the Kaggle competition data in this directory and create a JSON analysis file.

Competition: {self.competition_name}
Working directory: {competition_path}

Tasks:
1. Check if ./data/train.csv and ./data/test.csv exist
2. If they exist, read first 5 rows to understand data structure
3. Look for evaluation metric in ./pages/overview.html
4. Create a competition_analysis.json file with your findings

Required output format (save as competition_analysis.json):
{{
  "competition_type": "regression or classification",
  "metric_analysis": {{
    "metric_name": "RMSE or AUC or other"
  }},
  "data_overview": {{
    "train_shape": [rows, columns],
    "test_shape": [rows, columns],
    "target_column": "name of target column if found"
  }},
  "initial_strategy": {{
    "feature_engineering": [
      {{"type": "numerical", "description": "suggestion", "priority": "high/medium/low"}}
    ]
  }}
}}

IMPORTANT: Create the file even with partial information if some data is missing."""
            
            # Use the wrapper to run Claude Code
            result = wrapper.execute_task(
                prompt=simple_prompt,
                working_directory=competition_path,
                allowed_tools=["Read", "Write", "LS", "Grep", "Glob"],
                timeout=60  # Shorter timeout to prevent hanging
            )
            
            if result.success:
                # Check if the analysis file was created
                analysis_path = os.path.join(competition_path, "competition_analysis.json")
                if os.path.exists(analysis_path):
                    self.logger.info("Successfully created competition_analysis.json")
                    return read_json(analysis_path)
                else:
                    self.logger.warning("Claude Code did not create competition_analysis.json")
                    return None
            else:
                self.logger.error(f"Claude Code analysis failed: {result.error}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error running Claude analysis: {e}")
            return None

    def _enhance_competition_info(self, info: CompetitionInfo, claude_analysis: Dict[str, Any]) -> None:
        """Enhance competition info with Claude analysis results"""
        try:
            # Update evaluation metric if Claude found it
            if claude_analysis.get("metric_analysis", {}).get("metric_name"):
                info.evaluation_metric = claude_analysis["metric_analysis"]["metric_name"]
                self.logger.info(f"Updated evaluation metric from Claude analysis: {info.evaluation_metric}")
            
            # Update competition type
            if claude_analysis.get("competition_type"):
                info.competition_type = claude_analysis["competition_type"]
                info.competition_subtype = claude_analysis.get("competition_subtype", "")
            
            # Add initial insights
            if claude_analysis.get("initial_strategy", {}).get("feature_engineering"):
                info.initial_insights = claude_analysis["initial_strategy"]["feature_engineering"]
            
            # Add data quality warnings
            if claude_analysis.get("data_quality", {}).get("warnings"):
                info.data_warnings = claude_analysis["data_quality"]["warnings"]
                
        except Exception as e:
            self.logger.warning(f"Error enhancing competition info with Claude analysis: {e}")

    def get_competition_info(self) -> Optional[CompetitionInfo]:
        """コンペティション情報を取得する"""
        method_name = "get_competition_info"
        self._log_start(method_name)
        try:
            # First, try to use crawler data if enabled
            if self.use_crawler and not self.simulation_mode:
                # Check if crawler data exists
                competition_path = os.path.join(self.crawler_output_dir, self.competition_name)
                if not os.path.exists(competition_path):
                    self.logger.info("Crawler data not found, running crawler...")
                    if self._run_crawler():
                        # Run Claude analysis on the crawled data
                        claude_analysis = self._run_claude_analysis(competition_path)
                        
                        # Try to parse after crawling
                        info = parse_competition_info(self.competition_name, self.crawler_output_dir)
                        if info:
                            # Enhance with Claude analysis if available
                            if claude_analysis:
                                self._enhance_competition_info(info, claude_analysis)
                            
                            self.logger.info(f"Successfully parsed competition info from crawler data: {info.name}")
                            self._log_end(method_name, info)
                            return info
                else:
                    # Check if we already have Claude analysis
                    analysis_path = os.path.join(competition_path, "competition_analysis.json")
                    claude_analysis = None
                    if not os.path.exists(analysis_path):
                        # Run Claude analysis if not done before
                        claude_analysis = self._run_claude_analysis(competition_path)
                    else:
                        claude_analysis = read_json(analysis_path)
                    
                    # Parse existing crawler data
                    info = parse_competition_info(self.competition_name, self.crawler_output_dir)
                    if info:
                        # Enhance with Claude analysis if available
                        if claude_analysis:
                            self._enhance_competition_info(info, claude_analysis)
                            
                        self.logger.info(f"Successfully parsed competition info from existing crawler data: {info.name}")
                        self._log_end(method_name, info)
                        return info
                    else:
                        self.logger.warning("Failed to parse crawler data, will try other methods")
            
            # Fall back to API or simulation
            if self.simulation_mode or not self.api:
                # シミュレーション用のダミーデータ
                dummy_deadline = datetime.datetime.now() + datetime.timedelta(days=30)
                info = CompetitionInfo(
                    name=self.competition_name,
                    evaluation_metric="AUC",
                    deadline=dummy_deadline,
                    description_markdown=f"# Competition: {self.competition_name}\n\nThis is a dummy competition description.\nGoal: Predict the target variable.\nMetric: AUC",
                    data_files=["train.csv", "test.csv", "sample_submission.csv"]
                )
                self.logger.info(f"Generated dummy competition info for: {self.competition_name}")
            else:
                # 実際のKaggle APIから情報を取得
                comp = self.api.competition_view(self.competition_name)
                
                # 日付フォーマットは変わる可能性があるので例外処理
                deadline = None
                if hasattr(comp, 'deadline'):
                    try:
                        deadline = datetime.datetime.strptime(comp.deadline, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            deadline = datetime.datetime.strptime(comp.deadline, '%m/%d/%Y %H:%M:%S %p')
                        except ValueError:
                            self.logger.warning(f"Could not parse deadline: {comp.deadline}")
                
                # 利用可能なファイル一覧を取得
                try:
                    files = self.api.competition_list_files(self.competition_name)
                    data_files = [f.name for f in files]
                except Exception as file_error:
                    self.logger.warning(f"Could not get file list: {file_error}")
                    data_files = []
                
                info = CompetitionInfo(
                    name=comp.title,
                    evaluation_metric=comp.evaluationMetric if hasattr(comp, 'evaluationMetric') else "Unknown",
                    deadline=deadline,
                    description_markdown=comp.description,
                    data_files=data_files
                )
                self.logger.info(f"Successfully retrieved info for competition: {info.name}")
            
            self._log_end(method_name, info)
            return info
        except Exception as e:
            self._log_error(method_name, e)
            return None

    def download_data_files(self, competition_info: CompetitionInfo) -> bool:
        """データファイルをダウンロードする"""
        method_name = "download_data_files"
        self._log_start(method_name, competition_name=competition_info.name)
        try:
            ensure_dir(self.download_dir)
            
            # First, check if crawler has already downloaded the data
            if self.use_crawler and not self.simulation_mode:
                crawler_data_dir = os.path.join(self.crawler_output_dir, self.competition_name, "data")
                if os.path.exists(crawler_data_dir):
                    self.logger.info("Using data files from crawler output")
                    # Copy files from crawler data directory to our download directory
                    import shutil
                    for filename in os.listdir(crawler_data_dir):
                        src_path = os.path.join(crawler_data_dir, filename)
                        dst_path = os.path.join(self.download_dir, filename)
                        if os.path.isfile(src_path) and not filename.startswith('.'):
                            shutil.copy2(src_path, dst_path)
                            self.logger.info(f"Copied data file: {filename}")
                    
                    # Update competition_info with actual files
                    competition_info.data_files = [f for f in os.listdir(self.download_dir) 
                                                 if os.path.isfile(os.path.join(self.download_dir, f))]
                    self._log_end(method_name, result=True)
                    return True
            
            # Fall back to API or simulation
            if self.simulation_mode or not self.api:
                # シミュレーション用のダミーファイル作成
                for filename in competition_info.data_files:
                    dummy_file_path = os.path.join(self.download_dir, filename)
                    if not os.path.exists(dummy_file_path):
                        with open(dummy_file_path, 'w') as f:
                            f.write("dummy data for " + filename)
                        self.logger.info(f"Created dummy data file: {dummy_file_path}")
            else:
                # 実際のKaggle APIからファイルをダウンロード
                self.logger.info(f"Downloading competition files for {self.competition_name} to {self.download_dir}")
                
                # ZIPファイルのダウンロード先パス
                zip_path = os.path.join(self.download_dir, f"{self.competition_name}.zip")
                
                # ファイルのダウンロード
                self.api.competition_download_files(self.competition_name, path=self.download_dir, quiet=False)
                
                # ZIPファイルの解凍処理
                if os.path.exists(zip_path):
                    self.logger.info(f"Extracting downloaded ZIP file: {zip_path}")
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(self.download_dir)
                    
                    # ZIP解凍後はファイルを削除してもよい
                    os.remove(zip_path)
                    self.logger.info("ZIP file extracted and removed")
                
                # 実際にダウンロードされたファイルの確認
                downloaded_files = os.listdir(self.download_dir)
                self.logger.info(f"Downloaded files: {downloaded_files}")
                
                # データファイル一覧を更新
                competition_info.data_files = [f for f in downloaded_files if os.path.isfile(os.path.join(self.download_dir, f))]
            
            self._log_end(method_name, result=True)
            return True
        except Exception as e:
            self._log_error(method_name, e)
            return False

    def submit_predictions(self, file_path: str, message: str) -> bool:
        """予測結果を提出する"""
        method_name = "submit_predictions"
        self._log_start(method_name, file_path=file_path, message=message)
        
        if self.simulation_mode or not self.api:
            self.logger.info("Submission skipped (simulation mode).")
            self._log_end(method_name, result=True)
            return True
        
        try:
            # ファイルの存在確認
            if not os.path.exists(file_path):
                self.logger.error(f"Submission file does not exist: {file_path}")
                self._log_end(method_name, result=False)
                return False
                
            # Kaggle APIを使用して提出
            self.logger.info(f"Submitting {file_path} to competition {self.competition_name} with message: {message}")
            result = self.api.competition_submit(file_path, message, self.competition_name)
            
            # 提出結果の確認
            if hasattr(result, 'error'):
                self.logger.error(f"Submission failed: {result.error}")
                self._log_end(method_name, result=False)
                return False
                
            self.logger.info(f"Submission successful. Result: {result}")
            self._log_end(method_name, result=True)
            return True
            
        except Exception as e:
            self._log_error(method_name, e)
            return False
