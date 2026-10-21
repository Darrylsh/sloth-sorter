"""Folder scanning, file moving, run logging, and undo operations for Sloth Sorter."""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.config import ALLOWED_CATEGORIES, IGNORED_FOLDER_NAMES
from app.safety import ensure_inside_folder, sanitize_category, sanitize_kebab_name

logger = logging.getLogger("sloth_sorter.organizer")


def is_hidden_or_ignored(entry_path: Path, root_path: Path) -> bool:
    """Checks if a path or any of its parent segments within root is hidden or in ignore list."""
    try:
        rel_parts = entry_path.relative_to(root_path).parts
    except ValueError:
        rel_parts = entry_path.parts

    for part in rel_parts:
        if part.startswith(".") and part != ".":
            return True
        if part.lower() in IGNORED_FOLDER_NAMES:
            return True

    # Check Windows hidden file attribute if available
    try:
        import stat
        file_stat = entry_path.stat()
        if hasattr(file_stat, "st_file_attributes"):
            if file_stat.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN:
                return True
    except Exception:
        pass

    return False


def scan_folder_files(folder_path: Path, recursive: bool = False) -> List[Path]:
    """Scans folder for target files to organize.

    - Non-recursive by default.
    - Skips hidden files, directories, .sloth_trash, .sloth_log, and known category folders.
    - Prevents re-sorting files already categorized in previous runs.
    """
    valid_files: List[Path] = []
    category_names_lower = {cat.lower() for cat in ALLOWED_CATEGORIES}

    if not recursive:
        for item in folder_path.iterdir():
            if item.is_file():
                if not is_hidden_or_ignored(item, folder_path):
                    valid_files.append(item)
    else:
        for root, dirs, files in os.walk(folder_path):
            root_dir = Path(root)

            # Filter out ignored dirs in-place so os.walk does not recurse into them
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and d.lower() not in IGNORED_FOLDER_NAMES
                and d.lower() not in category_names_lower
            ]

            for fname in files:
                fpath = root_dir / fname
                if is_hidden_or_ignored(fpath, folder_path):
                    continue

                # Never re-scan files inside an existing category folder
                try:
                    rel_parts = fpath.relative_to(folder_path).parts
                    if len(rel_parts) > 1 and rel_parts[0].lower() in category_names_lower:
                        continue
                except ValueError:
                    pass

                valid_files.append(fpath)

    # Sort files naturally for consistent sequential processing
    valid_files.sort(key=lambda p: p.name.lower())
    return valid_files


def get_unique_destination(target_dir: Path, base_name: str, ext: str) -> Path:
    """Generates a non-conflicting destination path by appending -2, -3, etc. if needed."""
    candidate = target_dir / f"{base_name}{ext}"
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = target_dir / f"{base_name}-{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def apply_organization_plan(
    folder_path: Path,
    plan: List[dict],
    report: Optional[dict] = None
) -> dict:
    """Moves and renames files according to user-approved plan.

    - Strictly keeps files inside folder_path.
    - Never overwrites or deletes.
    - Writes run log to <folder>/.sloth_log/run-<timestamp>.json including optional Sloth Report stats.
    """
    now = datetime.now(timezone.utc)
    run_timestamp = now.strftime("%Y%m%d-%H%M%S")
    run_id = f"run-{run_timestamp}"

    log_dir = folder_path / ".sloth_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{run_id}.json"

    moves_record: List[dict] = []
    created_categories: Set[str] = set()

    for item in plan:
        original_rel = item.get("original")
        new_name_raw = item.get("new_name")
        category_raw = item.get("category", "Other")

        if not original_rel or not new_name_raw:
            continue

        src_path = folder_path / original_rel
        if not src_path.exists() or not src_path.is_file():
            logger.warning(f"File not found to move: {src_path}")
            continue

        # Security check: must be inside folder_path
        ensure_inside_folder(src_path, folder_path)

        category = sanitize_category(category_raw)
        ext = src_path.suffix.lower()
        kebab_name = sanitize_kebab_name(new_name_raw, fallback_original=src_path.stem)

        cat_dir = folder_path / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        created_categories.add(category)

        dst_path = get_unique_destination(cat_dir, kebab_name, ext)
        ensure_inside_folder(dst_path, folder_path)

        # Move file safely
        shutil.move(str(src_path), str(dst_path))

        moves_record.append({
            "source": str(src_path),
            "dest": str(dst_path),
            "source_relative": str(src_path.relative_to(folder_path)).replace("\\", "/"),
            "dest_relative": str(dst_path.relative_to(folder_path)).replace("\\", "/"),
            "original_name": src_path.name,
            "new_name": dst_path.name,
            "category": category
        })

    run_data = {
        "run_id": run_id,
        "timestamp": now.isoformat(),
        "folder_path": str(folder_path),
        "status": "applied",
        "moves_count": len(moves_record),
        "created_categories": list(created_categories),
        "moves": moves_record,
        "report": report or {}
    }

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2)

    return run_data


