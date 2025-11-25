"""
System Specifications Module

Detects hardware and system specifications for resource-aware
hypothesis generation. Cross-platform support for Linux and macOS.
"""

import platform
import os
import subprocess
import multiprocessing
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional imports for better functionality
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available. Using fallback methods for system detection.")

try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False


class SystemSpecsDetector:
    """Detects system specifications including CPU, RAM, GPU, and OS details."""

    def __init__(self):
        """Initialize the system specs detector."""
        self.platform = platform.system()
        self.specs = {}

    def get_specs(self) -> Dict[str, Any]:
        """
        Get comprehensive system specifications.

        Returns:
            Dictionary containing system specifications
        """
        logger.info(f"Detecting system specifications on {self.platform}")

        self.specs = {
            "platform": self._get_platform_info(),
            "cpu": self._get_cpu_info(),
            "memory": self._get_memory_info(),
            "gpu": self._get_gpu_info(),
            "python": self._get_python_info(),
            "runtime_estimates": self._calculate_runtime_estimates()
        }

        return self.specs

    def _get_platform_info(self) -> Dict[str, str]:
        """Get platform and OS information."""
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor()
        }

        # Additional OS-specific info
        if self.platform == "Darwin":
            info["os_type"] = "macOS"
            try:
                result = subprocess.run(
                    ["sw_vers", "-productVersion"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    info["macos_version"] = result.stdout.strip()
            except Exception as e:
                logger.debug(f"Could not get macOS version: {e}")

        elif self.platform == "Linux":
            info["os_type"] = "Linux"
            # Try to get distro information
            try:
                if Path("/etc/os-release").exists():
                    with open("/etc/os-release", "r") as f:
                        for line in f:
                            if line.startswith("PRETTY_NAME="):
                                info["distro"] = line.split("=")[1].strip().strip('"')
                                break
            except Exception as e:
                logger.debug(f"Could not get Linux distro: {e}")

        return info

    def _get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU information."""
        info = {
            "count": multiprocessing.cpu_count(),
            "physical_cores": None,
            "model": None,
            "frequency_mhz": None,
            "architecture": platform.machine()
        }

        # Get physical core count
        if PSUTIL_AVAILABLE:
            try:
                info["physical_cores"] = psutil.cpu_count(logical=False)
                freq = psutil.cpu_freq()
                if freq:
                    info["frequency_mhz"] = freq.max if freq.max else freq.current
            except Exception as e:
                logger.debug(f"Could not get CPU details via psutil: {e}")

        # Platform-specific CPU info
        if self.platform == "Darwin":
            # macOS specific
            try:
                # Get CPU brand
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    info["model"] = result.stdout.strip()

                # Get physical cores if not already obtained
                if info["physical_cores"] is None:
                    result = subprocess.run(
                        ["sysctl", "-n", "hw.physicalcpu"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        info["physical_cores"] = int(result.stdout.strip())

                # Check for Apple Silicon
                if "Apple" in info.get("model", "") or "M1" in info.get("model", "") or "M2" in info.get("model", "") or "M3" in info.get("model", ""):
                    info["has_neural_engine"] = True
                    info["architecture_type"] = "Apple Silicon"
                else:
                    info["architecture_type"] = "Intel"

            except Exception as e:
                logger.debug(f"Could not get macOS CPU details: {e}")

        elif self.platform == "Linux":
            # Linux specific
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if "model name" in line and info["model"] is None:
                            info["model"] = line.split(":")[1].strip()
                        elif "cpu cores" in line and info["physical_cores"] is None:
                            info["physical_cores"] = int(line.split(":")[1].strip())
                        elif "cpu MHz" in line and info["frequency_mhz"] is None:
                            info["frequency_mhz"] = float(line.split(":")[1].strip())
            except Exception as e:
                logger.debug(f"Could not read /proc/cpuinfo: {e}")

        # Fallback for physical cores
        if info["physical_cores"] is None:
            info["physical_cores"] = info["count"] // 2  # Assume hyperthreading

        # Determine compute capability
        info["compute_type"] = self._classify_cpu_capability(info)

        return info

    def _get_memory_info(self) -> Dict[str, Any]:
        """Get memory (RAM) information."""
        info = {
            "total_gb": None,
            "available_gb": None,
            "used_gb": None,
            "percent_used": None
        }

        if PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                info["total_gb"] = mem.total / (1024**3)
                info["available_gb"] = mem.available / (1024**3)
                info["used_gb"] = mem.used / (1024**3)
                info["percent_used"] = mem.percent
            except Exception as e:
                logger.debug(f"Could not get memory via psutil: {e}")
        else:
            # Platform-specific fallbacks
            if self.platform == "Darwin":
                try:
                    result = subprocess.run(
                        ["sysctl", "hw.memsize"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        mem_bytes = int(result.stdout.split(":")[1].strip())
                        info["total_gb"] = mem_bytes / (1024**3)
                except Exception as e:
                    logger.debug(f"Could not get macOS memory: {e}")

            elif self.platform == "Linux":
                try:
                    with open("/proc/meminfo", "r") as f:
                        for line in f:
                            if line.startswith("MemTotal:"):
                                mem_kb = int(line.split()[1])
                                info["total_gb"] = mem_kb / (1024**2)
                            elif line.startswith("MemAvailable:"):
                                mem_kb = int(line.split()[1])
                                info["available_gb"] = mem_kb / (1024**2)
                except Exception as e:
                    logger.debug(f"Could not read /proc/meminfo: {e}")

        # Calculate derived values
        if info["total_gb"] and info["available_gb"]:
            info["used_gb"] = info["total_gb"] - info["available_gb"]
            info["percent_used"] = (info["used_gb"] / info["total_gb"]) * 100

        # Classify memory capacity
        info["memory_class"] = self._classify_memory_capacity(info.get("total_gb", 0))

        return info

    def _get_gpu_info(self) -> Dict[str, Any]:
        """Get GPU information."""
        info = {
            "available": False,
            "count": 0,
            "devices": [],
            "cuda_available": False,
            "metal_available": False,
            "compute_capability": "cpu_only"
        }

        # Check for NVIDIA GPUs
        nvidia_info = self._check_nvidia_gpu()
        if nvidia_info["available"]:
            info.update(nvidia_info)
            return info

        # Check for Apple Silicon GPU (Metal)
        if self.platform == "Darwin":
            metal_info = self._check_apple_gpu()
            if metal_info["available"]:
                info.update(metal_info)
                return info

        # Check for AMD GPUs on Linux
        if self.platform == "Linux":
            amd_info = self._check_amd_gpu()
            if amd_info["available"]:
                info.update(amd_info)
                return info

        return info

    def _check_nvidia_gpu(self) -> Dict[str, Any]:
        """Check for NVIDIA GPUs."""
        info = {
            "available": False,
            "count": 0,
            "devices": [],
            "cuda_available": False
        }

        # Try using pynvml first
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                info["available"] = True
                info["count"] = device_count
                info["cuda_available"] = True

                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    name = pynvml.nvmlDeviceGetName(handle).decode()
                    memory_info = pynvml.nvmlDeviceGetMemoryInfo(handle)

                    device_info = {
                        "index": i,
                        "name": name,
                        "memory_gb": memory_info.total / (1024**3),
                        "memory_free_gb": memory_info.free / (1024**3)
                    }
                    info["devices"].append(device_info)

                pynvml.nvmlShutdown()
                info["compute_capability"] = "cuda"
                return info
            except Exception as e:
                logger.debug(f"Could not get NVIDIA GPU info via pynvml: {e}")

        # Fallback to nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                info["available"] = True
                info["cuda_available"] = True
                lines = result.stdout.strip().split("\n")
                info["count"] = len(lines)

                for i, line in enumerate(lines):
                    parts = line.split(",")
                    if len(parts) >= 3:
                        device_info = {
                            "index": i,
                            "name": parts[0].strip(),
                            "memory_mb": parts[1].strip(),
                            "memory_free_mb": parts[2].strip()
                        }
                        info["devices"].append(device_info)

                info["compute_capability"] = "cuda"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return info

    def _check_apple_gpu(self) -> Dict[str, Any]:
        """Check for Apple Silicon GPU (Metal support)."""
        info = {
            "available": False,
            "metal_available": False,
            "devices": []
        }

        try:
            # Check if this is Apple Silicon
            result = subprocess.run(
                ["sysctl", "-n", "hw.optional.arm64"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip() == "1":
                info["available"] = True
                info["metal_available"] = True

                # Get GPU cores for Apple Silicon
                result = subprocess.run(
                    ["sysctl", "-n", "hw.perflevel0.gpucount"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                gpu_cores = 0
                if result.returncode == 0:
                    try:
                        gpu_cores = int(result.stdout.strip())
                    except:
                        pass

                device_info = {
                    "name": "Apple Silicon GPU",
                    "type": "integrated",
                    "metal_supported": True,
                    "gpu_cores": gpu_cores if gpu_cores > 0 else "unknown"
                }

                # Try to determine specific chip
                cpu_result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if cpu_result.returncode == 0:
                    cpu_brand = cpu_result.stdout.strip()
                    if "M1" in cpu_brand:
                        device_info["chip"] = "M1"
                    elif "M2" in cpu_brand:
                        device_info["chip"] = "M2"
                    elif "M3" in cpu_brand:
                        device_info["chip"] = "M3"
                    else:
                        device_info["chip"] = "Apple Silicon"

                info["devices"].append(device_info)
                info["count"] = 1
                info["compute_capability"] = "metal"

        except Exception as e:
            logger.debug(f"Could not check for Apple GPU: {e}")

        return info

    def _check_amd_gpu(self) -> Dict[str, Any]:
        """Check for AMD GPUs on Linux."""
        info = {
            "available": False,
            "devices": []
        }

        try:
            # Check for ROCm installation
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                info["available"] = True
                info["rocm_available"] = True
                # Parse output for GPU information
                lines = result.stdout.strip().split("\n")
                for i, line in enumerate(lines):
                    if "GPU" in line:
                        info["devices"].append({
                            "index": i,
                            "name": line.strip(),
                            "type": "AMD"
                        })
                info["count"] = len(info["devices"])
                info["compute_capability"] = "rocm"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return info

    def _get_python_info(self) -> Dict[str, str]:
        """Get Python environment information."""
        import sys

        info = {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable
        }

        # Check for common ML frameworks
        frameworks = {}
        try:
            import torch
            frameworks["pytorch"] = torch.__version__
            if torch.cuda.is_available():
                frameworks["pytorch_cuda"] = True
        except ImportError:
            pass

        try:
            import tensorflow as tf
            frameworks["tensorflow"] = tf.__version__
        except ImportError:
            pass

        try:
            import sklearn
            frameworks["sklearn"] = sklearn.__version__
        except ImportError:
            pass

        try:
            import xgboost
            frameworks["xgboost"] = xgboost.__version__
        except ImportError:
            pass

        try:
            import lightgbm
            frameworks["lightgbm"] = lightgbm.__version__
        except ImportError:
            pass

        info["ml_frameworks"] = frameworks

        return info

    def _classify_cpu_capability(self, cpu_info: Dict) -> str:
        """Classify CPU compute capability."""
        cores = cpu_info.get("physical_cores", 1)

        if cores >= 32:
            return "high_performance"
        elif cores >= 8:
            return "standard"
        elif cores >= 4:
            return "basic"
        else:
            return "limited"

    def _classify_memory_capacity(self, total_gb: Optional[float]) -> str:
        """Classify memory capacity."""
        if total_gb is None:
            return "unknown"
        elif total_gb >= 64:
            return "high_memory"
        elif total_gb >= 16:
            return "standard_memory"
        elif total_gb >= 8:
            return "basic_memory"
        else:
            return "limited_memory"

    def _calculate_runtime_estimates(self) -> Dict[str, str]:
        """Calculate estimated runtimes based on system capabilities."""
        cpu_type = self.specs.get("cpu", {}).get("compute_type", "basic")
        memory_class = self.specs.get("memory", {}).get("memory_class", "basic_memory")
        gpu_available = self.specs.get("gpu", {}).get("available", False)

        estimates = {}

        # Base estimates (in minutes)
        if gpu_available:
            estimates["small_model"] = "5-10"
            estimates["medium_model"] = "15-30"
            estimates["large_model"] = "30-60"
            estimates["ensemble"] = "45-90"
            estimates["hardware_type"] = "GPU"
        elif cpu_type == "high_performance":
            estimates["small_model"] = "10-20"
            estimates["medium_model"] = "30-60"
            estimates["large_model"] = "60-120"
            estimates["ensemble"] = "90-180"
            estimates["hardware_type"] = "CPU (High Performance)"
        elif cpu_type == "standard":
            estimates["small_model"] = "15-30"
            estimates["medium_model"] = "45-90"
            estimates["large_model"] = "90-180"
            estimates["ensemble"] = "120-240"
            estimates["hardware_type"] = "CPU (Standard)"
        else:
            estimates["small_model"] = "20-40"
            estimates["medium_model"] = "60-120"
            estimates["large_model"] = "120-240"
            estimates["ensemble"] = "180-360"
            estimates["hardware_type"] = "CPU (Basic)"

        # Adjust for memory constraints
        if memory_class == "limited_memory":
            estimates["warning"] = "Limited memory may require batch size reduction"
        elif memory_class == "high_memory":
            estimates["note"] = "High memory allows for larger batch sizes"

        return estimates

    def get_prompt_placeholders(self) -> Dict[str, Any]:
        """
        Get placeholder values for KSE prompts related to system specs.

        Returns:
            Dictionary with keys matching prompt placeholders
        """
        specs = self.get_specs()

        placeholders = {
            "CPU_or_GPU": specs["runtime_estimates"].get("hardware_type", "CPU"),
            "expected_runtime_small": specs["runtime_estimates"].get("small_model", "15-30"),
            "expected_runtime_medium": specs["runtime_estimates"].get("medium_model", "45-90"),
            "expected_runtime_large": specs["runtime_estimates"].get("large_model", "90-180"),
            "cpu_cores": specs["cpu"].get("count", "[ASSUMED: 4]"),
            "memory_gb": f"{specs['memory'].get('total_gb', 8):.1f}" if specs["memory"].get("total_gb") else "[ASSUMED: 8]",
            "gpu_available": "Yes" if specs["gpu"].get("available") else "No",
            "platform": specs["platform"].get("os_type", specs["platform"].get("system", "Unknown"))
        }

        # Add GPU-specific information if available
        if specs["gpu"].get("available") and specs["gpu"].get("devices"):
            gpu_device = specs["gpu"]["devices"][0]
            placeholders["gpu_name"] = gpu_device.get("name", "Unknown GPU")
            if "memory_gb" in gpu_device:
                placeholders["gpu_memory_gb"] = f"{gpu_device['memory_gb']:.1f}"
            else:
                placeholders["gpu_memory_gb"] = "Unknown"
        else:
            placeholders["gpu_name"] = "No GPU"
            placeholders["gpu_memory_gb"] = "N/A"

        return placeholders

    def to_markdown(self) -> str:
        """
        Generate a markdown summary of system specifications.

        Returns:
            Markdown-formatted string with system specs
        """
        specs = self.get_specs()

        md = "## System Specifications\n\n"

        # Platform
        md += "### Platform\n"
        md += f"- OS: {specs['platform'].get('os_type', specs['platform'].get('system', 'Unknown'))}\n"
        md += f"- Version: {specs['platform'].get('version', 'Unknown')}\n"
        md += f"- Architecture: {specs['platform'].get('machine', 'Unknown')}\n\n"

        # CPU
        md += "### CPU\n"
        md += f"- Model: {specs['cpu'].get('model', 'Unknown')}\n"
        md += f"- Cores: {specs['cpu'].get('count', 'Unknown')} logical, {specs['cpu'].get('physical_cores', 'Unknown')} physical\n"
        if specs['cpu'].get('frequency_mhz'):
            md += f"- Frequency: {specs['cpu']['frequency_mhz']} MHz\n"
        md += f"- Capability: {specs['cpu'].get('compute_type', 'Unknown')}\n\n"

        # Memory
        md += "### Memory\n"
        if specs['memory'].get('total_gb'):
            md += f"- Total: {specs['memory']['total_gb']:.1f} GB\n"
            if specs['memory'].get('available_gb'):
                md += f"- Available: {specs['memory']['available_gb']:.1f} GB\n"
                md += f"- Used: {specs['memory'].get('percent_used', 0):.1f}%\n"
        else:
            md += "- Total: Unknown\n"
        md += f"- Class: {specs['memory'].get('memory_class', 'Unknown')}\n\n"

        # GPU
        md += "### GPU\n"
        if specs['gpu'].get('available'):
            md += f"- Available: Yes\n"
            md += f"- Count: {specs['gpu'].get('count', 0)}\n"
            if specs['gpu'].get('devices'):
                for device in specs['gpu']['devices']:
                    md += f"- Device: {device.get('name', 'Unknown')}\n"
                    if 'memory_gb' in device:
                        md += f"  - Memory: {device['memory_gb']:.1f} GB\n"
            if specs['gpu'].get('cuda_available'):
                md += "- CUDA: Available\n"
            if specs['gpu'].get('metal_available'):
                md += "- Metal: Available\n"
        else:
            md += "- Available: No\n\n"

        # Runtime Estimates
        md += "### Estimated Runtimes\n"
        estimates = specs.get('runtime_estimates', {})
        md += f"- Hardware Type: {estimates.get('hardware_type', 'Unknown')}\n"
        md += f"- Small Model: {estimates.get('small_model', 'Unknown')} minutes\n"
        md += f"- Medium Model: {estimates.get('medium_model', 'Unknown')} minutes\n"
        md += f"- Large Model: {estimates.get('large_model', 'Unknown')} minutes\n"
        md += f"- Ensemble: {estimates.get('ensemble', 'Unknown')} minutes\n"

        if 'warning' in estimates:
            md += f"\n⚠️ {estimates['warning']}\n"
        if 'note' in estimates:
            md += f"\nℹ️ {estimates['note']}\n"

        return md