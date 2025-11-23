# AutoKaggle Simulator - Detailed Flow

This document provides a comprehensive flow diagram and step-by-step breakdown of how the AutoKaggle Simulator operates, including the new kaggle_crawler integration.

## High-Level Flow Diagram

```mermaid
graph TD
    A[Start: main.py] --> B[Load Configuration]
    B --> C[Initialize MCDU]
    C --> D[Initialize All Components]
    D --> E{use_crawler?}
    E -->|Yes| F[Fetch/Parse Crawler Data]
    E -->|No| G[Setup Competition Data via API]
    F --> H[Extract Discussion Strategies]
    G --> I[Main Iteration Loop]
    H --> I
    
    I --> J[Generate Hypotheses with Insights]
    J --> K[Launch Parallel Experiments]
    K --> L[Monitor WAA Processes]
    L --> M{All Experiments Complete?}
    M -->|No| L
    M -->|Yes| N[Collect Results]
    N --> O[Analyze Performance]
    O --> P{Stop Conditions Met?}
    P -->|No| Q[Update State & Continue]
    Q --> J
    P -->|Yes| R{simulation_mode?}
    R -->|No| S[Final Submission]
    R -->|Yes| T[Skip Submission]
    S --> U[Cleanup & Exit]
    T --> U
```

## Detailed Component Flow

### Phase 1: System Initialization

```mermaid
sequenceDiagram
    participant Main as main.py
    participant MCDU as Master Controller
    participant KIM as Kaggle Interface Manager
    participant KSE as Knowledge Strategy Engine
    participant EO as Experiment Orchestrator
    participant RAD as Result Aggregator
    participant PA as Performance Analyzer
    
    Main->>Main: Load config.json
    Main->>Main: Setup logger & directories
    Main->>Main: Verify Git repository
    Main->>MCDU: Initialize with config
    MCDU->>KIM: Initialize component
    MCDU->>KSE: Initialize component
    MCDU->>EO: Initialize component
    MCDU->>RAD: Initialize component
    MCDU->>PA: Initialize component
    Main->>MCDU: Call run_main_loop()
```

### Phase 2: Competition Setup with Crawler Integration

```mermaid
sequenceDiagram
    participant MCDU as Master Controller
    participant KIM as Kaggle Interface Manager
    participant Crawler as kaggle_crawler
    participant Parser as crawler_parser
    
    MCDU->>KIM: get_competition_info(competition_name)
    
    alt use_crawler is true
        KIM->>KIM: Check if crawler data exists
        alt Data doesn't exist
            KIM->>Crawler: Run crawler for competition
            Crawler->>Crawler: Fetch pages & discussions
            Crawler->>Crawler: Download data files
            Crawler-->>KIM: Crawler complete
        end
        KIM->>Parser: parse_competition_info()
        Parser->>Parser: Extract name, metric, description
        Parser-->>KIM: Return CompetitionInfo
    else use_crawler is false
        KIM->>KIM: Use Kaggle API or simulation
        KIM->>KIM: Create CompetitionInfo object
    end
    
    KIM-->>MCDU: Return CompetitionInfo
    
    MCDU->>KIM: download_competition_data()
    alt Crawler data exists
        KIM->>KIM: Copy from crawler data dir
    else
        KIM->>KIM: Download via API/Simulate
    end
    KIM-->>MCDU: Return data file paths
```

### Phase 3: Iterative Experiment Loop

```mermaid
graph TD
    A[Start Iteration N] --> B[Strategy Generation Phase]
    B --> C[Experiment Execution Phase]
    C --> D[Result Collection Phase]
    D --> E[Analysis Phase]
    E --> F[Decision Phase]
    F --> G{Continue?}
    G -->|Yes| H[Increment Iteration]
    H --> A
    G -->|No| I[Final Phase]
```

#### Strategy Generation Phase with Discussion Insights

```mermaid
sequenceDiagram
    participant MCDU as Master Controller
    participant KSE as Knowledge Strategy Engine
    participant Parser as crawler_parser
    
    MCDU->>KSE: generate_hypotheses(competition_info, previous_results, analysis)
    
    alt First iteration and use_crawler
        KSE->>Parser: parse_discussion_strategies()
        Parser->>Parser: Extract ML algorithms from discussions
        Parser->>Parser: Find community insights
        Parser-->>KSE: Return strategy suggestions
        KSE->>KSE: Add discovered strategies (XGBoost_FromDiscussion, etc.)
    end
    
    KSE->>KSE: Analyze competition requirements
    KSE->>KSE: Review previous iteration results
    KSE->>KSE: Apply strategy selection logic
    
    loop For each hypothesis (wca_per_iteration times)
        KSE->>KSE: Select strategy (including community strategies)
        KSE->>KSE: Generate parameters
        KSE->>KSE: Find relevant discussion insights
        KSE->>KSE: Create task markdown with insights
        KSE->>KSE: Store in experiments/hypotheses/
        KSE->>KSE: Create ExperimentHypothesis object
    end
    
    KSE-->>MCDU: Return List[ExperimentHypothesis]
```

