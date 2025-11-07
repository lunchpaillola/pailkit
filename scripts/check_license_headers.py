#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Pre-commit hook to check for license headers in Python files.

Checks that Python files start with:
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
import sys
from pathlib import Path


def check_license_header(file_path: Path) -> bool:
    """Check if a file has the required license header."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")

            # Skip empty files
            if not lines or not any(line.strip() for line in lines):
                return True

            # Check for copyright notice (any year) and license text
            has_copyright = False
            has_license = False

            # Look in first 5 lines for the header
            for i, line in enumerate(lines[:5]):
                # Check for copyright with any year (e.g., "Copyright 2025" or "Copyright 2026")
                if "Copyright" in line and "Lunch Pail Labs, LLC" in line:
                    has_copyright = True
                if "Licensed under the Apache License, Version 2.0" in line:
                    has_license = True

            return has_copyright and has_license
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        return False


def main():
    """Check all provided files for license headers."""
    files = sys.argv[1:]

    if not files:
        return 0

    failed_files = []

    for file_path_str in files:
        file_path = Path(file_path_str)

        # Only check Python files
        if not file_path.suffix == ".py":
            continue

        # Skip __pycache__ and test files (optional - you can remove this if you want to check tests)
        if "__pycache__" in str(file_path):
            continue

        if not check_license_header(file_path):
            failed_files.append(file_path)

    if failed_files:
        print("❌ License header check failed for the following files:")
        for file_path in failed_files:
            print(f"  - {file_path}")
        print("\nPlease add the following header to these files:")
        print("# Copyright <YEAR> Lunch Pail Labs, LLC")
        print("# Licensed under the Apache License, Version 2.0")
        print("\nUse 'npm run update:copyright <YEAR>' to update copyright year across all files.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
