# AutoKaggler System Flow Diagram

## Overview
This document provides a visual representation of the AutoKaggler system flow using Mermaid diagrams.

## Main System Flow

```mermaid
flowchart TB
    Start([Start: main.py]) --> Init[Initialize Components]
    
    Init --> MCDU[MasterControllerDecisionUnit]
    
    MCDU --> CheckIter{Iteration < max_iterations?}
    CheckIter -->|No| End([End])
    CheckIter -->|Yes| KIM[KaggleInterfaceManager]
    
    %% Competition Data Flow
    KIM --> CrawlerCheck{Use Crawler?}
    CrawlerCheck -->|Yes| Crawler[kaggle_crawler]
    CrawlerCheck -->|No| KaggleAPI[Kaggle API]
    
    Crawler --> CompData[Competition Data]
    KaggleAPI --> CompData
    
    CompData --> ClaudeCheck{Claude Enabled?}
    ClaudeCheck -->|Yes| ClaudeAnalysis[Claude Code Analysis]
    ClaudeCheck -->|No| ParseData[Parse Competition Info]
    
    ClaudeAnalysis --> EnhancedInfo[Enhanced Competition Info]
    ParseData --> BasicInfo[Basic Competition Info]
    EnhancedInfo --> KSE[KnowledgeStrategyEngine]
    BasicInfo --> KSE
    
    %% Strategy Generation
    KSE --> GenStrat[Generate Strategies]
    GenStrat --> Strategies[List of Experiment Hypotheses]
    
    %% Experiment Execution
    Strategies --> EO[ExperimentOrchestrator]
    EO --> CreateWorktree[Create Git Worktree]
    CreateWorktree --> ExpLoop{For each experiment}
    
    ExpLoop --> WCACheck{Use Claude Code?}
    WCACheck -->|Yes| ClaudeExp[Claude Code Executor]
    WCACheck -->|No| WCA[WCASimulator]
    
    ClaudeExp --> ExpResult[Experiment Result]
    WCA --> ExpResult
    
    ExpResult --> RAD[ResultAggregatorDatabase]
    RAD --> MoreExp{More experiments?}
    MoreExp -->|Yes| ExpLoop
    MoreExp -->|No| PA[PerformanceAnalyzer]
    
    %% Analysis and Feedback
    PA --> Analysis[Generate Analysis Report]
    Analysis --> UpdateKSE[Update Strategy Knowledge]
    UpdateKSE --> CheckStop{Stop Conditions Met?}
    
    CheckStop -->|No| MCDU
    CheckStop -->|Yes| End
    
    %% Styling
    classDef component fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef external fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef decision fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef data fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    
    class MCDU,KIM,KSE,EO,RAD,PA component
    class Crawler,KaggleAPI,ClaudeAnalysis,ClaudeExp,WCA external
    class CheckIter,CrawlerCheck,ClaudeCheck,WCACheck,ExpLoop,MoreExp,CheckStop decision
    class CompData,EnhancedInfo,BasicInfo,Strategies,ExpResult,Analysis data
```

## Component Interactions

```mermaid
graph LR
    subgraph Core Components
        MCDU[MCDU<br/>Master Controller]
        KIM[KIM<br/>Kaggle Interface]
        KSE[KSE<br/>Strategy Engine]
        EO[EO<br/>Experiment Orchestrator]
        RAD[RAD<br/>Result Database]
        PA[PA<br/>Performance Analyzer]
    end
    
    subgraph External Services
        Kaggle[Kaggle API]
        Claude[Claude Code]
        Git[Git Worktrees]
    end
    
    subgraph Data Flow
        CompInfo[Competition Info]
        ExpHyp[Experiment Hypotheses]
        Results[Experiment Results]
        Reports[Analysis Reports]
    end
    
    MCDU -->|requests| KIM
    KIM -->|fetches from| Kaggle
    KIM -->|analyzes with| Claude
    KIM -->|produces| CompInfo
    
    CompInfo -->|feeds| KSE
    KSE -->|generates| ExpHyp
    
    ExpHyp -->|executed by| EO
    EO -->|uses| Git
    EO -->|may use| Claude
    EO -->|produces| Results
    
    Results -->|stored in| RAD
    RAD -->|analyzed by| PA
    PA -->|generates| Reports
    Reports -->|feedback to| KSE
    
    PA -->|control signals| MCDU
```

