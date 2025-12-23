"""
Session Manager for long-running ML training experiments.

Handles status file operations, session tracking, and resume logic
for experiments that outlast Codex CLI sessions.
"""

import os
import time
import logging
from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


# Constants for retry logic
MAX_STATUS_READ_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.5


class SessionStatus(Enum):
    """Status states for experiment sessions."""
    IDLE = "IDLE"           # Default, short commands (<10 min)
    RUNNING = "RUNNING"     # Long operations (>10 min), WAA must exit after setting
    COMPLETE = "COMPLETE"   # All done, can submit (terminal state)
    ERROR = "ERROR"         # Needs human intervention


@dataclass
class StatusEntry:
    """Single status entry in the append-only log."""
    timestamp: datetime
    status: SessionStatus
    message: str
    expected_duration_minutes: Optional[int] = None
    model_files: List[str] = field(default_factory=list)
    output_files: List[str] = field(default_factory=list)
    error_type: Optional[str] = None
    recovery_suggestion: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionContext:
    """Context passed to resumed sessions."""
    experiment_id: str
    previous_stdout: str
    previous_stderr: str
    previous_status: SessionStatus
    exit_code: int
    iteration_count: int
    task_markdown_path: str
    worktree_path: str
    elapsed_time_seconds: float = 0.0


STATUS_FILE_NAME = "experiment-status.yaml"


