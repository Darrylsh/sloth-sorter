import json
import re
import sys
import time
from pathlib import Path

# Ensure app is importable
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.analyzer import analyze_single_file, extract_text_from_file

DATE_PATTERNS = [
    re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})"),
    re.compile(r"\b(19\d\d|20\d\d)\b"),
]

MONTH_MAP = {
    "01": ["jan", "january"],
    "02": ["feb", "february"],
    "03": ["mar", "march"],
    "04": ["apr", "april"],
    "05": ["may"],
    "06": ["jun", "june"],
    "07": ["jul", "july"],
    "08": ["aug", "august"],
    "09": ["sep", "sept", "september"],
    "10": ["oct", "october"],
    "11": ["nov", "november"],
    "12": ["dec", "december"],
}


def is_date_verified(filename: str, new_name: str, file_path: Path, is_image: bool) -> tuple[bool, str]:
    """Checks whether any date extracted from new_name is verified by filename or content.
    Returns (is_verified, found_date_str).
    """
    # 1. Full YYYY-MM-DD
    match_full = re.search(r"(\d{4})-(\d{2})-(\d{2})", new_name)
    if match_full:
        date_str = match_full.group(0)
        year, month, day = match_full.groups()

        # For images: MUST be in filename
        if is_image:
            fn_clean = filename.replace("-", "").replace("_", "").replace(" ", "").lower()
            ds_clean = date_str.replace("-", "")
            # check YYYYMMDD or YYYY-MM-DD or year in filename
            if ds_clean in fn_clean or (year in filename and int(month) <= 12 and int(day) <= 31 and f"{year}{month}{day}" in fn_clean):
                return True, date_str
            # check with delimiters
            if f"{year}-{month}-{day}" in filename or f"{year}.{month}.{day}" in filename or f"{year}_{month}_{day}" in filename:
                return True, date_str
            return False, date_str

        # For text / documents: check filename OR text content
        fn_lower = filename.lower()
        if date_str in fn_lower or f"{year}{month}{day}" in fn_lower:
            return True, date_str

        # Check extracted text
        text = extract_text_from_file(file_path)
        if not text:
            return False, date_str

        text_lower = text.lower()
        # Direct YYYY-MM-DD or MM/DD/YYYY or DD/MM/YYYY
        if date_str in text_lower or f"{int(month)}/{int(day)}/{year}" in text_lower or f"{month}/{day}/{year}" in text_lower:
            return True, date_str

        # Month name forms (e.g. October 18, 2026 or Oct 18, 2026)
        month_names = MONTH_MAP.get(month, [])
        for mname in month_names:
            day_num = str(int(day))
            if year in text_lower and mname in text_lower and (day in text_lower or day_num in text_lower):
                return True, date_str

        return False, date_str

    # 2. Check year alone if in new_name (e.g., 2022, 2024, 2026)
    match_year = re.search(r"\b(19\d\d|20\d\d)\b", new_name)
    if match_year:
        year_str = match_year.group(1)
        if is_image:
            if year_str in filename:
                return True, year_str
            return False, year_str

        if year_str in filename:
            return True, year_str

        text = extract_text_from_file(file_path)
        if text and year_str in text:
            return True, year_str
        return False, year_str

    # No date in name
    return True, ""


def run_eval(sample_dir: Path = None, expected_path: Path = None):
    if sample_dir is None:
        sample_dir = repo_root / "sample_mess"
    if expected_path is None:
        expected_path = repo_root / "eval" / "expected.json"

    with open(expected_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    files = sorted([p for p in sample_dir.iterdir() if p.is_file() and not p.name.startswith(".")])
    print(f"Running evaluation on {len(files)} files in {sample_dir.name}...")

    results = []
    total_time = 0.0
    fallback_count = 0
    mismatches = []
    unverified_dates = []

    for idx, fpath in enumerate(files, 1):
        t0 = time.perf_counter()
        res = analyze_single_file(fpath)
        elapsed = time.perf_counter() - t0
        total_time += elapsed

        exp_cat = expected.get(fpath.name, "Unknown")
        is_fallback = res.get("classification_type") == "fallback"
        if is_fallback:
            fallback_count += 1

        actual_cat = res.get("category", "Other")
        new_name = res.get("new_name", fpath.stem)
        ext = fpath.suffix.lower()
        is_image = ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]

        verified, date_str = is_date_verified(fpath.name, new_name, fpath, is_image)
        if not verified:
            unverified_dates.append({
                "filename": fpath.name,
                "new_name": new_name,
                "unverified_date": date_str,
            })

        matched = (actual_cat == exp_cat)
        if not matched:
            mismatches.append({
                "filename": fpath.name,
                "expected": exp_cat,
                "actual": actual_cat,
                "new_name": new_name,
                "confidence": res.get("confidence"),
                "reason": res.get("reason", "")[:100],
            })

        print(f"[{idx:02d}/{len(files):02d}] {fpath.name:36s} -> {new_name} [{actual_cat}] ({res.get('confidence')}) [{elapsed:.2f}s]")
        results.append({
            "filename": fpath.name,
            "expected": exp_cat,
            "actual": actual_cat,
            "new_name": new_name,
            "confidence": res.get("confidence"),
            "elapsed": elapsed,
            "is_fallback": is_fallback,
        })

    avg_time = total_time / len(files) if files else 0
    accuracy = (len(files) - len(mismatches)) / len(files) * 100 if files else 0

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total Files Analyzed    : {len(files)}")
    print(f"Category Accuracy       : {accuracy:.1f}% ({len(files) - len(mismatches)}/{len(files)})")
    print(f"Mismatches Count        : {len(mismatches)}")
    print(f"Unverified Dates Count  : {len(unverified_dates)}")
    print(f"Fallback Count          : {fallback_count}")
    print(f"Total Time              : {total_time:.2f}s")
    print(f"Average Time per File   : {avg_time:.2f}s")

    if mismatches:
        print("\nMISMATCHES:")
        for m in mismatches:
            print(f"  - {m['filename']}: Expected '{m['expected']}', got '{m['actual']}' (confidence: {m['confidence']})")

    if unverified_dates:
        print("\nUNVERIFIED DATES IN NEW NAMES:")
        for u in unverified_dates:
            print(f"  - {u['filename']}: '{u['new_name']}' contained unverified date '{u['unverified_date']}'")

    return {
        "accuracy": accuracy,
        "mismatches": mismatches,
        "unverified_dates": unverified_dates,
        "fallback_count": fallback_count,
        "avg_time": avg_time,
        "total_time": total_time,
        "results": results,
    }


if __name__ == "__main__":
    run_eval()