## Detailed Component Flows

### 1. Competition Data Acquisition Flow

```mermaid
flowchart LR
    Start([KIM.get_competition_info]) --> Check{Crawler enabled?}
    
    Check -->|Yes| CrawlerPath
    Check -->|No| APIPath
    
    subgraph CrawlerPath [Crawler Path]
        RunCrawler[Run kaggle_crawler]
        RunCrawler --> CrawlPages[Crawl Competition Pages]
        CrawlPages --> CrawlDiscussions[Crawl Discussions]
        CrawlDiscussions --> DownloadData[Download Datasets]
    end
    
    subgraph APIPath [API Path]
        AuthAPI[Authenticate Kaggle API]
        AuthAPI --> FetchMeta[Fetch Competition Metadata]
        FetchMeta --> DownloadFiles[Download Data Files]
    end
    
    CrawlerPath --> ParseInfo[Parse Competition Info]
    APIPath --> ParseInfo
    
    ParseInfo --> ClaudeAnalysis{Claude enabled?}
    ClaudeAnalysis -->|Yes| RunClaude[Run Claude Analysis]
    ClaudeAnalysis -->|No| ReturnBasic[Return Basic Info]
    
    RunClaude --> EnhanceInfo[Enhance Competition Info]
    EnhanceInfo --> Return([Return Enhanced Info])
    ReturnBasic --> Return
```

### 2. Experiment Execution Flow

```mermaid
flowchart TB
    Start([EO.run_experiments]) --> PrepareExp[Prepare Experiments]
    
    PrepareExp --> Loop{For each experiment}
    Loop -->|Next| CreateBranch[Create Git Worktree]
    
    CreateBranch --> PrepareTask[Prepare Task Markdown]
    PrepareTask --> ExecutorChoice{Claude Code enabled?}
    
    ExecutorChoice -->|Yes| ClaudePath
    ExecutorChoice -->|No| WCAPath
    
    subgraph ClaudePath [Claude Code Path]
        PreparePrompt[Prepare Detailed Prompt]
        PreparePrompt --> CallClaude[Execute via ClaudeCodeWrapper]
        CallClaude --> ParseResponse[Parse Claude Response]
    end
    
    subgraph WCAPath [WCA Simulator Path]
        SimulateWork[Simulate ML Work]
        SimulateWork --> GenerateResults[Generate Mock Results]
    end
    
    ClaudePath --> CollectResults[Collect Results]
    WCAPath --> CollectResults
    
    CollectResults --> StoreRAD[Store in RAD]
    StoreRAD --> CleanupWorktree[Cleanup Worktree]
    
    CleanupWorktree --> MoreExp{More experiments?}
    MoreExp -->|Yes| Loop
    MoreExp -->|No| End([Return all results])
```

### 3. Strategy Generation Flow

```mermaid
flowchart LR
    Start([KSE.generate_strategies]) --> LoadHistory[Load Historical Results]
    
    LoadHistory --> AnalyzeComp[Analyze Competition Type]
    AnalyzeComp --> CheckType{Competition Type?}
    
    CheckType -->|Regression| RegStrategies[Regression Strategies]
    CheckType -->|Classification| ClassStrategies[Classification Strategies]
    CheckType -->|Unknown| DefaultStrategies[Default Strategies]
    
    RegStrategies --> Combine[Combine & Prioritize]
    ClassStrategies --> Combine
    DefaultStrategies --> Combine
    
    Combine --> ApplyInsights{Claude Insights?}
    ApplyInsights -->|Yes| EnhanceWithClaude[Enhance with Claude Suggestions]
    ApplyInsights -->|No| BasicStrategies[Use Basic Strategies]
    
    EnhanceWithClaude --> FilterDuplicates[Filter Duplicates]
    BasicStrategies --> FilterDuplicates
    
    FilterDuplicates --> Return([Return Strategy List])
```

