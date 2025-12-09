#!/usr/bin/env python3
"""
Rename CSV files from old naming scheme to new.

SN217993_CAN_2025_11_12_0819_0.csv -> CAN_TMS_SN217993_2025-11-12T08:19:00.000Z.csv
"""

import os
import re
import shutil
import argparse
from pathlib import Path


def parse_source_filename(filename: str) -> dict | None:
    """Parse filename into components. Returns None if it doesn't match."""
    # Remove .csv extension
    name = filename.rsplit('.', 1)[0]

    # Pattern: VEHICLE_ID_DATA_TYPE_YEAR_MONTH_DAY_TIME_INCREMENT
    # VEHICLE_ID can contain letters and numbers
    # DATA_TYPE can contain letters and numbers
    # TIME is 4 digits (HHMM)
    pattern = r'^([A-Za-z0-9]+)_([A-Za-z0-9]+)_(\d{4})_(\d{2})_(\d{2})_(\d{4})_(\d+)$'

    match = re.match(pattern, name)
    if not match:
        return None

    vehicle_id, data_type, year, month, day, time_str, increment = match.groups()

    # Extract hours and minutes from time (format: HHMM)
    hours = time_str[:2]
    minutes = time_str[2:]

    return {
        'vehicle_id': vehicle_id,
        'data_type': data_type,
        'year': year,
        'month': month,
        'day': day,
        'hours': hours,
        'minutes': minutes,
        'increment': int(increment)
    }


def create_target_filename(parsed: dict) -> str:
    """Build the new filename from parsed components."""
    # Build ISO 8601 timestamp
    # Seconds and milliseconds are unknown, so we use 00 and 000
    timestamp = (
        f"{parsed['year']}-{parsed['month']}-{parsed['day']}T"
        f"{parsed['hours']}:{parsed['minutes']}:00.000Z"
    )

    return f"{parsed['data_type']}_TMS_{parsed['vehicle_id']}_{timestamp}.csv"


def rename_csvs(source_dir: str, output_dir: str | None = None, dry_run: bool = False) -> None:
    """Move CSVs from source_dir to output_dir with new names."""
    source_path = Path(source_dir).resolve()

    if not source_path.exists():
        print(f"Error: Source directory does not exist: {source_path}")
        return

    if not source_path.is_dir():
        print(f"Error: Source path is not a directory: {source_path}")
        return

    # Use provided output directory or default to 'renamed' next to this script
    if output_dir:
        renamed_dir = Path(output_dir).resolve()
    else:
        script_dir = Path(__file__).parent.resolve()
        renamed_dir = script_dir / "renamed"

    if not dry_run:
        renamed_dir.mkdir(exist_ok=True)

    # Find all CSV files in source directory and subdirectories
    csv_files = list(source_path.glob("**/*.csv"))

    if not csv_files:
        print(f"No CSV files found in: {source_path}")
        return

    print(f"Found {len(csv_files)} CSV file(s) in: {source_path}")
    print(f"Target directory: {renamed_dir}")
    print()

    success_count = 0
    error_count = 0

    for csv_file in sorted(csv_files):
        filename = csv_file.name
        parsed = parse_source_filename(filename)

        if parsed is None:
            print(f"  SKIP: {filename} (doesn't match expected pattern)")
            error_count += 1
            continue

        new_filename = create_target_filename(parsed)
        target_path = renamed_dir / new_filename

        if dry_run:
            print(f"  [DRY RUN] {filename}")
            print(f"         -> {new_filename}")
        else:
            try:
                shutil.move(str(csv_file), str(target_path))
                print(f"  MOVED: {filename}")
                print(f"      -> {new_filename}")
                success_count += 1
            except Exception as e:
                print(f"  ERROR: {filename} - {e}")
                error_count += 1

    print()
    if dry_run:
        print(f"Dry run complete. {len(csv_files)} file(s) would be processed.")
    else:
        print(f"Complete. {success_count} file(s) moved, {error_count} error(s)/skipped.")


def main():
    parser = argparse.ArgumentParser(
        description="Rename and move CSV files to standardized format."
    )
    parser.add_argument(
        "source_dir",
        help="Source directory containing CSV files to rename"
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory for renamed files (default: 'renamed' next to script)"
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be done without actually moving files"
    )

    args = parser.parse_args()
    rename_csvs(args.source_dir, args.output_dir, args.dry_run)


if __name__ == "__main__":
    main()
