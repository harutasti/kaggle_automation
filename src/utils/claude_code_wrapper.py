#!/usr/bin/env python3
"""
claude_code_wrapper.py - Python wrapper for Claude Code CLI integration with AutoKaggler

This module provides a Python interface to the Claude Code CLI, enabling AutoKaggler
to leverage Claude's capabilities for ML experiment implementation and analysis.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.file_utils import ensure_dir, read_json, write_json


@dataclass
class ClaudeCodeResult:
    """Result from Claude Code execution"""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time: float = 0.0
    tokens_used: int = 0
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    tools_called: List[str] = field(default_factory=list)
    session_name: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ClaudeCodeException(Exception):
    """Custom exception for Claude Code errors"""
    pass


class ClaudeCodeWrapper:
    """
    Wrapper for Claude Code CLI providing Python interface for AutoKaggler integration.
    
    This wrapper handles:
    - Command construction and execution
    - Session management
    - Error handling and retries
    - Output parsing
    - Tool permission management
    - Usage tracking
    """
    
    # Default allowed tools for different task types
    DEFAULT_EXPERIMENT_TOOLS = [
        "Read", "Write", "Edit", "MultiEdit",
        "LS", "Grep", "Glob",
        "Bash", "NotebookRead", "NotebookEdit"
    ]
    
    DEFAULT_ANALYSIS_TOOLS = [
        "Read", "Grep", "Glob", "LS"
    ]
    
    DEFAULT_REPORT_TOOLS = [
        "Read", "Write", "Edit", "MultiEdit"
    ]
    
    # Disallowed tools for safety
    DISALLOWED_TOOLS = [
        "Bash(rm -rf:*)",
        "Bash(git reset --hard:*)",
        "Bash(git push:*)",
        "Bash(sudo:*)",
        "Bash(pip install:*)",
        "Bash(npm install:*)"
    ]
    
    def __init__(self, config: Dict[str, Any], debug: bool = False):
        """
        Initialize Claude Code wrapper.
        
        Args:
            config: Configuration dictionary with claude_code settings
            debug: Enable debug logging
        """
        self.config = config
        self.claude_config = config.get("claude_code", {})
        self.debug = debug
        
        # Setup logger
        self.logger = logging.getLogger("AutoKaggle.ClaudeCodeWrapper")
        if debug:
            self.logger.setLevel(logging.DEBUG)
        
        # Initialize settings
        self.model = self.claude_config.get("model", "claude-3-5-sonnet-20241022")
        self.output_format = self.claude_config.get("output_format", "json")
        self.session_prefix = self.claude_config.get("session_prefix", "autokaggler")
        self.default_timeout = self.claude_config.get("default_timeout", 3600)
        
        # Permissions
        self.skip_permissions = self.claude_config.get("permissions", {}).get("skip_prompts", True)
        self.sandbox_mode = self.claude_config.get("permissions", {}).get("sandbox_mode", False)
        self.working_directory_only = self.claude_config.get("permissions", {}).get("working_directory_only", True)
        
        # Usage tracking
        self.usage_tracking_enabled = self.claude_config.get("track_usage", True)
        self.usage_log_path = os.path.join(config.get("experiments_base_dir", "./experiments"), "claude_usage.json")
        self._initialize_usage_tracking()
        
        # Session management
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        self.logger.info(f"Claude Code wrapper initialized with model: {self.model}")
    
    def _initialize_usage_tracking(self):
        """Initialize usage tracking file"""
        if self.usage_tracking_enabled:
            ensure_dir(os.path.dirname(self.usage_log_path))
            if not os.path.exists(self.usage_log_path):
                write_json({"sessions": {}, "total_tokens": 0, "total_cost": 0.0}, self.usage_log_path)
    
    def _build_command(self, 
                      prompt: str,
                      session: Optional[str] = None,
                      allowed_tools: Optional[List[str]] = None,
                      interactive: bool = False,
                      output_format: Optional[str] = None,
                      no_stream: bool = False) -> List[str]:
        """
        Build Claude CLI command with appropriate flags.
        
        Args:
            prompt: The prompt to send to Claude
            session: Session name for context continuity
            allowed_tools: List of allowed tools
            interactive: Whether to run in interactive mode
            output_format: Output format (json, text, stream-json)
            no_stream: Disable streaming output
            timeout: Command timeout in seconds
            
        Returns:
            List of command arguments
        """
        cmd = ["claude"]
        
        if interactive:
            # Interactive mode
            if self.skip_permissions:
                cmd.append("--dangerously-skip-permissions")
        else:
            # Non-interactive mode - prompt must come right after -p
            cmd.extend(["-p", prompt])
            
            # Skip permissions flag doesn't work outside Docker
            # if self.claude_config.get("permissions", {}).get("skip_prompts", False):
            #     cmd.append("--dangerously-skip-permissions")
            
            # Output format
            format_to_use = output_format or self.output_format
            cmd.extend(["--output-format", format_to_use])
        
        # Model
        cmd.extend(["--model", self.model])
        
        # Session - Claude Code doesn't support --session flag
        # We'll track sessions internally instead
        # if session:
        #     cmd.extend(["--session", session])
        
        # Tools
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        cmd.extend(["--disallowedTools", ",".join(self.DISALLOWED_TOOLS)])
        
        # Sandbox mode - not supported by current Claude CLI
        # if self.sandbox_mode:
        #     cmd.append("--sandbox")
        
        # Debug mode
        if self.debug:
            cmd.append("--verbose")
        
        return cmd
    
    def _parse_output(self, stdout: str, output_format: str) -> Tuple[Dict[str, Any], str]:
        """
        Parse Claude Code output based on format.
        
        Args:
            stdout: Raw stdout from Claude
            output_format: Expected output format
            
        Returns:
            Tuple of (parsed_data, raw_output)
        """
        if output_format == "json":
            try:
                # Claude Code returns JSON when using --output-format json
                parsed = json.loads(stdout)
                return parsed, stdout
            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse JSON output: {e}")
                # Try to extract JSON from output
                import re
                json_match = re.search(r'\{.*\}', stdout, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        return parsed, stdout
                    except:
                        pass
                return {}, stdout
        else:
            # Text format
            return {"response": stdout}, stdout
    
    def _extract_file_operations(self, output: str) -> Tuple[List[str], List[str]]:
        """
        Extract file operations from Claude's output.
        
        Args:
            output: Raw output from Claude
            
        Returns:
            Tuple of (files_created, files_modified)
        """
        files_created = []
        files_modified = []
        
        # Simple pattern matching for file operations
        # This could be enhanced based on actual Claude Code output patterns
        import re
        
        # Look for file creation patterns
        create_patterns = [
            r"Created file: (.+)",
            r"Writing to (.+)",
            r"File created at: (.+)"
        ]
        for pattern in create_patterns:
            matches = re.findall(pattern, output)
            files_created.extend(matches)
        
        # Look for file modification patterns
        modify_patterns = [
            r"Modified file: (.+)",
            r"Edited (.+)",
            r"Updated (.+)"
        ]
        for pattern in modify_patterns:
            matches = re.findall(pattern, output)
            files_modified.extend(matches)
        
        return list(set(files_created)), list(set(files_modified))
    
    def _track_usage(self, result: ClaudeCodeResult):
        """Track usage statistics"""
        if not self.usage_tracking_enabled:
            return
        
        try:
            usage_data = read_json(self.usage_log_path)
            
            # Update session data
            session_key = result.session_name or "default"
            if session_key not in usage_data["sessions"]:
                usage_data["sessions"][session_key] = {
                    "total_tokens": 0,
                    "total_calls": 0,
                    "total_time": 0.0,
                    "created_at": datetime.now().isoformat()
                }
            
            session_data = usage_data["sessions"][session_key]
            session_data["total_tokens"] += result.tokens_used
            session_data["total_calls"] += 1
            session_data["total_time"] += result.execution_time
            session_data["last_used"] = datetime.now().isoformat()
            
            # Update totals
            usage_data["total_tokens"] += result.tokens_used
            
            # Estimate cost (rough approximation)
            # Claude 3.5 Sonnet: $3 per million input tokens, $15 per million output tokens
            # Assuming 80/20 split for input/output
            estimated_cost = (result.tokens_used * 0.8 * 3 / 1_000_000) + \
                           (result.tokens_used * 0.2 * 15 / 1_000_000)
            usage_data["total_cost"] += estimated_cost
            
            write_json(usage_data, self.usage_log_path)
            
        except Exception as e:
            self.logger.error(f"Failed to track usage: {e}")
    
    def execute_task(self,
                    prompt: str,
                    session: Optional[str] = None,
                    working_directory: Optional[str] = None,
                    allowed_tools: Optional[List[str]] = None,
                    timeout: Optional[int] = None,
                    continue_session: bool = False,
                    max_retries: int = 2,
                    output_format: Optional[str] = None) -> ClaudeCodeResult:
        """
        Execute a task using Claude Code CLI.
        
        Args:
            prompt: Task prompt for Claude
            session: Session name for context
            working_directory: Working directory for execution
            allowed_tools: List of allowed tools (defaults to experiment tools)
            timeout: Execution timeout in seconds
            continue_session: Whether to continue existing session
            max_retries: Maximum retry attempts on failure
            output_format: Override output format
            
        Returns:
            ClaudeCodeResult with execution details
        """
        # Prepare session
        if session and not continue_session:
            session = f"{self.session_prefix}_{session}_{int(time.time())}"
        elif not session:
            session = f"{self.session_prefix}_task_{int(time.time())}"
        
        # Default tools if not specified
        if allowed_tools is None:
            allowed_tools = self.DEFAULT_EXPERIMENT_TOOLS
        
        # Build command
        cmd = self._build_command(
            prompt=prompt,
            session=session,
            allowed_tools=allowed_tools,
            output_format=output_format or self.output_format
        )
        
        self.logger.info(f"Executing Claude Code: {' '.join(cmd[:5])}...")
        if self.debug:
            self.logger.debug(f"Full command: {' '.join(cmd)}")
            self.logger.debug(f"Prompt: {prompt[:200]}...")
        
        # Execute with retries
        start_time = time.time()
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                # Set working directory
                cwd = working_directory or os.getcwd()
                
                # Execute command
                process = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout or self.default_timeout
                )
                
                execution_time = time.time() - start_time
                
                # Parse output
                parsed_data, raw_output = self._parse_output(
                    process.stdout, 
                    output_format or self.output_format
                )
                
                # Extract file operations
                files_created, files_modified = self._extract_file_operations(process.stdout)
                
                # Check for errors
                if process.returncode != 0:
                    error_msg = process.stderr or "Unknown error"
                    self.logger.error(f"Claude Code error (attempt {attempt + 1}): {error_msg}")
                    
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    
                    result = ClaudeCodeResult(
                        success=False,
                        error=error_msg,
                        error_type="execution_error",
                        raw_output=process.stdout,
                        execution_time=execution_time,
                        session_name=session
                    )
                else:
                    # Success
                    result = ClaudeCodeResult(
                        success=True,
                        data=parsed_data,
                        raw_output=process.stdout,
                        execution_time=execution_time,
                        files_created=files_created,
                        files_modified=files_modified,
                        session_name=session,
                        tokens_used=parsed_data.get("usage", {}).get("total_tokens", 0)
                    )
                    
                    self.logger.info(f"Task completed successfully in {execution_time:.2f}s")
                    break
                    
            except subprocess.TimeoutExpired:
                error_msg = f"Timeout after {timeout or self.default_timeout} seconds"
                self.logger.error(f"Claude Code timeout (attempt {attempt + 1})")
                
                if attempt < max_retries:
                    continue
                
                result = ClaudeCodeResult(
                    success=False,
                    error=error_msg,
                    error_type="timeout",
                    execution_time=time.time() - start_time,
                    session_name=session
                )
                
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                self.logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
                last_error = e
                
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                
                result = ClaudeCodeResult(
                    success=False,
                    error=error_msg,
                    error_type="unknown",
                    execution_time=time.time() - start_time,
                    session_name=session
                )
        
        # Track usage
        self._track_usage(result)
        
        # Store session info
        if session:
            self.active_sessions[session] = {
                "last_result": result,
                "created_at": datetime.now(),
                "working_directory": working_directory
            }
        
        return result
    
    def execute_experiment(self, 
                         experiment: Any,
                         worktree_path: str,
                         task_markdown_path: Optional[str] = None) -> ClaudeCodeResult:
        """
        Execute an ML experiment using Claude Code.
        
        Args:
            experiment: ExperimentHypothesis object
            worktree_path: Git worktree path for isolated execution
            task_markdown_path: Optional path to task markdown file
            
        Returns:
            ClaudeCodeResult with experiment results
        """
        # Create detailed prompt for experiment
        prompt = self._create_experiment_prompt(experiment, worktree_path, task_markdown_path)
        
        # Execute with experiment-specific settings
        return self.execute_task(
            prompt=prompt,
            session=f"exp_{experiment.id}",
            working_directory=worktree_path,
            allowed_tools=self.DEFAULT_EXPERIMENT_TOOLS,
            timeout=3600  # 1 hour for experiments
        )
    
    def _create_experiment_prompt(self, experiment: Any, worktree_path: str, 
                                task_markdown_path: Optional[str] = None) -> str:
        """Create detailed prompt for experiment execution"""
        if task_markdown_path and os.path.exists(task_markdown_path):
            return f"Read and implement the experiment described in {task_markdown_path}"
        
        # Build prompt from experiment object
        prompt = f"""
