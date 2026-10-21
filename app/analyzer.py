"""File analysis engine for Sloth Sorter.

Handles text extraction, image downsizing, sequential local AI classification
via Ollama (Gemma 3:4B), collision resolution, performance timing, and SSE stream generation.
"""

import asyncio
import base64
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

import ollama
from PIL import Image

# Prevent DecompressionBombError for large screenshots/wallpapers
Image.MAX_IMAGE_PIXELS = 100_000_000

from app.config import (
    ALLOWED_CATEGORIES,
    ANALYSIS_SYSTEM_PROMPT,
    ARCHIVE_EXTENSIONS,
    DEFAULT_DELAY_MS,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_HOST,
    DOCX_EXTENSIONS,
    EXTENSION_CATEGORY_MAP,
    IMAGE_EXTENSIONS,
    MAX_IMAGE_DIMENSION,
    MAX_TEXT_SNIPPET_LENGTH,
    MEDIA_EXTENSIONS,
    OLLAMA_JSON_SCHEMA,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_TEMPERATURE,
    OLLAMA_TIMEOUT,
    PDF_EXTENSIONS,
    TEXT_EXTENSIONS,
)
from app.safety import sanitize_category, sanitize_kebab_name

logger = logging.getLogger("sloth_sorter.analyzer")

# Reusable persistent Ollama client with request timeout
_ollama_client = ollama.Client(host=DEFAULT_OLLAMA_HOST, timeout=OLLAMA_TIMEOUT)


class MissingDependencyError(Exception):
    """Raised when an optional third-party library is required but not installed."""
    def __init__(self, package_name: str):
        super().__init__(f"Missing dependency: {package_name}")
        self.package_name = package_name


def warmup_model(model: str = DEFAULT_MODEL) -> bool:
    """Sends a tiny 1-token request to Ollama to preload model weights into VRAM."""
    try:
        _ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            options={"num_predict": 1},
            keep_alive=OLLAMA_KEEP_ALIVE
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to warmup model {model}: {e}")
        return False


