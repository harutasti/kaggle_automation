"""
Resource Monitor for detecting training completion.

Monitors GPU/CPU utilization and model file activity to determine
when long-running training processes have completed.
"""

import os
import time
import subprocess
import platform
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
import logging

# Model file extensions to monitor for write activity
MODEL_FILE_EXTENSIONS: Set[str] = {
    '.pkl', '.pt', '.pth', '.bin', '.onnx', '.h5', '.keras',
    '.joblib', '.sav', '.model', '.cbm', '.lgb', '.xgb',
    '.weights', '.ckpt', '.safetensors'
}


@dataclass
class ResourceSnapshot:
    """Point-in-time resource utilization snapshot."""
    timestamp: datetime
    gpu_utilization_percent: Optional[float]  # None if no GPU
    gpu_memory_used_gb: Optional[float]
    cpu_utilization_percent: float
    memory_used_gb: float
    model_files_modified: List[str] = field(default_factory=list)


class ResourceMonitor:
    """
    Monitors system resources to detect when training is complete.

    Training is considered complete when:
    1. GPU utilization < 10% for threshold minutes (or CPU if no GPU)
    2. No model file writes detected for threshold minutes
    """

    def __init__(self, watch_directory: str, logger: Optional[logging.Logger] = None):
        """
        Initialize the resource monitor.

        Args:
            watch_directory: Directory to monitor for model file activity
            logger: Optional logger instance
        """
        self.watch_dir = Path(watch_directory)
        self.logger = logger or logging.getLogger(__name__)

        # History of snapshots for trend analysis
        self._utilization_history: List[ResourceSnapshot] = []

        # Track model file modification times
        self._file_mod_times: Dict[str, float] = {}

        # Cache GPU detection result
        self._gpu_available: Optional[bool] = None
        self._gpu_type: Optional[str] = None  # 'nvidia', 'apple', 'amd', None

        # Initialize file tracking
        self._update_file_mod_times()

    def _detect_gpu_type(self) -> Optional[str]:
        """Detect available GPU type."""
        if self._gpu_type is not None or self._gpu_available is False:
            return self._gpu_type

        # Check NVIDIA GPU (most common for ML)
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                self._gpu_type = 'nvidia'
                self._gpu_available = True
                return 'nvidia'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Check Apple Silicon (macOS with M1/M2/M3)
        if platform.system() == 'Darwin' and platform.machine() == 'arm64':
            self._gpu_type = 'apple'
            self._gpu_available = True
            return 'apple'

        # Check AMD ROCm
        try:
            result = subprocess.run(
                ['rocm-smi', '--showuse'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                self._gpu_type = 'amd'
                self._gpu_available = True
                return 'amd'
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        self._gpu_available = False
        self._gpu_type = None
        return None

    def get_gpu_utilization(self) -> Optional[float]:
        """
        Get current GPU utilization percentage.

        Returns:
            GPU utilization 0-100, or None if no GPU available
        """
        gpu_type = self._detect_gpu_type()

        if gpu_type == 'nvidia':
            return self._get_nvidia_utilization()
        elif gpu_type == 'apple':
            return self._get_apple_utilization()
        elif gpu_type == 'amd':
            return self._get_amd_utilization()

        return None

    def _get_nvidia_utilization(self) -> Optional[float]:
        """Get NVIDIA GPU utilization using nvidia-smi."""
        try:
            # Try pynvml first for better performance
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                pynvml.nvmlShutdown()
                return float(util.gpu)
            except ImportError:
                pass

            # Fallback to nvidia-smi
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Handle multiple GPUs - take max utilization
                utils = [float(x.strip()) for x in result.stdout.strip().split('\n') if x.strip()]
                return max(utils) if utils else None
        except Exception as e:
            self.logger.warning(f"Failed to get NVIDIA GPU utilization: {e}")

        return None

    def _get_apple_utilization(self) -> Optional[float]:
        """
        Get Apple Silicon GPU utilization.

        Note: macOS doesn't expose GPU utilization directly.
        We use powermetrics or activity monitor data as proxy.
        For ML workloads, we fall back to CPU monitoring.
        """
        # Apple Silicon GPU utilization is not easily accessible
        # powermetrics requires root, so we return None and rely on CPU fallback
        self.logger.debug("Apple Silicon GPU utilization not directly available, using CPU fallback")
        return None

    def _get_amd_utilization(self) -> Optional[float]:
        """Get AMD GPU utilization using rocm-smi."""
        try:
            result = subprocess.run(
                ['rocm-smi', '--showuse', '--json'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                # Parse ROCm JSON output
                for card in data.get('card0', {}).values():
                    if 'GPU use (%)' in card:
                        return float(card['GPU use (%)'])
        except Exception as e:
            self.logger.warning(f"Failed to get AMD GPU utilization: {e}")

        return None

    def get_cpu_utilization(self) -> float:
        """
        Get current CPU utilization percentage.

        Returns:
            CPU utilization 0-100
        """
        try:
            import psutil
            return psutil.cpu_percent(interval=0.5)
        except ImportError:
            # Fallback using /proc/stat on Linux or top on macOS
            return self._get_cpu_utilization_fallback()

    def _get_cpu_utilization_fallback(self) -> float:
        """Fallback CPU utilization using system commands."""
        system = platform.system()

        try:
            if system == 'Linux':
                # Read /proc/stat
                with open('/proc/stat', 'r') as f:
                    line = f.readline()
                    values = line.split()[1:8]
                    values = [int(v) for v in values]
                    idle = values[3]
                    total = sum(values)
                    # Would need previous reading for delta, return estimate
                    return min(100.0, (1 - idle / total) * 100)
            elif system == 'Darwin':
                # Use top on macOS
                result = subprocess.run(
                    ['top', '-l', '1', '-n', '0'],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split('\n'):
                    if 'CPU usage' in line:
                        # Parse "CPU usage: X% user, Y% sys, Z% idle"
                        parts = line.split(',')
                        for part in parts:
                            if 'idle' in part:
                                idle = float(part.split('%')[0].split()[-1])
                                return 100.0 - idle
        except Exception as e:
            self.logger.warning(f"Failed to get CPU utilization: {e}")

        return 50.0  # Default fallback

    def _get_model_files(self) -> List[Path]:
        """Get all model files in the watch directory."""
        model_files = []
        if not self.watch_dir.exists():
            return model_files

        for ext in MODEL_FILE_EXTENSIONS:
            model_files.extend(self.watch_dir.rglob(f'*{ext}'))

        return model_files

    def _update_file_mod_times(self) -> List[str]:
        """
        Update tracked file modification times.

        Returns:
            List of files that were modified since last check
        """
        modified_files = []
        current_files = {}

        for file_path in self._get_model_files():
            try:
                mtime = file_path.stat().st_mtime
                str_path = str(file_path)
                current_files[str_path] = mtime

                # Check if this file was modified
                if str_path in self._file_mod_times:
                    if mtime > self._file_mod_times[str_path]:
                        modified_files.append(str_path)
                else:
                    # New file
                    modified_files.append(str_path)
            except (OSError, FileNotFoundError):
                continue

        self._file_mod_times = current_files
        return modified_files

    def check_model_file_activity(self, seconds_threshold: int = 60) -> bool:
        """
        Check if any model files were modified recently.

        Args:
            seconds_threshold: Consider files modified within this many seconds as active

        Returns:
            True if any model files were modified within threshold
        """
        now = time.time()

        for file_path in self._get_model_files():
            try:
                mtime = file_path.stat().st_mtime
                if now - mtime < seconds_threshold:
                    self.logger.debug(f"Model file recently modified: {file_path}")
                    return True
            except (OSError, FileNotFoundError):
                continue

        return False

    def take_snapshot(self) -> ResourceSnapshot:
        """
        Take a current resource utilization snapshot.

        Returns:
            ResourceSnapshot with current metrics
        """
        gpu_util = self.get_gpu_utilization()
        cpu_util = self.get_cpu_utilization()

        # Get GPU memory if available
        gpu_memory = None
        if self._gpu_type == 'nvidia':
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_memory = mem_info.used / (1024**3)  # Convert to GB
                pynvml.nvmlShutdown()
            except:
                pass

        # Get system memory
        memory_used = 0.0
        try:
            import psutil
            mem = psutil.virtual_memory()
            memory_used = mem.used / (1024**3)
        except ImportError:
            pass

        modified_files = self._update_file_mod_times()

        snapshot = ResourceSnapshot(
            timestamp=datetime.now(),
            gpu_utilization_percent=gpu_util,
            gpu_memory_used_gb=gpu_memory,
            cpu_utilization_percent=cpu_util,
            memory_used_gb=memory_used,
            model_files_modified=modified_files
        )

        self._utilization_history.append(snapshot)

        # Keep history bounded (last 30 minutes at 30s intervals = 60 entries)
        if len(self._utilization_history) > 60:
            self._utilization_history = self._utilization_history[-60:]

        return snapshot

    def is_training_likely_complete(self, idle_threshold_minutes: int = 3) -> bool:
        """
        Determine if training is likely complete.

        Criteria:
        1. GPU/CPU utilization < 10% for threshold minutes
        2. No model file writes for threshold minutes

        Args:
            idle_threshold_minutes: Minutes of idle time required

        Returns:
            True if training appears complete
        """
        threshold = timedelta(minutes=idle_threshold_minutes)
        now = datetime.now()

        # Take fresh snapshot
        snapshot = self.take_snapshot()

        # Check for recent file writes (always disqualifies)
        if self.check_model_file_activity(seconds_threshold=60):
            self.logger.debug("Model file activity detected, training not complete")
            return False

        # Need enough history
        if len(self._utilization_history) < 2:
            self.logger.debug("Insufficient history, training status unknown")
            return False

        # Check utilization over threshold period
        utilization_threshold = 10.0
        idle_start = None

        for snap in reversed(self._utilization_history):
            age = now - snap.timestamp
            if age > threshold:
                break

            # Use GPU if available, otherwise CPU
            util = snap.gpu_utilization_percent
            if util is None:
                util = snap.cpu_utilization_percent

            if util > utilization_threshold:
                self.logger.debug(f"Utilization {util:.1f}% > threshold, training not complete")
                return False

            if idle_start is None:
                idle_start = snap.timestamp

        # Verify we have enough idle history
        if idle_start is None:
            return False

        idle_duration = now - idle_start
        if idle_duration >= threshold:
            self.logger.info(
                f"Training likely complete: idle for {idle_duration.total_seconds()/60:.1f} minutes, "
                f"no file writes"
            )
            return True

        return False

    def get_utilization_summary(self) -> Dict[str, Any]:
        """
        Get summary of recent utilization.

        Returns:
            Dict with utilization statistics
        """
        if not self._utilization_history:
            return {'status': 'no_data'}

        recent = self._utilization_history[-10:]  # Last ~5 minutes

        gpu_utils = [s.gpu_utilization_percent for s in recent if s.gpu_utilization_percent is not None]
        cpu_utils = [s.cpu_utilization_percent for s in recent]

        return {
            'gpu_available': self._gpu_available,
            'gpu_type': self._gpu_type,
            'gpu_avg': sum(gpu_utils) / len(gpu_utils) if gpu_utils else None,
            'cpu_avg': sum(cpu_utils) / len(cpu_utils) if cpu_utils else None,
            'model_files_tracked': len(self._file_mod_times),
            'snapshots_count': len(self._utilization_history)
        }
