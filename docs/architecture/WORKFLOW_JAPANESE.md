# AutoKaggler ワークフロー詳細解説

## 概要

AutoKagglerは、複数のAIエージェントを並列実行してKaggleコンペティションに自律的に参加するシステムです。
本ドキュメントでは、システム全体のワークフローをMermaidグラフで可視化し、各フェーズの動作を詳しく解説します。

---

## 1. システム全体フロー

```mermaid
graph TB
    Start([開始: main.py]) --> LoadConfig[設定ファイル読み込み]
    LoadConfig --> InitMCDU[MCDU初期化]
    InitMCDU --> InitComponents[全コンポーネント初期化]

    InitComponents --> CheckCrawler{use_crawler?}
    CheckCrawler -->|Yes| FetchCrawler[クローラーでデータ取得]
    CheckCrawler -->|No| UseAPI[Kaggle API使用]

    FetchCrawler --> ExtractInsights[ディスカッションから<br/>戦略抽出]
    UseAPI --> MainLoop[メインイテレーションループ]
    ExtractInsights --> MainLoop

    MainLoop --> GenHypothesis[仮説生成<br/>KSE]
    GenHypothesis --> LaunchExp[実験並列実行<br/>EO]
    LaunchExp --> Monitor[WCAプロセス監視]

    Monitor --> CheckComplete{全実験完了?}
    CheckComplete -->|No| Monitor
    CheckComplete -->|Yes| CollectResults[結果収集<br/>RAD]

    CollectResults --> Analyze[パフォーマンス分析<br/>PA]
    Analyze --> CheckStop{停止条件?}

    CheckStop -->|達成| FinalReport[最終レポート作成]
    CheckStop -->|未達成| UpdateState[状態更新]
    UpdateState --> GenHypothesis

    FinalReport --> End([終了])

    style Start fill:#e1f5e1
    style End fill:#ffe1e1
    style MainLoop fill:#e1e5ff
    style GenHypothesis fill:#fff4e1
    style LaunchExp fill:#fff4e1
    style CollectResults fill:#fff4e1
    style Analyze fill:#fff4e1
```

---

## 2. コンポーネント構成図

```mermaid
graph LR
    subgraph "中央制御"
        MCDU[MCDU<br/>マスター制御<br/>決定ユニット]
    end

    subgraph "データ管理"
        KIM[KIM<br/>Kaggleインターフェース<br/>マネージャー]
        RAD[RAD<br/>結果集約<br/>データベース]
    end

    subgraph "戦略・分析"
        KSE[KSE<br/>知識戦略<br/>エンジン]
        PA[PA<br/>パフォーマンス<br/>アナライザー]
    end

    subgraph "実行管理"
        EO[EO<br/>実験<br/>オーケストレーター]
        WCA1[WCA-1]
        WCA2[WCA-2]
        WCA3[WCA-3]
    end

    subgraph "外部連携"
        Crawler[kaggle_crawler<br/>クローラー]
        KaggleAPI[Kaggle API]
    end

    MCDU --> KIM
    MCDU --> KSE
    MCDU --> EO
    MCDU --> RAD
    MCDU --> PA

    KIM --> Crawler
    KIM --> KaggleAPI

    EO --> WCA1
    EO --> WCA2
    EO --> WCA3

    KSE --> RAD
    PA --> RAD

    style MCDU fill:#ff9999
    style KIM fill:#99ccff
    style KSE fill:#ffcc99
    style EO fill:#cc99ff
    style RAD fill:#99ff99
    style PA fill:#ffff99
```

---

## 3. 初期化フェーズ詳細