def list_past_runs(folder_path: Path) -> List[dict]:
    """Retrieves list of past runs recorded in .sloth_log for the folder."""
    log_dir = folder_path / ".sloth_log"
    if not log_dir.exists() or not log_dir.is_dir():
        return []

    runs: List[dict] = []
    for log_path in log_dir.glob("run-*.json"):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    can_undo = True
                    if data.get("status") == "undone":
                        can_undo = False
                    else:
                        for move in data.get("moves", []):
                            if not Path(move["dest"]).exists():
                                can_undo = False
                                break
                    data["can_undo"] = can_undo
                    runs.append(data)
        except Exception as e:
            logger.warning(f"Error reading run log {log_path.name}: {e}")

    runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return runs


def cleanup_empty_folders(folder_path: Path, categories: List[str]):
    """Removes empty category folders if no files or subdirectories remain."""
    for cat in categories:
        cat_dir = folder_path / cat
        if cat_dir.exists() and cat_dir.is_dir():
            try:
                if not any(cat_dir.iterdir()):
                    cat_dir.rmdir()
                    logger.info(f"Cleaned up empty category directory: {cat_dir}")
            except Exception as e:
                logger.warning(f"Failed to remove empty directory {cat_dir}: {e}")


def undo_run(folder_path: Path, run_id: str) -> dict:
    """Reverses all file moves recorded in a given run log and cleans up empty folders."""
    log_dir = folder_path / ".sloth_log"
    log_file = log_dir / f"{run_id}.json"

    if not log_file.exists():
        raise FileNotFoundError(f"Run log not found: {run_id}")

    with open(log_file, "r", encoding="utf-8") as f:
        run_data = json.load(f)

    if run_data.get("status") == "undone":
        return {
            "success": False,
            "message": f"Run {run_id} has already been undone.",
            "reversed_count": 0
        }

    reversed_moves = []
    affected_categories = set(run_data.get("created_categories", []))

    for move in run_data.get("moves", []):
        dest_path = Path(move["dest"])
        src_path = Path(move["source"])

        if dest_path.exists():
            if src_path.exists():
                stem = src_path.stem
                ext = src_path.suffix
                src_path = get_unique_destination(src_path.parent, stem, ext)

            src_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest_path), str(src_path))
            reversed_moves.append({
                "from": str(dest_path),
                "to": str(src_path),
                "filename": src_path.name
            })
            if "category" in move:
                affected_categories.add(move["category"])

    cleanup_empty_folders(folder_path, list(affected_categories))

    run_data["status"] = "undone"
    run_data["undone_at"] = datetime.now(timezone.utc).isoformat()
    run_data["reversed_moves"] = reversed_moves

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(run_data, f, indent=2)

    return {
        "success": True,
        "run_id": run_id,
        "reversed_count": len(reversed_moves),
        "moves": reversed_moves
    }
