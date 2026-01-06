import logging
import datetime
import os
import zipfile
import subprocess
import sys
import json
import time
import threading
from collections import deque
from pathlib import Path
from typing import Optional, List, Dict, Any

# Kaggle 1.8+ no longer ships kaggle.rest; fall back to requests HTTPError
try:  # pragma: no cover - import compatibility
    from kaggle.rest import ApiException  # Kaggle <=1.6
except ImportError:  # Kaggle >=1.8
    try:
        from requests import HTTPError as ApiException  # type: ignore
    except Exception:  # Last resort
        ApiException = Exception  # type: ignore

from .base_component import BaseComponent
from ..data_models import CompetitionInfo
from ..utils.file_utils import ensure_dir, is_higher_better_from_leaderboard
from ..utils.crawler_parser import parse_competition_info
from ..utils.dataset_analyzer import DatasetAnalyzer

class KaggleInterfaceManager(BaseComponent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.competition_name = config.get("kaggle_competition_name", "dummy-competition")
        # Use experiment_run_dir if available (timestamped), otherwise fall back to experiments_base_dir
        self.experiment_run_dir = config.get("experiment_run_dir", config.get("experiments_base_dir", "./experiments"))
        self.download_dir = os.path.join(self.experiment_run_dir, "kaggle_data")
        self.simulation_mode = config.get("simulation_mode", False)
        ensure_dir(self.download_dir)

        # Dry-run (simulation_mode) still exercises everything except Codex, so Kaggle API is required.
        # Fail fast on missing/invalid credentials.
        self.api = self._authenticate_kaggle()
        self.use_crawler = config.get("use_crawler", True)  # Default to using crawler
        self.crawler_output_dir = "kaggle_competitions"
        self.max_discussions = config.get("max_discussions", 100)
        self.dataset_analysis = None  # Will store dataset analysis results
        self._dataset_analyzer = None  # Will store DatasetAnalyzer instance for placeholder generation
        self.analyze_dataset = config.get("analyze_dataset", True)  # Enable dataset analysis by default
        self.last_submission_ref: Optional[int] = None  # For fetching official score after submit

    def _authenticate_kaggle(self):
        """Authenticate with the Kaggle API."""
        try:
            # Prefer project-root kaggle.json if present
            project_root = Path(__file__).resolve().parents[2]
            project_kaggle = project_root / "kaggle.json"
            if not os.environ.get("KAGGLE_CONFIG_DIR") and project_kaggle.exists():
                os.environ["KAGGLE_CONFIG_DIR"] = str(project_root)
                self.logger.info(f"Using kaggle.json from project root: {project_kaggle}")
                try:
                    os.chmod(project_kaggle, 0o600)
                except Exception as chmod_err:
                    self.logger.warning(f"Could not set permissions on {project_kaggle}: {chmod_err}")

            # Import here to avoid authentication at module import time
            from kaggle.api.kaggle_api_extended import KaggleApi
            api = KaggleApi()
            api.authenticate()
            self.logger.info("Kaggle API authenticated successfully.")
            return api
        except ImportError:
            self.logger.critical("Kaggle API is not available. Install the kaggle package and authenticate before running.")
            sys.exit(1)
        except Exception as e:
            self.logger.critical(f"Kaggle API authentication failed: {e}")
            sys.exit(1)
    
    def _run_crawler(self) -> bool:
        """Run kaggle_crawler to fetch competition data."""
        try:
            crawler_script = os.path.join("src", "kaggle_crawler", "crawl_kaggle_competition.py")
            if not os.path.exists(crawler_script):
                self.logger.error(f"Crawler script not found: {crawler_script}")
                return False
            
            cmd = [
                sys.executable,
                "-u",
                crawler_script,
                self.competition_name,
                "--max-discussions",
                str(self.max_discussions),
            ]
            if self.config.get("crawler_force_refresh", False):
                cmd.append("--force")
            if not self.config.get("crawler_cache_enabled", True):
                cmd.append("--no-cache")
            cache_ttl = self.config.get("crawler_cache_ttl_hours")
            if cache_ttl is not None:
                cmd.extend(["--cache-ttl-hours", str(cache_ttl)])
            if not self.config.get("crawler_summary_enabled", True):
                cmd.append("--no-summary")

            self.logger.info(f"Running kaggle_crawler for competition: {self.competition_name}")

            # Stream output to avoid hanging on long runs and detect completion markers.
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            output_tail = deque(maxlen=200)
            completion_seen_at: Optional[float] = None
            last_output_at: Optional[float] = None
            stream_output = bool(self.config.get("crawler_stream_output", True))

            def _reader():
                nonlocal completion_seen_at
                if not proc.stdout:
                    return
                for raw in proc.stdout:
                    line = raw.rstrip("\n")
                    if not line:
                        continue
                    last_output_at = time.monotonic()
                    output_tail.append(line)
                    # Detect the crawler's natural completion marker.
                    if "=== All done ===" in line or line.startswith("[output] files saved"):
                        completion_seen_at = time.monotonic()
                    if stream_output:
                        print(line, flush=True)
                    self.logger.debug(f"[crawler] {line}")
                try:
                    proc.stdout.close()
                except Exception:
                    pass

            reader_thread = threading.Thread(target=_reader, daemon=True)
            reader_thread.start()

            timeout = self.config.get("crawler_timeout_seconds")
            idle_timeout = self.config.get("crawler_output_idle_seconds", 600)
            completion_grace = float(self.config.get("crawler_completion_grace_seconds", 20.0))
            start_ts = time.monotonic()
            terminated_after_completion = False

            while True:
                ret = proc.poll()
                if ret is not None:
                    break

                if completion_seen_at is not None:
                    if time.monotonic() - completion_seen_at > completion_grace:
                        self.logger.warning(
                            "Crawler reported completion but process still running; terminating after grace period."
                        )
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=10)
                        terminated_after_completion = True
                        break

                if (
                    idle_timeout
                    and last_output_at is not None
                    and time.monotonic() - last_output_at > float(idle_timeout)
                ):
                    overview_path = os.path.join(
                        self.crawler_output_dir,
                        self.competition_name,
                        "pages",
                        f"{self.competition_name}_overview.md",
                    )
                    data_dir = os.path.join(
                        self.crawler_output_dir,
                        self.competition_name,
                        "data",
                    )
                    outputs_ready = os.path.exists(overview_path) or os.path.isdir(data_dir)
                    if outputs_ready:
                        self.logger.warning(
                            f"Crawler output idle for {idle_timeout}s with outputs present; terminating."
                        )
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=10)
                        terminated_after_completion = True
                        break
                    self.logger.error(
                        f"Crawler output idle for {idle_timeout}s without outputs; terminating."
                    )
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                    break

                if timeout is not None and (time.monotonic() - start_ts) > float(timeout):
                    self.logger.error(f"Crawler timed out after {timeout} seconds; terminating.")
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=10)
                    break

                time.sleep(0.5)

            # Ensure reader thread finishes draining output.
            reader_thread.join(timeout=2)

            retcode = proc.poll()
            if retcode is None:
                try:
                    retcode = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    retcode = proc.wait(timeout=5)

            if retcode != 0:
                tail = "\n".join(output_tail)
                overview_file = os.path.join(
                    self.crawler_output_dir,
                    self.competition_name,
                    "pages",
                    f"{self.competition_name}_overview.md",
                )
                if completion_seen_at is not None or terminated_after_completion or os.path.exists(overview_file):
                    self.logger.warning(
                        f"Crawler exited with code {retcode}, but output appears usable. Continuing."
                    )
                    if tail:
                        self.logger.debug(f"Crawler output tail:\n{tail}")
                    return True

                self.logger.error(f"Crawler failed (exit={retcode}). Output tail:\n{tail}")
                return False

            self.logger.info("Crawler completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error running crawler: {e}")
            return False

    def refresh_crawler_data(self) -> bool:
        """Force-refresh crawler output for the competition."""
        if not self.use_crawler:
            self.logger.info("Crawler disabled; skipping refresh.")
            return True
        self.logger.info("Refreshing crawler data (forced)...")
        return self._run_crawler()

    def _parse_deadline(self, raw_deadline: Any) -> Optional[datetime.datetime]:
        """Convert Kaggle API deadline field into a datetime object when possible."""
        if isinstance(raw_deadline, datetime.datetime):
            return raw_deadline

        if isinstance(raw_deadline, str):
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y %H:%M:%S %p",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%fZ",
            ]:
                try:
                    return datetime.datetime.strptime(raw_deadline, fmt)
                except ValueError:
                    continue
        return None

    def _get_competition_metadata_from_api(self) -> CompetitionInfo:
        """Fetch competition metadata using supported Kaggle API endpoints."""
        if self.api is None:
            raise RuntimeError("Kaggle API is unavailable; cannot fetch competition info.")

        try:
            competitions = self.api.competitions_list(search=self.competition_name)
        except Exception as api_err:
            raise RuntimeError(f"Failed to fetch competition list: {api_err}") from api_err

        target_competition = None
        if competitions:
            for comp in competitions:
                comp_ref = getattr(comp, "ref", "")
                # Handle case where ref is a full URL
                if comp_ref.startswith("http"):
                    comp_ref = comp_ref.rstrip("/").split("/")[-1]
                if comp_ref.lower() == self.competition_name.lower():
                    target_competition = comp
                    break
            if target_competition is None:
                target_competition = competitions[0]
                first_ref = getattr(target_competition, 'ref', 'unknown')
                if first_ref.startswith("http"):
                    first_ref = first_ref.rstrip("/").split("/")[-1]
                self.logger.warning(
                    f"Exact match for competition '{self.competition_name}' not found; "
                    f"using search result '{first_ref}'."
                )

        if target_competition is None:
            raise RuntimeError(f"Competition '{self.competition_name}' not found via Kaggle API.")

        competition_ref = getattr(target_competition, "ref", self.competition_name)
        # Handle case where ref is a full URL instead of just the slug
        if competition_ref and competition_ref.startswith("http"):
            # Extract slug from URL like https://www.kaggle.com/competitions/house-prices-...
            competition_ref = competition_ref.rstrip("/").split("/")[-1]
        deadline = self._parse_deadline(getattr(target_competition, "deadline", None))
        evaluation_metric = getattr(target_competition, "evaluationMetric", None) or "Unknown"

        try:
            file_list = self.api.competition_list_files(competition_ref)
            # Handle both FileList object (has .files attribute) and direct list
            files = getattr(file_list, 'files', file_list) or []
            data_files = [f.name for f in files]
        except Exception as file_error:
            self.logger.error(f"Failed to get file list for competition '{competition_ref}': {file_error}")
            raise RuntimeError(f"Failed to fetch competition file list from Kaggle API: {file_error}") from file_error

        description = getattr(target_competition, "description", None)
        if not description:
            description = (
                f"# Competition: {getattr(target_competition, 'title', competition_ref)}\n\n"
                f"No description was returned by the Kaggle API. "
                f"Visit https://www.kaggle.com/competitions/{competition_ref} for details."
            )

        # Determine metric direction from leaderboard
        higher_is_better = is_higher_better_from_leaderboard(competition_ref, evaluation_metric)

        return CompetitionInfo(
            name=getattr(target_competition, "title", competition_ref),
            evaluation_metric=evaluation_metric,
            deadline=deadline,
            description_markdown=description,
            data_files=data_files,
            competition_type=getattr(target_competition, "category", None),
            higher_is_better=higher_is_better,
        )

    def get_competition_info(self) -> Optional[CompetitionInfo]:
        """Retrieve competition information."""
        method_name = "get_competition_info"
        self._log_start(method_name)
        try:
            # First, try to use crawler data if enabled
            if self.use_crawler:
                competition_path = os.path.join(self.crawler_output_dir, self.competition_name)
                overview_file = os.path.join(competition_path, "pages", f"{self.competition_name}_overview.md")
                crawler_ok = self.refresh_crawler_data()

                # Parse crawler data if available
                if os.path.exists(overview_file):
                    info = parse_competition_info(self.competition_name, self.crawler_output_dir)
                    if info:
                        self.logger.info(f"Successfully parsed competition info from crawler data: {info.name}")
                        self._log_end(method_name, info)
                        return info

                if not crawler_ok:
                    self.logger.warning("Crawler failed to fetch competition data, falling back to other methods.")
                else:
                    self.logger.warning("Crawler completed but parsing failed, falling back to other methods.")
            
            # Fall back to Kaggle API
            info = self._get_competition_metadata_from_api()
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
            if self.use_crawler:
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

                    # Extract any zip files copied from the crawler output.
                    for filename in os.listdir(self.download_dir):
                        if not filename.lower().endswith(".zip"):
                            continue
                        zip_path = os.path.join(self.download_dir, filename)
                        try:
                            self.logger.info(f"Extracting crawler ZIP: {zip_path}")
                            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                                zip_ref.extractall(self.download_dir)
                            os.remove(zip_path)
                            self.logger.info(f"Removed crawler ZIP after extraction: {filename}")
                        except Exception as e:
                            self.logger.error(f"Failed to extract crawler ZIP {zip_path}: {e}")
                    
                    # Update competition_info with actual files
                    competition_info.data_files = [f for f in os.listdir(self.download_dir)
                                                 if os.path.isfile(os.path.join(self.download_dir, f))]

                    if not any(not f.lower().endswith(".zip") for f in competition_info.data_files):
                        self.logger.warning(
                            "Crawler data contains only ZIP files; falling back to Kaggle API download."
                        )
                    else:
                        # Analyze dataset if enabled
                        if self.analyze_dataset:
                            self._analyze_competition_dataset()

                        self._log_end(method_name, result=True)
                        return True

            if self.api is None:
                raise RuntimeError("Kaggle API is unavailable; cannot download competition data.")

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

            # Initialize dataset analyzer and store for later use
            self._dataset_analyzer = DatasetAnalyzer(self.competition_name, data_dir)

            # Analyze the dataset
            self.dataset_analysis = self._dataset_analyzer.analyze_competition_data()

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

    def get_dataset_analysis_placeholders(self) -> Optional[Dict[str, Any]]:
        """
        Get dataset analysis formatted as prompt placeholders for KSE.

        Returns:
            Dictionary with keys matching KSE prompt placeholders, or None if analysis unavailable
        """
        # Ensure analysis has been performed
        if self._dataset_analyzer is None:
            if self.analyze_dataset:
                self._analyze_competition_dataset()

        # Return placeholders if analyzer is available
        if self._dataset_analyzer is not None:
            try:
                return self._dataset_analyzer.get_prompt_placeholders()
            except Exception as e:
                self.logger.warning(f"Failed to get dataset placeholders: {e}")
                return None

        return None

    def submit_predictions(self, file_path: str, message: str) -> bool:
        """Submit predictions to Kaggle."""
        method_name = "submit_predictions"
        self._log_start(method_name, file_path=file_path, message=message)
        
        # Dry-run explicitly disables submissions to avoid leaderboard side effects.
        if self.simulation_mode:
            self.logger.info("Dry-run: Kaggle submission disabled. Skipping.")
            self._log_end(method_name, result=False)
            return False

        if self.api is None:
            self.logger.error("Kaggle API unavailable; cannot submit.")
            self._log_end(method_name, result=False)
            return False

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
            try:
                submission_ref = None
                if isinstance(result, dict):
                    submission_ref = result.get("ref")
                else:
                    submission_ref = getattr(result, "ref", None)
                if submission_ref is not None:
                    self.last_submission_ref = int(submission_ref)
                    self.logger.debug(f"Stored last submission ref: {self.last_submission_ref}")
            except Exception as e:
                self.logger.debug(f"Could not extract submission ref from submit result: {e}")
            self._log_end(method_name, result=True)
            return True

        except ApiException as e:
            # Explicitly handle common Kaggle rule-acceptance failure
            status_code = getattr(e, "status", None) or getattr(getattr(e, "response", None), "status_code", None)
            error_payload = ""
            try:
                body = getattr(e, "body", None)
                if body:
                    error_payload = json.loads(body or "{}").get("message", "") or body
            except Exception:
                error_payload = getattr(e, "body", "") or str(e)

            message_str = f"{error_payload}".lower()
            if (status_code == 403) or ("403" in str(e)) or ("forbidden" in message_str):
                if "rule" in message_str or "accept" in message_str:
                    self.logger.critical(
                        "Kaggle rejected the submission with 403: competition rules not accepted.\n"
                        f"Please accept the rules at https://www.kaggle.com/competitions/{self.competition_name}/rules "
                        "and re-run. Aborting all iterations to avoid repeated failures."
                    )
                    sys.exit(1)

            self._log_error(method_name, e)
            return False
        except Exception as e:
            self._log_error(method_name, e)
            return False

    def get_submission_score_once(
        self,
        submission_ref: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a Kaggle submission score once (no waiting).

        This is useful when you have multiple submissions and want to poll them in a loop
        without serially blocking for each one.
        """
        if self.simulation_mode:
            return None

        if self.api is None:
            return None

        target_ref = submission_ref or self.last_submission_ref
        if target_ref is None:
            return None

        try:
            # Kaggle 1.8+ supports page_size; pull more than the default 20 to reduce races.
            try:
                submissions = self.api.competition_submissions(self.competition_name, page_size=100)
            except TypeError:
                submissions = self.api.competition_submissions(self.competition_name)

            if not submissions:
                return None

            # Filter out None entries (Kaggle SDK types are Optional in the signature).
            submissions = [s for s in submissions if s is not None]
            if not submissions:
                return None

            target = None
            for submission in submissions:
                ref_val = None
                if isinstance(submission, dict):
                    ref_val = submission.get("ref") or submission.get("id")
                else:
                    ref_val = getattr(submission, "ref", None) or getattr(submission, "id", None)
                if ref_val is not None and int(ref_val) == int(target_ref):
                    target = submission
                    break

            if target is None:
                # Avoid returning the wrong submission's score.
                return None

            # Extract score across Kaggle API versions (camelCase vs snake_case).
            public_score_raw = None
            if isinstance(target, dict):
                public_score_raw = (
                    target.get("publicScore")
                    or target.get("public_score")
                    or target.get("publicscore")
                )
            else:
                public_score_raw = (
                    getattr(target, "public_score", None)
                    or getattr(target, "publicScore", None)
                )

            if public_score_raw is None or not str(public_score_raw).strip():
                return None

            try:
                score_val = float(public_score_raw)
            except Exception:
                return None

            return {
                "score": score_val,
                "status": "complete",
                "submission_id": (target.get("ref") if isinstance(target, dict) else getattr(target, "ref", None)),
                "description": (
                    target.get("description") if isinstance(target, dict) else getattr(target, "description", None)
                ),
                "date": str(target.get("date") if isinstance(target, dict) else getattr(target, "date", None)),
            }
        except Exception:
            return None

    def get_submission_score(
        self,
        wait_timeout: int = 300,
        submission_ref: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent submission score from Kaggle.

        Polls Kaggle API until the latest submission has a public score,
        or until the timeout is reached.

        Args:
            wait_timeout: Maximum seconds to wait for score (default: 5 minutes)
            submission_ref: Optional submission ref returned by submit API; if provided,
                polls for that submission specifically to avoid races with other submissions.

        Returns:
            Dict with submission details including score, or None if unavailable
        """
        method_name = "get_submission_score"
        self._log_start(method_name, wait_timeout=wait_timeout)

        if self.simulation_mode:
            self.logger.info("Dry-run: Kaggle submission scoring disabled.")
            self._log_end(method_name, result=None)
            return None

        if self.api is None:
            self.logger.warning("Kaggle API unavailable; cannot fetch submission score.")
            self._log_end(method_name, result=None)
            return None

        try:
            import time

            target_ref = submission_ref or self.last_submission_ref
            if target_ref is None:
                self.logger.warning("No submission ref available to poll for a score.")
                self._log_end(method_name, result=None)
                return None

            # Allow config override for polling cadence.
            poll_interval = self.config.get("kaggle_score_poll_interval_seconds", 10)
            try:
                poll_interval = float(poll_interval)
            except Exception:
                poll_interval = 10.0
            if poll_interval <= 0:
                poll_interval = 10.0

            start = time.time()
            while time.time() - start < wait_timeout:
                result = self.get_submission_score_once(submission_ref=int(target_ref))
                if result is not None and result.get("score") is not None:
                    self.logger.info(f"Got submission score: {result['score']}")
                    self._log_end(method_name, result=result)
                    return result

                time.sleep(poll_interval)

            # Timeout reached
            self.logger.warning(f"Timed out waiting for submission score after {wait_timeout}s")
            self._log_end(method_name, result=None)
            return None

        except Exception as e:
            self._log_error(method_name, e)
            return None
