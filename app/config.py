"""Configuration, category definitions, and prompt templates for Sloth Sorter."""
import os
from typing import Dict, List, Set

# Model & Host Configuration (configurable via environment variables)
DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("SLOTH_MODEL", "gemma3:4b")

# Ollama performance and memory options for local laptops (RTX 3050 4GB VRAM)
OLLAMA_KEEP_ALIVE = "10m"   # Keep weights in VRAM between sequential files
OLLAMA_NUM_CTX = 4096       # Keep context window compact to minimize VRAM usage

# Pacing and Limits
DEFAULT_DELAY_MS = 300
MAX_IMAGE_DIMENSION = 640
MAX_TEXT_SNIPPET_LENGTH = 800
MAX_FILENAME_LENGTH = 60

# Model generation options for fast, constrained responses
OLLAMA_TIMEOUT = 60.0
OLLAMA_TEMPERATURE = 0.15
OLLAMA_NUM_PREDICT = 120

# Allowed Categories
ALLOWED_CATEGORIES: List[str] = [
    "Screenshots",
    "Documents",
    "Receipts-Bills",
    "Study-Notes",
    "Code",
    "Images",
    "Media",
    "Archives",
    "Other",
]

# JSON schema for Ollama structured output
OLLAMA_JSON_SCHEMA: Dict = {
    "type": "object",
    "properties": {
        "new_name": {
            "type": "string",
            "description": "Descriptive lowercase-kebab-case name without file extension (max 60 chars)"
        },
        "category": {
            "type": "string",
            "enum": ALLOWED_CATEGORIES,
            "description": "One of the allowed categories"
        },
        "reason": {
            "type": "string",
            "description": "One sentence explanation"
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "med", "low"],
            "description": "Confidence level"
        }
    },
    "required": ["new_name", "category", "reason", "confidence"]
}

# File extension groupings (lowercase)
IMAGE_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".svg"}

TEXT_EXTENSIONS: Set[str] = {
    ".txt", ".md", ".markdown", ".csv", ".tsv",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".xml", ".sql", ".sh", ".bash",
    ".bat", ".ps1", ".c", ".cpp", ".h", ".hpp", ".rs", ".go",
    ".java", ".kt", ".rb", ".php", ".env", ".toml", ".ini",
    ".log", ".conf", ".cfg"
}

PDF_EXTENSIONS: Set[str] = {".pdf"}
DOCX_EXTENSIONS: Set[str] = {".docx"}

MEDIA_EXTENSIONS: Set[str] = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
    ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm"
}

ARCHIVE_EXTENSIONS: Set[str] = {
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".iso"
}

EXTENSION_CATEGORY_MAP: Dict[str, str] = {
    **{ext: "Media" for ext in MEDIA_EXTENSIONS},
    **{ext: "Archives" for ext in ARCHIVE_EXTENSIONS},
    ".exe": "Other",
    ".msi": "Other",
    ".dmg": "Other",
    ".apk": "Other",
    ".bin": "Other",
    ".dat": "Other",
}

# Protected folders and system items to ignore
IGNORED_FOLDER_NAMES: Set[str] = {
    ".sloth_log",
    ".sloth_trash",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".gemini",
    ".idea",
    ".vscode",
    ".pytest_cache",
}

# Concise prompt with 2 compact few-shot examples and strict date/confidence guidelines
ANALYSIS_SYSTEM_PROMPT = """You are Sloth Sorter. Propose a clean file name, category, and confidence level based on file contents.

CATEGORIES (pick one):
- Screenshots: captured screen images (UI, chats, errors, dashboards, window chrome)
- Documents: contracts, agreements, reports, resumes, letters (.pdf, .docx, .pptx)
- Receipts-Bills: receipts, invoices, utility bills, financial statements
- Study-Notes: lecture notes, summaries, study guides, todo lists, meeting minutes
- Code: source code, scripts, database schemas/dumps (.py, .js, .ts, .sh, .sql)
- Images: photos, art, memes, wallpapers, avatars
- Media: audio and video files (.mp3, .mp4, etc.)
- Archives: archive packages only (.zip, .tar, .gz, .7z, .rar)
- Other: last resort only when no other category fits

RULES:
1. new_name: lowercase-kebab-case, max 60 chars, no file extension.
2. DATES: Only include a date if it is clearly visible in the content. Never invent or guess a date. If there is no visible date, omit it.
3. confidence: Use "high" only when content clearly and unambiguously identifies the file. Use "med" when partially recognized. Use "low" when content is ambiguous, blurry, tiny, or decorative.
4. Return valid JSON strictly matching schema.

EXAMPLES:
Input: Receipt from Nebula Coffee for 4.50 galactic credits.
Output: {"new_name": "nebula-coffee-receipt", "category": "Receipts-Bills", "reason": "Receipt from Nebula Coffee.", "confidence": "high"}

Input: Python file defining FastAPI endpoints /ping and /health.
Output: {"new_name": "fastapi-health-service", "category": "Code", "reason": "Python script implementing FastAPI service with health check routes.", "confidence": "high"}
"""