def format_size_human(bytes_size: int) -> str:
    """Converts bytes to human readable string (KB, MB, GB)."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"


def clean_text_snippet(raw_text: str, max_chars: int = MAX_TEXT_SNIPPET_LENGTH) -> Optional[str]:
    """Cleans extracted text by stripping repeated whitespace and blank lines, up to max_chars."""
    if not raw_text or not raw_text.strip():
        return None
    cleaned_lines = []
    for line in raw_text.splitlines():
        line_clean = re.sub(r"[ \t]+", " ", line.strip())
        if line_clean:
            cleaned_lines.append(line_clean)
    result = "\n".join(cleaned_lines).strip()
    return result[:max_chars] if result else None


def extract_text_from_file(file_path: Path) -> Optional[str]:
    """Extracts first ~800 characters of cleaned text from supported document/code/text formats."""
    # Check for empty file
    try:
        if file_path.stat().st_size == 0:
            return None
    except Exception:
        return None

    ext = file_path.suffix.lower()

    # 1. PDF
    if ext in PDF_EXTENSIONS:
        try:
            import pypdf
        except ImportError:
            raise MissingDependencyError("pypdf")

        full_text = None
        try:
            reader = pypdf.PdfReader(str(file_path))
            if not reader.is_encrypted:
                extracted_text = []
                char_count = 0
                for page in reader.pages:
                    text = page.extract_text() or ""
                    extracted_text.append(text)
                    char_count += len(text)
                    if char_count >= MAX_TEXT_SNIPPET_LENGTH * 2:
                        break
                full_text = "\n".join(extracted_text).strip()
        except Exception as e:
            # Fallback: if file is actually a text file disguised with a .PDF extension
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    txt = f.read(MAX_TEXT_SNIPPET_LENGTH * 2)
                    if txt and not txt.startswith("%PDF"):
                        full_text = txt
            except Exception:
                pass
            if not full_text:
                logger.warning(f"Failed to extract PDF text from {file_path.name}: {e}")
                return None

        return clean_text_snippet(full_text) if full_text else None

    # 2. DOCX
    if ext in DOCX_EXTENSIONS:
        try:
            import docx
        except ImportError:
            raise MissingDependencyError("python-docx")

        try:
            doc = docx.Document(str(file_path))
            paragraphs = []
            char_count = 0
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    paragraphs.append(text)
                    char_count += len(text)
                    if char_count >= MAX_TEXT_SNIPPET_LENGTH * 2:
                        break
            full_text = "\n".join(paragraphs).strip()
            return clean_text_snippet(full_text) if full_text else None
        except Exception as e:
            logger.warning(f"Failed to extract DOCX text from {file_path.name}: {e}")
            return None

    # 3. Plain text / code
    if ext in TEXT_EXTENSIONS or not ext:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                snippet = f.read(MAX_TEXT_SNIPPET_LENGTH * 3)
                return clean_text_snippet(snippet)
        except Exception as e:
            logger.warning(f"Failed to read text from {file_path.name}: {e}")
            return None

    return None


def prepare_image_b64(file_path: Path) -> Optional[str]:
    """Opens image, handles animation/alpha channels, resizes, and returns base64 JPEG string."""
    try:
        from PIL import Image
    except ImportError:
        raise MissingDependencyError("Pillow")

    try:
        if file_path.stat().st_size == 0:
            return None

        with Image.open(file_path) as img:
            # For animated GIFs, seek to first frame
            if getattr(img, "is_animated", False):
                img.seek(0)

            # Convert palette/transparency to RGB
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                mask = img.split()[3] if img.mode == "RGBA" else None
                background.paste(img, mask=mask)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Resize if either dimension exceeds MAX_IMAGE_DIMENSION
            w, h = img.size
            if max(w, h) > MAX_IMAGE_DIMENSION:
                ratio = MAX_IMAGE_DIMENSION / max(w, h)
                new_w = max(1, int(w * ratio))
                new_h = max(1, int(h * ratio))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to process image {file_path.name}: {e}")
        return None


def clean_and_parse_json(raw_text: str) -> Optional[dict]:
    """Robustly extracts and parses JSON from raw model output."""
    if not raw_text:
        return None

    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


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

CODE_EXTENSIONS: Set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".bash", ".sql",
    ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".html",
    ".css", ".ps1", ".bat"
}

ARCHIVE_EXTS: Set[str] = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"
}


def strip_unverified_dates(
    new_name: str,
    filename: str,
    extracted_text: Optional[str],
    is_image: bool
) -> Tuple[str, Optional[str]]:
    """Checks for dates in new_name and strips any that cannot be verified by content/filename.
    Returns (cleaned_name, stripped_date_or_None).
    """
    fn_lower = filename.lower()
    fn_clean = re.sub(r"[-_.\s]", "", fn_lower)
    stripped_date = None

    def remove_date_substr(curr_name: str, target_match: str) -> str:
        pattern = re.compile(r"-?" + re.escape(target_match) + r"-?")
        res = pattern.sub("-", curr_name)
        res = re.sub(r"-+", "-", res).strip("-")
        return res

    # 1. Check for YYYY-MM-DD
    match_full = re.search(r"(\d{4})-(\d{2})-(\d{2})", new_name)
    if match_full:
        date_str = match_full.group(0)
        year, month, day = match_full.groups()
        verified = False

        if is_image:
            # For images, keep date only if also in filename
            date_clean = f"{year}{month}{day}"
            if (date_clean in fn_clean or
                f"{year}-{month}-{day}" in fn_lower or
                f"{year}_{month}_{day}" in fn_lower or
                f"{year}.{month}.{day}" in fn_lower):
                verified = True
        else:
            # For text/documents: filename or extracted_text
            date_clean = f"{year}{month}{day}"
            if date_clean in fn_clean or date_str in fn_lower:
                verified = True
            elif extracted_text:
                txt_lower = extracted_text.lower()
                if (date_str in txt_lower or
                    f"{int(month)}/{int(day)}/{year}" in txt_lower or
                    f"{month}/{day}/{year}" in txt_lower):
                    verified = True
                else:
                    month_names = MONTH_MAP.get(month, [])
                    for mname in month_names:
                        day_num = str(int(day))
                        if year in txt_lower and mname in txt_lower and (day in txt_lower or day_num in txt_lower):
                            verified = True
                            break

        if not verified:
            new_name = remove_date_substr(new_name, date_str)
            stripped_date = date_str

    # 2. Check for YYYY-MM (if not already stripped by full date)
    match_ym = re.search(r"(\d{4})-(\d{2})", new_name)
    if match_ym and not stripped_date:
        ym_str = match_ym.group(0)
        year, month = match_ym.groups()
        verified = False

        if is_image:
            if f"{year}{month}" in fn_clean or f"{year}-{month}" in fn_lower:
                verified = True
        else:
            if f"{year}{month}" in fn_clean or ym_str in fn_lower:
                verified = True
            elif extracted_text:
                txt_lower = extracted_text.lower()
                if ym_str in txt_lower or f"{month}/{year}" in txt_lower:
                    verified = True
                else:
                    month_names = MONTH_MAP.get(month, [])
                    for mname in month_names:
                        if year in txt_lower and mname in txt_lower:
                            verified = True
                            break
        if not verified:
            new_name = remove_date_substr(new_name, ym_str)
            stripped_date = ym_str

    # 3. Check for standalone 4-digit Year YYYY
    match_year = re.search(r"\b(19\d\d|20\d\d)\b", new_name)
    if match_year and not stripped_date:
        year_str = match_year.group(1)
        verified = False

        if is_image:
            if year_str in fn_lower:
                verified = True
        else:
            if year_str in fn_lower:
                verified = True
            elif extracted_text and year_str in extracted_text.lower():
                verified = True

        if not verified:
            new_name = remove_date_substr(new_name, year_str)
            stripped_date = year_str

    if not new_name:
        new_name = sanitize_kebab_name(Path(filename).stem)

    return new_name, stripped_date


def correct_category(
    model_category: str,
    filename: str,
    new_name: str,
    reason: str,
    ext: str,
    is_image: bool
) -> Tuple[str, Optional[str]]:
    """Applies deterministic category rules after model answers.
    Returns (final_category, category_correction_or_None).
    """
    initial_category = model_category
    cat = model_category
    fn_lower = filename.lower()
    reason_lower = reason.lower()
    combined = f"{new_name} {reason_lower} {fn_lower}"

    # 1. Extension wins for code
    if ext in CODE_EXTENSIONS:
        cat = "Code"

    # 2. Screenshots: image whose filename contains screenshot/capture or reason indicates screenshot/UI
    elif is_image:
        screenshot_fn = any(k in fn_lower for k in ["screenshot", "screen shot", "screen_shot", "capture"])
        screenshot_reason = any(k in reason_lower for k in [
            "screenshot", "ui", "terminal", "dashboard", "chat window", "window chrome", "dialog"
        ])
        if screenshot_fn or screenshot_reason:
            cat = "Screenshots"
        elif cat == "Other":
            cat = "Images"

    # 3. PDF/DOCX where model said Other -> Documents (unless receipt/study keyword matches)
    elif ext in {".pdf", ".docx", ".pptx", ".xlsx"} and cat == "Other":
        if any(k in combined for k in ["receipt", "invoice", "bill", "tax"]):
            cat = "Receipts-Bills"
        elif any(k in combined for k in ["notes", "lecture", "study", "homework", "exam", "quiz", "summary"]):
            cat = "Study-Notes"
        else:
            cat = "Documents"

    # 4. Archives only for actual archive extensions
    elif cat == "Archives" and ext not in ARCHIVE_EXTS:
        if ext in CODE_EXTENSIONS:
            cat = "Code"
        elif ext in {".pdf", ".docx", ".pptx", ".xlsx"}:
            cat = "Documents"
        else:
            cat = "Other"

    # Validate against allowed
    cat = sanitize_category(cat)
    correction = f"{initial_category} -> {cat}" if cat != initial_category else None
    return cat, correction


def adjust_confidence(
    model_conf: str,
    filename: str,
    reason: str,
    final_category: str,
    is_image: bool,
    was_date_stripped: bool,
    was_category_corrected: bool,
    is_fallback: bool
) -> str:
    """Adjusts confidence honestly based on fallbacks, corrections, and image type."""
    if is_fallback:
        return "low"

    conf = model_conf.lower()
    if conf not in ("high", "med", "low"):
        conf = "med"

    # Downgrade to med if date was stripped or category corrected
    if (was_date_stripped or was_category_corrected) and conf == "high":
        conf = "med"

    # Photos, memes, and avatars
    if is_image and final_category in ("Images", "Other"):
        combined = f"{filename} {reason}".lower()
        if any(k in combined for k in ["meme", "avatar", "profile_photo", "profile photo"]):
            conf = "low"
        elif any(k in combined for k in ["dcim", "img_", "nature", "forest", "sunrise", "landscape", "wallpaper", "photo", "scenic"]):
            conf = "med"

    return conf


def post_process_proposal(
    file_path: Path,
    raw_name: str,
    raw_category: str,
    reason: str,
    raw_confidence: str,
    classification_type: str,
    extracted_text: Optional[str] = None
) -> Tuple[dict, Optional[str], Optional[str]]:
    """Applies date stripping, deterministic category correction, and honest confidence adjustments.
    Returns (proposal_dict, stripped_date_or_None, category_correction_or_None).
    """
    ext = file_path.suffix.lower()
    is_image = ext in IMAGE_EXTENSIONS
    is_fallback = classification_type == "fallback"

    kebab_name = sanitize_kebab_name(str(raw_name), fallback_original=file_path.stem)

    cleaned_name, stripped_date = strip_unverified_dates(
        kebab_name, file_path.name, extracted_text, is_image
    )

    final_cat, cat_correction = correct_category(
        raw_category, file_path.name, cleaned_name, reason, ext, is_image
    )

    final_conf = adjust_confidence(
        raw_confidence,
        file_path.name,
        reason,
        final_cat,
        is_image,
        was_date_stripped=bool(stripped_date),
        was_category_corrected=bool(cat_correction),
        is_fallback=is_fallback
    )

    proposal = {
        "new_name": cleaned_name,
        "category": final_cat,
        "reason": reason,
        "confidence": final_conf,
        "classification_type": classification_type
    }
    return proposal, stripped_date, cat_correction


def log_debug_entry(
    folder_path: Path,
    filename: str,
    file_type: str,
    model_called: bool,
    raw_model_response: Optional[str],
    fallback_reason: Optional[str],
    elapsed_time: float,
    stripped_date: Optional[str] = None,
    category_correction: Optional[str] = None
) -> None:
    """Writes a debug entry line to .sloth_log/debug.jsonl."""
    try:
        log_dir = folder_path / ".sloth_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        debug_path = log_dir / "debug.jsonl"
        entry = {
            "filename": filename,
            "file_type": file_type,
            "model_called": model_called,
            "raw_model_response": raw_model_response[:500] if raw_model_response else None,
            "fallback_reason": fallback_reason,
            "elapsed_time": round(elapsed_time, 3)
        }
        if stripped_date:
            entry["stripped_date"] = stripped_date
        if category_correction:
            entry["category_correction"] = category_correction
        with open(debug_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"Failed to write debug log: {e}")



def call_gemma_model_detailed(
    prompt: str,
    image_b64: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    fallback_prompt: Optional[str] = None
) -> Tuple[Optional[dict], Optional[str], Optional[str]]:
    """Invokes local Ollama gemma3:4b with prompt, JSON schema, and constrained generation parameters."""
    user_msg: dict = {"role": "user", "content": prompt}
    if image_b64:
        user_msg["images"] = [image_b64]

    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        user_msg
    ]

    chat_options = {
        "num_ctx": OLLAMA_NUM_CTX,
        "temperature": OLLAMA_TEMPERATURE,
        "num_predict": OLLAMA_NUM_PREDICT,
    }

    raw_content = ""
    try:
        response = _ollama_client.chat(
            model=model,
            messages=messages,
            format=OLLAMA_JSON_SCHEMA,
            keep_alive=OLLAMA_KEEP_ALIVE,
            options=chat_options
        )
        content = response.message.content if hasattr(response, "message") and response.message else ""
        raw_content = content
        if content and content.strip():
            parsed = clean_and_parse_json(content)
            if parsed and "new_name" in parsed:
                return parsed, raw_content, None

        # Retry once with a simplified, short prompt before falling back
        logger.info("First attempt produced invalid output or failed, retrying once with simplified short prompt...")
        simple_prompt = fallback_prompt or "Output strictly valid JSON with 'new_name', 'category', 'reason', and 'confidence'."
        retry_msg: dict = {"role": "user", "content": simple_prompt}
        if image_b64:
            retry_msg["images"] = [image_b64]

        retry_messages = [
            {"role": "system", "content": "You are Sloth Sorter. Output only JSON matching schema."},
            retry_msg
        ]
        retry_resp = _ollama_client.chat(
            model=model,
            messages=retry_messages,
            format=OLLAMA_JSON_SCHEMA,
            keep_alive=OLLAMA_KEEP_ALIVE,
            options=chat_options
        )
        retry_content = retry_resp.message.content if hasattr(retry_resp, "message") and retry_resp.message else ""
        raw_content = retry_content
        if not retry_content or not retry_content.strip():
            return None, "", "empty response"

        parsed_retry = clean_and_parse_json(retry_content)
        if parsed_retry and "new_name" in parsed_retry:
            return parsed_retry, raw_content, None

        return None, raw_content, "invalid JSON"

    except Exception as e:
        err_msg = str(e).lower()
        reason = "timeout" if "timeout" in err_msg else "exception"
        logger.error(f"Error calling Ollama model {model}: {e}")
        return None, raw_content, reason


def call_gemma_model(
    prompt: str,
    image_b64: Optional[str] = None,
    model: str = DEFAULT_MODEL
) -> Optional[dict]:
    """Invokes local Ollama gemma3:4b with prompt and optional image, returning parsed dict."""
    parsed, _, _ = call_gemma_model_detailed(prompt, image_b64=image_b64, model=model)
    return parsed


def infer_category_and_name_from_rules(file_path: Path) -> Tuple[str, str]:
    """Infers an intelligent category and readable kebab name using filename stem, keywords, and headings."""
    stem = file_path.stem or file_path.name
    ext = file_path.suffix.lower()

    heading_title = None
    first_meaningful_line = None
    if ext in TEXT_EXTENSIONS or not ext:
        try:
            if file_path.stat().st_size > 0:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for _ in range(10):
                        line = f.readline().strip()
                        if line:
                            if not first_meaningful_line and len(line) >= 4:
                                first_meaningful_line = line
                            if line.startswith("#"):
                                heading_title = re.sub(r"^#+\s*", "", line).strip()
                                break
                            elif line.lower().startswith("title:"):
                                heading_title = line[6:].strip()
                                break
        except Exception:
            pass

    # Keyword check on stem + first line
    combined = f"{stem} {heading_title or ''} {first_meaningful_line or ''}".lower()

    if any(k in combined for k in ("receipt", "invoice", "bill", "payment", "stripe", "unpaid", "checkout", "tax", "charge", "electric")):
        category = "Receipts-Bills"
    elif any(k in combined for k in ("screenshot", "screen shot", "screen-shot", "screen_shot", "capture")):
        category = "Screenshots"
    elif any(k in combined for k in ("notes", "note", "lecture", "homework", "exam", "study", "syllabus", "summary", "mitosis", "quiz")):
        category = "Study-Notes"
    elif any(k in combined for k in ("contract", "agreement", "nda", "report", "resume", "minutes", "memo", "policy", "proposal", "financial", "document")):
        category = "Documents"
    elif any(k in combined for k in ("script", "server", "deploy", "migration", "config", "schema", "test", "database", "auth", "api")):
        category = "Code"
    elif ext in IMAGE_EXTENSIONS:
        category = "Images"
    elif ext in MEDIA_EXTENSIONS:
        category = "Media"
    elif ext in ARCHIVE_EXTENSIONS:
        category = "Archives"
    elif ext in PDF_EXTENSIONS or ext in DOCX_EXTENSIONS:
        category = "Documents"
    elif ext in TEXT_EXTENSIONS:
        category = "Code" if ext in {".py", ".js", ".ts", ".html", ".css", ".sql", ".sh"} else "Documents"
    else:
        category = EXTENSION_CATEGORY_MAP.get(ext, "Other")

    # Name derivation: prefer heading if present, otherwise clean stem
    is_generic_stem = stem.lower() in ("untitled", "document", "file", "notes", "draft", "temp", "scratch")
    if heading_title and (is_generic_stem or len(heading_title) <= 45):
        candidate_name = heading_title
    else:
        candidate_name = stem

    kebab_name = sanitize_kebab_name(candidate_name, fallback_original=stem)
    return category, kebab_name


def fallback_classification(file_path: Path, reason_note: str = "") -> dict:
    """Generates an intelligent rule-based fallback proposal when model cannot process the file."""
    category, kebab_name = infer_category_and_name_from_rules(file_path)
    note = f" ({reason_note})" if reason_note else ""

    return {
        "new_name": kebab_name,
        "category": category,
        "reason": f"Classified by keyword or extension rule{note}.",
        "confidence": "low" if reason_note else "med",
        "classification_type": "fallback" if reason_note else "extension"
    }


def analyze_single_file(file_path: Path, model: str = DEFAULT_MODEL, log_debug: bool = True) -> dict:
    """Analyzes a single file using Ollama or rules based on extension."""
    file_start_time = time.time()
    model_called = False
    raw_response = None
    fallback_reason = None
    ext = file_path.suffix.lower()
    file_type = ext or "none"

    # Check for 0-byte file
    try:
        if file_path.stat().st_size == 0:
            raw_proposal = fallback_classification(file_path, "Empty file (0 bytes)")
            proposal, s_date, c_corr = post_process_proposal(
                file_path, raw_proposal["new_name"], raw_proposal["category"],
                raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
            )
            fallback_reason = "other"
            if log_debug:
                log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
            return proposal
    except Exception:
        raw_proposal = fallback_classification(file_path, "File unreadable")
        proposal, s_date, c_corr = post_process_proposal(
            file_path, raw_proposal["new_name"], raw_proposal["category"],
            raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
        )
        fallback_reason = "other"
        if log_debug:
            log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
        return proposal

    # Case A: Images
    if ext in IMAGE_EXTENSIONS:
        try:
            b64_img = prepare_image_b64(file_path)
        except MissingDependencyError as e:
            fallback_reason = "missing_dependency"
            raw_proposal = fallback_classification(file_path, f"Missing dependency: {e.package_name}")
            proposal, s_date, c_corr = post_process_proposal(
                file_path, raw_proposal["new_name"], raw_proposal["category"],
                raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
            )
            if log_debug:
                log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
            return proposal

        if b64_img:
            prompt = (
                f"Analyze image '{file_path.name}'. Propose descriptive lowercase-kebab-case name, "
                "category (Screenshots, Documents, Receipts-Bills, Study-Notes, Code, Images, Media, Archives, Other), "
                "and confidence (high, med, low)."
            )
            retry_prompt = f"Name this image '{file_path.name}' and pick category. Return JSON."
            model_called = True
            result, raw_response, call_err = call_gemma_model_detailed(prompt, image_b64=b64_img, model=model, fallback_prompt=retry_prompt)
            if result:
                raw_name = result.get("new_name") or file_path.stem
                cat = result.get("category", "Images")
                reason = str(result.get("reason", "Visual content analyzed by local Gemma model."))
                conf = str(result.get("confidence", "med"))

                proposal, s_date, c_corr = post_process_proposal(
                    file_path, raw_name, cat, reason, conf, "model"
                )
                fallback_reason = None
                if log_debug:
                    log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
                return proposal
            else:
                fallback_reason = call_err if call_err else "other"
        else:
            fallback_reason = "other"

        raw_proposal = fallback_classification(file_path, "Could not load image for vision analysis")
        proposal, s_date, c_corr = post_process_proposal(
            file_path, raw_proposal["new_name"], raw_proposal["category"],
            raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
        )
        if log_debug:
            log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
        return proposal

    # Case B: Text / Documents
    if ext in TEXT_EXTENSIONS or ext in PDF_EXTENSIONS or ext in DOCX_EXTENSIONS or not ext:
        try:
            text_snippet = extract_text_from_file(file_path)
        except MissingDependencyError as e:
            fallback_reason = "missing_dependency"
            raw_proposal = fallback_classification(file_path, f"Missing dependency: {e.package_name}")
            proposal, s_date, c_corr = post_process_proposal(
                file_path, raw_proposal["new_name"], raw_proposal["category"],
                raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
            )
            if log_debug:
                log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
            return proposal

        if text_snippet:
            prompt = (
                f"Analyze '{file_path.name}'.\nExcerpt:\n{text_snippet}\n"
                "Propose descriptive lowercase-kebab-case name, category, confidence (high, med, low)."
            )
            retry_prompt = f"Classify file '{file_path.name}'. Excerpt: {text_snippet[:150]}. Return JSON."
            model_called = True
            result, raw_response, call_err = call_gemma_model_detailed(prompt, image_b64=None, model=model, fallback_prompt=retry_prompt)
            if result:
                raw_name = result.get("new_name") or file_path.stem
                cat = result.get("category", "Documents")
                reason = str(result.get("reason", "Text excerpt analyzed by local Gemma model."))
                conf = str(result.get("confidence", "med"))

                proposal, s_date, c_corr = post_process_proposal(
                    file_path, raw_name, cat, reason, conf, "model", extracted_text=text_snippet
                )
                fallback_reason = None
                if log_debug:
                    log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
                return proposal
            else:
                fallback_reason = call_err if call_err else "other"
        else:
            fallback_reason = "other"

        raw_proposal = fallback_classification(file_path, "No extractable text found")
        proposal, s_date, c_corr = post_process_proposal(
            file_path, raw_proposal["new_name"], raw_proposal["category"],
            raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
        )
        if log_debug:
            log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
        return proposal

    # Case C: Media, Archives, Binaries, etc. (No model call needed by design)
    raw_proposal = fallback_classification(file_path, "")
    proposal, s_date, c_corr = post_process_proposal(
        file_path, raw_proposal["new_name"], raw_proposal["category"],
        raw_proposal["reason"], raw_proposal["confidence"], raw_proposal["classification_type"]
    )
    fallback_reason = None
    if log_debug:
        log_debug_entry(file_path.parent, file_path.name, file_type, model_called, raw_response, fallback_reason, time.time() - file_start_time, s_date, c_corr)
    return proposal


def resolve_collision(
    category: str,
    base_kebab_name: str,
    ext: str,
    assigned_names_by_cat: Dict[str, Set[str]],
    folder_root: Path
) -> str:
    """Ensures proposed name is unique within the category plan and does not conflict with existing files."""
    candidate = base_kebab_name
    counter = 2

    target_cat_dir = folder_root / category
    while True:
        full_filename = f"{candidate}{ext}"
        already_planned = full_filename in assigned_names_by_cat.get(category, set())
        already_on_disk = (target_cat_dir / full_filename).exists()

        if not already_planned and not already_on_disk:
            assigned_names_by_cat.setdefault(category, set()).add(full_filename)
            return candidate

        candidate = f"{base_kebab_name}-{counter}"
        counter += 1


async def stream_folder_analysis(
    folder_path: Path,
    file_list: List[Path],
    delay_ms: int = DEFAULT_DELAY_MS,
    model: str = DEFAULT_MODEL
) -> AsyncGenerator[str, None]:
    """Asynchronous generator that processes files ONE AT A TIME with a gentle delay

    and yields Server-Sent Events (SSE). Measures performance stats and emits a Sloth Report.
    """
    total = len(file_list)
    assigned_names: Dict[str, Set[str]] = {}
    completed_items: List[dict] = []

    # Emit initial start event
    start_payload = json.dumps({
        "event": "start",
        "total": total,
        "folder_path": str(folder_path)
    })
    yield f"data: {start_payload}\n\n"

    # Clear previous debug log for fresh diagnosis
    try:
        debug_log_file = folder_path / ".sloth_log" / "debug.jsonl"
        if debug_log_file.exists():
            debug_log_file.unlink()
    except Exception:
        pass

    overall_start_time = time.time()
    durations: List[float] = []
    slowest_file = ""
    slowest_duration = 0.0

    model_count = 0
    extension_count = 0
    fallback_count = 0

    for idx, file_path in enumerate(file_list, start=1):
        file_start = time.time()

        # 1. Gentle sloth delay (slow and steady, never hogging CPU/GPU)
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000.0)

        # 2. Run analysis synchronously in thread pool
        loop = asyncio.get_running_loop()
        proposal = await loop.run_in_executor(None, analyze_single_file, file_path, model)

        file_duration = time.time() - file_start
        durations.append(file_duration)
        if file_duration > slowest_duration:
            slowest_duration = file_duration
            slowest_file = file_path.name

        # Track classification counts
        ctype = proposal.get("classification_type", "model")
        if ctype == "model":
            model_count += 1
        elif ctype == "extension":
            extension_count += 1
        else:
            fallback_count += 1

        # 3. Resolve potential name collisions
        ext = file_path.suffix.lower()
        final_kebab = resolve_collision(
            proposal["category"],
            proposal["new_name"],
            ext,
            assigned_names,
            folder_path
        )
        proposal["new_name"] = final_kebab

        # 4. Compute metadata
        try:
            size_bytes = file_path.stat().st_size
        except Exception:
            size_bytes = 0

        try:
            rel_path = str(file_path.relative_to(folder_path)).replace("\\", "/")
        except Exception:
            rel_path = file_path.name

        item_data = {
            "index": idx,
            "original": file_path.name,
            "relative_path": rel_path,
            "new_name": proposal["new_name"],
            "extension": ext,
            "category": proposal["category"],
            "reason": proposal["reason"],
            "confidence": proposal.get("confidence", "high"),
            "classification_type": ctype,
            "duration_sec": round(file_duration, 2),
            "size_bytes": size_bytes,
            "size_human": format_size_human(size_bytes),
            "is_image": ext in IMAGE_EXTENSIONS,
        }
        completed_items.append(item_data)

        # 5. Yield progress event
        progress_payload = json.dumps({
            "event": "progress",
            "current": idx,
            "total": total,
            "percent": int((idx / total) * 100) if total > 0 else 100,
            "item": item_data
        })
        yield f"data: {progress_payload}\n\n"

    total_duration = time.time() - overall_start_time
    avg_duration = (total_duration / total) if total > 0 else 0.0

    sloth_report = {
        "total_files": total,
        "total_duration_sec": round(total_duration, 2),
        "avg_duration_sec": round(avg_duration, 2),
        "slowest_file": slowest_file,
        "slowest_duration_sec": round(slowest_duration, 2),
        "model_classified": model_count,
        "extension_only": extension_count,
        "fallback_count": fallback_count,
        "offline_guarantee": "0 bytes sent to the internet"
    }

    # Send final completion event with complete report
    done_payload = json.dumps({
        "event": "done",
        "total": total,
        "items": completed_items,
        "report": sloth_report
    })
    yield f"data: {done_payload}\n\n"