You are implementing an ML experiment for a Kaggle competition.

## Experiment ID: {experiment.id}

## Hypothesis
{experiment.hypothesis}

## Strategy: {experiment.strategy_name}
{experiment.strategy_description}

## Implementation Steps
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(experiment.implementation_steps))}

## Parameters
{json.dumps(experiment.parameters, indent=2)}

## Working Directory
You are in: {worktree_path}

## Requirements
1. Implement the experiment following the steps above
2. Use the specified parameters
3. Generate a submission.csv file
4. Save the cross-validation score to result.json
5. Handle errors gracefully and log important information

Please implement this experiment step by step.
"""
        return prompt
    
    def analyze_content(self,
                       prompt: str,
                       content: Any,
                       output_format: str = "structured",
                       session: Optional[str] = None) -> ClaudeCodeResult:
        """
        Analyze content using Claude Code.
        
        Args:
            prompt: Analysis prompt
            content: Content to analyze (will be converted to string)
            output_format: Expected output format
            session: Session name for context
            
        Returns:
            ClaudeCodeResult with analysis
        """
        # Prepare content
        if isinstance(content, list):
            content_str = "\n---\n".join(str(item) for item in content)
        else:
            content_str = str(content)
        
        # Create temp file if content is large
        if len(content_str) > 10000:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(content_str)
                temp_path = f.name
            
            full_prompt = f"{prompt}\n\nAnalyze the content in: {temp_path}"
            
            try:
                result = self.execute_task(
                    prompt=full_prompt,
                    session=session or "analysis",
                    allowed_tools=self.DEFAULT_ANALYSIS_TOOLS
                )
            finally:
                os.unlink(temp_path)
                
            return result
        else:
            # Include content directly in prompt
            full_prompt = f"{prompt}\n\n## Content to Analyze\n{content_str}"
            
            return self.execute_task(
                prompt=full_prompt,
                session=session or "analysis",
                allowed_tools=self.DEFAULT_ANALYSIS_TOOLS
            )
    
    def generate_report(self,
                       report_type: str,
                       data: Dict[str, Any],
                       output_path: str,
                       session: Optional[str] = None) -> ClaudeCodeResult:
        """
        Generate a report using Claude Code.
        
        Args:
            report_type: Type of report (summary, technical, analysis)
            data: Data for report generation
            output_path: Path where report should be saved
            session: Session name for context
            
        Returns:
            ClaudeCodeResult with report details
        """
        # Prepare data
        data_path = None
        if len(json.dumps(data)) > 5000:
            # Save to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(data, f, indent=2)
                data_path = f.name
        
        # Create prompt based on report type
        prompts = {
            "summary": "Generate a comprehensive summary report",
            "technical": "Create detailed technical documentation",
            "analysis": "Produce an in-depth analysis report"
        }
        
        base_prompt = prompts.get(report_type, "Generate a report")
        
        if data_path:
            prompt = f"{base_prompt} using the data in {data_path}. Save the report to {output_path}"
        else:
            prompt = f"{base_prompt} using the following data:\n{json.dumps(data, indent=2)}\n\nSave the report to {output_path}"
        
        try:
            result = self.execute_task(
                prompt=prompt,
                session=session or f"report_{report_type}",
                allowed_tools=self.DEFAULT_REPORT_TOOLS
            )
        finally:
            if data_path:
                os.unlink(data_path)
        
        return result
    
    def interactive_session(self,
                          initial_prompt: str,
                          session: str,
                          working_directory: Optional[str] = None):
        """
        Start an interactive Claude Code session.
        
        Args:
            initial_prompt: Initial prompt to start the session
            session: Session name
            working_directory: Working directory for the session
        """
        cmd = self._build_command(
            prompt=initial_prompt,
            session=f"{self.session_prefix}_{session}",
            allowed_tools=self.DEFAULT_EXPERIMENT_TOOLS,
            interactive=True
        )
        
        self.logger.info(f"Starting interactive session: {session}")
        
        # Change to working directory if specified
        if working_directory:
            os.chdir(working_directory)
        
        # Use pty for interactive session
        import pty
        pty.spawn(cmd)
    
    def cleanup_old_sessions(self, days: int = 7):
        """
        Clean up old Claude Code sessions.
        
        Args:
            days: Remove sessions older than this many days
        """
        try:
            # This would interface with Claude Code's session management
            # For now, just clean our tracking
            cutoff_time = datetime.now().timestamp() - (days * 86400)
            
            sessions_to_remove = []
            for session_name, session_data in self.active_sessions.items():
                if session_data["created_at"].timestamp() < cutoff_time:
                    sessions_to_remove.append(session_name)
            
            for session_name in sessions_to_remove:
                del self.active_sessions[session_name]
            
            if sessions_to_remove:
                self.logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup sessions: {e}")
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        if not self.usage_tracking_enabled:
            return {}
        
        try:
            return read_json(self.usage_log_path)
        except:
            return {}
    
    def validate_setup(self) -> bool:
        """
        Validate Claude Code CLI is properly installed and configured.
        
        Returns:
            True if setup is valid
        """
        try:
            # Check if claude command exists
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.logger.error("Claude Code CLI not found. Please install it first.")
                return False
            
            # Check API key
            if not os.environ.get("ANTHROPIC_API_KEY"):
                self.logger.error("ANTHROPIC_API_KEY environment variable not set")
                return False
            
            self.logger.info("Claude Code setup validated successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to validate setup: {e}")
            return False


# Convenience functions for common operations
def create_experiment_task(experiment: Any, competition_info: Any) -> str:
    """
    Create a detailed task markdown for experiment execution.
    
    Args:
        experiment: ExperimentHypothesis object
        competition_info: CompetitionInfo object
        
    Returns:
        Markdown formatted task description
    """
    return f"""# Experiment Task: {experiment.id}

