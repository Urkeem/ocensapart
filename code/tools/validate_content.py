"""Command-line content, dependency, asset, and balance validation."""

from pathlib import Path
import sys


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from data.content_validation import validate_all_content


def main():
    issues = validate_all_content()
    if issues:
        for issue in issues:
            print(issue)
        return 1
    print("Content validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
