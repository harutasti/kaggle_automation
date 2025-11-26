"""
GPU Resource Allocator for Parallel WAAs

Handles static GPU allocation at launch time for multi-GPU systems.
Supports both multi-GPU allocation (dedicated GPUs per WAA) and
single-GPU sharing (memory fraction per WAA).
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class GPUAllocation:
    """GPU allocation result for a single WAA."""
    waa_index: int                    # 0-based index
    cuda_visible_devices: str         # e.g., "0,1,2" or "0" or ""
    memory_fraction: float            # 1.0 for exclusive, 0.33 for shared
    gpu_count: int                    # Number of GPUs assigned
    total_memory_gb: float            # Total VRAM available for this WAA
    env_vars: Dict[str, str]          # Environment variables to set
    prompt_instructions: str          # Instructions for the WAA prompt


class GPUAllocator:
    """
    Allocates GPU resources to parallel WAAs.

    Allocation strategy:
    - Multi-GPU (GPUs >= WAAs): Fair distribution of GPUs per WAA
      Example: 8 GPUs, 3 WAAs -> WAA_0: cuda:0-2, WAA_1: cuda:3-5, WAA_2: cuda:6-7
    - Single-GPU sharing (GPUs < WAAs): Memory fraction allocation
      Example: 1 GPU, 3 WAAs -> Each gets 33% of VRAM
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize GPU allocator.

        Args:
            config: Configuration dictionary with optional gpu_allocation settings
        """
        self.config = config or {}
        self._gpu_info: Optional[Dict[str, Any]] = None

        # Configuration for GPU allocation
        gpu_config = self.config.get("gpu_allocation", {})
        self.memory_headroom_percent = gpu_config.get("memory_headroom_percent", 5)
        self.enabled = gpu_config.get("enabled", True)

    def detect_gpus(self) -> Dict[str, Any]:
        """
        Detect available GPUs using SystemSpecsDetector.

        Returns:
            Dictionary with GPU information including count, devices, etc.
        """
        if self._gpu_info is not None:
            return self._gpu_info

        try:
            from .system_specs import SystemSpecsDetector
            detector = SystemSpecsDetector()
            specs = detector.get_specs()

            self._gpu_info = {
                "available": specs["gpu"]["available"],
                "count": specs["gpu"]["count"],
                "devices": specs["gpu"]["devices"],
                "cuda_available": specs["gpu"].get("cuda_available", False),
                "compute_capability": specs["gpu"].get("compute_capability", "cpu_only")
            }
        except Exception as e:
            logger.warning(f"Failed to detect GPUs: {e}")
            self._gpu_info = {
                "available": False,
                "count": 0,
                "devices": [],
                "cuda_available": False,
                "compute_capability": "cpu_only"
            }

        logger.info(f"Detected {self._gpu_info['count']} GPU(s), "
                    f"compute_capability={self._gpu_info['compute_capability']}")
        return self._gpu_info

    def allocate(self, waa_index: int, total_waas: int) -> GPUAllocation:
        """
        Allocate GPUs for a specific WAA.

        Args:
            waa_index: 0-based index of the WAA (from exp{M} in experiment_id)
            total_waas: Total number of parallel WAAs

        Returns:
            GPUAllocation with env vars and prompt instructions
        """
        if not self.enabled:
            return self._cpu_only_allocation(waa_index, reason="GPU allocation disabled")

        gpu_info = self.detect_gpus()

        if not gpu_info["available"] or gpu_info["count"] == 0:
            return self._cpu_only_allocation(waa_index, reason="No GPUs available")

        gpu_count = gpu_info["count"]

        if gpu_count >= total_waas:
            # Multi-GPU allocation: distribute GPUs fairly
            return self._multi_gpu_allocation(waa_index, total_waas, gpu_info)
        else:
            # Single/few GPU sharing: use memory fractions
            return self._shared_gpu_allocation(waa_index, total_waas, gpu_info)

    def _multi_gpu_allocation(
        self,
        waa_index: int,
        total_waas: int,
        gpu_info: Dict[str, Any]
    ) -> GPUAllocation:
        """
        Allocate dedicated GPUs to each WAA when we have enough GPUs.

        Distribution algorithm:
        - Base allocation: gpu_count // total_waas per WAA
        - Extra GPUs: Distributed to earlier WAAs (one each)

        Example with 8 GPUs and 3 WAAs:
        - gpus_per_waa = 8 // 3 = 2
        - extra = 8 % 3 = 2
        - WAA_0: 2 + 1 = 3 GPUs (0, 1, 2)
        - WAA_1: 2 + 1 = 3 GPUs (3, 4, 5)
        - WAA_2: 2 + 0 = 2 GPUs (6, 7)
        """
        gpu_count = gpu_info["count"]
        gpus_per_waa = gpu_count // total_waas
        extra_gpus = gpu_count % total_waas

        # Calculate GPU range for this WAA
        start_gpu = 0
        for i in range(waa_index):
            start_gpu += gpus_per_waa + (1 if i < extra_gpus else 0)

        num_gpus = gpus_per_waa + (1 if waa_index < extra_gpus else 0)
        end_gpu = start_gpu + num_gpus

        gpu_ids = list(range(start_gpu, end_gpu))
        cuda_devices = ",".join(str(g) for g in gpu_ids)

        # Calculate total memory for assigned GPUs
        total_memory = 0.0
        for idx in gpu_ids:
            if idx < len(gpu_info["devices"]):
                device = gpu_info["devices"][idx]
                # Handle both memory_gb (pynvml) and memory_mb (nvidia-smi fallback)
                if "memory_gb" in device:
                    total_memory += device["memory_gb"]
                elif "memory_mb" in device:
                    try:
                        mem_str = str(device["memory_mb"]).replace(" MiB", "").strip()
                        total_memory += float(mem_str) / 1024
                    except (ValueError, TypeError):
                        pass

        env_vars = {
            "CUDA_VISIBLE_DEVICES": cuda_devices,
        }

        prompt_instructions = self._generate_multi_gpu_instructions(
            waa_index, gpu_ids, total_memory, total_waas
        )

        logger.info(f"WAA_{waa_index}: Allocated GPUs {gpu_ids} "
                    f"(CUDA_VISIBLE_DEVICES={cuda_devices}, {total_memory:.1f} GB)")

        return GPUAllocation(
            waa_index=waa_index,
            cuda_visible_devices=cuda_devices,
            memory_fraction=1.0,
            gpu_count=num_gpus,
            total_memory_gb=total_memory,
            env_vars=env_vars,
            prompt_instructions=prompt_instructions
        )

    def _shared_gpu_allocation(
        self,
        waa_index: int,
        total_waas: int,
        gpu_info: Dict[str, Any]
    ) -> GPUAllocation:
        """
        Allocate shared GPU access with memory fractions when GPUs < WAAs.

        Distribution algorithm:
        - Round-robin assignment of WAAs to GPUs
        - Memory fraction = 1 / (WAAs sharing this GPU) * (1 - headroom)
        """
        gpu_count = gpu_info["count"]

        # Assign WAAs to GPUs round-robin style
        assigned_gpu = waa_index % gpu_count

        # Calculate how many WAAs are sharing this GPU
        waas_on_this_gpu = 0
        for i in range(total_waas):
            if i % gpu_count == assigned_gpu:
                waas_on_this_gpu += 1

        # Calculate memory fraction with headroom
        base_fraction = 1.0 / waas_on_this_gpu
        headroom = self.memory_headroom_percent / 100.0
        memory_fraction = base_fraction * (1.0 - headroom)

        # Get GPU memory
        total_memory = 0.0
        if assigned_gpu < len(gpu_info["devices"]):
            device = gpu_info["devices"][assigned_gpu]
            if "memory_gb" in device:
                total_memory = device["memory_gb"]
            elif "memory_mb" in device:
                try:
                    mem_str = str(device["memory_mb"]).replace(" MiB", "").strip()
                    total_memory = float(mem_str) / 1024
                except (ValueError, TypeError):
                    pass

        available_memory = total_memory * memory_fraction

        env_vars = {
            "CUDA_VISIBLE_DEVICES": str(assigned_gpu),
            "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:512,expandable_segments:True",
        }

        prompt_instructions = self._generate_shared_gpu_instructions(
            waa_index, assigned_gpu, waas_on_this_gpu,
            memory_fraction, available_memory, total_memory, total_waas
        )

        logger.info(f"WAA_{waa_index}: Sharing GPU {assigned_gpu} with "
                    f"{waas_on_this_gpu - 1} other WAA(s), "
                    f"memory_fraction={memory_fraction:.2f} ({available_memory:.1f} GB)")

        return GPUAllocation(
            waa_index=waa_index,
            cuda_visible_devices=str(assigned_gpu),
            memory_fraction=memory_fraction,
            gpu_count=1,
            total_memory_gb=available_memory,
            env_vars=env_vars,
            prompt_instructions=prompt_instructions
        )

    def _cpu_only_allocation(
        self,
        waa_index: int,
        reason: str = "No GPUs available"
    ) -> GPUAllocation:
        """Return CPU-only allocation when no GPUs available."""
        env_vars = {
            "CUDA_VISIBLE_DEVICES": "",  # Disable GPU access
        }

        prompt_instructions = self._generate_cpu_only_instructions(waa_index, reason)

        logger.info(f"WAA_{waa_index}: CPU-only allocation ({reason})")

        return GPUAllocation(
            waa_index=waa_index,
            cuda_visible_devices="",
            memory_fraction=0.0,
            gpu_count=0,
            total_memory_gb=0.0,
            env_vars=env_vars,
            prompt_instructions=prompt_instructions
        )

    def _generate_multi_gpu_instructions(
        self,
        waa_index: int,
        gpu_ids: List[int],
        total_memory: float,
        total_waas: int
    ) -> str:
        """Generate prompt instructions for multi-GPU exclusive allocation."""
        gpu_list = ", ".join(f"cuda:{g}" for g in gpu_ids)
        remapped_range = f"cuda:0" if len(gpu_ids) == 1 else f"cuda:0 to cuda:{len(gpu_ids)-1}"

        return f"""## GPU Resource Allocation

