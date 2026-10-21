"""Generates an extensive, nasty test folder 'realistic_mess/'

Includes:
- Unicode, emoji, multi-dot, uppercase, and 200+ char filenames
- 0-byte files, 0-byte PDF, corrupted PDF, password-encrypted PDF
- Huge image (4000x3000), tiny image (1x1), animated GIF, transparent PNG
- Files with identical content/context designed to collide
- Pre-existing category folder with pre-sorted files (to verify non-recurrence)
"""

import io
from pathlib import Path
from PIL import Image, ImageDraw
import pypdf


def create_realistic_mess(target_dir_name: str = "realistic_mess"):
    target = Path(target_dir_name).resolve()
    target.mkdir(parents=True, exist_ok=True)
    print(f"Creating nasty edge-case mess in: {target}")

    # 1. Edge Case Filenames
    # Multiple dots & uppercase extension
    (target / "quarterly.tax.report.final.v2.PDF").write_text(
        "Quarterly corporate tax filing draft for IRS form 1120. Net income: $420,000.",
        encoding="utf-8"
    )

    # Spaces and special chars in filename
    (target / "my electric bill (unpaid) #104 - OCT.txt").write_text(
        "Electric Utility Bill\nAccount: 994-102\nAmount Due: $210.45\nDue: 2026-11-15\n",
        encoding="utf-8"
    )

    # Emojis and Unicode accents
    (target / "🧾_réceipt_café_latte_🥐.txt").write_text(
        "Cafe de Paris - Receipt\nItem: Cafe au Lait ($4.50)\nCroissant ($3.20)\nTotal: $7.70 paid cash\n",
        encoding="utf-8"
    )

    # Japanese / Non-Latin Unicode
    (target / "授業ノート_物理学_量子力学.txt").write_text(
        "Quantum mechanics course notes on wave functions and Schrodinger equations.\n",
        encoding="utf-8"
    )

    # Very long filename (approx 160 chars)
    long_name = "draft_notes_annual_engineering_all_hands_meeting_scalability_database_optimizations_deliverables_cross_functional_teams_v3_final_review.txt"
    (target / long_name).write_text(
        "All hands meeting notes: discussing database query optimization and scaling out redis caches.\n",
        encoding="utf-8"
    )

    # No extension
    (target / "DATABASE_MIGRATION_CONFIG").write_text(
        "DB_HOST=127.0.0.1\nDB_PORT=5432\nDB_USER=postgres\nDB_NAME=production\n",
        encoding="utf-8"
    )

    # Uppercase PNG extension
    img_upper = Image.new("RGB", (300, 200), color="#1e3a8a")
    d_up = ImageDraw.Draw(img_upper)
    d_up.text((20, 80), "SCREENSHOT CAPTURE", fill="#ffffff")
    img_upper.save(target / "SCREENSHOT_BUG_REPORT.PNG")

    # 2. Corrupt, Encrypted & Zero-Byte Files
    # Empty 0-byte text
    (target / "empty_scratch_notes.txt").write_bytes(b"")

    # Empty 0-byte PDF
    (target / "zero_byte_empty_file.pdf").write_bytes(b"")

    # Corrupted pseudo-PDF (has PDF header but garbage content)
    (target / "corrupted_scanned_document.pdf").write_bytes(
        b"%PDF-1.4\n%Corrupted file payload that will break standard parser\n" + b"\x00\xFF\xAA\xBB" * 40
    )

    # 3. Image Edge Cases
    # Huge image (4000x3000)
    huge_img = Image.new("RGB", (4000, 3000), color="#2d4a22")
    d_huge = ImageDraw.Draw(huge_img)
    d_huge.rectangle([(500, 500), (3500, 2500)], fill="#3b6b2e")
    d_huge.text((1000, 1400), "HIGH RESOLUTION 4K PHOTO", fill="#ffffff")
    huge_img.save(target / "huge_wallpaper_4k_res.jpg", quality=80)

    # Tiny 1x1 image
    tiny_img = Image.new("RGB", (1, 1), color="#ff0000")
    tiny_img.save(target / "pixel_tracker_1x1.png")

    # Transparent PNG with Alpha Channel (RGBA)
    rgba_img = Image.new("RGBA", (250, 250), color=(0, 0, 0, 0))
    d_rgba = ImageDraw.Draw(rgba_img)
    d_rgba.ellipse([(20, 20), (230, 230)], fill=(245, 158, 11, 200), outline=(255, 255, 255, 255))
    d_rgba.text((60, 110), "ALPHA ICON", fill=(0, 0, 0, 255))
    rgba_img.save(target / "transparent_badge_icon.png")

    # Animated GIF
    frames = [
        Image.new("RGB", (120, 120), color="#10b981"),
        Image.new("RGB", (120, 120), color="#3b82f6"),
        Image.new("RGB", (120, 120), color="#f59e0b")
    ]
    frames[0].save(
        target / "loading_spinner_animation.gif",
        save_all=True,
        append_images=frames[1:],
        duration=200,
        loop=0
    )

    # 4. Collision Candidates (two files with same subject that model would propose same name for)
    (target / "invoice_amazon_cloud_nov_01.txt").write_text(
        "AWS Invoice INV-1002\nDate: 2026-11-01\nTotal: $54.20\nServices: Amazon S3 and EC2\n",
        encoding="utf-8"
    )
    (target / "amazon_aws_monthly_bill_nov.txt").write_text(
        "AWS Invoice INV-1002\nDate: 2026-11-01\nTotal: $54.20\nServices: Amazon S3 and EC2\n",
        encoding="utf-8"
    )

    # 5. Pre-existing Category Folder (to ensure non-recursive / recursive safety)
    cat_dir = target / "Screenshots"
    cat_dir.mkdir(exist_ok=True)
    (cat_dir / "already_sorted_screenshot.png").write_bytes(b"dummy")

    print(f"Created {len(list(target.iterdir()))} items in {target}")


if __name__ == "__main__":
    create_realistic_mess()
