## GPU Resource Allocation

**WAA Index**: {waa_index} (of {total_waas} total)
**Assigned GPUs**: {cuda_visible_devices}
**Memory Allocation**: {memory_percent}% ({total_memory_gb:.1f} GB)
**Number of GPUs**: {gpu_count}
**Allocation Mode**: {allocation_mode}

### Environment Configuration

The following environment variables have been pre-configured for your process:
- `CUDA_VISIBLE_DEVICES={cuda_visible_devices}`

### CRITICAL: Memory Management Rules

#### If you have EXCLUSIVE GPU access (1 or more dedicated GPUs):

You have full access to your assigned GPU(s). Use your preferred GPU library (PyTorch, CuPy, JAX, etc.).

#### If you are SHARING a GPU (memory_fraction < 100%):

You MUST set memory limits at the START of your script. Example for PyTorch:

```python
import torch

# CRITICAL: Set this FIRST, before any CUDA operations!
torch.cuda.set_per_process_memory_fraction({memory_fraction}, device=0)

# Verify your allocation
props = torch.cuda.get_device_properties(0)
print(f"GPU: {props.name}")
print(f"Total memory: {props.total_memory / 1e9:.1f} GB")
print(f"Your allocation: {total_memory_gb:.1f} GB ({memory_percent}%)")
```

### Best Practices

1. **Always check GPU availability first**:
```python
import torch
if torch.cuda.is_available():
    print(f"Using GPU: {torch.cuda.get_device_name(0)}")
else:
    print("GPU not available, using CPU")
```

2. **For shared GPU access, keep memory usage conservative**:
- Use smaller batches or chunked evaluation
- Avoid large temporary allocations
- Prefer streaming or incremental computations

3. **Handle OOM errors gracefully**:
```python
try:
    # GPU-heavy operation
    pass
except torch.cuda.OutOfMemoryError:
    torch.cuda.empty_cache()
    print("OOM error - reducing workload and retrying")
```

4. **Clear cache between phases**:
```python
torch.cuda.empty_cache()
import gc
gc.collect()
```

### Multi-GPU Use (if {gpu_count} > 1)

If you can parallelize independent runs, launch them on separate GPUs. For single-run multi-GPU, use your framework's standard multi-GPU patterns.

### No GPU Available (CPU-only mode)

If `CUDA_VISIBLE_DEVICES=""`, use CPU-optimized algorithms:
- Vectorize critical loops (numpy)
- Use `numba` for hot paths
- Parallelize independent runs

---

## Aggressive Resource Utilization (MAXIMIZE YOUR RESOURCES)

Your goal is to keep allocated resources busy. If you are CPU-bound, parallelize runs. If you are GPU-bound, increase workload per batch or reduce Python overhead.

**WARNING**: Exceeding your memory allocation will cause GPU Out-of-Memory errors and may affect other parallel experiments running on the same GPU!
