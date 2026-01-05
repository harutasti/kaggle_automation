from __future__ import annotations

import argparse
import sys

from ..utils.submission_validator import validate_submission


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Kaggle submission files.")
    parser.add_argument("--competition", required=True, help="Competition name (e.g., santa-2025)")
    parser.add_argument("--submission", required=True, help="Path to submission CSV")
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Experiment run directory (optional; used to locate kaggle_data)",
    )
    args = parser.parse_args(argv)

    ok, reason = validate_submission(
        competition_name=args.competition,
        submission_path=args.submission,
        experiment_run_dir=args.run_dir,
    )

    if ok:
        print("VALID")
        return 0

    print(f"INVALID: {reason}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