```mermaid
sequenceDiagram
    participant Main as main.py
    participant MCDU as MCDU
    participant KIM as KIM
    participant KSE as KSE
    participant EO as EO
    participant RAD as RAD
    participant PA as PA
    participant Crawler as kaggle_crawler

    Main->>Main: 1. config.json読み込み
    Main->>Main: 2. ロガー設定
    Main->>Main: 3. ディレクトリ作成
    Main->>Main: 4. Gitリポジトリ確認

    Main->>MCDU: 5. MCDU初期化
    activate MCDU

    MCDU->>KIM: 6. KIM初期化
    activate KIM
    KIM-->>MCDU: 初期化完了
    deactivate KIM

    MCDU->>KSE: 7. KSE初期化
    activate KSE
    KSE-->>MCDU: 初期化完了
    deactivate KSE

    MCDU->>EO: 8. EO初期化
    activate EO
    EO-->>MCDU: 初期化完了
    deactivate EO

    MCDU->>RAD: 9. RAD初期化
    activate RAD
    RAD-->>MCDU: 初期化完了
    deactivate RAD

    MCDU->>PA: 10. PA初期化
    activate PA
    PA-->>MCDU: 初期化完了
    deactivate PA

    Main->>MCDU: 11. run_main_loop()実行

    MCDU->>KIM: 12. get_competition_info()
    activate KIM

    alt use_crawler=true
        KIM->>Crawler: 13. クローラー実行
        activate Crawler
        Crawler->>Crawler: コンペページ取得
        Crawler->>Crawler: ディスカッション取得
        Crawler->>Crawler: データファイルDL
        Crawler-->>KIM: 完了
        deactivate Crawler
        KIM->>KIM: 14. クローラーデータ解析
    else use_crawler=false
        KIM->>KIM: 15. APIまたはシミュレーション
    end

    KIM-->>MCDU: 16. CompetitionInfo返却
    deactivate KIM

    deactivate MCDU
```

---

## 4. イテレーションループ詳細

```mermaid
graph TD
    IterStart[イテレーション N 開始] --> CheckIteration{初回イテレーション?}

    CheckIteration -->|Yes| GenInitial[初期仮説生成<br/>KSE.generate_initial_hypotheses]
    CheckIteration -->|No| GenNext[次イテレーション仮説生成<br/>KSE.generate_next_hypotheses]

    GenInitial --> UseCrawler{use_crawler?}
    UseCrawler -->|Yes| ParseDiscussion[ディスカッション解析<br/>コミュニティ戦略抽出]
    UseCrawler -->|No| StandardStrategy[標準戦略選択]

    ParseDiscussion --> CreateHypothesis[仮説オブジェクト生成]
    StandardStrategy --> CreateHypothesis
    GenNext --> CreateHypothesis

    CreateHypothesis --> LaunchPhase[実験起動フェーズ]

    LaunchPhase --> CreateWorktree[Gitワークツリー作成]
    CreateWorktree --> CopyTask[タスクファイル配置]
    CopyTask --> StartWCA[WCAプロセス起動]

    StartWCA --> MonitorPhase[監視フェーズ]
    MonitorPhase --> CheckDone{DONE/ERRORファイル?}
    CheckDone -->|未検出| Sleep[10秒待機]
    Sleep --> CheckDone
    CheckDone -->|検出| CollectPhase[結果収集フェーズ]

    CollectPhase --> ReadResults[結果ファイル読み込み]
    ReadResults --> StoreRAD[RADに保存]
    StoreRAD --> CleanupWorktree[ワークツリー削除]

    CleanupWorktree --> AllDone{全実験完了?}
    AllDone -->|No| MonitorPhase
    AllDone -->|Yes| AnalyzePhase[分析フェーズ]

    AnalyzePhase --> CalcStats[統計計算<br/>PA.analyze_results]
    CalcStats --> FindBest[最良実験特定]
    FindBest --> GenRecommend[推奨事項生成]

    GenRecommend --> DecisionPhase[意思決定フェーズ]
    DecisionPhase --> UpdateBest[全体ベストスコア更新]
    UpdateBest --> CheckStopCond{停止条件判定}

    CheckStopCond -->|最大イテレーション到達| Stop[停止]
    CheckStopCond -->|スコア閾値達成| Stop
    CheckStopCond -->|改善なし連続| Stop
    CheckStopCond -->|継続| IncIteration[イテレーション+1]

    IncIteration --> IterStart
    Stop --> FinalReport[最終レポート出力]

    style IterStart fill:#e1ffe1
    style LaunchPhase fill:#ffe1e1
    style MonitorPhase fill:#e1e1ff
    style CollectPhase fill:#ffe1ff
    style AnalyzePhase fill:#ffffe1
    style DecisionPhase fill:#e1ffff
    style Stop fill:#ff9999
```