**WAA Index**: {waa_index} (of {total_waas} total)
**Assigned GPUs**: {gpu_list} ({len(gpu_ids)} GPU(s))
**Total VRAM**: {total_memory:.1f} GB
**Allocation Mode**: Exclusive (full access)

### Environment Configuration
- `CUDA_VISIBLE_DEVICES={",".join(str(g) for g in gpu_ids)}`

### Usage Guidelines

1. **GPU Access**: You have **exclusive access** to your assigned GPU(s)
2. **Device Mapping**: PyTorch remaps your GPUs to {remapped_range}
3. **No memory limits needed**: You have full access to all {total_memory:.1f} GB

### Code Example
```python
import torch

# Check GPU availability
print(f"GPUs available: {{torch.cuda.device_count()}}")  # Should be {len(gpu_ids)}

# Use your primary GPU
device = torch.device('cuda:0')
model = model.to(device)
```

### Multi-GPU Training (if using {len(gpu_ids)} GPUs)
```python
import torch.nn as nn

# DataParallel for simple multi-GPU
if torch.cuda.device_count() > 1:
    model = nn.DataParallel(model)
model = model.to('cuda:0')
```
"""

    def _generate_shared_gpu_instructions(
        self,
        waa_index: int,
        gpu_id: int,
        waas_sharing: int,
        memory_fraction: float,
        available_memory: float,
        total_memory: float,
        total_waas: int
    ) -> str:
        """Generate prompt instructions for shared GPU allocation."""
        memory_percent = int(memory_fraction * 100)

        return f"""## GPU Resource Allocation

