# AutoKaggle Simulator

An automated machine learning system that simulates autonomous participation in Kaggle competitions using multiple AI agents working in parallel.

## Overview

AutoKaggle is a sophisticated simulation framework designed to model how AI agents could autonomously compete in machine learning competitions. The system orchestrates multiple "Worker Claude Agents" (WCAs) that execute different experimental strategies in parallel, analyze results, and iteratively improve performance.

## Architecture

The system follows a modular component-based architecture with the following key components:

### Visual Documentation

For a comprehensive understanding of the system flow:
- **[Quick Flow Overview](QUICK_FLOW_OVERVIEW.md)** - High-level system flow and simplified diagrams
- **[System Flow Diagram](SYSTEM_FLOW_DIAGRAM.md)** - Detailed technical flows and component interactions

### Core Components

- **MCDU (Master Controller Decision Unit)** - Central orchestrator that manages the overall workflow
- **KIM (Kaggle Interface Manager)** - Handles interaction with Kaggle platform (simulated)
- **KSE (Knowledge Strategy Engine)** - Generates experimental hypotheses and strategies
- **EO (Experiment Orchestrator)** - Manages parallel experiment execution using Git worktrees
- **RAD (Result Aggregator Database)** - Collects and stores experiment results
- **PA (Performance Analyzer)** - Analyzes results and provides insights for next iterations

### Data Models

The system uses structured dataclasses for consistent data flow:
- `CompetitionInfo` - Competition metadata and requirements
- `ExperimentHypothesis` - Proposed experimental strategies
- `ExperimentResult` - Outcomes from executed experiments
- `AnalysisResult` - Performance analysis and recommendations

## Key Features

### Parallel Experiment Execution
- Creates isolated Git worktrees for each experiment
- Runs multiple Worker Claude Agents simultaneously
- Each WCA operates independently with its own workspace and logging

### Intelligent Strategy Generation
- Analyzes competition requirements and generates appropriate ML strategies
- Learns from previous iteration results to improve hypothesis generation
- Supports various ML approaches (LightGBM, Neural Networks, Feature Engineering, etc.)

### Automated Result Analysis
- Aggregates results from all parallel experiments
- Identifies best-performing strategies and parameters
- Generates insights and recommendations for subsequent iterations

### Adaptive Stopping Conditions
- Configurable score thresholds
- Early stopping when no improvement is detected
- Maximum iteration limits to prevent infinite execution

## Configuration

The system is configured via `config.json`:

```json
{
  "kaggle_competition_name": "titanic",
  "max_iterations": 5,
  "wca_per_iteration": 3,
  "stop_condition": {
    "score_threshold": 0.95,
    "no_improvement_iterations": 2
  },
  "experiments_base_dir": "./experiments",
  "log_file": "./logs/auto_kaggle.log",
  "log_level": "INFO",
  "simulation_mode": false
}
```

## Directory Structure

```
auto_kaggler/
├── components/           # Core system components
│   ├── mcdu.py          # Master Controller
│   ├── kim.py           # Kaggle Interface Manager
│   ├── kse.py           # Knowledge Strategy Engine
│   ├── eo.py            # Experiment Orchestrator
│   ├── rad.py           # Result Aggregator
│   ├── pa.py            # Performance Analyzer
│   └── wca_simulator.py # Worker Agent Simulator
├── experiments/         # Generated during execution
│   ├── worktrees/       # Isolated experiment workspaces
│   ├── results/         # Collected experiment outputs
│   ├── hypotheses/      # Generated strategy descriptions
│   ├── analysis/        # Performance analysis reports
│   └── kaggle_data/     # Competition data
├── utils/               # Utility functions
├── data_models.py       # Data structure definitions
├── config.json          # System configuration
└── main.py              # Application entry point
```

## Workflow

1. **Initialization**: MCDU loads configuration and initializes all components
2. **Competition Setup**: KIM retrieves competition information and data
3. **Strategy Generation**: KSE analyzes competition and generates experimental hypotheses
4. **Parallel Execution**: EO creates isolated workspaces and launches multiple WCAs
5. **Result Collection**: RAD aggregates results from completed experiments
6. **Analysis**: PA analyzes iteration results and provides recommendations
7. **Decision**: MCDU decides whether to continue or stop based on performance
8. **Iteration**: Process repeats with improved strategies until stopping conditions are met

## Current Status

The system is currently in simulation mode, generating realistic but dummy data to demonstrate the architecture and workflow. Key simulation features include:

- Dummy competition data generation
- Randomized experiment scores with realistic distributions
- Simulated processing times and occasional failures
- Mock file operations and API interactions

## Future Enhancements

When connected to real Kaggle APIs and Claude Code agents, the system could:

- Download actual competition data and requirements
- Execute real ML experiments with proper model training
- Submit predictions to Kaggle competitions
- Implement sophisticated strategy optimization
- Provide detailed performance analytics and insights

## Usage

```bash
# Run the simulator
uv run main.py

# Monitor logs
tail -f logs/auto_kaggle.log
```

The system requires a Git repository and will create necessary directories automatically during execution.