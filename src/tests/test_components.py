#!/usr/bin/env python3
"""
Test script to validate three core components of AutoKaggle:
1. System Detection
2. Dataset Analysis
3. Prompt Filling

Tests across four different competition types:
- Titanic (Binary Classification)
- House Prices (Regression)
- NFL Big Data Bowl (Analytics/Non-standard)
- Cotton Weed Detection (Computer Vision)
"""

import os
import sys
import json
import re
from pathlib import Path

# Add project root to path
# Go up two levels from src/tests to get to the project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.utils.system_specs import SystemSpecsDetector
from src.utils.dataset_analyzer import DatasetAnalyzer
from src.utils.prompt_filler import PromptFiller


def test_system_detection():
    """Test system specifications detection."""
    print("=" * 80)
    print("TESTING SYSTEM DETECTION")
    print("=" * 80)

    try:
        detector = SystemSpecsDetector()
        specs = detector.get_specs()
        placeholders = detector.get_prompt_placeholders()

        print("\n=== SYSTEM SPECIFICATIONS ===")
        print(detector.to_markdown())

        print("\n=== PROMPT PLACEHOLDERS ===")
        for key, value in placeholders.items():
            print(f"  {key}: {value}")

        print("\n✅ System detection completed successfully")
        return specs, placeholders

    except Exception as e:
        print(f"\n❌ System detection failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def test_dataset_analysis():
    """Test dataset analysis for each competition."""
    print("\n" + "=" * 80)
    print("TESTING DATASET ANALYSIS")
    print("=" * 80)

    competitions = [
        ("titanic", "kaggle_competitions/titanic/data"),
        ("house-prices", "kaggle_competitions/house-prices-advanced-regression-techniques/data"),
        ("nfl", "kaggle_competitions/nfl-big-data-bowl-2026-analytics/data"),
        ("cotton-weed", "kaggle_competitions/the-3lc-cotton-weed-detection-challenge/data")
    ]

    results = {}

    for comp_name, data_path in competitions:
        print(f"\n{'=' * 40}")
        print(f"ANALYZING: {comp_name.upper()}")
        print('=' * 40)

        full_path = os.path.join(project_root, data_path)

        if not os.path.exists(full_path):
            print(f"⚠️  Data directory not found: {full_path}")
            results[comp_name] = None
            continue

        try:
            analyzer = DatasetAnalyzer(comp_name, full_path)
            analysis = analyzer.analyze_competition_data()
            placeholders = analyzer.get_prompt_placeholders()

            # Display key results
            print(f"Competition Type: {placeholders.get('competition_type', 'Unknown')}")
            print(f"Train Size: {placeholders.get('train_size', 'N/A')}")
            print(f"Test Size: {placeholders.get('test_size', 'N/A')}")
            print(f"Features: {placeholders.get('feature_count', 'N/A')} "
                  f"(Numeric: {placeholders.get('numeric_count', 'N/A')}, "
                  f"Categorical: {placeholders.get('categorical_count', 'N/A')})")
            print(f"Target Variable: {placeholders.get('target_variable', 'N/A')}")
            print(f"Target Distribution: {placeholders.get('target_distribution', 'N/A')}")
            print(f"Missing Data: {placeholders.get('missing_data_summary', 'N/A')}")
            print(f"Unique Characteristics: {placeholders.get('unique_characteristics', 'N/A')}")

            # Check for fallback values
            fallback_count = sum(1 for v in placeholders.values() if isinstance(v, str) and '[ASSUMED' in str(v))
            if fallback_count > 0:
                print(f"⚠️  {fallback_count} fields using fallback [ASSUMED] values")

            print(f"✅ Dataset analysis completed for {comp_name}")
            results[comp_name] = placeholders

        except Exception as e:
            print(f"❌ Dataset analysis failed for {comp_name}: {e}")
            import traceback
            traceback.print_exc()
            results[comp_name] = None

    return results


def test_prompt_filling(system_specs, dataset_analyses):
    """Test prompt filling for each competition."""
    print("\n" + "=" * 80)
    print("TESTING PROMPT FILLING")
    print("=" * 80)

    if not system_specs:
        print("❌ Cannot test prompt filling without system specs")
        return

    # Competition configurations
    competitions = [
        ("titanic", "Accuracy", "Binary Classification"),
        ("house-prices", "RMSE", "Regression"),
        ("nfl", "Custom Analytics", "Analytics"),
        ("cotton-weed", "mAP@0.5", "Object Detection")
    ]

    try:
        # Initialize prompt filler with path relative to project root
        prompts_path = os.path.join(project_root, "prompts/KSE")
        prompt_filler = PromptFiller(prompts_dir=prompts_path)
        print("✅ Prompt templates loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load prompt templates: {e}")
        return

    for comp_name, metric, comp_type in competitions:
        print(f"\n{'=' * 40}")
        print(f"PROMPT FILLING FOR: {comp_name.upper()}")
        print('=' * 40)

        try:
            # Get dataset analysis or use defaults
            if dataset_analyses and comp_name in dataset_analyses and dataset_analyses[comp_name]:
                dataset_analysis = dataset_analyses[comp_name]
            else:
                print("⚠️  Using default dataset placeholders (analysis not available)")
                dataset_analysis = {
                    "train_size": "[ASSUMED: 1000]",
                    "test_size": "[ASSUMED: 500]",
                    "feature_count": "[ASSUMED: 20]",
                    "numeric_count": "[ASSUMED: 10]",
                    "categorical_count": "[ASSUMED: 10]",
                    "target_variable": "[ASSUMED: target]",
                    "competition_type": f"[ASSUMED: {comp_type}]",
                    "target_distribution": "[ASSUMED: unknown]",
                    "class_distribution": "[ASSUMED: balanced]",
                    "missing_data_summary": "[ASSUMED: no missing data]",
                    "unique_characteristics": "[ASSUMED: standard dataset]",
                    "temporal_or_cross_sectional": "[ASSUMED: cross-sectional]"
                }

            # Prepare competition info
            competition_info = {
                "name": comp_name,
                "evaluation_metric": metric,
                "submission_format": "csv with id and prediction columns"
            }

            # Mock community insights (in real usage, would come from crawler)
            community_insights = {
                "winning_approaches": ["Baseline approach", "Feature engineering focus"],
                "benchmarks": {"baseline": 0.75, "top": 0.85},
                "common_pitfalls": ["Overfitting on small dataset"],
                "recommended_techniques": ["Cross-validation", "Ensemble methods"],
                "domain_knowledge": "Standard ML competition",
                "ceiling_score": 0.95
            }

            # Fill initial iteration prompt
            filled_prompt = prompt_filler.fill_initial_prompt(
                competition_info=competition_info,
                dataset_analysis=dataset_analysis,
                system_specs=system_specs,
                community_insights=community_insights,
                num_hypotheses=3
            )

            # Analyze filled prompt
            print(f"Prompt length: {len(filled_prompt):,} characters")

            # Check for unfilled placeholders (excluding code examples in backticks)
            # Remove code blocks first
            prompt_without_code = re.sub(r'```[\s\S]*?```', '', filled_prompt)
            # Look for remaining placeholders
            remaining = re.findall(r'\{([^}]+)\}', prompt_without_code)
            # Filter out likely template examples
            actual_placeholders = [p for p in remaining if not any(x in p for x in ['hypothesis_id', 'exp_id', 'feature_', 'param_', 'X', 'Y'])]

            print(f"Potential unfilled placeholders: {len(actual_placeholders)}")
            if actual_placeholders[:5]:  # Show first 5 if any
                print(f"  Examples: {actual_placeholders[:5]}")

            # Count [ASSUMED] markers
            assumed_count = len(re.findall(r'\[ASSUMED[^\]]*\]', filled_prompt))
            print(f"Fallback [ASSUMED] values used: {assumed_count}")

            # Save filled prompt for inspection in the tests directory
            output_path = os.path.join(os.path.dirname(__file__), f"test_output_{comp_name}_prompt.md")
            with open(output_path, "w") as f:
                f.write(filled_prompt)
            print(f"✅ Filled prompt saved to: test_output_{comp_name}_prompt.md")

            # Verify key sections are present
            key_sections = [
                "Competition Context",
                "Dataset Echo-Back",
                "Cross-Validation Selection Matrix",
                "Hypothesis Generation Requirements",
                "Output Template"
            ]

            missing_sections = []
            for section in key_sections:
                if section not in filled_prompt:
                    missing_sections.append(section)

            if missing_sections:
                print(f"⚠️  Missing sections: {missing_sections}")
            else:
                print("✅ All key sections present")

        except Exception as e:
            print(f"❌ Prompt filling failed for {comp_name}: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Run all component tests."""
    print("=" * 80)
    print("AUTOKAGGLE COMPONENT TESTING")
    print("=" * 80)
    print("\nTesting three core components:")
    print("1. System Detection")
    print("2. Dataset Analysis")
    print("3. Prompt Filling")
    print("\nAcross four competition types:")
    print("- Titanic (Binary Classification)")
    print("- House Prices (Regression)")
    print("- NFL Big Data Bowl (Analytics)")
    print("- Cotton Weed Detection (Computer Vision)")

    # Test 1: System Detection
    system_specs, system_placeholders = test_system_detection()

    # Test 2: Dataset Analysis
    dataset_analyses = test_dataset_analysis()

    # Test 3: Prompt Filling
    test_prompt_filling(system_placeholders, dataset_analyses)

    # Summary
    print("\n" + "=" * 80)
    print("TESTING SUMMARY")
    print("=" * 80)

    if system_specs:
        print("✅ System Detection: PASSED")
    else:
        print("❌ System Detection: FAILED")

    if dataset_analyses:
        successful = sum(1 for v in dataset_analyses.values() if v is not None)
        total = len(dataset_analyses)
        print(f"📊 Dataset Analysis: {successful}/{total} competitions analyzed")
        for comp, result in dataset_analyses.items():
            status = "✅" if result else "❌"
            print(f"   {status} {comp}")
    else:
        print("❌ Dataset Analysis: FAILED")

    # Check if prompt files were created in the tests directory
    tests_dir = Path(os.path.dirname(__file__))
    prompt_files = list(tests_dir.glob('test_output_*_prompt.md'))
    if prompt_files:
        print(f"📝 Prompt Filling: {len(prompt_files)} prompts generated")
        for pf in prompt_files:
            print(f"   ✅ {pf.name}")
    else:
        print("❌ Prompt Filling: No prompts generated")

    print("\n" + "=" * 80)
    print("Testing complete. Review the output files for detailed results.")
    print("=" * 80)


if __name__ == "__main__":
    main()