## Competition: {competition_info.name}
- **Evaluation Metric**: {competition_info.evaluation_metric}
- **Submission Format**: {competition_info.submission_format}

## Hypothesis
{experiment.hypothesis}

## Strategy: {experiment.strategy_name}
{experiment.strategy_description}

## Implementation Plan
{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(experiment.implementation_steps))}

## Parameters
```json
{json.dumps(experiment.parameters, indent=2)}
```

## Data Paths
- Training: `{competition_info.train_data_path}`
- Test: `{competition_info.test_data_path}`
- Sample Submission: `{competition_info.sample_submission_path}`

## Requirements
1. Load and preprocess the data
2. Implement the strategy with specified parameters
3. Use {experiment.parameters.get('cv_folds', 5)}-fold cross-validation
4. Generate predictions for test set
5. Create `submission.csv` in competition format
6. Save results to `result.json` with structure:
   ```json
   {{
     "score": <cv_score>,
     "metrics": {{}},
     "feature_importance": [...],
     "execution_time": <seconds>
   }}
   ```

## Success Criteria
- Valid submission file generated
- Cross-validation score reported
- No errors during execution
- Execution time under 60 minutes

Begin implementation:
"""


def parse_experiment_result(result: ClaudeCodeResult, experiment_id: str) -> Dict[str, Any]:
    """
    Parse Claude Code result into AutoKaggler experiment result format.
    
    Args:
        result: ClaudeCodeResult from execution
        experiment_id: Experiment ID
        
    Returns:
        Parsed experiment result
    """
    if not result.success:
        return {
            "experiment_id": experiment_id,
            "success": False,
            "error": result.error,
            "error_type": result.error_type
        }
    
    # Look for result.json in files created
    result_data = {}
    for file in result.files_created:
        if file.endswith("result.json") or "result_" in file:
            try:
                result_data = read_json(file)
                break
            except:
                pass
    
    # Extract from Claude's response if not in file
    if not result_data and "score" in result.data:
        result_data = result.data
    
    return {
        "experiment_id": experiment_id,
        "success": True,
        "score": result_data.get("score"),
        "metrics": result_data.get("metrics", {}),
        "execution_time": result.execution_time,
        "files_created": result.files_created,
        "tokens_used": result.tokens_used
    }


if __name__ == "__main__":
    # Example usage
    config = {
        "claude_code": {
            "enabled": True,
            "model": "claude-3-5-sonnet-20241022",
            "output_format": "json"
        },
        "experiments_base_dir": "./experiments"
    }
    
    wrapper = ClaudeCodeWrapper(config, debug=True)
    
    # Validate setup
    if not wrapper.validate_setup():
        print("Claude Code setup validation failed")
        exit(1)
    
    # Example: Simple analysis task
    result = wrapper.execute_task(
        prompt="List all Python files in the current directory and count lines of code",
        allowed_tools=["LS", "Grep", "Read"]
    )
    
    if result.success:
        print(f"Success! Execution time: {result.execution_time:.2f}s")
        print(f"Result: {json.dumps(result.data, indent=2)}")
    else:
        print(f"Failed: {result.error}")