---

## 5. WCA（Worker Claude Agent）実行フロー

```mermaid
graph TD
    WCAStart[WCAプロセス起動] --> SetupLogger[ローカルロガー設定]
    SetupLogger --> ReadTask[task.md読み込み]
    ReadTask --> ParseInstruction[指示解析]

    ParseInstruction --> ExtractInfo[情報抽出]
    ExtractInfo --> InfoList[・アルゴリズム名<br/>・ハイパーパラメータ<br/>・特徴量エンジニアリング<br/>・コミュニティインサイト]

    InfoList --> SimulateML[ML作業シミュレーション]
    SimulateML --> DataLoad[データ読み込みシミュレート]
    DataLoad --> Training[学習シミュレート]
    Training --> Prediction[予測シミュレート]

    Prediction --> GenScore[スコア生成<br/>正規分布ランダム]
    GenScore --> SimFailure{失敗シミュレート?<br/>10%確率}

    SimFailure -->|Yes| WriteError[ERROR_*.txtファイル作成]
    WriteError --> WriteErrorDone[DONE_ERROR_*.txtマーカー作成]
    WriteErrorDone --> ExitError[エラー終了]

    SimFailure -->|No| WriteResults[結果ファイル作成]
    WriteResults --> WriteMetrics[metrics.json作成]
    WriteMetrics --> WritePredictions[predictions.csv作成]
    WritePredictions --> WriteSummary[summary.txt作成]
    WriteSummary --> WriteSuccess[DONE_SUCCESS_*.txtマーカー作成]
    WriteSuccess --> ExitSuccess[正常終了]

    style WCAStart fill:#ccffcc
    style SimFailure fill:#ffcccc
    style WriteSuccess fill:#ccffff
    style ExitSuccess fill:#ccffcc
    style ExitError fill:#ffcccc
```

---

## 6. データフロー図

```mermaid
graph LR
    subgraph "入力データ"
        Config[config.json]
        CrawlerData[kaggle_competitions/<br/>competition_id/]
        KaggleFiles[train.csv<br/>test.csv]
    end

    subgraph "MCDU制御フロー"
        CompInfo[CompetitionInfo]
        Hypotheses[ExperimentHypothesis<br/>リスト]
        Results[ExperimentResult<br/>リスト]
        Analysis[AnalysisResult]
    end

    subgraph "実験実行データ"
        Worktrees[experiments/worktrees/<br/>exp_*_iter*_wca*/]
        TaskMD[task.md<br/>実験指示書]
        ResultFiles[metrics.json<br/>predictions.csv<br/>summary.txt]
    end

    subgraph "永続化データ"
        HypothesisJSON[experiments/hypotheses/<br/>iter*_hypothesis_*.json]
        ResultsJSON[experiments/results/<br/>exp_*_result.json]
        AnalysisJSON[experiments/analysis/<br/>iter*_analysis.json]
    end

    Config --> MCDU
    CrawlerData --> KIM
    KIM --> CompInfo
    CompInfo --> KSE

    KSE --> Hypotheses
    Hypotheses --> HypothesisJSON
    Hypotheses --> EO

    EO --> Worktrees
    EO --> TaskMD
    TaskMD --> WCA
    KaggleFiles --> WCA

    WCA --> ResultFiles
    ResultFiles --> RAD
    RAD --> Results
    Results --> ResultsJSON

    Results --> PA
    PA --> Analysis
    Analysis --> AnalysisJSON

    Analysis --> MCDU
    Results --> MCDU

    style MCDU fill:#ff9999
    style KIM fill:#99ccff
    style KSE fill:#ffcc99
    style EO fill:#cc99ff
    style WCA fill:#99ff99
    style RAD fill:#99ff99
    style PA fill:#ffff99
```

---

## 7. 停止条件判定フロー

