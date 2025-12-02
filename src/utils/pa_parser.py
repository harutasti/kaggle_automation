"""
Parser for PA (Performance Analyzer) Codex output.

Parses structured markdown output from PA Codex into the AnalysisResult data model.
"""

import re
import logging
import yaml
from typing import Dict, List, Any, Optional, Tuple

from src.data_models import ExperimentDecision, ExperimentDecisionType

logger = logging.getLogger(__name__)


def parse_pa_codex_output(codex_output: str) -> Dict[str, Any]:
    """
    Parse Codex output from PA analysis into structured format.

    Args:
        codex_output: Markdown text from Codex PA analysis

    Returns:
        Dictionary with parsed analysis fields matching AnalysisResult structure
    """

    result = {
        "success_patterns": [],
        "failure_patterns": [],
        "feature_importance": [],
        "hyperparameter_insights": [],
        "high_priority_recommendations": [],
        "medium_priority_recommendations": [],
        "experimental_recommendations": [],
        "avoid_recommendations": [],
        "unresolved_questions": [],
        "overfitting_analysis": None,
        "convergence_status": None,
        "improvement_rate": None,
        "computational_efficiency": [],
        "top_discoveries": [],
        "critical_decisions": [],
        "summary": ""
    }

    try:
        # Split content into sections
        sections = _split_into_sections(codex_output)

        # Parse each section
        if "SUCCESS PATTERNS" in sections:
            result["success_patterns"] = _parse_bullet_list(sections["SUCCESS PATTERNS"])

        if "FAILURE PATTERNS" in sections:
            result["failure_patterns"] = _parse_bullet_list(sections["FAILURE PATTERNS"])

        if "FEATURE IMPORTANCE" in sections:
            result["feature_importance"] = _parse_feature_importance(sections["FEATURE IMPORTANCE"])

        if "HYPERPARAMETER INSIGHTS" in sections:
            result["hyperparameter_insights"] = _parse_bullet_list(sections["HYPERPARAMETER INSIGHTS"])

        if "HIGH PRIORITY RECOMMENDATIONS" in sections:
            result["high_priority_recommendations"] = _parse_bullet_list(sections["HIGH PRIORITY RECOMMENDATIONS"])

        if "MEDIUM PRIORITY RECOMMENDATIONS" in sections:
            result["medium_priority_recommendations"] = _parse_bullet_list(sections["MEDIUM PRIORITY RECOMMENDATIONS"])

        if "EXPERIMENTAL RECOMMENDATIONS" in sections:
            result["experimental_recommendations"] = _parse_bullet_list(sections["EXPERIMENTAL RECOMMENDATIONS"])

        if "APPROACHES TO AVOID" in sections:
            result["avoid_recommendations"] = _parse_bullet_list(sections["APPROACHES TO AVOID"])

        if "UNRESOLVED QUESTIONS" in sections:
            result["unresolved_questions"] = _parse_bullet_list(sections["UNRESOLVED QUESTIONS"])

        if "OVERFITTING ANALYSIS" in sections:
            result["overfitting_analysis"] = sections["OVERFITTING ANALYSIS"].strip()

        if "COMPUTATIONAL EFFICIENCY" in sections:
            result["computational_efficiency"] = _parse_bullet_list(sections["COMPUTATIONAL EFFICIENCY"])

        if "Performance Trajectory" in sections:
            result["convergence_status"], result["improvement_rate"] = _parse_convergence(sections["Performance Trajectory"])

        if "Top Discoveries" in sections:
            result["top_discoveries"] = _parse_bullet_list(sections["Top Discoveries"])

        if "Critical Decisions for Next Iteration" in sections:
            result["critical_decisions"] = _parse_bullet_list(sections["Critical Decisions for Next Iteration"])

        if "ITERATION SUMMARY" in sections:
            result["summary"] = sections["ITERATION SUMMARY"].strip()

    except Exception as e:
        logger.error(f"Error parsing PA Codex output: {e}")
        logger.debug(f"Codex output was:\n{codex_output}")

    return result


