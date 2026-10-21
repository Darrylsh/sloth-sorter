#!/usr/bin/env python3
"""Safe test helper: Copies sample files from a real user directory into real_test/

NEVER moves or alters source files. Only reads and copies up to N files.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def make_real_test_copy(source_dir: Path, count: int = 40, dest_dir: Path = None) -> list[Path]:
    if dest_dir is None:
        dest_dir = Path("real_test").resolve()

    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError(f"Source folder does not exist or is not a directory: {source_dir}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Destination folder ready: {dest_dir}")
    print(f"Scanning top-level files in: {source_dir}")

    copied_files: list[Path] = []
    skipped_large: list[tuple[str, int]] = []
    skipped_hidden: list[str] = []

    # Iterate over top-level files only
    for entry in source_dir.iterdir():
        if len(copied_files) >= count:
            break

        # Skip directories
        if not entry.is_file():
            continue

        # Skip hidden files
        if entry.name.startswith("."):
            skipped_hidden.append(entry.name)
            continue

        # Check Windows hidden attribute if on Windows
        if sys.platform == "win32":
            try:
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(str(entry))
                if attrs != -1 and (attrs & 2):  # FILE_ATTRIBUTE_HIDDEN = 2
                    skipped_hidden.append(entry.name)
                    continue
            except Exception:
                pass

        # Check file size (skip files > 20MB)
        try:
            size = entry.stat().st_size
            if size > MAX_FILE_SIZE_BYTES:
                skipped_large.append((entry.name, size))
                continue
        except Exception:
            continue

        dest_file = dest_dir / entry.name
        try:
            shutil.copy2(entry, dest_file)
            copied_files.append(dest_file)
            print(f"  [{len(copied_files):02d}/{count}] Copied: {entry.name} ({size / 1024:.1f} KB)")
        except Exception as e:
            print(f"  [ERROR] Failed to copy {entry.name}: {e}")

    print("\nSummary:")
    print(f"  Total files copied : {len(copied_files)}")
    if skipped_large:
        print(f"  Skipped (>20MB)    : {len(skipped_large)} files")
        for name, size in skipped_large[:5]:
            print(f"    - {name} ({size / (1024*1024):.1f} MB)")
    if skipped_hidden:
        print(f"  Skipped hidden     : {len(skipped_hidden)} files")

    return copied_files


def main():
    parser = argparse.ArgumentParser(
        description="Safely copies top-level files from a folder into real_test/ without modifying the source."
    )
    parser.add_argument("source", type=str, help="Source directory path containing real files")
    parser.add_argument(
        "--count", "-n", type=int, default=40, help="Maximum number of files to copy (default: 40)"
    )
    parser.add_argument(
        "--dest", "-d", type=str, default="real_test", help="Destination folder (default: real_test)"
    )

    args = parser.parse_args()
    source_path = Path(args.source).expanduser().resolve()
    dest_path = Path(args.dest).expanduser().resolve()

    try:
        make_real_test_copy(source_path, count=args.count, dest_dir=dest_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
