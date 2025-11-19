# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands
- Use `uv run main.py` to run the main application
- Use `uv add <package>` to add packages (DO NOT use pip)
- Use `uv run pytest tests/` to run all tests (when tests are added)
- Use `uv run pytest tests/test_file.py::test_function` to run a specific test
- Use `uv run black .` to format code (when black is installed)
- Use `uv run mypy .` to type check (when mypy is installed)

## Kaggle Crawler
- Use `uv run python src/kaggle_crawler/crawl_kaggle_competition.py <competition_id>` to crawl competition data
- Use `uv run python src/kaggle_crawler/crawl_kaggle_competition.py <competition_id> --force` to force re-crawl
- The crawler outputs to `kaggle_competitions/<competition_id>/`
- Crawled data includes:
  - Competition pages (overview, rules, leaderboard)
  - Discussion threads with community insights
  - Competition datasets (requires kaggle.json credentials)

## Code Style
- Use snake_case for functions, variables, and modules
- Use CamelCase for classes
- Include type hints for ALL function parameters and return values
- Format imports: standard library, third-party, then local imports with blank lines between groups
- Organize imports alphabetically within each group
- Log all significant operations and errors using the inherited self.logger from BaseComponent
- Handle exceptions with specific error messages and proper logging using _log_error method
- Create dataclasses in data_models.py for structured data
- Each component must inherit from BaseComponent for consistent initialization
- Document functions with docstrings using """triple quotes"""
- Use relative imports for module references (from .base_component import BaseComponent)
- Ensure all file operations use utils.file_utils functions for consistent error handling
- For API interaction, gracefully fall back to simulation mode on failures