#### Experiment Execution Phase

```mermaid
sequenceDiagram
    participant MCDU as Master Controller
    participant EO as Experiment Orchestrator
    participant Git as Git Worktrees
    participant WAA as Worker Agent Processes
    
    MCDU->>EO: execute_experiments(hypotheses_list)
    
    loop For each hypothesis
        EO->>Git: Create isolated worktree
        Git-->>EO: Return worktree path
        EO->>WAA: Launch wca_simulator.py process
        Note over WAA: Process runs independently
    end
    
    EO->>EO: Track active processes
    EO-->>MCDU: Return process tracking info
    
    MCDU->>EO: wait_for_completion()
    
    loop Monitor processes
        EO->>EO: Check for DONE_* files
        EO->>EO: Update process status
        EO->>Git: Cleanup completed worktrees
    end
    
    EO-->>MCDU: All experiments complete
```

#### Worker Agent Simulation Detail

```mermaid
graph TD
    A[WAA Process Starts] --> B[Setup Local Logger]
    B --> C[Read Task Markdown]
    C --> D[Parse Instructions]
    D --> E[Simulate ML Work]
    E --> F[Generate Random Score]
    F --> G{Simulate Failure?}
    G -->|Yes| H[Write ERROR file]
    G -->|No| I[Create Result Files]
    I --> J[Write DONE file]
    H --> K[Exit with Error]
    J --> L[Exit Successfully]
```

#### Result Collection Phase

```mermaid
sequenceDiagram
    participant MCDU as Master Controller
    participant RAD as Result Aggregator
    participant FS as File System
    
    loop For each completed experiment
        MCDU->>RAD: collect_result(experiment_id, worktree_path)
        RAD->>FS: Read DONE file status
        RAD->>FS: Read result.json score
        RAD->>FS: Copy output files to results/
        RAD->>RAD: Create ExperimentResult object
        RAD->>FS: Update results_manifest.json
        RAD-->>MCDU: Return ExperimentResult
    end
    
    MCDU->>RAD: get_results_for_iteration(iteration_num)
    RAD-->>MCDU: Return List[ExperimentResult]
```

#### Analysis Phase

```mermaid
sequenceDiagram
    participant MCDU as Master Controller
    participant PA as Performance Analyzer
    
    MCDU->>PA: analyze_iteration(results_list, previous_best_score)
    PA->>PA: Calculate success/failure rates
    PA->>PA: Find best score in iteration
    PA->>PA: Determine improvement trend
    PA->>PA: Generate strategy recommendations
    PA->>PA: Create markdown analysis report
    PA->>PA: Save to experiments/analysis/
    PA->>PA: Create AnalysisResult object
    PA-->>MCDU: Return AnalysisResult
```

#### Decision Phase

```mermaid
graph TD
    A[Receive Analysis Results] --> B{Check Score Threshold}
    B -->|Exceeded| C[Stop: Target Achieved]
    B -->|Not Exceeded| D{Check Max Iterations}
    D -->|Reached| E[Stop: Max Iterations]
    D -->|Not Reached| F{Check Improvement}
    F -->|No Improvement| G[Increment No-Improvement Counter]
    G --> H{Counter >= Threshold?}
    H -->|Yes| I[Stop: No Improvement]
    H -->|No| J[Continue: Next Iteration]
    F -->|Improvement Found| K[Reset No-Improvement Counter]
    K --> J
```

## Crawler Integration Flow

### Crawler Execution Detail

```mermaid
graph TD
    A[KIM needs competition data] --> B{Crawler data exists?}
    B -->|No| C[Execute kaggle_crawler]
    B -->|Yes| D[Use existing data]
    
    C --> E[Crawl competition pages]
    E --> F[Crawl top N discussions]
    F --> G[Download data files]
    G --> H[Clean discussion content]
    H --> I[Aggregate upvoted content]
    
    D --> J[Parse competition info]
    I --> J
    J --> K[Extract strategies]
    K --> L[Return to KIM/KSE]
```

### Crawler Output Structure
```
kaggle_competitions/{competition_id}/
├── data/                    # Downloaded competition data
│   ├── train.csv
│   ├── test.csv
│   └── sample_submission.csv
├── pages/                   # Competition page content
│   ├── {competition_id}_overview.md
│   ├── {competition_id}_rules.md
│   └── {competition_id}_leaderboard.md
└── discussions/             # Discussion threads
    └── top_N_most_voted/
        ├── discussion_*.md  # Individual cleaned discussions
        └── upvoted_discussions.md  # Aggregated insights
```