class SessionManager:
    """
    Manages experiment session lifecycle and status tracking.

    Responsibilities:
    - Create and update experiment-status.yaml files
    - Track session state across Codex invocations
    - Coordinate with ResourceMonitor for resume triggers
    - Build context for session resume
    """

    def __init__(self, experiment_run_dir: str, logger: Optional[logging.Logger] = None):
        """
        Initialize the session manager.

        Args:
            experiment_run_dir: Base directory for experiment outputs
            logger: Optional logger instance
        """
        self.experiment_run_dir = Path(experiment_run_dir)
        self.logger = logger or logging.getLogger(__name__)

        # Track active monitors per experiment
        self._active_monitors: Dict[str, Any] = {}  # {exp_id: ResourceMonitor}

        # Session iteration counts
        self._session_iterations: Dict[str, int] = {}  # {exp_id: iteration_count}

        # Ensure sessions directory exists
        self.sessions_dir = self.experiment_run_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create_status_file(self, worktree_path: str, exp_id: str) -> Path:
        """
        Create initial experiment-status.yaml with IDLE status.

        Args:
            worktree_path: Path to the experiment worktree
            exp_id: Experiment identifier

        Returns:
            Path to the created status file
        """
        status_path = Path(worktree_path) / STATUS_FILE_NAME

        initial_entry = {
            'timestamp': datetime.now().isoformat(),
            'status': SessionStatus.IDLE.value,
            'message': 'Initial state - experiment starting'
        }

        content = {
            'experiment_id': exp_id,
            'created_at': datetime.now().isoformat(),
            'statuses': [initial_entry]
        }

        # Use the simple writer to enforce two-space indent for list entries.
        # This matches the WAA prompt append format and avoids YAML corruption.
        self._simple_yaml_write(status_path, content)
        self.logger.info(f"Created status file: {status_path}")

        # Initialize session tracking
        self._session_iterations[exp_id] = 0

        return status_path

    def read_current_status(self, worktree_path: str) -> Optional[StatusEntry]:
        """
        Read and parse the latest status from experiment-status.yaml.

        Args:
            worktree_path: Path to the experiment worktree

        Returns:
            Latest StatusEntry or None if file doesn't exist
        """
        status_path = Path(worktree_path) / STATUS_FILE_NAME

        if not status_path.exists():
            return None

        try:
            content = self._read_yaml(status_path)
            if not content or 'statuses' not in content:
                return None

            statuses = content['statuses']
            if not statuses:
                return None

            # Get the last status entry
            last_entry = statuses[-1]

            return StatusEntry(
                timestamp=self._parse_timestamp(last_entry.get('timestamp', '')),
                status=SessionStatus(last_entry.get('status', 'IDLE')),
                message=last_entry.get('message', ''),
                expected_duration_minutes=last_entry.get('expected_duration_minutes'),
                model_files=last_entry.get('model_files', []),
                output_files=last_entry.get('output_files', []),
                error_type=last_entry.get('error_type'),
                recovery_suggestion=last_entry.get('recovery_suggestion'),
                metadata=last_entry.get('metadata', {})
            )
        except Exception as e:
            self.logger.error(f"Failed to read status file {status_path}: {e}")
            return None

    def read_current_status_with_error(
        self, worktree_path: str
    ) -> tuple[Optional[StatusEntry], Optional[str]]:
        """
        Read the latest status and surface YAML parse errors separately.

        Returns:
            (StatusEntry or None, parse_error_message or None)
        """
        status_path = Path(worktree_path) / STATUS_FILE_NAME

        if not status_path.exists():
            return None, None

        try:
            content, parse_error = self._read_yaml_with_error(status_path)
            if parse_error:
                return None, parse_error
            if not content or 'statuses' not in content:
                return None, None

            statuses = content['statuses']
            if not statuses:
                return None, None

            last_entry = statuses[-1]
            return StatusEntry(
                timestamp=self._parse_timestamp(last_entry.get('timestamp', '')),
                status=SessionStatus(last_entry.get('status', 'IDLE')),
                message=last_entry.get('message', ''),
                expected_duration_minutes=last_entry.get('expected_duration_minutes'),
                model_files=last_entry.get('model_files', []),
                output_files=last_entry.get('output_files', []),
                error_type=last_entry.get('error_type'),
                recovery_suggestion=last_entry.get('recovery_suggestion'),
                metadata=last_entry.get('metadata', {})
            ), None
        except Exception as e:
            self.logger.error(f"Failed to read status file {status_path}: {e}")
            return None, None

    def append_status(
        self,
        worktree_path: str,
        status: SessionStatus,
        message: str,
        **kwargs
    ) -> bool:
        """
        Append a new status entry to the status file.

        Args:
            worktree_path: Path to the experiment worktree
            status: New status value
            message: Status message
            **kwargs: Additional fields (expected_duration_minutes, error_type, etc.)

        Returns:
            True if successful
        """
        status_path = Path(worktree_path) / STATUS_FILE_NAME

        try:
            if status_path.exists():
                content = self._read_yaml(status_path)
            else:
                content = {'statuses': []}

            new_entry = {
                'timestamp': datetime.now().isoformat(),
                'status': status.value,
                'message': message
            }

            # Add optional fields
            for key in ['expected_duration_minutes', 'model_files', 'output_files',
                        'error_type', 'recovery_suggestion', 'metadata']:
                if key in kwargs and kwargs[key] is not None:
                    new_entry[key] = kwargs[key]

            content['statuses'].append(new_entry)
            self._write_yaml(status_path, content)

            self.logger.info(f"Updated status to {status.value}: {message}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to append status: {e}")
            return False

    def get_all_statuses(self, worktree_path: str) -> List[StatusEntry]:
        """
        Get all status entries from the status file.

        Args:
            worktree_path: Path to the experiment worktree

        Returns:
            List of all StatusEntry objects
        """
        status_path = Path(worktree_path) / STATUS_FILE_NAME

        if not status_path.exists():
            return []

        try:
            content = self._read_yaml(status_path)
            if not content or 'statuses' not in content:
                return []

            entries = []
            for entry in content['statuses']:
                entries.append(StatusEntry(
                    timestamp=self._parse_timestamp(entry.get('timestamp', '')),
                    status=SessionStatus(entry.get('status', 'IDLE')),
                    message=entry.get('message', ''),
                    expected_duration_minutes=entry.get('expected_duration_minutes'),
                    model_files=entry.get('model_files', []),
                    output_files=entry.get('output_files', []),
                    error_type=entry.get('error_type'),
                    recovery_suggestion=entry.get('recovery_suggestion'),
                    metadata=entry.get('metadata', {})
                ))
            return entries

        except Exception as e:
            self.logger.error(f"Failed to read statuses: {e}")
            return []

    def build_resume_context(
        self,
        exp_id: str,
        worktree_path: str,
        stdout: str,
        stderr: str,
        exit_code: int
    ) -> SessionContext:
        """
        Build context object for session resume.

        Args:
            exp_id: Experiment identifier
            worktree_path: Path to experiment worktree
            stdout: Previous session stdout
            stderr: Previous session stderr
            exit_code: Previous process exit code

        Returns:
            SessionContext for resume
        """
        current_status = self.read_current_status(worktree_path)

        # Increment iteration count
        iteration = self._session_iterations.get(exp_id, 0) + 1
        self._session_iterations[exp_id] = iteration

        # Find task markdown path
        task_markdown_path = ""
        hypotheses_dir = self.experiment_run_dir / "hypotheses"
        if hypotheses_dir.exists():
            for f in hypotheses_dir.glob(f"*{exp_id}*.md"):
                task_markdown_path = str(f)
                break

        # Calculate elapsed time from status history
        elapsed = 0.0
        statuses = self.get_all_statuses(worktree_path)
        if statuses:
            first_ts = statuses[0].timestamp
            elapsed = (datetime.now() - first_ts).total_seconds()

        return SessionContext(
            experiment_id=exp_id,
            previous_stdout=stdout,
            previous_stderr=stderr,
            previous_status=current_status.status if current_status else SessionStatus.IDLE,
            exit_code=exit_code,
            iteration_count=iteration,
            task_markdown_path=task_markdown_path,
            worktree_path=worktree_path,
            elapsed_time_seconds=elapsed
        )

    def log_session_event(
        self,
        exp_id: str,
        event_type: str,
        status: SessionStatus,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a session event to the JSONL log file.

        Args:
            exp_id: Experiment identifier
            event_type: Type of event (START, RESUME, COMPLETE, ERROR)
            status: Current status
            context: Optional context data
        """
        import json

        log_path = self.sessions_dir / f"{exp_id}.jsonl"

        entry = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'session_number': self._session_iterations.get(exp_id, 0),
            'status': status.value,
            'context': context
        }

        try:
            with open(log_path, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to log session event: {e}")

    def get_session_history(self, exp_id: str) -> List[Dict[str, Any]]:
        """
        Read session history from JSONL log.

        Args:
            exp_id: Experiment identifier

        Returns:
            List of session events
        """
        import json

        log_path = self.sessions_dir / f"{exp_id}.jsonl"

        if not log_path.exists():
            return []

        events = []
        try:
            with open(log_path, 'r') as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        except Exception as e:
            self.logger.error(f"Failed to read session history: {e}")

        return events

    def is_terminal_status(self, status: SessionStatus) -> bool:
        """Check if a status is terminal (COMPLETE or ERROR)."""
        return status in (SessionStatus.COMPLETE, SessionStatus.ERROR)

    def _read_yaml(self, path: Path, max_retries: int = MAX_STATUS_READ_RETRIES) -> Dict[str, Any]:
        """Read YAML file with fallback for missing PyYAML and retry logic."""
        content, _ = self._read_yaml_with_error(path, max_retries=max_retries)
        return content

    def _read_yaml_with_error(
        self, path: Path, max_retries: int = MAX_STATUS_READ_RETRIES
    ) -> tuple[Dict[str, Any], Optional[str]]:
        """Read YAML file and return parse error message if parsing failed."""
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                if yaml is not None:
                    with open(path, 'r') as f:
                        return yaml.safe_load(f) or {}, None
                # Simple fallback parser for our specific format
                return self._simple_yaml_parse(path), None
            except FileNotFoundError:
                # File doesn't exist - don't retry, this is expected
                return {}, None
            except PermissionError as e:
                # Permission issues - don't retry
                self.logger.error(f"Permission denied reading {path}: {e}")
                return {}, None
            except Exception as e:
                # Parse errors or other issues - retry with backoff
                error_name = type(e).__name__
                is_parse_error = (
                    (yaml is not None and isinstance(e, yaml.YAMLError)) or
                    'parse' in error_name.lower() or
                    'scan' in error_name.lower() or
                    'yaml' in error_name.lower()
                )

                if is_parse_error and attempt < max_retries - 1:
                    last_error = e
                    wait_time = RETRY_BACKOFF_SECONDS * (2 ** attempt)
                    self.logger.warning(
                        f"Failed to parse YAML {path} (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                elif is_parse_error:
                    last_error = e
                    # Will fall through to "all retries exhausted" message
                else:
                    # Non-parse errors - don't retry
                    self.logger.error(f"Error reading {path}: {e}")
                    return {}, None

        # All retries exhausted
        self.logger.error(
            f"Failed to parse YAML {path} after {max_retries} attempts. "
            f"Last error: {last_error}. File may be corrupted."
        )
        return {}, str(last_error) if last_error is not None else None

    def _write_yaml(self, path: Path, content: Dict[str, Any]) -> None:
        """Write YAML file with fallback for missing PyYAML."""
        if yaml is not None:
            with open(path, 'w') as f:
                yaml.dump(content, f, default_flow_style=False, sort_keys=False)
        else:
            # Simple fallback writer
            self._simple_yaml_write(path, content)

    def _simple_yaml_parse(self, path: Path) -> Dict[str, Any]:
        """Simple YAML parser for status files when PyYAML not available."""
        import re

        result: Dict[str, Any] = {'statuses': []}
        current_entry: Dict[str, Any] = {}

        with open(path, 'r') as f:
            for line in f:
                line = line.rstrip()
                stripped = line.lstrip()

                # Skip empty lines and comments
                if not stripped or stripped.startswith('#'):
                    continue

                # Top-level key
                if stripped.startswith('experiment_id:'):
                    result['experiment_id'] = stripped.split(':', 1)[1].strip().strip('"\'')
                elif stripped.startswith('created_at:'):
                    result['created_at'] = stripped.split(':', 1)[1].strip().strip('"\'')
                elif stripped == 'statuses:':
                    continue
                elif stripped.startswith('- timestamp:'):
                    if current_entry:
                        result['statuses'].append(current_entry)
                    ts = stripped.split(':', 1)[1].strip().strip('"\'')
                    current_entry = {'timestamp': ts}
                elif stripped.startswith('status:'):
                    current_entry['status'] = stripped.split(':', 1)[1].strip().strip('"\'')
                elif stripped.startswith('message:'):
                    current_entry['message'] = stripped.split(':', 1)[1].strip().strip('"\'')

        if current_entry:
            result['statuses'].append(current_entry)

        return result

    def _simple_yaml_write(self, path: Path, content: Dict[str, Any]) -> None:
        """Simple YAML writer for status files when PyYAML not available."""
        with open(path, 'w') as f:
            if 'experiment_id' in content:
                f.write(f"experiment_id: \"{content['experiment_id']}\"\n")
            if 'created_at' in content:
                f.write(f"created_at: \"{content['created_at']}\"\n")

            f.write("statuses:\n")
            for entry in content.get('statuses', []):
                f.write(f"  - timestamp: \"{entry.get('timestamp', '')}\"\n")
                f.write(f"    status: {entry.get('status', 'IDLE')}\n")
                f.write(f"    message: \"{entry.get('message', '')}\"\n")
                if entry.get('expected_duration_minutes'):
                    f.write(f"    expected_duration_minutes: {entry['expected_duration_minutes']}\n")
                if entry.get('error_type'):
                    f.write(f"    error_type: \"{entry['error_type']}\"\n")
                if entry.get('recovery_suggestion'):
                    f.write(f"    recovery_suggestion: \"{entry['recovery_suggestion']}\"\n")

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse ISO format timestamp string."""
        if not ts_str:
            return datetime.now()

        # Handle shell placeholders like "$(date -Iseconds)" by substituting current time
        if ts_str.startswith("$(") or "$(" in ts_str:
            return datetime.now()

        try:
            # Handle various ISO formats
            if 'T' in ts_str:
                if '+' in ts_str or ts_str.endswith('Z'):
                    # With timezone
                    ts_str = ts_str.replace('Z', '+00:00')
                    return datetime.fromisoformat(ts_str)
                else:
                    return datetime.fromisoformat(ts_str)
            else:
                return datetime.fromisoformat(ts_str)
        except ValueError:
            self.logger.warning(f"Failed to parse timestamp: {ts_str}")
            return datetime.now()