def _split_into_sections(content: str) -> Dict[str, str]:
    """
    Split markdown content into sections based on headers.

    Returns:
        Dictionary mapping section names to their content
    """
    sections = {}
    current_section = None
    current_content = []

    lines = content.split('\n')

    for line in lines:
        # Check for section headers (### or ##)
        if line.startswith('###'):
            # Save previous section if exists
            if current_section:
                sections[current_section] = '\n'.join(current_content)

            # Start new section
            current_section = line.replace('###', '').strip()
            current_content = []

        elif line.startswith('##') and not line.startswith('###'):
            # Save previous section if exists
            if current_section:
                sections[current_section] = '\n'.join(current_content)

            # Check if it's a major section we care about
            section_name = line.replace('##', '').strip()
            if section_name in ['RECOMMENDATIONS', 'CONVERGENCE ANALYSIS', 'KEY INSIGHTS SUMMARY']:
                current_section = None  # Will be handled by subsections
                current_content = []
            else:
                current_section = section_name
                current_content = []
        else:
            # Add content to current section
            if current_section:
                current_content.append(line)

    # Save last section
    if current_section and current_content:
        sections[current_section] = '\n'.join(current_content)

    return sections


def _parse_bullet_list(content: str) -> List[str]:
    """
    Parse bullet points from markdown content.

    Expects format:
    - **Name:** Description

    Returns:
        List of parsed items (full text after the bullet)
    """
    items = []

    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('- '):
            # Remove the bullet point prefix
            item = line[2:].strip()
            items.append(item)
        elif line.startswith('* '):
            # Alternative bullet format
            item = line[2:].strip()
            items.append(item)
        elif re.match(r'^\d+\.\s', line):
            # Numbered list format
            item = re.sub(r'^\d+\.\s+', '', line).strip()
            items.append(item)

    return items


def _parse_feature_importance(content: str) -> List[Dict[str, Any]]:
    """
    Parse feature importance section into structured format.

    Expects format:
    - **Feature Name:** Importance score X.XX (stability: high/medium/low)

    Returns:
        List of dictionaries with feature, importance, and stability
    """
    features = []

    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('- '):
            # Parse feature importance line
            match = re.match(
                r'- \*\*([^:]+):\*\*.*?(\d+\.?\d*).*?\(stability:\s*(\w+)',
                line,
                re.IGNORECASE
            )
            if match:
                feature_name = match.group(1).strip()
                importance = float(match.group(2))
                stability = match.group(3).lower()

                features.append({
                    "feature": feature_name,
                    "importance": importance,
                    "stability": stability
                })
            else:
                # Try simpler format
                simple_match = re.match(r'- \*\*([^:]+):\*\*\s*(.+)', line)
                if simple_match:
                    features.append({
                        "feature": simple_match.group(1).strip(),
                        "importance": 0.0,  # Default if not parsed
                        "stability": "unknown",
                        "description": simple_match.group(2).strip()
                    })

    return features


def _parse_convergence(content: str) -> tuple[Optional[str], Optional[float]]:
    """
    Parse convergence analysis section.

    Returns:
        Tuple of (convergence_status, improvement_rate)
    """
    convergence_status = None
    improvement_rate = None

    lines = content.strip().split('\n')
    for line in lines:
        # Look for trend line
        if '**Trend:**' in line or '**trend:**' in line:
            if 'Improving' in line or 'improving' in line:
                convergence_status = "Improving"
            elif 'Plateau' in line or 'plateau' in line:
                convergence_status = "Plateau"
            elif 'Declining' in line or 'declining' in line:
                convergence_status = "Declining"

        # Look for improvement rate
        if '**Improvement Rate:**' in line or '**improvement rate:**' in line:
            match = re.search(r'(\d+\.?\d*)%', line)
            if match:
                improvement_rate = float(match.group(1))

    return convergence_status, improvement_rate


def extract_best_score_info(content: str) -> tuple[Optional[float], Optional[str]]:
    """
    Extract best score and experiment ID from PA output.

    Returns:
        Tuple of (best_score, best_experiment_id)
    """
    best_score = None
    best_experiment_id = None

    # Look for best score pattern
    score_pattern = r'\*\*Best Score:\*\*\s*(\d+\.?\d*)\s*\(([^)]+)\)'
    match = re.search(score_pattern, content, re.IGNORECASE)

    if match:
        best_score = float(match.group(1))
        best_experiment_id = match.group(2).strip()

    return best_score, best_experiment_id


