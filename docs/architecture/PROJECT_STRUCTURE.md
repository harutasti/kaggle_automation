# AutoKaggle Project Structure

## Optimized Directory Layout

```
auto_kaggler/
├── README.md                    # Project overview and setup instructions
├── main.py                      # Entry point for the application
├── config.json                  # System configuration
├── data_models.py               # Data structure definitions
├── pyproject.toml               # Python project configuration
├── uv.lock                      # Dependency lock file
│
├── components/                  # Core system components
│   ├── base_component.py        # Base class for all components
│   ├── mcdu.py                  # Master Controller Decision Unit
│   ├── kim.py                   # Kaggle Interface Manager
│   ├── kse.py                   # Knowledge Strategy Engine
│   ├── eo.py                    # Experiment Orchestrator
│   ├── rad.py                   # Result Aggregator Database
│   ├── pa.py                    # Performance Analyzer
│   └── wca_simulator.py         # Worker AI Agent Simulator
│
├── utils/                       # Utility modules
│   ├── file_utils.py            # File system operations
│   ├── logger.py                # Logging configuration
│   └── crawler_parser.py        # Parser for crawler output
│
├── kaggle_crawler/              # Kaggle web scraper
│   ├── crawl_kaggle_competition.py
│   ├── crawl_discussions.py
│   ├── pyproject.toml
│   └── README.md
│
│
├── docs/                        # Project documentation
│   ├── README.md                # Documentation index
│   ├── PROJECT_OVERVIEW.md      # High-level system overview
│   ├── DETAILED_FLOW.md         # Detailed flow diagrams
│   ├── INTEGRATION_GUIDE.md     # Crawler integration guide
│   ├── INTEGRATION_SUMMARY.md   # Integration changes summary
│   ├── SSL_FIX_GUIDE.md         # SSL troubleshooting
│   └── file_descriptions.md     # Component descriptions
│
├── experiments/                 # Generated experiment data (git-ignored)
│   ├── hypotheses/              # Generated task instructions
│   ├── worktrees/               # Git worktrees for experiments
│   ├── results/                 # Experiment outputs
│   ├── analysis/                # Performance analysis reports
│   └── kaggle_data/             # Downloaded competition data
│
├── logs/                        # Application logs (git-ignored)
│   └── auto_kaggle.log
│
└── kaggle_competitions/         # Crawler output data (git-ignored)
    └── {competition_id}/
        ├── data/                # Competition datasets
        ├── pages/               # Competition pages
        └── discussions/         # Discussion threads
```

## Key Directories

### `/components`
Core system components implementing the multi-agent architecture. Each component has a specific responsibility in the ML experiment pipeline.

### `/utils`
Shared utility functions for file operations, logging, and data parsing.

### `/kaggle_crawler`
Kaggle web scraping and data collection module, now fully integrated as part of the core system.

### `/docs`
All project documentation.

### `/experiments`
Runtime-generated data from ML experiments. This directory is created automatically and contains:
- Experiment hypotheses and task instructions
- Git worktrees for isolated experiment execution
- Model outputs and predictions
- Performance analysis reports

### `/kaggle_competitions`
Output from the kaggle_crawler containing:
- Downloaded competition data
- Scraped competition pages
- Community discussions and insights

## Benefits of This Structure

1. **Clear Separation of Concerns**
   - Core logic in `/components`
   - Web scraping in `/kaggle_crawler`
   - Documentation in `/docs`
   - Generated data in designated directories

2. **Clean Root Directory**
   - Only essential files remain in root
   - Easy to find main entry points and configuration

3. **Scalability**
   - All source code organized under `/src`
   - Documentation organized for growth
   - Clear patterns for new components

4. **Git-Friendly**
   - Generated data properly isolated
   - Clean separation of source and output
   - Minimal root directory clutter