```mermaid
graph TD
    Start[停止条件判定開始] --> Check1{stop_reasonが<br/>既にセット済み?}
    Check1 -->|Yes| StopWithReason[理由付きで停止]
    Check1 -->|No| Check2{current_iteration ≥<br/>max_iterations?}

    Check2 -->|Yes| SetReason1[stop_reason =<br/>'最大イテレーション到達']
    SetReason1 --> StopMax[停止: 最大回数]

    Check2 -->|No| Check3{best_score ≥<br/>score_threshold?}
    Check3 -->|Yes| SetReason2[stop_reason =<br/>'スコア閾値達成']
    SetReason2 --> StopThreshold[停止: 目標達成]

    Check3 -->|No| Check4{iterations_without_<br/>improvement ≥<br/>no_improvement_threshold?}
    Check4 -->|Yes| SetReason3[stop_reason =<br/>'改善なし連続']
    SetReason3 --> StopNoImprove[停止: 改善停滞]

    Check4 -->|No| Continue[継続: 次イテレーションへ]

    StopWithReason --> LogStop[停止理由をログ出力]
    StopMax --> LogStop
    StopThreshold --> LogStop
    StopNoImprove --> LogStop

    LogStop --> FinalReport[最終レポート作成]
    Continue --> NextIter[次イテレーション開始]

    style StopWithReason fill:#ff9999
    style StopMax fill:#ff9999
    style StopThreshold fill:#99ff99
    style StopNoImprove fill:#ffcc99
    style Continue fill:#99ccff
```

---

## 8. 仮説生成戦略選択フロー

```mermaid
graph TD
    StartGen[仮説生成開始] --> CheckFirst{初回イテレーション?}

    CheckFirst -->|Yes| CheckCrawler{use_crawler?}
    CheckCrawler -->|Yes| ParseDisc[parse_discussion_strategies]
    CheckCrawler -->|No| BaseStrategies[基本戦略リスト使用]

    ParseDisc --> ExtractAlgo[アルゴリズム名抽出<br/>LightGBM, XGBoost等]
    ExtractAlgo --> ExtractTips[コミュニティTips抽出]
    ExtractTips --> AddCommunity[コミュニティ戦略追加]
    AddCommunity --> MergeStrategies[戦略リストマージ]

    BaseStrategies --> MergeStrategies
    MergeStrategies --> SelectLoop[N個の仮説選択ループ]

    CheckFirst -->|No| LoadPrevious[前イテレーション結果ロード]
    LoadPrevious --> AnalyzePrev[前回分析結果確認]
    AnalyzePrev --> FindSuccess[成功戦略特定]
    FindSuccess --> FindFail[失敗戦略特定]
    FindFail --> AdaptStrategy[戦略適応]
    AdaptStrategy --> SelectLoop

    SelectLoop --> PickStrategy[戦略選択<br/>ランダム or 適応的]
    PickStrategy --> GenParams[パラメータ生成]
    GenParams --> FindInsights{関連インサイト検索}

    FindInsights -->|見つかった| AttachInsight[インサイト添付]
    FindInsights -->|見つからない| NoInsight[インサイトなし]

    AttachInsight --> CreateTaskMD[task.md作成]
    NoInsight --> CreateTaskMD

    CreateTaskMD --> SaveHypothesis[hypothesis JSON保存]
    SaveHypothesis --> AddToList[仮説リストに追加]

    AddToList --> CheckCount{N個生成完了?}
    CheckCount -->|No| SelectLoop
    CheckCount -->|Yes| ReturnList[ExperimentHypothesisリスト返却]

    style CheckFirst fill:#e1f5ff
    style ParseDisc fill:#fff4e1
    style LoadPrevious fill:#ffe1f5
    style AdaptStrategy fill:#e1ffe1
    style ReturnList fill:#99ff99
```

---

## 9. パフォーマンス分析フロー