## File System Flow

### Directory Creation Timeline

```
Startup:
├── logs/ (created)
├── experiments/ (created)
    ├── worktrees/ (created)
    ├── results/ (created)
    ├── hypotheses/ (created)
    ├── analysis/ (created)
    └── kaggle_data/ (created)

During Execution:
experiments/
├── worktrees/
│   ├── exp_001/ (created per experiment)
│   ├── exp_002/ (created per experiment)
│   └── exp_003/ (created per experiment)
├── results/
│   ├── results_manifest.json (updated continuously)
│   ├── exp_001/ (created after completion)
│   ├── exp_002/ (created after completion)
│   └── exp_003/ (created after completion)
├── hypotheses/
│   ├── task_001.md (created per hypothesis)
│   ├── task_002.md (created per hypothesis)
│   └── task_003.md (created per hypothesis)
├── analysis/
│   ├── analysis_iter_1.md (created per iteration)
│   ├── analysis_iter_2.md (created per iteration)
│   └── analysis_iter_3.md (created per iteration)
└── kaggle_data/
    ├── train.csv (simulated download)
    ├── test.csv (simulated download)
    └── sample_submission.csv (simulated download)
```

## Error Handling Flow

```mermaid
graph TD
    A[Error Occurs] --> B{Error Level}
    B -->|WAA Process Error| C[Write ERROR file]
    C --> D[Mark experiment as FAILED]
    D --> E[Continue with other experiments]
    
    B -->|Component Error| F[Log error with exc_info]
    F --> G[Attempt graceful degradation]
    G --> H{Can Continue?}
    H -->|Yes| I[Continue execution]
    H -->|No| J[Escalate to MCDU]
    
    B -->|Critical System Error| K[Log critical error]
    K --> L[Cleanup resources]
    L --> M[Exit with error code]
```

## Configuration Impact Flow

```mermaid
graph LR
    A[config.json] --> B[max_iterations]
    A --> C[wca_per_iteration]
    A --> D[stop_condition]
    A --> E[simulation_mode]
    A --> F[use_crawler]
    A --> G[max_discussions]
    
    B --> H[MCDU Loop Control]
    C --> I[KSE Hypothesis Generation]
    C --> J[EO Process Management]
    D --> K[MCDU Decision Logic]
    E --> L[KIM Submission Behavior]
    E --> M[WAA Simulation Level]
    F --> N[KIM Data Source Selection]
    F --> O[KSE Strategy Discovery]
    G --> P[Crawler Discussion Limit]
```

### New Configuration Options

- **use_crawler** (boolean, default: true)
  - When true: KIM uses kaggle_crawler for competition data
  - When false: KIM uses Kaggle API or simulation mode
  
- **max_discussions** (integer, default: 20)
  - Controls how many top-voted discussions to crawl
  - More discussions = more community insights but longer crawl time

- **simulation_mode** behavior with crawler:
  - true: Uses real crawler data but skips final submission (avoids SSL errors)
  - false: Full operation including Kaggle API submission

## Performance Monitoring Flow

```mermaid
sequenceDiagram
    participant Logger as Logging System
    participant MCDU as Master Controller
    participant Components as All Components
    
    Components->>Logger: Log operation start/end
    Components->>Logger: Log errors with stack traces
    Components->>Logger: Log performance metrics
    
    MCDU->>Logger: Log iteration summaries
    MCDU->>Logger: Log best scores and improvements
    MCDU->>Logger: Log stopping decisions
    
    Logger->>Logger: Write to auto_kaggle.log
    Logger->>Logger: Console output (if configured)
```

## New Components and Modules

### utils/crawler_parser.py
- **parse_competition_info()**: Extracts competition details from crawler markdown files
  - Parses competition name, evaluation metric, deadline
  - Identifies regression competitions and their metrics (RMSE, MAE)
  - Lists available data files

- **parse_discussion_strategies()**: Extracts ML strategies from community discussions
  - Finds mentioned algorithms (XGBoost, LightGBM, Neural Networks, etc.)
  - Extracts feature engineering insights
  - Returns strategies with context and upvote counts

### Enhanced KIM Features
- Automatic crawler execution if data doesn't exist
- Fallback chain: Crawler → Kaggle API → Simulation
- Reuses downloaded data from crawler to avoid redundant downloads
- Configurable through use_crawler flag

### Enhanced KSE Features
- Dynamic strategy discovery from discussions
- Adds community-validated strategies (e.g., XGBoost_FromDiscussion)
- Includes relevant discussion insights in task instructions
- Prioritizes successful community approaches

This detailed flow shows how the AutoKaggle Simulator orchestrates complex parallel ML experimentation through a sophisticated multi-agent architecture, with robust error handling, performance monitoring, adaptive decision-making capabilities, and now with real Kaggle competition data and community insights integration.
