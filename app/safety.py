"""Path sanitization, safety checks, and traversal protection for Sloth Sorter."""
import os
import re
import unicodedata
from pathlib import Path
from typing import Tuple
from app.config import ALLOWED_CATEGORIES, MAX_FILENAME_LENGTH


def validate_and_resolve_folder(raw_path: str) -> Path:
    """Validates that raw_path exists, is a directory, and resolves it to a canonical absolute Path.

    Handles Windows edge cases: quotes, backslashes, trailing slashes, spaces.
    """
    if not raw_path or not str(raw_path).strip():
        raise ValueError("Folder path cannot be empty.")

    cleaned_str = str(raw_path).strip().strip('"').strip("'")
    # Strip any trailing slashes/backslashes (except root like C:\)
    if len(cleaned_str) > 3:
        cleaned_str = cleaned_str.rstrip("\\/")

    path_obj = Path(cleaned_str).expanduser()

    if not path_obj.is_absolute():
        path_obj = (Path.cwd() / path_obj).resolve()
    else:
        path_obj = path_obj.resolve()

    if not path_obj.exists():
        raise FileNotFoundError(f"Folder does not exist: {path_obj}")

    if not path_obj.is_dir():
        raise ValueError(f"Path is not a directory: {path_obj}")

    return path_obj


def ensure_inside_folder(file_path: Path, folder_root: Path) -> Path:
    """Ensures file_path is strictly contained within folder_root to prevent traversal."""
    resolved_file = file_path.resolve()
    resolved_root = folder_root.resolve()

    try:
        resolved_file.relative_to(resolved_root)
    except ValueError:
        raise PermissionError(
            f"Security violation: path '{resolved_file}' is outside folder root '{resolved_root}'"
        )
    return resolved_file


def sanitize_kebab_name(name: str, fallback_original: str = "sorted-file") -> str:
    """Sanitizes a proposed filename to strictly valid lowercase-kebab-case.

    - Strips extensions if the model accidentally included one
    - Normalizes unicode (decomposes accents, replaces emojis/symbols)
    - Replaces non-alphanumeric characters and dots with hyphens
    - Collapses consecutive hyphens
    - Truncates to MAX_FILENAME_LENGTH (60 chars)
    """
    if not name or not str(name).strip():
        return _make_fallback_kebab(fallback_original)

    # 1. Normalize unicode (NFKD decomposes e.g. é into e + accent)
    raw_str = str(name).strip()
    norm = unicodedata.normalize("NFKD", raw_str)
    # Strip non-ASCII characters
    ascii_str = norm.encode("ascii", "ignore").decode("ascii")

    # If all characters were non-ASCII (e.g. pure emojis or CJK), fallback safely
    if not ascii_str.strip():
        return _make_fallback_kebab(fallback_original)

    # 2. Strip extension if model included one (e.g. .pdf, .png)
    if "." in ascii_str:
        # Check if the end looks like an extension (1-6 letters)
        ascii_str = re.sub(r"\.[a-zA-Z0-9]{1,6}$", "", ascii_str)

    # 3. Lowercase
    lowered = ascii_str.lower().strip()

    # 4. Replace spaces, dots, underscores, and any non-alphanumerics with hyphens
    kebab = re.sub(r"[^a-z0-9]+", "-", lowered)

    # 5. Collapse multiple hyphens and trim ends
    kebab = re.sub(r"-+", "-", kebab).strip("-")

    # 6. Truncate to MAX_FILENAME_LENGTH
    if len(kebab) > MAX_FILENAME_LENGTH:
        kebab = kebab[:MAX_FILENAME_LENGTH].rstrip("-")

    if not kebab:
        return _make_fallback_kebab(fallback_original)

    return kebab


def _make_fallback_kebab(original_name: str) -> str:
    """Creates a safe fallback kebab name from the original filename stem."""
    if not original_name or not str(original_name).strip():
        return "file"

    stem = Path(original_name).stem if "." in original_name else original_name
    norm = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
    clean = clean[:MAX_FILENAME_LENGTH].rstrip("-")
    return clean or "sorted-file"


def sanitize_category(category: str) -> str:
    """Ensures category is one of the allowed categories, with safe fallback to 'Other'."""
    if not category:
        return "Other"

    cat_clean = str(category).strip()
    for allowed in ALLOWED_CATEGORIES:
        if allowed.lower() == cat_clean.lower():
            return allowed

    # Robust fuzzy matching for common variations
    norm = cat_clean.lower()
    if "screenshot" in norm:
        return "Screenshots"
    if "receipt" in norm or "bill" in norm or "invoice" in norm or "statement" in norm:
        return "Receipts-Bills"
    if "note" in norm or "study" in norm or "lecture" in norm or "homework" in norm:
        return "Study-Notes"
    if "code" in norm or "script" in norm or "dev" in norm or "sql" in norm:
        return "Code"
    if "doc" in norm or "pdf" in norm or "resume" in norm or "contract" in norm:
        return "Documents"
    if "img" in norm or "photo" in norm or "image" in norm or "picture" in norm:
        return "Images"
    if "media" in norm or "video" in norm or "audio" in norm or "song" in norm:
        return "Media"
    if "archive" in norm or "zip" in norm or "backup" in norm:
        return "Archives"

    return "Other"