**WAA Index**: {waa_index} (of {total_waas} total)
**Assigned GPU**: cuda:{gpu_id}
**Sharing With**: {waas_sharing - 1} other WAA(s)
**Your Memory Allocation**: {available_memory:.1f} GB ({memory_percent}% of {total_memory:.1f} GB)
**Allocation Mode**: Shared (memory-limited)

### Environment Configuration
- `CUDA_VISIBLE_DEVICES={gpu_id}`
- `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512,expandable_segments:True`

### CRITICAL: Memory Management

You are **sharing this GPU** with other experiments. You **MUST** limit your memory usage.

#### Step 1: Set Memory Fraction FIRST
```python
import torch

# CRITICAL: Set this BEFORE any CUDA operations!
torch.cuda.set_per_process_memory_fraction({memory_fraction:.3f}, device=0)

# Verify your allocation
print(f"Memory fraction: {memory_fraction:.3f}")
print(f"Available VRAM: ~{available_memory:.1f} GB")
```

#### Step 2: Use Appropriate Batch Sizes
```python
# Calculate safe batch size based on your memory limit
# Rule of thumb: Leave 20% headroom for gradients/optimizer states
usable_memory_gb = {available_memory:.1f} * 0.8  # ~{available_memory * 0.8:.1f} GB

# Example for typical models:
# - Small model (ResNet18): batch_size ~64-128
# - Medium model (ResNet50): batch_size ~32-64
# - Large model (ViT-B): batch_size ~16-32
```

