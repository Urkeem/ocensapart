"""Validate The Last Cure content asset contracts.

Run from the repository root with: python code/tools/validate_assets.py
"""

from __future__ import annotations

from pathlib import Path
import sys


CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from data.asset_validation import validate_asset_manifest


def main() -> int:
    issues = validate_asset_manifest()
    if issues:
        print(f"Asset validation failed with {len(issues)} issue(s):")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Asset validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
