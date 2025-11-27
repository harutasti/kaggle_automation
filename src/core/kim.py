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
from ..utils.dataset_analyzer import DatasetAnalyzer

class KaggleInterfaceManager(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.competition_name = config.get("kaggle_competition_name", "dummy-competition")
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.download_dir = os.path.join(self.experiment_run_dir, "kaggle_data")

        # Only ensure directory if not in dry-run mode
        if not config.get("dry_run", False):
            ensure_dir(self.download_dir)

        self.api = self._authenticate_kaggle()
        self.simulation_mode = config.get("simulation_mode", False)
        self.use_crawler = config.get("use_crawler", True)  # Default to using crawler
        self.crawler_output_dir = "kaggle_competitions"
        self.max_discussions = config.get("max_discussions", 20)
        self.dataset_analysis = None  # Will store dataset analysis results
        self.analyze_dataset = config.get("analyze_dataset", True)  # Enable dataset analysis by default

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
            if self.simulation_mode or self.api is None:
                # Dummy data for simulation mode or when API auth failed
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
                # Fetch info from real Kaggle API (api is guaranteed non-None here)
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

                    # Analyze dataset if enabled
                    if self.analyze_dataset:
                        self._analyze_competition_dataset()

                    self._log_end(method_name, result=True)
                    return True
            
            # Fall back to API or simulation
            if self.simulation_mode or self.api is None:
                # Create dummy files for simulation mode or when API auth failed
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

            # Analyze dataset if enabled
            if self.analyze_dataset:
                self._analyze_competition_dataset()

            self._log_end(method_name, result=True)
            return True
        except Exception as e:
            self._log_error(method_name, e)
            return False

    def _analyze_competition_dataset(self) -> Optional[Dict[str, Any]]:
        """Analyze the downloaded competition dataset."""
        try:
            self.logger.info("Analyzing competition dataset...")

            # Determine data directory
            data_dir = self.download_dir
            if not os.path.exists(data_dir):
                # Try crawler data directory
                crawler_data_dir = os.path.join(self.crawler_output_dir, self.competition_name, "data")
                if os.path.exists(crawler_data_dir):
                    data_dir = crawler_data_dir
                else:
                    self.logger.warning("No data directory found for analysis")
                    return None

            # Initialize dataset analyzer
            analyzer = DatasetAnalyzer(self.competition_name, data_dir)

            # Analyze the dataset
            self.dataset_analysis = analyzer.analyze_competition_data()

            # Log key statistics
            if self.dataset_analysis:
                stats = self.dataset_analysis.get("dataset_stats", {})
                self.logger.info(f"Dataset Analysis Complete:")
                self.logger.info(f"  - Training samples: {stats.get('train_size', 'N/A')}")
                self.logger.info(f"  - Test samples: {stats.get('test_size', 'N/A')}")
                self.logger.info(f"  - Features: {stats.get('feature_count', 'N/A')}")

                target = self.dataset_analysis.get("target_analysis", {})
                if target:
                    self.logger.info(f"  - Target variable: {target.get('target_variable', 'N/A')}")
                    self.logger.info(f"  - Problem type: {target.get('problem_type', 'N/A')}")

                missing = self.dataset_analysis.get("missing_data", {})
                if missing:
                    self.logger.info(f"  - Missing data pattern: {missing.get('missing_pattern', 'N/A')}")

            return self.dataset_analysis

        except Exception as e:
            self.logger.error(f"Failed to analyze dataset: {e}")
            return None

    def get_dataset_analysis(self) -> Optional[Dict[str, Any]]:
        """Get the cached dataset analysis results."""
        if self.dataset_analysis is None and self.analyze_dataset:
            # Try to analyze now if not done yet
            self._analyze_competition_dataset()
        return self.dataset_analysis

    def submit_predictions(self, file_path: str, message: str) -> bool:
        """Submit predictions to Kaggle."""
        method_name = "submit_predictions"
        self._log_start(method_name, file_path=file_path, message=message)
        
        if self.simulation_mode or self.api is None:
            self.logger.info("Submission skipped (simulation mode or API unavailable).")
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

    def get_submission_score(self, wait_timeout: int = 300) -> Optional[Dict[str, Any]]:
        """
        Get the most recent submission score from Kaggle.

        Polls Kaggle API until the latest submission has a public score,
        or until the timeout is reached.

        Args:
            wait_timeout: Maximum seconds to wait for score (default: 5 minutes)

        Returns:
            Dict with submission details including score, or None if unavailable
        """
        method_name = "get_submission_score"
        self._log_start(method_name, wait_timeout=wait_timeout)

        if self.simulation_mode or self.api is None:
            # Return simulated score for testing or when API unavailable
            self.logger.info("Returning simulated submission score (simulation mode or API unavailable)")
            result = {"score": 0.85, "status": "complete", "submission_id": "simulated"}
            self._log_end(method_name, result=result)
            return result

        try:
            import time
            start = time.time()

            while time.time() - start < wait_timeout:
                try:
                    submissions = self.api.competition_submissions(self.competition_name)

                    if submissions:
                        latest = submissions[0]

                        # Check if score is available
                        if hasattr(latest, 'publicScore') and latest.publicScore:
                            result = {
                                "score": float(latest.publicScore),
                                "status": "complete",
                                "submission_id": getattr(latest, 'ref', None),
                                "description": getattr(latest, 'description', None),
                                "date": str(getattr(latest, 'date', None))
                            }
                            self.logger.info(f"Got submission score: {result['score']}")
                            self._log_end(method_name, result=result)
                            return result

                        # Score not yet available
                        status = getattr(latest, 'status', 'unknown')
                        self.logger.debug(f"Submission status: {status}, waiting for score...")

                except Exception as poll_error:
                    self.logger.warning(f"Error polling submissions: {poll_error}")

                # Wait before retry
                time.sleep(10)

            # Timeout reached
            self.logger.warning(f"Timed out waiting for submission score after {wait_timeout}s")
            self._log_end(method_name, result=None)
            return None

        except Exception as e:
            self._log_error(method_name, e)
            return None