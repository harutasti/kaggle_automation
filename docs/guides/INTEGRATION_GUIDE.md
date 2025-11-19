# Integration Guide: kaggle_crawler with auto_kaggler

## Overview

The kaggle_crawler project has been successfully integrated into the auto_kaggler environment. Both projects now share the same uv environment with all necessary dependencies installed.

## Environment Setup Completed

1. **Dependencies Added** to `pyproject.toml`:
   - `crawl4ai>=0.6.3` - Web scraping framework
   - `tqdm>=4.67.1` - Progress bars
   - `kaggle>=1.7.4.5` - Kaggle API client (upgraded)

2. **Playwright Setup** completed via `uv run crawl4ai-setup`

3. **Verification** successful via `uv run crawl4ai-doctor`

## How to Use kaggle_crawler

### Basic Usage

```bash
# Crawl a competition (e.g., Titanic)
uv run python kaggle_crawler/crawl_kaggle_competition.py titanic

# Force re-crawl (deletes existing data)
uv run python kaggle_crawler/crawl_kaggle_competition.py titanic --force

# Crawl with more discussions
uv run python kaggle_crawler/crawl_kaggle_competition.py titanic --max-discussions 50

# Debug mode (visible browser)
uv run python kaggle_crawler/crawl_kaggle_competition.py titanic --visible
```

### Output Structure

Crawled data is saved to:
```
kaggle_crawler/kaggle_competitions/{competition_id}/
├── data/           # Competition datasets (requires kaggle.json)
├── pages/          # Main competition pages
│   ├── overview.md
│   ├── rules.md
│   └── leaderboard.md
└── discussions/    # Discussion threads
    └── top_N_most_voted/
        ├── discussion_*.md
        └── upvoted_discussions.md  # Aggregated insights
```

## Integration Points with auto_kaggler

### 1. KIM (Kaggle Interface Manager) Enhancement

Instead of simulating competition data, KIM can now:
- Call kaggle_crawler to fetch real competition data
- Parse the markdown files for competition details
- Extract evaluation metrics from overview.md
- Use discussion insights for strategy generation

### 2. KSE (Knowledge Strategy Engine) Enhancement

KSE can leverage crawled discussions to:
- Extract successful approaches from top-voted discussions
- Identify common pitfalls and solutions
- Generate more informed hypotheses based on community wisdom
- Parse feature engineering ideas from upvoted_discussions.md

### 3. Data Access

The crawled data provides:
- **Competition Overview**: Rules, evaluation metrics, timelines
- **Leaderboard Data**: Current top scores and trends
- **Community Knowledge**: Proven strategies, feature ideas, model approaches
- **Datasets**: Actual competition data files (with Kaggle API credentials)

## Implementation Example

```python
# In kim.py
def get_real_competition_info(self, competition_name: str) -> CompetitionInfo:
    # Run crawler
    crawler_path = "kaggle_crawler/crawl_kaggle_competition.py"
    subprocess.run([sys.executable, crawler_path, competition_name])
    
    # Read crawled data
    base_path = f"kaggle_crawler/kaggle_competitions/{competition_name}"
    overview = read_markdown(f"{base_path}/pages/overview.md")
    rules = read_markdown(f"{base_path}/pages/rules.md")
    
    # Parse and return CompetitionInfo
    return parse_competition_info(overview, rules)

# In kse.py
def analyze_community_insights(self, competition_name: str):
    # Read aggregated discussions
    insights_path = f"kaggle_crawler/kaggle_competitions/{competition_name}/discussions/top_20_most_voted/upvoted_discussions.md"
    insights = read_markdown(insights_path)
    
    # Extract strategies and features
    strategies = extract_strategies_from_discussions(insights)
    return strategies
```

## Next Steps

1. **Modify KIM** to use kaggle_crawler instead of simulation
2. **Update KSE** to incorporate discussion insights
3. **Add kaggle.json** for dataset downloads (place in project root or ~/.kaggle/)
4. **Test with real competition** data flow

## Notes

- The crawler implements rate limiting and retry logic
- Headless mode by default (use --visible for debugging)
- Requires internet connection and may take several minutes
- Discussion cleaning removes user URLs while preserving content