def extract_improvement_trend(content: str) -> str:
    """
    Extract improvement trend from PA output.

    Returns:
        Improvement trend string ("Improving", "Plateau", "Declining")
    """
    # Check convergence analysis first
    if 'Plateau' in content and ('convergence' in content.lower() or 'trend' in content.lower()):
        return "Plateau"
    elif 'Declining' in content and ('convergence' in content.lower() or 'trend' in content.lower()):
        return "Declining"
    elif 'Improving' in content and ('convergence' in content.lower() or 'trend' in content.lower()):
        return "Improving"

    # Default to stagnant if unclear
    return "Stagnant"


def parse_evolution_decisions(codex_output: str) -> Tuple[List[ExperimentDecision], Dict[str, Any]]:
    """
    Parse evolution decisions YAML block from PA output.

    Expects PA output to contain a YAML block with format:
    ```yaml
    decisions:
      - experiment_id: "iter1_exp1_abc123"
        decision: CONTINUE
        confidence: 0.85
        reasoning: "..."
        improvement_instructions: "..."
        potential_ceiling: 0.82
        priority_rank: 1
      - experiment_id: "iter1_exp2_def456"
        decision: TERMINATE
        confidence: 0.90
        reasoning: "..."
        termination_reason: "..."
        priority_rank: 3
    summary:
      continue_count: 2
      terminate_count: 1
      new_slots: 1
    ```

    Args:
        codex_output: Markdown text from Codex PA analysis

    Returns:
        Tuple of (List[ExperimentDecision], summary_dict)

    Raises:
        ValueError: If YAML block cannot be found or parsed
    """
    decisions = []
    summary = {}

    # Find YAML code block containing "decisions:"
    yaml_pattern = r'```yaml\s*([\s\S]*?decisions:[\s\S]*?)```'
    match = re.search(yaml_pattern, codex_output, re.IGNORECASE)

    if not match:
        # Try alternative pattern without code fence
        yaml_pattern_alt = r'decisions:\s*\n([\s\S]*?)(?=\n##|\n---|\Z)'
        match_alt = re.search(yaml_pattern_alt, codex_output)
        if match_alt:
            yaml_content = "decisions:\n" + match_alt.group(1)
        else:
            raise ValueError("Could not find evolution decisions YAML block in PA output")
    else:
        yaml_content = match.group(1)

    try:
        parsed = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse evolution decisions YAML: {e}")

    if not parsed or 'decisions' not in parsed:
        raise ValueError("YAML block does not contain 'decisions' key")

    # Parse each decision
    for decision_data in parsed.get('decisions', []):
        try:
            decision = _parse_single_decision(decision_data)
            decisions.append(decision)
        except Exception as e:
            logger.warning(f"Failed to parse decision for {decision_data.get('experiment_id', 'unknown')}: {e}")
            continue

    # Parse summary if present
    summary = parsed.get('summary', {})
    if not summary:
        # Generate summary from parsed decisions
        summary = {
            'continue_count': sum(1 for d in decisions if d.decision == ExperimentDecisionType.CONTINUE),
            'terminate_count': sum(1 for d in decisions if d.decision == ExperimentDecisionType.TERMINATE),
            'new_slots': sum(1 for d in decisions if d.decision == ExperimentDecisionType.TERMINATE)
        }

    return decisions, summary


