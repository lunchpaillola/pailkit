#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Script to update copyright year in license headers across the codebase.

Usage:
    python3 scripts/update_copyright_year.py 2026
    python3 scripts/update_copyright_year.py 2026 --dry-run  # Preview changes
"""
import argparse
import re
import sys
from pathlib import Path


def update_copyright_in_file(file_path: Path, new_year: str, dry_run: bool = False) -> bool:
    """Update copyright year in a single file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern to match copyright lines with any year
        # Matches: "Copyright 2025 Lunch Pail Labs, LLC" or "Copyright 2024-2025 Lunch Pail Labs, LLC"
        pattern = r"(Copyright\s+)(\d{4}(?:-\d{4})?)(\s+Lunch Pail Labs, LLC)"

        def replace_year(match):
            return f"{match.group(1)}{new_year}{match.group(3)}"

        new_content = re.sub(pattern, replace_year, content)

        if content != new_content:
            if dry_run:
                print(f"Would update: {file_path}")
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return False


def update_license_file(file_path: Path, new_year: str, dry_run: bool = False) -> bool:
    """Update copyright year in LICENSE file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Pattern for LICENSE file format
        pattern = r"(Copyright\s+)(\d{4})(\s+Lunch Pail Labs, LLC)"

        def replace_year(match):
            return f"{match.group(1)}{new_year}{match.group(3)}"

        new_content = re.sub(pattern, replace_year, content)

        if content != new_content:
            if dry_run:
                print(f"Would update: {file_path}")
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return False


def main():
    """Update copyright year across all files."""
    parser = argparse.ArgumentParser(
        description="Update copyright year in license headers across the codebase"
    )
    parser.add_argument(
        "year",
        type=str,
        help="New copyright year (e.g., 2026)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files"
    )
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="Root directory to search (default: current directory)"
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    new_year = args.year

    if not new_year.isdigit():
        print(f"Error: Year must be numeric (got: {new_year})", file=sys.stderr)
        return 1

    updated_count = 0

    # Update LICENSE file
    license_file = root / "LICENSE"
    if license_file.exists():
        if update_license_file(license_file, new_year, args.dry_run):
            updated_count += 1

    # Update all Python files
    for py_file in root.rglob("*.py"):
        # Skip __pycache__ and virtual environments
        if "__pycache__" in str(py_file) or ".venv" in str(py_file) or "venv" in str(py_file):
            continue

        if update_copyright_in_file(py_file, new_year, args.dry_run):
            updated_count += 1

    # Update JavaScript/TypeScript files if they exist
    for js_file in root.rglob("*.{js,ts,jsx,tsx}"):
        # Skip node_modules
        if "node_modules" in str(js_file):
            continue

        if update_copyright_in_file(js_file, new_year, args.dry_run):
            updated_count += 1

    if args.dry_run:
        print(f"\n✨ Would update {updated_count} file(s)")
        print("Run without --dry-run to apply changes")
    else:
        print(f"\n✅ Updated {updated_count} file(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
