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
from ..utils.file_utils import ensure_dir
from ..utils.crawler_parser import parse_competition_info

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
        """Authenticate with the Kaggle API."""
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

    def get_competition_info(self) -> Optional[CompetitionInfo]:
        """Retrieve competition information."""
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
                        # Try to parse after crawling
                        info = parse_competition_info(self.competition_name, self.crawler_output_dir)
                        if info:
                            self.logger.info(f"Successfully parsed competition info from crawler data: {info.name}")
                            self._log_end(method_name, info)
                            return info
                else:
                    # Parse existing crawler data
                    info = parse_competition_info(self.competition_name, self.crawler_output_dir)
                    if info:
                        self.logger.info(f"Successfully parsed competition info from existing crawler data: {info.name}")
                        self._log_end(method_name, info)
                        return info
                    else:
                        self.logger.warning("Failed to parse crawler data, will try other methods")
            
            # Fall back to API or simulation
            if self.simulation_mode or not self.api:
                # Dummy data for simulation mode
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
                # Fetch info from real Kaggle API
                comp = self.api.competition_view(self.competition_name)
                
                # Parse deadline with flexible formats
                deadline = None
                if hasattr(comp, 'deadline'):
                    try:
                        deadline = datetime.datetime.strptime(comp.deadline, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            deadline = datetime.datetime.strptime(comp.deadline, '%m/%d/%Y %H:%M:%S %p')
                        except ValueError:
                            self.logger.warning(f"Could not parse deadline: {comp.deadline}")
                
                # Get available file list
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
        """Download competition data files."""
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
                # Create dummy files for simulation mode
                for filename in competition_info.data_files:
                    dummy_file_path = os.path.join(self.download_dir, filename)
                    if not os.path.exists(dummy_file_path):
                        with open(dummy_file_path, 'w') as f:
                            f.write("dummy data for " + filename)
                        self.logger.info(f"Created dummy data file: {dummy_file_path}")
            else:
                # Download files from Kaggle API
                self.logger.info(f"Downloading competition files for {self.competition_name} to {self.download_dir}")
                
                # Destination for ZIP download
                zip_path = os.path.join(self.download_dir, f"{self.competition_name}.zip")
                
                # Download the file
                self.api.competition_download_files(self.competition_name, path=self.download_dir, quiet=False)
                
                # Extract the ZIP file
                if os.path.exists(zip_path):
                    self.logger.info(f"Extracting downloaded ZIP file: {zip_path}")
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(self.download_dir)
                    
                    # Optionally remove the ZIP after extraction
                    os.remove(zip_path)
                    self.logger.info("ZIP file extracted and removed")
                
                # Inspect downloaded files
                downloaded_files = os.listdir(self.download_dir)
                self.logger.info(f"Downloaded files: {downloaded_files}")
                
                # Update data file list
                competition_info.data_files = [f for f in downloaded_files if os.path.isfile(os.path.join(self.download_dir, f))]
            
            self._log_end(method_name, result=True)
            return True
        except Exception as e:
            self._log_error(method_name, e)
            return False

    def submit_predictions(self, file_path: str, message: str) -> bool:
        """Submit predictions to Kaggle."""
        method_name = "submit_predictions"
        self._log_start(method_name, file_path=file_path, message=message)
        
        if self.simulation_mode or not self.api:
            self.logger.info("Submission skipped (simulation mode).")
            self._log_end(method_name, result=True)
            return True
        
        try:
            # Confirm file exists
            if not os.path.exists(file_path):
                self.logger.error(f"Submission file does not exist: {file_path}")
                self._log_end(method_name, result=False)
                return False
                
            # Submit via Kaggle API
            self.logger.info(f"Submitting {file_path} to competition {self.competition_name} with message: {message}")
            result = self.api.competition_submit(file_path, message, self.competition_name)
            
            # Check submission result
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