#### Step 3: Handle OOM Gracefully
```python
try:
    outputs = model(inputs)
except torch.cuda.OutOfMemoryError:
    torch.cuda.empty_cache()
    print("OOM error - reduce batch size!")
    # Retry with smaller batch
```

#### Step 4: Clear Cache Periodically
```python
# Between training phases or after validation
torch.cuda.empty_cache()
import gc
gc.collect()
```

### WARNING
**Exceeding your memory allocation ({available_memory:.1f} GB) will cause CUDA OOM errors and may crash other parallel experiments!**
"""

    def _generate_cpu_only_instructions(
        self,
        waa_index: int,
        reason: str
    ) -> str:
        """Generate prompt instructions for CPU-only execution."""
        return f"""## GPU Resource Allocation

**WAA Index**: {waa_index}
**Status**: CPU-only mode
**Reason**: {reason}

### Environment Configuration
- `CUDA_VISIBLE_DEVICES=""` (GPU access disabled)

### Guidelines for CPU-Only Execution

Since no GPU is available, use CPU-optimized algorithms:

#### Recommended Models
```python
# Tree-based models (highly efficient on CPU)
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
import lightgbm as lgb
import xgboost as xgb

# Use all CPU cores
model = RandomForestClassifier(n_jobs=-1)
lgb_params = {{'num_threads': -1}}
xgb_params = {{'nthread': -1}}
```

#### Avoid Deep Learning
- Neural networks will be extremely slow on CPU
- If you must use PyTorch/TensorFlow, use small models only
- Consider using sklearn alternatives instead

#### Memory Optimization
```python
# Use memory-efficient data types
import pandas as pd
df = df.astype({{'int_col': 'int32', 'float_col': 'float32'}})

# Process data in chunks if needed
for chunk in pd.read_csv('large_file.csv', chunksize=10000):
    process(chunk)
```
"""

    @staticmethod
    def parse_waa_index(experiment_id: str) -> int:
        """
        Extract WAA index from experiment_id.

        Format: iter{N}_exp{M}_{uuid} -> returns M-1 (0-based)

        Args:
            experiment_id: e.g., "iter0_exp2_abc123"

        Returns:
            0-based WAA index (e.g., 1 for exp2)
        """
        match = re.match(r'iter\d+_exp(\d+)_', experiment_id)
        if match:
            return int(match.group(1)) - 1  # Convert to 0-based
        return 0  # Default to first WAA if parsing fails

    def get_allocation_summary(self, total_waas: int) -> str:
        """
        Get a summary of GPU allocation for all WAAs.

        Args:
            total_waas: Total number of WAAs

        Returns:
            Human-readable summary string
        """
        gpu_info = self.detect_gpus()
        gpu_count = gpu_info.get("count", 0)

        lines = [
            f"GPU Allocation Summary:",
            f"  Total GPUs: {gpu_count}",
            f"  Total WAAs: {total_waas}",
            f"  Mode: {'Multi-GPU (exclusive)' if gpu_count >= total_waas else 'Shared GPU' if gpu_count > 0 else 'CPU-only'}",
            ""
        ]

        for i in range(total_waas):
            alloc = self.allocate(i, total_waas)
            lines.append(f"  WAA_{i}: CUDA_VISIBLE_DEVICES={alloc.cuda_visible_devices or 'N/A'}, "
                         f"memory={alloc.total_memory_gb:.1f} GB, "
                         f"fraction={alloc.memory_fraction:.2f}")

        return "\n".join(lines)
