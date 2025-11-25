"""
Parser for PA (Performance Analyzer) Codex output.

Parses structured markdown output from PA Codex into the AnalysisResult data model.
"""

import re
import logging
from typing import Dict, List, Any, Optional

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