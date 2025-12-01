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

You have full access to your assigned GPU(s). Use standard PyTorch code:

```python
import torch

# Check available GPUs
print(f"GPUs available: {{torch.cuda.device_count()}}")

# Use your primary GPU
device = torch.device('cuda:0')
model = model.to(device)

# For multi-GPU training
if torch.cuda.device_count() > 1:
    model = torch.nn.DataParallel(model)
```

#### If you are SHARING a GPU (memory_fraction < 100%):

You MUST set memory limits at the START of your script:

```python
import torch

# CRITICAL: Set this FIRST, before any CUDA operations!
torch.cuda.set_per_process_memory_fraction({memory_fraction}, device=0)

# Verify your allocation
props = torch.cuda.get_device_properties(0)
print(f"GPU: {{props.name}}")
print(f"Total memory: {{props.total_memory / 1e9:.1f}} GB")
print(f"Your allocation: {total_memory_gb:.1f} GB ({memory_percent}%)")
```

### Best Practices

1. **Always check GPU availability first**:
```python
import torch
if torch.cuda.is_available():
    device = torch.device('cuda:0')
    print(f"Using GPU: {{torch.cuda.get_device_name(0)}}")
else:
    device = torch.device('cpu')
    print("GPU not available, using CPU")
```

2. **For shared GPU access, use smaller batch sizes**:
```python
# Calculate safe batch size based on your memory allocation
available_gb = {total_memory_gb}
model_memory_estimate_gb = 2.0  # Adjust based on your model
batch_memory_per_sample_gb = 0.001  # Adjust based on data

safe_batch_size = int((available_gb - model_memory_estimate_gb) / batch_memory_per_sample_gb)
batch_size = min(safe_batch_size, 64)  # Cap at reasonable maximum
```

3. **Handle OOM errors gracefully**:
```python
try:
    outputs = model(inputs)
    loss = criterion(outputs, targets)
    loss.backward()
except torch.cuda.OutOfMemoryError:
    torch.cuda.empty_cache()
    print("OOM error - reducing batch size and retrying")
    # Implement batch size reduction logic
```

4. **Clear cache between training phases**:
```python
# After validation or between epochs if memory is tight
torch.cuda.empty_cache()
import gc
gc.collect()
```

5. **Enable gradient checkpointing for large models**:
```python
# Reduces memory at the cost of compute time
model.gradient_checkpointing_enable()
```

### Multi-GPU Training (if {gpu_count} > 1)

```python
import torch
import torch.nn as nn

# Simple DataParallel (easiest)
model = nn.DataParallel(model)
model = model.to('cuda:0')

# Or DistributedDataParallel (better scaling)
# Requires additional setup with torch.distributed
```

### No GPU Available (CPU-only mode)

If `CUDA_VISIBLE_DEVICES=""`, use CPU-optimized algorithms:

```python
# Tree-based models are highly efficient on CPU
from sklearn.ensemble import RandomForestClassifier
import lightgbm as lgb
import xgboost as xgb

# Use all CPU cores
model = RandomForestClassifier(n_jobs=-1)
lgb.train(params={{'num_threads': -1}}, ...)
```

---

## Aggressive GPU Utilization (MAXIMIZE YOUR RESOURCES)

Your goal is to keep GPU utilization **above 80%** during training. Don't let allocated resources sit idle!

### Utilization Targets

**GPU-Bound Operations:**
- Training: Maintain >80% GPU utilization
- Batch size: Use the LARGEST that fits in memory
- Mixed precision: Enable fp16 for faster throughput

**CPU-Bound Operations:**
- GBDT models: Set n_jobs=-1 (use all cores)
- Data preprocessing: Parallelize with multiple workers
- CV folds: Run in parallel when possible

### Maximizing Throughput

**1. Find Optimal Batch Size**
Start large and reduce only if OOM occurs. Larger batches = better GPU utilization.

**2. Enable Mixed Precision**
Use automatic mixed precision (AMP) for neural networks—typically 1.5-2x speedup.

**3. Optimize Data Loading**
- Use multiple data loading workers
- Enable pin_memory for faster GPU transfer
- Prefetch batches to avoid idle GPU time

**4. Monitor and Adjust**
Check GPU utilization periodically. If below 80%, increase batch size or data loading workers.

### When to Use CPU vs GPU

**Use GPU for:**
- Neural network training/inference
- Large matrix operations
- Deep tabular models (TabNet, etc.)

**Use CPU for:**
- GBDT models (LightGBM, XGBoost, CatBoost)—they're CPU-optimized
- Data preprocessing and feature engineering
- Small models where GPU overhead exceeds benefit

---

**WARNING**: Exceeding your memory allocation will cause CUDA Out-of-Memory errors and may affect other parallel experiments running on the same GPU!
