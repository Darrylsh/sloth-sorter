"""Unit tests for organizer.py."""
import json
from pathlib import Path
from app.organizer import (
    apply_organization_plan,
    get_unique_destination,
    list_past_runs,
    scan_folder_files,
    undo_run,
)


def test_scan_folder_files_skips_hidden_and_categories(tmp_path):
    # Regular files
    (tmp_path / "file1.txt").write_text("1")
    (tmp_path / "file2.jpg").write_text("2")

    # Hidden files
    (tmp_path / ".hidden_file.txt").write_text("hidden")
    (tmp_path / ".sloth_log").mkdir()
    (tmp_path / ".sloth_log" / "run-test.json").write_text("{}")

    # Category folders from previous runs
    cat_dir = tmp_path / "Screenshots"
    cat_dir.mkdir()
    (cat_dir / "already_sorted.png").write_text("sorted")

    # Non-recursive scan: should only find file1 and file2
    files = scan_folder_files(tmp_path, recursive=False)
    filenames = [f.name for f in files]
    assert "file1.txt" in filenames
    assert "file2.jpg" in filenames
    assert ".hidden_file.txt" not in filenames
    assert "already_sorted.png" not in filenames

    # Recursive scan: still skips category folder items
    files_rec = scan_folder_files(tmp_path, recursive=True)
    filenames_rec = [f.name for f in files_rec]
    assert "already_sorted.png" not in filenames_rec


def test_get_unique_destination_collision_handling(tmp_path):
    target_dir = tmp_path / "Receipts-Bills"
    target_dir.mkdir()

    # First file
    dest1 = get_unique_destination(target_dir, "aws-invoice", ".txt")
    assert dest1.name == "aws-invoice.txt"
    dest1.write_text("bill 1")

    # Second file with same candidate name
    dest2 = get_unique_destination(target_dir, "aws-invoice", ".txt")
    assert dest2.name == "aws-invoice-2.txt"
    dest2.write_text("bill 2")

    # Third file
    dest3 = get_unique_destination(target_dir, "aws-invoice", ".txt")
    assert dest3.name == "aws-invoice-3.txt"


def test_apply_and_undo_roundtrip(tmp_path):
    # Create test files
    f1 = tmp_path / "grocery_receipt.txt"
    f1.write_text("Milk $3.00")
    f2 = tmp_path / "photo.png"
    f2.write_text("PNG DATA")

    plan = [
        {"original": "grocery_receipt.txt", "new_name": "target-grocery-receipt", "category": "Receipts-Bills"},
        {"original": "photo.png", "new_name": "nature-landscape", "category": "Images"}
    ]

    report = {"total_files": 2, "total_duration_sec": 1.2}

    # 1. Apply
    run_result = apply_organization_plan(tmp_path, plan, report=report)
    run_id = run_result["run_id"]

    assert run_result["moves_count"] == 2
    assert not f1.exists()
    assert not f2.exists()

    expected_dst1 = tmp_path / "Receipts-Bills" / "target-grocery-receipt.txt"
    expected_dst2 = tmp_path / "Images" / "nature-landscape.png"
    assert expected_dst1.exists()
    assert expected_dst2.exists()

    # Verify run was logged in .sloth_log
    past_runs = list_past_runs(tmp_path)
    assert len(past_runs) == 1
    assert past_runs[0]["run_id"] == run_id
    assert past_runs[0]["report"]["total_files"] == 2

    # 2. Undo
    undo_result = undo_run(tmp_path, run_id)
    assert undo_result["success"] is True
    assert undo_result["reversed_count"] == 2

    # Original files should be restored
    assert f1.exists()
    assert f2.exists()
    assert f1.read_text() == "Milk $3.00"

    # Empty category directories should be removed
    assert not (tmp_path / "Receipts-Bills").exists()
    assert not (tmp_path / "Images").exists()