## Data Model Relationships

```mermaid
erDiagram
    CompetitionInfo ||--o{ ExperimentHypothesis : generates
    ExperimentHypothesis ||--|| ExperimentResult : produces
    ExperimentResult }|--|| ResultAggregatorDatabase : stored-in
    ResultAggregatorDatabase ||--|| AnalysisResult : analyzed-by
    
    CompetitionInfo {
        string name
        string evaluation_metric
        datetime deadline
        string description_markdown
        list data_files
        string competition_type
        string competition_subtype
        list initial_insights
        list data_warnings
    }
    
    ExperimentHypothesis {
        string experiment_id
        int iteration
        string strategy_name
        dict parameters
        string task_markdown_path
    }
    
    ExperimentResult {
        string experiment_id
        int iteration
        string strategy_name
        dict parameters
        datetime start_time
        datetime end_time
        float execution_time_seconds
        float score
        list result_files
        string log_path
        string status
        string error_message
    }
    
    AnalysisResult {
        int iteration
        string summary_markdown
        float best_score
        string best_experiment_id
        string improvement_trend
        list recommended_strategies
    }
```

## Error Handling Flow

```mermaid
flowchart TB
    Operation[Any Operation] --> TryCatch{Try-Catch Block}
    
    TryCatch -->|Success| Continue[Continue Flow]
    TryCatch -->|Error| LogError[Log Error]
    
    LogError --> ErrorType{Error Type?}
    
    ErrorType -->|Network| Retry{Retry?}
    ErrorType -->|Permission| RequestPerm[Request Permission]
    ErrorType -->|Timeout| Fallback[Use Fallback]
    ErrorType -->|Critical| StopExecution[Stop Execution]
    
    Retry -->|Yes| Operation
    Retry -->|No| Fallback
    
    RequestPerm -->|Granted| Operation
    RequestPerm -->|Denied| Fallback
    
    Fallback --> SimulationMode[Enable Simulation Mode]
    SimulationMode --> Continue
    
    StopExecution --> CleanupResources[Cleanup Resources]
    CleanupResources --> Exit([Exit with Error])
```

## Configuration Flow

```mermaid
flowchart LR
    Start([Load Config]) --> ReadFile[Read config.json]
    
    ReadFile --> ValidateConfig{Valid JSON?}
    ValidateConfig -->|No| UseDefaults[Use Default Config]
    ValidateConfig -->|Yes| MergeDefaults[Merge with Defaults]
    
    UseDefaults --> CheckEnv[Check Environment Variables]
    MergeDefaults --> CheckEnv
    
    CheckEnv --> OverrideConfig[Override with Env Vars]
    OverrideConfig --> InitComponents[Initialize Components]
    
    InitComponents --> ConfigureLogging[Configure Logging]
    ConfigureLogging --> ConfigureAPIs[Configure External APIs]
    ConfigureAPIs --> Ready([System Ready])
```

## Key Features

1. **Modular Architecture**: Each component has a single responsibility
2. **External Service Integration**: Kaggle API, Claude Code, Git
3. **Fallback Mechanisms**: Simulation mode when APIs fail
4. **Iterative Improvement**: Feedback loop from analysis to strategy generation
5. **Experiment Isolation**: Git worktrees for clean experiment environments
6. **Flexible Execution**: Support for both Claude Code and simulation

## Usage

To visualize these diagrams:
1. Copy the Mermaid code blocks
2. Use [Mermaid Live Editor](https://mermaid.live/)
3. Or use any Markdown viewer that supports Mermaid (GitHub, VSCode, etc.)