```mermaid
graph TD
    StartAnalysis[PA.analyze_results開始] --> LoadResults[イテレーション結果ロード]
    LoadResults --> CheckEmpty{結果が空?}

    CheckEmpty -->|Yes| CreateEmptyAnalysis[空の分析結果作成]
    CreateEmptyAnalysis --> ReturnEmpty[AnalysisResult返却]

    CheckEmpty -->|No| FilterValid[有効な結果フィルタ<br/>status='success']
    FilterValid --> CheckValidEmpty{有効結果なし?}

    CheckValidEmpty -->|Yes| CreateEmptyAnalysis
    CheckValidEmpty -->|No| CalcStats[統計計算]

    CalcStats --> CalcBest[最良スコア特定]
    CalcBest --> CalcWorst[最悪スコア特定]
    CalcWorst --> CalcAvg[平均スコア計算]
    CalcAvg --> CalcStdDev[標準偏差計算]

    CalcStdDev --> GroupByStrategy[戦略別グループ化]
    GroupByStrategy --> CalcStrategyAvg[戦略別平均計算]
    CalcStrategyAvg --> RankStrategies[戦略ランキング作成]

    RankStrategies --> AnalyzeParams[パラメータ分析]
    AnalyzeParams --> FindPatterns[成功パターン発見]
    FindPatterns --> FindAntiPatterns[失敗パターン発見]

    FindAntiPatterns --> GenRecommendations[推奨事項生成]
    GenRecommendations --> RecList[・優秀戦略の継続<br/>・パラメータ調整<br/>・新戦略の試行<br/>・失敗戦略の回避]

    RecList --> CreateAnalysis[AnalysisResultオブジェクト作成]
    CreateAnalysis --> SaveAnalysisJSON[analysis JSON保存]
    SaveAnalysisJSON --> LogSummary[分析サマリーログ出力]
    LogSummary --> ReturnAnalysis[AnalysisResult返却]

    style StartAnalysis fill:#ffffe1
    style CalcStats fill:#e1f5ff
    style GenRecommendations fill:#ffe1e1
    style ReturnAnalysis fill:#99ff99
```

---

## 10. システム状態遷移図

```mermaid
stateDiagram-v2
    [*] --> Initializing: システム起動
    Initializing --> Ready: 全コンポーネント初期化完了

    Ready --> FetchingData: コンペ情報取得開始
    FetchingData --> Ready: データ取得失敗
    FetchingData --> Iterating: データ取得成功

    Iterating --> GeneratingHypothesis: 仮説生成開始
    GeneratingHypothesis --> Iterating: 仮説生成失敗
    GeneratingHypothesis --> LaunchingExperiments: 仮説生成成功

    LaunchingExperiments --> RunningExperiments: WCA起動成功
    LaunchingExperiments --> Iterating: WCA起動失敗

    RunningExperiments --> RunningExperiments: 実験実行中
    RunningExperiments --> CollectingResults: 全実験完了

    CollectingResults --> Analyzing: 結果収集完了

    Analyzing --> DecisionMaking: 分析完了

    DecisionMaking --> Iterating: 継続判断
    DecisionMaking --> Finalizing: 停止判断

    Finalizing --> [*]: 最終レポート出力完了

    note right of Initializing
        MCDU, KIM, KSE,
        EO, RAD, PA初期化
    end note

    note right of RunningExperiments
        複数WCAが並列実行
        Gitワークツリー使用
    end note

    note right of DecisionMaking
        停止条件:
        - max_iterations到達
        - score_threshold達成
        - 改善停滞
    end note
```

---

## 11. データモデル関係図

```mermaid
classDiagram
    class CompetitionInfo {
        +str name
        +str description
        +str metric
        +List~str~ data_files
        +Dict~str,Any~ metadata
    }

    class ExperimentHypothesis {
        +str experiment_id
        +int iteration
        +str strategy
        +Dict~str,Any~ parameters
        +str task_description
        +List~str~ insights
        +str created_at
    }

    class ExperimentResult {
        +str experiment_id
        +int iteration
        +str status
        +float score
        +str strategy
        +Dict~str,Any~ parameters
        +str error_message
        +Dict~str,Any~ metrics
        +str completed_at
    }

    class AnalysisResult {
        +int iteration
        +float best_score
        +str best_experiment_id
        +float worst_score
        +float average_score
        +float std_deviation
        +Dict~str,float~ strategy_performance
        +List~str~ recommendations
        +str created_at
    }

    MCDU --> CompetitionInfo: 取得
    MCDU --> ExperimentHypothesis: 生成指示
    MCDU --> ExperimentResult: 収集
    MCDU --> AnalysisResult: 受取

    KSE --> ExperimentHypothesis: 生成
    EO --> ExperimentHypothesis: 実行
    RAD --> ExperimentResult: 保存
    PA --> AnalysisResult: 生成

    ExperimentHypothesis --> ExperimentResult: 実行後変換
    ExperimentResult --> AnalysisResult: 分析に使用
```

