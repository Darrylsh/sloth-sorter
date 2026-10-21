"""Unit tests for safety.py."""
import pytest
from pathlib import Path
from app.safety import (
    ensure_inside_folder,
    sanitize_category,
    sanitize_kebab_name,
    validate_and_resolve_folder,
)


def test_validate_and_resolve_folder(tmp_path):
    # Valid existing directory
    resolved = validate_and_resolve_folder(str(tmp_path))
    assert resolved == tmp_path.resolve()

    # Handles quotes and trailing slashes
    quoted = f'"{tmp_path}\\"'
    assert validate_and_resolve_folder(quoted) == tmp_path.resolve()

    # Empty path raises error
    with pytest.raises(ValueError):
        validate_and_resolve_folder("")

    # Non-existent path raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        validate_and_resolve_folder(str(tmp_path / "does_not_exist"))


def test_ensure_inside_folder_prevents_traversal(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    safe_file = root / "valid.txt"
    safe_file.write_text("ok")

    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret")

    # Inside folder: passes
    assert ensure_inside_folder(safe_file, root) == safe_file.resolve()

    # Outside folder: raises PermissionError
    with pytest.raises(PermissionError):
        ensure_inside_folder(outside_file, root)

    # Relative traversal attempt
    traversal_path = root / ".." / "secret.txt"
    with pytest.raises(PermissionError):
        ensure_inside_folder(traversal_path, root)


def test_sanitize_kebab_name():
    # Basic kebab
    assert sanitize_kebab_name("My Great File") == "my-great-file"

    # Multiple dots and extension stripping
    assert sanitize_kebab_name("report.final.v2.pdf") == "report-final-v2"

    # Unicode with accents
    assert sanitize_kebab_name("réceipt_café_latte") == "receipt-cafe-latte"

    # Emojis and special symbols
    assert sanitize_kebab_name("🧾 Invoice #492! ($89.00)") == "invoice-492-89-00"

    # Very long name (truncated to <= 60 chars)
    long_name = "a" * 120
    cleaned = sanitize_kebab_name(long_name)
    assert len(cleaned) <= 60
    assert cleaned == "a" * 60

    # Non-Latin characters fallback safely
    assert sanitize_kebab_name("授業ノート_物理学", fallback_original="physics-notes") == "physics-notes"

    # Empty or pure symbols fallback
    assert sanitize_kebab_name("---", fallback_original="document") == "document"


def test_sanitize_category():
    # Exact matches
    assert sanitize_category("Screenshots") == "Screenshots"
    assert sanitize_category("Receipts-Bills") == "Receipts-Bills"

    # Case insensitive
    assert sanitize_category("documents") == "Documents"
    assert sanitize_category("code") == "Code"

    # Fuzzy matches
    assert sanitize_category("Stripe Bill") == "Receipts-Bills"
    assert sanitize_category("Slack Screenshot") == "Screenshots"
    assert sanitize_category("Lecture Note") == "Study-Notes"

    # Unknown category fallback
    assert sanitize_category("random_gibberish_123") == "Other"
    assert sanitize_category("") == "Other"


def test_sanitize_kebab_name_strips_extensions_and_bad_chars():
    # Model accidentally returned filename with extension
    assert sanitize_kebab_name("monthly-report.pdf") == "monthly-report"
    assert sanitize_kebab_name("screenshot_error_404.png") == "screenshot-error-404"
    # Special punctuation and caps
    assert sanitize_kebab_name("PROJECT::Alpha (v2.1)!!") == "project-alpha-v2-1"


def test_infer_category_and_name_from_rules(tmp_path):
    from app.analyzer import infer_category_and_name_from_rules

    # Receipt keyword in filename
    receipt_file = tmp_path / "target_receipt_oct.txt"
    receipt_file.write_text("Total: $42.50 paid card")
    cat, name = infer_category_and_name_from_rules(receipt_file)
    assert cat == "Receipts-Bills"
    assert name == "target-receipt-oct"

    # Heading in markdown file
    notes_file = tmp_path / "study_session.md"
    notes_file.write_text("# Biology Mitosis Study Guide\nPoint 1: Prophase\n")
    cat, name = infer_category_and_name_from_rules(notes_file)
    assert cat == "Study-Notes"
    assert "biology-mitosis-study-guide" in name


def test_strip_unverified_dates():
    from app.analyzer import strip_unverified_dates

    # 1. Unverified date in text file gets stripped
    name, stripped = strip_unverified_dates(
        "biology-mitosis-notes-2024-10-27",
        "biology_mitosis_notes.txt",
        extracted_text="Mitosis stages: prophase, metaphase.",
        is_image=False
    )
    assert name == "biology-mitosis-notes"
    assert stripped == "2024-10-27"

    # 2. Verified date in text file is preserved
    name, stripped = strip_unverified_dates(
        "aws-bill-2026-10-01",
        "aws_cloud_invoice_0921.txt",
        extracted_text="Billing Date: October 01, 2026. Total: $48.20",
        is_image=False
    )
    assert name == "aws-bill-2026-10-01"
    assert stripped is None

    # 3. Image with date in filename is preserved
    name, stripped = strip_unverified_dates(
        "slack-hotfix-2026-10-21",
        "Screenshot 2026-10-21 at 3.12.png",
        extracted_text=None,
        is_image=True
    )
    assert name == "slack-hotfix-2026-10-21"
    assert stripped is None

    # 4. Image with date NOT in filename gets stripped
    name, stripped = strip_unverified_dates(
        "sunrise-over-forest-2024-03-08",
        "IMG_4821.jpg",
        extracted_text=None,
        is_image=True
    )
    assert name == "sunrise-over-forest"
    assert stripped == "2024-03-08"


def test_correct_category_rules():
    from app.analyzer import correct_category

    # 1. Code extension always wins
    cat, corr = correct_category("Archives", "database_dump_schema.sql", "database-schema", "sql schema", ".sql", is_image=False)
    assert cat == "Code"
    assert corr == "Archives -> Code"

    # 2. Screenshot filename triggers Screenshots
    cat, corr = correct_category("Other", "Screenshot 2026-10-21 at 3.12.png", "slack-hotfix", "chat window", ".png", is_image=True)
    assert cat == "Screenshots"
    assert corr == "Other -> Screenshots"

    # 3. Screenshot reason triggers Screenshots
    cat, corr = correct_category("Images", "img_001.png", "analytics-data", "Analytics dashboard UI with graphs", ".png", is_image=True)
    assert cat == "Screenshots"
    assert corr == "Images -> Screenshots"

    # 4. PDF/DOCX where model said Other -> Documents
    cat, corr = correct_category("Other", "contract_nda.pdf", "nda-confidentiality", "Mutual NDA agreement", ".pdf", is_image=False)
    assert cat == "Documents"
    assert corr == "Other -> Documents"

    # 5. Non-archive extension categorized as Archives gets corrected
    cat, corr = correct_category("Archives", "script.py", "python-script", "script", ".py", is_image=False)
    assert cat == "Code"


def test_adjust_confidence():
    from app.analyzer import adjust_confidence

    # 1. Fallback is always low
    assert adjust_confidence("high", "test.txt", "reason", "Documents", False, False, False, is_fallback=True) == "low"

    # 2. Date stripped or category corrected downgrades high to med
    assert adjust_confidence("high", "notes.txt", "reason", "Study-Notes", False, was_date_stripped=True, was_category_corrected=False, is_fallback=False) == "med"
    assert adjust_confidence("high", "test.sql", "reason", "Code", False, was_date_stripped=False, was_category_corrected=True, is_fallback=False) == "med"

    # 3. Photos downgraded to med
    assert adjust_confidence("high", "DCIM_0092_nature.jpg", "Photo of nature forest", "Images", True, False, False, is_fallback=False) == "med"

    # 4. Memes and avatars downgraded to low
    assert adjust_confidence("high", "meme_cat_coffee_v1.jpg", "Funny meme about code compilation", "Images", True, False, False, is_fallback=False) == "low"
    assert adjust_confidence("high", "profile_photo_avatar.png", "Blue circle profile avatar", "Images", True, False, False, is_fallback=False) == "low"

