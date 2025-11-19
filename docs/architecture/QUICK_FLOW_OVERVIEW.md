# AutoKaggler Quick Flow Overview

## High-Level System Flow

```mermaid
flowchart TD
    Start([Start AutoKaggler]) --> Init[Load Configuration]
    
    Init --> MainLoop{Main Loop<br/>Iteration < Max?}
    MainLoop -->|No| End([End: Best Model Found])
    
    MainLoop -->|Yes| Step1[1. Get Competition Data]
    Step1 --> Step2[2. Analyze with Claude]
    Step2 --> Step3[3. Generate ML Strategies] 
    Step3 --> Step4[4. Execute Experiments]
    Step4 --> Step5[5. Collect Results]
    Step5 --> Step6[6. Analyze Performance]
    Step6 --> Decision{Good Enough?}
    
    Decision -->|No| Feedback[Update Strategies]
    Feedback --> MainLoop
    Decision -->|Yes| End
    
    style Start fill:#4CAF50,color:#fff
    style End fill:#FF5252,color:#fff
    style Step2 fill:#2196F3,color:#fff
    style Step4 fill:#FF9800,color:#fff
```

## Core Component Responsibilities

```mermaid
graph TB
    subgraph "🎯 Master Controller (MCDU)"
        MCDU[Orchestrates the entire pipeline<br/>Manages iterations<br/>Checks stop conditions]
    end
    
    subgraph "📊 Kaggle Interface (KIM)"
        KIM[Downloads competition data<br/>Runs kaggle_crawler<br/>Integrates Claude analysis]
    end
    
    subgraph "🧠 Strategy Engine (KSE)"
        KSE[Generates ML experiments<br/>Learns from past results<br/>Prioritizes strategies]
    end
    
    subgraph "🔬 Experiment Orchestrator (EO)"
        EO[Creates isolated environments<br/>Runs experiments<br/>Manages Git worktrees]
    end
    
    subgraph "💾 Result Database (RAD)"
        RAD[Stores all results<br/>Tracks experiment history<br/>Provides data for analysis]
    end
    
    subgraph "📈 Performance Analyzer (PA)"
        PA[Analyzes results<br/>Identifies best models<br/>Suggests improvements]
    end
```

## Simplified Execution Flow

```mermaid
sequenceDiagram
    participant User
    participant AutoKaggler
    participant Kaggle
    participant Claude
    participant Git
    
    User->>AutoKaggler: Start with competition name
    
    loop Each Iteration
        AutoKaggler->>Kaggle: Fetch competition data
        Kaggle-->>AutoKaggler: Data & metadata
        
        AutoKaggler->>Claude: Analyze competition
        Claude-->>AutoKaggler: Insights & suggestions
        
        AutoKaggler->>AutoKaggler: Generate experiments
        
        loop Each Experiment
            AutoKaggler->>Git: Create worktree
            AutoKaggler->>Claude: Execute ML code
            Claude-->>AutoKaggler: Results
            AutoKaggler->>Git: Cleanup worktree
        end
        
        AutoKaggler->>AutoKaggler: Analyze all results
        AutoKaggler->>User: Progress report
    end
    
    AutoKaggler->>User: Final best model
```

## Key Integration Points

```mermaid
mindmap
  root((AutoKaggler))
    External APIs
      Kaggle API
        Competition data
        Leaderboard
        Submissions
      Claude Code
        Competition analysis
        Code generation
        Experiment execution
    Internal Systems
      Git Integration
        Worktree isolation
        Version control
        Experiment tracking
      File System
        Data storage
        Model artifacts
        Logs & reports
    Configuration
      config.json
        Competition settings
        API credentials
        Execution parameters
      CLAUDE.md
        Project instructions
        Code style guide
        Tool preferences
```

## Data Flow Summary

```mermaid
flowchart LR
    Competition[Kaggle Competition] --> Crawler[kaggle_crawler]
    Crawler --> RawData[Raw Data<br/>Pages, Discussions]
    
    RawData --> Claude[Claude Analysis]
    Claude --> EnrichedData[Enriched Data<br/>+ Insights]
    
    EnrichedData --> Strategies[ML Strategies]
    Strategies --> Experiments[Experiments]
    
    Experiments --> Results[Results<br/>Models, Scores]
    Results --> Analysis[Performance<br/>Analysis]
    
    Analysis --> Learning[Learning<br/>Feedback]
    Learning --> Strategies
    
    style Claude fill:#2196F3,color:#fff
    style Analysis fill:#4CAF50,color:#fff
```

## Quick Start Understanding

1. **Input**: Kaggle competition name
2. **Process**: Automated ML pipeline with Claude integration
3. **Output**: Best performing model and submission

### The Loop:
1. 📥 **Fetch** - Get competition data
2. 🤖 **Analyze** - Claude understands the problem
3. 💡 **Strategize** - Generate ML approaches
4. 🧪 **Experiment** - Run isolated experiments
5. 📊 **Evaluate** - Measure performance
6. 🔄 **Iterate** - Learn and improve

### Key Features:
- **Fully Automated**: Runs without manual intervention
- **Claude-Powered**: Leverages AI for analysis and coding
- **Isolated Experiments**: Each experiment in its own Git worktree
- **Continuous Learning**: Improves strategies based on results
- **Flexible**: Supports both real execution and simulation mode