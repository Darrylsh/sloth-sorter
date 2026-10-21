"""FastAPI Application for Sloth Sorter.

Provides API endpoints for health inspection, folder scanning, SSE-streamed
AI analysis, plan application, and undo operations.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.analyzer import format_size_human, stream_folder_analysis
from app.config import DEFAULT_DELAY_MS, DEFAULT_MODEL, DEFAULT_OLLAMA_HOST, IMAGE_EXTENSIONS
from app.organizer import apply_organization_plan, list_past_runs, scan_folder_files, undo_run
from app.safety import ensure_inside_folder, validate_and_resolve_folder

import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sloth_sorter.main")


def check_dependencies() -> dict:
    """Checks availability of key runtime libraries: pypdf, python-docx, Pillow, and ollama."""
    deps = {
        "pypdf": False,
        "python-docx": False,
        "Pillow": False,
        "ollama": False
    }
    try:
        import pypdf
        deps["pypdf"] = True
    except ImportError:
        pass

    try:
        import docx
        deps["python-docx"] = True
    except ImportError:
        pass

    try:
        import PIL
        deps["Pillow"] = True
    except ImportError:
        pass

    try:
        import ollama
        deps["ollama"] = True
    except ImportError:
        pass

    return deps


# Startup logging
logger.info(f"Sloth Sorter Python interpreter: {sys.executable} (version {sys.version.split()[0]})")
_startup_deps = check_dependencies()
_missing_startup = [p for p, ok in _startup_deps.items() if not ok]
if _missing_startup:
    logger.warning(
        f"Missing required packages: {', '.join(_missing_startup)}. "
        f"Run: {sys.executable} -m pip install {' '.join(_missing_startup)}"
    )
else:
    logger.info("All required dependencies (pypdf, python-docx, Pillow, ollama) are installed and importable.")

app = FastAPI(
    title="Sloth Sorter",
    description="Gentle, local AI-powered folder organizer using Gemma 3:4B via Ollama.",
    version="1.0.0"
)

# CORS middleware for development ease
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static paths
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    folder_path: str = Field(..., description="Absolute or relative folder path to scan")
    recursive: bool = Field(False, description="Whether to scan subdirectories recursively")


class PlanItem(BaseModel):
    original: str = Field(..., description="Original filename or relative path")
    new_name: str = Field(..., description="Proposed new name without extension")
    category: str = Field(..., description="Target category folder")


class ApplyRequest(BaseModel):
    folder_path: str = Field(..., description="Folder path being organized")
    plan: List[PlanItem] = Field(..., description="Approved list of file reorganization operations")
    report: Optional[dict] = Field(None, description="Sloth report statistics from analysis")


class UndoRequest(BaseModel):
    folder_path: str = Field(..., description="Folder path containing the .sloth_log")
    run_id: str = Field(..., description="Identifier of the run to undo")


class AnalyzeRequest(BaseModel):
    folder_path: str
    delay_ms: int = DEFAULT_DELAY_MS
    recursive: bool = False


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Checks if local Ollama server is running, gemma3:4b is pulled, and runtime dependencies are importable."""
    deps = check_dependencies()
    missing_deps = [pkg for pkg, ok in deps.items() if not ok]
    fix_cmd = f"{sys.executable} -m pip install {' '.join(missing_deps)}" if missing_deps else None

    ollama_reachable = False
    model_ready = False
    ollama_err = None
    tip = None

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{DEFAULT_OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                ollama_reachable = True
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                model_ready = any(DEFAULT_MODEL in m or m.startswith("gemma3:4b") for m in models)
                if not model_ready:
                    ollama_err = f"Ollama is running, but model '{DEFAULT_MODEL}' is not pulled."
                    tip = f"Open terminal and run: ollama pull {DEFAULT_MODEL}"
            else:
                ollama_reachable = True
                ollama_err = f"Ollama returned HTTP status {resp.status_code}."
                tip = "Check Ollama server health."
    except Exception as e:
        ollama_reachable = False
        ollama_err = f"Cannot reach Ollama at {DEFAULT_OLLAMA_HOST}: {str(e)}"
        tip = "Ensure Ollama is started by running: ollama serve"

    if not ollama_reachable or not model_ready:
        status = "error" if not ollama_reachable else "degraded"
        error_msg = ollama_err
    elif missing_deps:
        status = "degraded"
        error_msg = f"Missing dependencies: {', '.join(missing_deps)}. Run: {fix_cmd}"
        tip = f"Run: {fix_cmd}"
    else:
        status = "ok"
        error_msg = None
        tip = "Sloth is awake and ready to organize."

    return {
        "status": status,
        "ollama_reachable": ollama_reachable,
        "model_ready": model_ready,
        "model_name": DEFAULT_MODEL,
        "dependencies": deps,
        "missing_dependencies": missing_deps,
        "fix_command": fix_cmd,
        "error_message": error_msg,
        "tip": tip
    }


@app.post("/api/warmup")
async def warmup_endpoint():
    """Warms up local Ollama Gemma model so the first processed file has no cold-start delay."""
    from app.analyzer import warmup_model
    import asyncio
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(None, warmup_model, DEFAULT_MODEL)
    return {
        "warmed_up": success,
        "model": DEFAULT_MODEL
    }


@app.post("/api/scan")
async def scan_folder(req: ScanRequest):
    """Scans the specified folder and returns candidates to organize."""
    try:
        resolved_folder = validate_and_resolve_folder(req.folder_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    files = scan_folder_files(resolved_folder, recursive=req.recursive)

    file_metadata = []
    for f in files:
        try:
            size_b = f.stat().st_size
        except Exception:
            size_b = 0

        ext = f.suffix.lower()
        rel = str(f.relative_to(resolved_folder)).replace("\\", "/")
        file_metadata.append({
            "name": f.name,
            "relative_path": rel,
            "size_bytes": size_b,
            "size_human": format_size_human(size_b),
            "extension": ext,
            "is_image": ext in IMAGE_EXTENSIONS
        })

    return {
        "folder_path": str(resolved_folder),
        "count": len(files),
        "files": file_metadata
    }


@app.get("/api/analyze")
async def analyze_folder_sse(
    folder_path: str = Query(..., description="Target folder path"),
    delay_ms: int = Query(DEFAULT_DELAY_MS, description="Pacing delay in milliseconds"),
    recursive: bool = Query(False, description="Scan subfolders recursively")
):
    """Streams file-by-file AI analysis via Server-Sent Events (SSE)."""
    try:
        resolved_folder = validate_and_resolve_folder(folder_path)
    except Exception as e:
        async def error_stream():
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    files = scan_folder_files(resolved_folder, recursive=recursive)

    generator = stream_folder_analysis(
        folder_path=resolved_folder,
        file_list=files,
        delay_ms=max(0, delay_ms),
        model=DEFAULT_MODEL
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/analyze")
async def analyze_folder_sse_post(req: AnalyzeRequest):
    """POST alternative for SSE analysis if requested with JSON body."""
    return await analyze_folder_sse(
        folder_path=req.folder_path,
        delay_ms=req.delay_ms,
        recursive=req.recursive
    )


@app.post("/api/apply")
async def apply_plan(req: ApplyRequest):
    """Moves and renames files into category folders as confirmed by the user."""
    try:
        resolved_folder = validate_and_resolve_folder(req.folder_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    plan_dicts = [item.model_dump() for item in req.plan]

    try:
        result = apply_organization_plan(resolved_folder, plan_dicts, report=req.report)
        return result
    except Exception as e:
        logger.error(f"Failed to apply organization plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to apply plan: {str(e)}")


@app.get("/api/runs")
async def get_runs(folder_path: str = Query(..., description="Folder path to check history for")):
    """Returns past runs recorded in .sloth_log for this folder."""
    try:
        resolved_folder = validate_and_resolve_folder(folder_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    runs = list_past_runs(resolved_folder)
    return {
        "folder_path": str(resolved_folder),
        "runs": runs
    }


@app.post("/api/undo")
async def undo_past_run(req: UndoRequest):
    """Reverses the moves made in a past run and cleans up empty category folders."""
    try:
        resolved_folder = validate_and_resolve_folder(req.folder_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = undo_run(resolved_folder, req.run_id)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to undo run {req.run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to undo run: {str(e)}")


@app.get("/api/thumbnail")
async def get_thumbnail(
    folder_path: str = Query(...),
    relative_path: str = Query(...)
):
    """Safely serves image preview thumbnail for images in the folder."""
    try:
        resolved_folder = validate_and_resolve_folder(folder_path)
        file_path = (resolved_folder / relative_path).resolve()
        ensure_inside_folder(file_path, resolved_folder)

        if not file_path.exists() or file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            raise HTTPException(status_code=404, detail="Image not found")

        return FileResponse(
            path=str(file_path),
            headers={"Cache-Control": "public, max-age=3600"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Static frontend mounting
# ---------------------------------------------------------------------------

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return HTMLResponse("<h1>Sloth Sorter Frontend Initializing...</h1>")