def _parse_single_decision(data: Dict[str, Any]) -> ExperimentDecision:
    """
    Parse a single experiment decision from YAML data.

    Args:
        data: Dictionary with decision fields

    Returns:
        ExperimentDecision object

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Required fields
    experiment_id = data.get('experiment_id')
    if not experiment_id:
        raise ValueError("Missing required field: experiment_id")

    decision_str = data.get('decision', '').upper()
    if decision_str not in ('CONTINUE', 'TERMINATE'):
        raise ValueError(f"Invalid decision value: {decision_str}. Must be CONTINUE or TERMINATE")

    decision_type = ExperimentDecisionType.CONTINUE if decision_str == 'CONTINUE' else ExperimentDecisionType.TERMINATE

    reasoning = data.get('reasoning', '')
    if not reasoning:
        raise ValueError("Missing required field: reasoning")

    confidence = float(data.get('confidence', 0.5))
    if not 0.0 <= confidence <= 1.0:
        logger.warning(f"Confidence {confidence} out of range [0, 1], clamping")
        confidence = max(0.0, min(1.0, confidence))

    # Optional fields
    improvement_instructions = data.get('improvement_instructions')
    termination_reason = data.get('termination_reason')
    potential_ceiling = data.get('potential_ceiling')
    if potential_ceiling is not None:
        potential_ceiling = float(potential_ceiling)

    priority_rank = int(data.get('priority_rank', 0))

    return ExperimentDecision(
        experiment_id=experiment_id,
        decision=decision_type,
        reasoning=reasoning,
        confidence=confidence,
        improvement_instructions=improvement_instructions,
        termination_reason=termination_reason,
        potential_ceiling=potential_ceiling,
        priority_rank=priority_rank
    )


def validate_evolution_decisions(
    decisions: List[ExperimentDecision],
    expected_experiment_ids: List[str]
) -> Tuple[bool, List[str]]:
    """
    Validate that evolution decisions cover all expected experiments.

    Args:
        decisions: List of parsed ExperimentDecision objects
        expected_experiment_ids: List of experiment IDs that should have decisions

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    # Get IDs from decisions
    decision_ids = {d.experiment_id for d in decisions}
    expected_ids = set(expected_experiment_ids)

    # Check for missing decisions
    missing = expected_ids - decision_ids
    if missing:
        issues.append(f"Missing decisions for experiments: {sorted(missing)}")

    # Check for extra decisions (not necessarily an error, but worth noting)
    extra = decision_ids - expected_ids
    if extra:
        issues.append(f"Unexpected decisions for experiments: {sorted(extra)}")

    # Check that CONTINUE decisions have improvement_instructions
    for decision in decisions:
        if decision.decision == ExperimentDecisionType.CONTINUE:
            if not decision.improvement_instructions:
                issues.append(f"CONTINUE decision for {decision.experiment_id} missing improvement_instructions")

        if decision.decision == ExperimentDecisionType.TERMINATE:
            if not decision.termination_reason and not decision.reasoning:
                issues.append(f"TERMINATE decision for {decision.experiment_id} missing termination_reason")

    is_valid = len(issues) == 0
    return is_valid, issues


def generate_decision_retry_prompt(issues: List[str], original_output: str) -> str:
    """
    Generate a prompt to retry decision generation when validation fails.

    Args:
        issues: List of validation issues
        original_output: The original PA output that failed validation

    Returns:
        Prompt string for retrying decision generation
    """
    issues_text = "\n".join(f"- {issue}" for issue in issues)

    return f"""Your previous evolution decisions output had validation issues:

{issues_text}

Please provide corrected evolution decisions in the following EXACT YAML format:

```yaml
decisions:
  - experiment_id: "<exact experiment ID>"
    decision: CONTINUE  # or TERMINATE
    confidence: 0.85  # 0.0-1.0
    reasoning: "Why this decision was made"
    improvement_instructions: |  # Required for CONTINUE
      1. First improvement
      2. Second improvement
    potential_ceiling: 0.82  # Optional: estimated max score
    priority_rank: 1  # 1=highest priority

  - experiment_id: "<another experiment ID>"
    decision: TERMINATE
    confidence: 0.90
    reasoning: "Why terminating"
    termination_reason: "Specific reason for termination"
    priority_rank: 3

summary:
  continue_count: <number of CONTINUE decisions>
  terminate_count: <number of TERMINATE decisions>
  new_slots: <same as terminate_count>
```

CRITICAL REQUIREMENTS:
1. Every experiment must have exactly one decision
2. CONTINUE decisions MUST have improvement_instructions
3. TERMINATE decisions SHOULD have termination_reason
4. Confidence must be between 0.0 and 1.0
5. Use exact experiment IDs as provided in the results

Please output ONLY the corrected YAML block."""