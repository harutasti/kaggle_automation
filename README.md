# AutoKaggle - Automated Machine Learning Competition System

An intelligent system that simulates autonomous participation in Kaggle competitions using multiple AI agents working in parallel.

## Overview

AutoKaggle orchestrates multiple worker AI agents (WAAs) that execute different experimental strategies in parallel, analyze results, and iteratively improve performance. The system integrates with Kaggle to fetch real competition data and leverages community insights from discussions.

## Features

- **Multi-Agent Architecture**: Parallel execution of ML experiments using isolated Git worktrees
- **Real Competition Data**: Integration with Kaggle crawler for actual competition data
- **Community Insights**: Extracts successful strategies from top-voted discussions
- **Adaptive Strategy Generation**: Learns from previous iterations to improve hypotheses
- **Comprehensive Analysis**: Automated performance analysis and strategy recommendations

## Project Structure

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for detailed directory layout.

```
auto_kaggler/
    components/          # Core system components
    utils/              # Utility functions
    integrations/       # External integrations (kaggle_crawler)
    docs/               # Project documentation
    experiments/        # Generated experiment data
    kaggle_competitions/ # Crawler output data
```

## Quick Start

### Prerequisites

- Python 3.12+
- Git
- uv (Python package manager)

### Installation

```bash
# Clone the repository
git clone <repository_url>
cd auto_kaggler

# Install dependencies
uv sync

# Setup crawler (for Playwright dependencies)
uv run crawl4ai-setup
```

### Configuration

Edit `config.json` to set your target competition:

```json
{
  "kaggle_competition_name": "house-prices-advanced-regression-techniques",
  "max_iterations": 5,
  "wca_per_iteration": 3,
  "simulation_mode": true,
  "use_crawler": true
}
```

### Running

```bash
# Run the main system
uv run python main.py

# Crawl competition data manually
uv run python integrations/kaggle_crawler/crawl_kaggle_competition.py <competition_id>
```

## Documentation

- [Project Overview](docs/PROJECT_OVERVIEW.md) - High-level system description
- [Detailed Flow](docs/DETAILED_FLOW.md) - Comprehensive flow diagrams
- [Integration Guide](docs/INTEGRATION_GUIDE.md) - Kaggle crawler integration
- [SSL Fix Guide](docs/SSL_FIX_GUIDE.md) - Troubleshooting SSL errors

## Key Components

- **MCDU**: Master Controller Decision Unit - Orchestrates the entire workflow
- **KIM**: Kaggle Interface Manager - Handles Kaggle interactions and data
- **KSE**: Knowledge Strategy Engine - Generates ML experiment hypotheses
- **EO**: Experiment Orchestrator - Manages parallel experiment execution
- **RAD**: Result Aggregator Database - Collects and stores results
- **PA**: Performance Analyzer - Analyzes results and provides insights