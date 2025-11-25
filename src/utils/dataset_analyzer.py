"""
Dataset Analyzer Module

Analyzes competition datasets to extract statistics and metadata
for filling KSE prompt placeholders.
"""

import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DatasetAnalyzer:
    """Analyzes competition datasets to extract key statistics and metadata."""

    def __init__(self, competition_name: str, data_dir: str):
        """
        Initialize the dataset analyzer.

        Args:
            competition_name: Name of the competition
            data_dir: Directory containing the competition data files
        """
        self.competition_name = competition_name
        self.data_dir = Path(data_dir)
        self.train_data = None
        self.test_data = None
        self.sample_submission = None

    def analyze_competition_data(self) -> Dict[str, Any]:
        """
        Analyze the competition data and return comprehensive statistics.

        Returns:
            Dictionary containing all dataset statistics and metadata
        """
        logger.info(f"Analyzing competition data for: {self.competition_name}")

        # Load data files
        self._load_data_files()

        # Prepare results dictionary
        analysis = {
            "competition_name": self.competition_name,
            "data_files": self._get_data_files(),
            "dataset_stats": {},
            "feature_analysis": {},
            "target_analysis": {},
            "missing_data": {},
            "data_quality": {}
        }

        if self.train_data is not None:
            analysis["dataset_stats"] = self._analyze_dataset_stats()
            analysis["feature_analysis"] = self._analyze_features()
            analysis["target_analysis"] = self._analyze_target()
            analysis["missing_data"] = self._analyze_missing_data()
            analysis["data_quality"] = self._analyze_data_quality()
        else:
            logger.warning("No training data found for analysis")

        return analysis

    def _load_data_files(self) -> None:
        """Load the main data files (train, test, sample_submission)."""
        train_path = self.data_dir / "train.csv"
        test_path = self.data_dir / "test.csv"
        submission_path = self.data_dir / "sample_submission.csv"

        # Try loading training data
        if train_path.exists():
            try:
                self.train_data = pd.read_csv(train_path)
                logger.info(f"Loaded train.csv: {self.train_data.shape}")
            except Exception as e:
                logger.error(f"Failed to load train.csv: {e}")

        # Try loading test data
        if test_path.exists():
            try:
                self.test_data = pd.read_csv(test_path)
                logger.info(f"Loaded test.csv: {self.test_data.shape}")
            except Exception as e:
                logger.error(f"Failed to load test.csv: {e}")

        # Try loading sample submission
        if submission_path.exists():
            try:
                self.sample_submission = pd.read_csv(submission_path)
                logger.info(f"Loaded sample_submission.csv: {self.sample_submission.shape}")
            except Exception as e:
                logger.error(f"Failed to load sample_submission.csv: {e}")

    def _get_data_files(self) -> List[str]:
        """Get list of all data files in the competition directory."""
        data_files = []
        for file_path in self.data_dir.iterdir():
            if file_path.is_file():
                file_info = {
                    "name": file_path.name,
                    "size_mb": file_path.stat().st_size / (1024 * 1024),
                    "extension": file_path.suffix
                }
                data_files.append(file_info)
        return data_files

    def _analyze_dataset_stats(self) -> Dict[str, Any]:
        """Analyze basic dataset statistics."""
        stats = {
            "train_size": len(self.train_data) if self.train_data is not None else 0,
            "test_size": len(self.test_data) if self.test_data is not None else 0,
            "feature_count": len(self.train_data.columns) - 1 if self.train_data is not None else 0,
            "train_columns": list(self.train_data.columns) if self.train_data is not None else [],
            "test_columns": list(self.test_data.columns) if self.test_data is not None else [],
            "memory_usage_mb": self.train_data.memory_usage(deep=True).sum() / (1024 * 1024) if self.train_data is not None else 0
        }

        # Identify common columns (features) between train and test
        if self.train_data is not None and self.test_data is not None:
            common_cols = set(self.train_data.columns) & set(self.test_data.columns)
            stats["common_features"] = list(common_cols)
            stats["train_only_columns"] = list(set(self.train_data.columns) - set(self.test_data.columns))

        return stats

    def _analyze_features(self) -> Dict[str, Any]:
        """Analyze feature types and characteristics."""
        if self.train_data is None:
            return {}

        feature_info = {
            "numeric_features": [],
            "categorical_features": [],
            "datetime_features": [],
            "text_features": [],
            "numeric_count": 0,
            "categorical_count": 0,
            "feature_details": {}
        }

        for col in self.train_data.columns:
            dtype = str(self.train_data[col].dtype)
            unique_count = self.train_data[col].nunique()
            missing_count = self.train_data[col].isnull().sum()

            col_info = {
                "dtype": dtype,
                "unique_values": unique_count,
                "missing_count": missing_count,
                "missing_percent": (missing_count / len(self.train_data)) * 100
            }

            # Classify feature type
            if dtype in ['int64', 'float64', 'int32', 'float32']:
                feature_info["numeric_features"].append(col)
                # Additional numeric statistics
                col_info["mean"] = self.train_data[col].mean()
                col_info["std"] = self.train_data[col].std()
                col_info["min"] = self.train_data[col].min()
                col_info["max"] = self.train_data[col].max()
                col_info["skewness"] = self.train_data[col].skew()
                col_info["kurtosis"] = self.train_data[col].kurtosis()
            elif dtype == 'object':
                # Check if it might be datetime
                sample = self.train_data[col].dropna().head(5)
                if self._is_datetime_column(col):
                    feature_info["datetime_features"].append(col)
                elif unique_count < len(self.train_data) * 0.5:  # Less than 50% unique
                    feature_info["categorical_features"].append(col)
                    # Top categories for categorical features
                    if unique_count <= 20:
                        col_info["value_counts"] = self.train_data[col].value_counts().to_dict()
                else:
                    feature_info["text_features"].append(col)
            elif dtype == 'bool':
                feature_info["categorical_features"].append(col)
                col_info["value_counts"] = self.train_data[col].value_counts().to_dict()

            feature_info["feature_details"][col] = col_info

        feature_info["numeric_count"] = len(feature_info["numeric_features"])
        feature_info["categorical_count"] = len(feature_info["categorical_features"])

        return feature_info

    def _is_datetime_column(self, col_name: str) -> bool:
        """Check if a column might be datetime based on name and content."""
        datetime_keywords = ['date', 'time', 'year', 'month', 'day', 'hour', 'minute']
        col_lower = col_name.lower()

        # Check column name
        if any(keyword in col_lower for keyword in datetime_keywords):
            return True

        # Try parsing a sample
        if self.train_data is not None:
            try:
                sample = self.train_data[col_name].dropna().head(10)
                if len(sample) > 0:
                    pd.to_datetime(sample, errors='coerce')
                    return True
            except:
                pass

        return False

    def _analyze_target(self) -> Dict[str, Any]:
        """Analyze target variable (if identifiable)."""
        if self.train_data is None or self.sample_submission is None:
            return {}

        # Identify target column
        submission_cols = list(self.sample_submission.columns)
        id_cols = [col for col in submission_cols if 'id' in col.lower()]
        target_cols = [col for col in submission_cols if col not in id_cols]

        if not target_cols:
            return {}

        target_col = target_cols[0]  # Assume first non-ID column is target

        # Check if target exists in train data
        if target_col not in self.train_data.columns:
            return {"target_variable": target_col, "target_in_train": False}

        target_data = self.train_data[target_col]

        target_info = {
            "target_variable": target_col,
            "target_in_train": True,
            "target_dtype": str(target_data.dtype),
            "unique_values": target_data.nunique()
        }

        # Determine if classification or regression
        if target_data.dtype in ['int64', 'int32', 'bool']:
            if target_data.nunique() <= 20:  # Likely classification
                target_info["problem_type"] = "classification"
                target_info["class_distribution"] = target_data.value_counts().to_dict()
                target_info["class_balance"] = self._calculate_class_balance(target_data)
                target_info["num_classes"] = target_data.nunique()
            else:
                target_info["problem_type"] = "regression"
                target_info["target_stats"] = {
                    "mean": float(target_data.mean()),
                    "std": float(target_data.std()),
                    "min": float(target_data.min()),
                    "max": float(target_data.max()),
                    "skewness": float(target_data.skew()),
                    "kurtosis": float(target_data.kurtosis())
                }
        elif target_data.dtype in ['float64', 'float32']:
            target_info["problem_type"] = "regression"
            target_info["target_stats"] = {
                "mean": float(target_data.mean()),
                "std": float(target_data.std()),
                "min": float(target_data.min()),
                "max": float(target_data.max()),
                "skewness": float(target_data.skew()),
                "kurtosis": float(target_data.kurtosis())
            }
        else:
            target_info["problem_type"] = "unknown"

        return target_info

    def _calculate_class_balance(self, target_data: pd.Series) -> Dict[str, float]:
        """Calculate class balance metrics."""
        value_counts = target_data.value_counts()
        total = len(target_data)

        balance_info = {
            "class_percentages": {str(k): (v/total)*100 for k, v in value_counts.items()},
            "imbalance_ratio": float(value_counts.max() / value_counts.min()),
            "minority_class": str(value_counts.idxmin()),
            "majority_class": str(value_counts.idxmax()),
            "is_imbalanced": (value_counts.min() / total) < 0.3  # Less than 30% is considered imbalanced
        }

        return balance_info

    def _analyze_missing_data(self) -> Dict[str, Any]:
        """Analyze missing data patterns."""
        if self.train_data is None:
            return {}

        missing_info = {
            "total_missing_values": int(self.train_data.isnull().sum().sum()),
            "columns_with_missing": {},
            "missing_pattern": "none"
        }

        for col in self.train_data.columns:
            missing_count = self.train_data[col].isnull().sum()
            if missing_count > 0:
                missing_percent = (missing_count / len(self.train_data)) * 100
                missing_info["columns_with_missing"][col] = {
                    "count": int(missing_count),
                    "percent": float(missing_percent),
                    "severity": self._classify_missing_severity(missing_percent)
                }

        # Determine overall missing data pattern
        if not missing_info["columns_with_missing"]:
            missing_info["missing_pattern"] = "none"
        elif len(missing_info["columns_with_missing"]) < 5:
            missing_info["missing_pattern"] = "sparse"
        elif any(v["percent"] > 50 for v in missing_info["columns_with_missing"].values()):
            missing_info["missing_pattern"] = "severe"
        else:
            missing_info["missing_pattern"] = "moderate"

        # Summary statistics
        if missing_info["columns_with_missing"]:
            missing_percents = [v["percent"] for v in missing_info["columns_with_missing"].values()]
            missing_info["missing_summary"] = {
                "num_columns_with_missing": len(missing_info["columns_with_missing"]),
                "avg_missing_percent": float(np.mean(missing_percents)),
                "max_missing_percent": float(max(missing_percents)),
                "min_missing_percent": float(min(missing_percents))
            }
        else:
            missing_info["missing_summary"] = {
                "num_columns_with_missing": 0,
                "avg_missing_percent": 0.0,
                "max_missing_percent": 0.0,
                "min_missing_percent": 0.0
            }

        return missing_info

    def _classify_missing_severity(self, missing_percent: float) -> str:
        """Classify the severity of missing data."""
        if missing_percent == 0:
            return "none"
        elif missing_percent < 5:
            return "low"
        elif missing_percent < 20:
            return "moderate"
        elif missing_percent < 50:
            return "high"
        else:
            return "severe"

    def _analyze_data_quality(self) -> Dict[str, Any]:
        """Analyze overall data quality indicators."""
        if self.train_data is None:
            return {}

        quality_info = {
            "has_duplicates": bool(self.train_data.duplicated().any()),
            "duplicate_count": int(self.train_data.duplicated().sum()),
            "constant_columns": [],
            "highly_correlated_features": [],
            "potential_leakage_features": []
        }

        # Find constant columns
        for col in self.train_data.columns:
            if self.train_data[col].nunique() == 1:
                quality_info["constant_columns"].append(col)

        # Find highly correlated numeric features
        numeric_cols = self.train_data.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) > 1:
            corr_matrix = self.train_data[numeric_cols].corr().abs()
            upper_triangle = corr_matrix.where(
                np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
            )

            high_corr_pairs = []
            for col in upper_triangle.columns:
                for row in upper_triangle.index:
                    if upper_triangle.loc[row, col] > 0.95:  # Very high correlation
                        high_corr_pairs.append({
                            "feature1": row,
                            "feature2": col,
                            "correlation": float(upper_triangle.loc[row, col])
                        })

            quality_info["highly_correlated_features"] = high_corr_pairs

        # Identify potential data leakage (features with suspiciously high correlation to target)
        target_info = self._analyze_target()
        if target_info and "target_variable" in target_info and target_info["target_in_train"]:
            target_col = target_info["target_variable"]
            if target_col in numeric_cols:
                for col in numeric_cols:
                    if col != target_col:
                        corr_with_target = abs(self.train_data[col].corr(self.train_data[target_col]))
                        if corr_with_target > 0.99:  # Suspiciously high correlation
                            quality_info["potential_leakage_features"].append({
                                "feature": col,
                                "correlation_with_target": float(corr_with_target)
                            })

        return quality_info

    def get_prompt_placeholders(self) -> Dict[str, Any]:
        """
        Get all placeholder values for KSE prompts.

        Returns:
            Dictionary with keys matching prompt placeholders
        """
        analysis = self.analyze_competition_data()

        # Prepare placeholder values
        placeholders = {
            "competition_name": self.competition_name,
            "train_size": analysis["dataset_stats"].get("train_size", "[ASSUMED: 1000]"),
            "test_size": analysis["dataset_stats"].get("test_size", "[ASSUMED: 500]"),
            "feature_count": analysis["dataset_stats"].get("feature_count", "[ASSUMED: 20]"),
            "numeric_count": analysis["feature_analysis"].get("numeric_count", "[ASSUMED: 10]"),
            "categorical_count": analysis["feature_analysis"].get("categorical_count", "[ASSUMED: 10]")
        }

        # Target variable information
        if analysis["target_analysis"]:
            placeholders["target_variable"] = analysis["target_analysis"].get("target_variable", "[ASSUMED: target]")
            placeholders["competition_type"] = analysis["target_analysis"].get("problem_type", "[ASSUMED: classification]")

            if "class_distribution" in analysis["target_analysis"]:
                placeholders["target_distribution"] = str(analysis["target_analysis"]["class_distribution"])
                placeholders["class_distribution"] = analysis["target_analysis"]["class_balance"]["class_percentages"]
            elif "target_stats" in analysis["target_analysis"]:
                placeholders["target_distribution"] = f"Mean: {analysis['target_analysis']['target_stats']['mean']:.2f}, Std: {analysis['target_analysis']['target_stats']['std']:.2f}"
                placeholders["class_distribution"] = "[ASSUMED: N/A for regression]"
            else:
                placeholders["target_distribution"] = "[ASSUMED: unknown distribution]"
                placeholders["class_distribution"] = "[ASSUMED: balanced]"
        else:
            placeholders["target_variable"] = "[ASSUMED: target]"
            placeholders["competition_type"] = "[ASSUMED: classification]"
            placeholders["target_distribution"] = "[ASSUMED: unknown distribution]"
            placeholders["class_distribution"] = "[ASSUMED: balanced]"

        # Missing data summary
        if analysis["missing_data"] and "missing_summary" in analysis["missing_data"]:
            missing = analysis["missing_data"]["missing_summary"]
            placeholders["missing_data_summary"] = f"{missing['num_columns_with_missing']} columns with missing data, avg {missing['avg_missing_percent']:.1f}% missing"
        else:
            placeholders["missing_data_summary"] = "[ASSUMED: no missing data]"

        # Unique characteristics
        characteristics = []
        if analysis["data_quality"].get("has_duplicates"):
            characteristics.append(f"{analysis['data_quality']['duplicate_count']} duplicate rows")
        if analysis["data_quality"].get("constant_columns"):
            characteristics.append(f"{len(analysis['data_quality']['constant_columns'])} constant features")
        if analysis["data_quality"].get("potential_leakage_features"):
            characteristics.append("potential data leakage detected")

        placeholders["unique_characteristics"] = "; ".join(characteristics) if characteristics else "standard tabular dataset"

        # Data collection type (heuristic based on features)
        if any("time" in col.lower() or "date" in col.lower() for col in analysis["dataset_stats"].get("train_columns", [])):
            placeholders["temporal_or_cross_sectional"] = "temporal"
        else:
            placeholders["temporal_or_cross_sectional"] = "cross-sectional"

        return placeholders