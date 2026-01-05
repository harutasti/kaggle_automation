import argparse
from pathlib import Path

from src.utils.submission_validator import validate_submission


def validate(submission_path: str, run_dir: str | None) -> int:
    ok, reason = validate_submission(
        competition_name="santa-2025",
        submission_path=submission_path,
        experiment_run_dir=run_dir,
    )
    if ok:
        print("OK: submission is valid")
        return 0
    print(f"INVALID: {reason}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="santa-2025 competition helper")
    parser.add_argument("--submission", required=True, help="Path to submission CSV")
    parser.add_argument("--run-dir", default=None, help="Experiment run dir for validator context")
    args = parser.parse_args()

    submission_path = str(Path(args.submission))
    return validate(submission_path, args.run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