---

## 12. ファイルシステム構造とデータフロー

```mermaid
graph TD
    subgraph "設定ファイル"
        A[config/config.json]
    end

    subgraph "クローラー出力"
        B[kaggle_competitions/<br/>competition_id/]
        B1[overview.md]
        B2[data_page.md]
        B3[discussions/*.md]
        B4[datasets/*.csv]
    end

    subgraph "実験作業領域"
        C[experiments/worktrees/]
        C1[exp_UUID_iter0_wca1/]
        C2[exp_UUID_iter0_wca2/]
        C3[exp_UUID_iter0_wca3/]
    end

    subgraph "実験出力"
        D[experiments/results/]
        D1[exp_UUID_result.json]
        D2[exp_UUID_metrics.json]
        D3[exp_UUID_predictions.csv]
    end

    subgraph "仮説保存"
        E[experiments/hypotheses/]
        E1[iter0_hypothesis_1.json]
        E2[iter0_hypothesis_2.json]
        E3[iter0_hypothesis_3.json]
    end

    subgraph "分析結果"
        F[experiments/analysis/]
        F1[iter0_analysis.json]
        F2[iter1_analysis.json]
    end

    subgraph "ログ"
        G[logs/auto_kaggle.log]
        H[experiments/worktrees/<br/>exp_UUID/wca.log]
    end

    A --> MCDU
    B --> KIM
    B1 --> KIM
    B2 --> KIM
    B3 --> KSE
    B4 --> EO

    KSE --> E
    E --> EO

    EO --> C
    C --> C1
    C --> C2
    C --> C3

    C1 --> D
    C2 --> D
    C3 --> D

    D --> RAD
    D1 --> RAD
    D2 --> RAD
    D3 --> RAD

    RAD --> PA
    PA --> F

    MCDU --> G
    EO --> H

    style A fill:#ffe1e1
    style B fill:#e1f5ff
    style C fill:#fff4e1
    style D fill:#e1ffe1
    style E fill:#ffe1ff
    style F fill:#ffffe1
```

---

## まとめ

### 主要なワークフローポイント

1. **初期化**: 全コンポーネントを初期化し、Kaggleクローラーでコンペデータを取得
2. **イテレーション**: 仮説生成 → 並列実験 → 結果収集 → 分析 → 意思決定のサイクル
3. **並列実行**: Gitワークツリーを使用して複数WCAを独立した環境で同時実行
4. **学習機構**: 前イテレーションの結果を分析し、次の仮説生成に反映
5. **適応的停止**: スコア閾値、改善停滞、最大イテレーション数による自動停止

### キー技術

- **Git Worktrees**: 実験の完全な分離環境
- **crawl4ai**: Kaggleページとディスカッションのスクレイピング
- **JSON永続化**: 全データをJSONで保存し、再現性を確保
- **構造化ログ**: 全コンポーネントで統一されたログ出力
- **データクラス**: 型安全なデータモデル (src/data_models.py)

### 設定可能なパラメータ

| パラメータ | 説明 | デフォルト |
|----------|------|----------|
| max_iterations | 最大イテレーション数 | 5 |
| wca_per_iteration | イテレーション毎のWCA数 | 3 |
| score_threshold | 目標スコア閾値 | 0.95 |
| no_improvement_iterations | 改善なし許容回数 | 2 |
| simulation_mode | シミュレーションモード | true |
| use_crawler | クローラー使用 | true |

---

## 参考ドキュメント

- [PROJECT_OVERVIEW.md](architecture/PROJECT_OVERVIEW.md) - システム概要
- [DETAILED_FLOW.md](architecture/DETAILED_FLOW.md) - 詳細フロー（英語）
- [PROJECT_STRUCTURE.md](architecture/PROJECT_STRUCTURE.md) - プロジェクト構造
- [INTEGRATION_GUIDE.md](guides/INTEGRATION_GUIDE.md) - クローラー統合ガイド
