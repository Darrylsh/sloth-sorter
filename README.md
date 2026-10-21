# 🦥 Sloth Sorter

> **"Does the chore so you don't have to. Slowly."**

Sloth Sorter is an offline desktop web application that organizes messy folders using local multimodal AI (**Gemma 3:4B** running via **Ollama**). By processing files **sequentially, one by one, with a gentle pacing delay**, it brings order to chaotic downloads, desktops, and project dumps without bogging down your machine—designed specifically to run comfortably on everyday laptops with zero data ever leaving your device.

![Sloth Sorter Demo](docs/demo.gif)

---

## 💻 Tested On
- **Hardware**: NVIDIA GeForce RTX 3050 Laptop GPU (4GB VRAM), 16GB RAM
- **Operating System**: Windows 11
- **Model**: `gemma3:4b` running locally via Ollama
- **Python Requirement**: Python 3.9+

---

## 📊 Measured Benchmark Results
These numbers are taken directly from actual benchmark runs on the repository's 26-file test set (`sample_mess`):

- **Dataset**: 26 files (PDFs, DOCX documents, code scripts, screenshots, receipts, notes, and photos)
- **Fallbacks**: **0 fallbacks (0.0%)** — all files processed successfully
- **Pacing & Speed**:
  - **First file**: ~23s (initial cold-start to load 4B model weights into VRAM; subsequent runs can use the **Wake The Sloth** warm-up button to preload weights)
  - **Subsequent files**: **~4.0s average per file** after model warm-up (3.0s – 5.9s per file)
  - **Total batch time**: ~118s for 26 files
- **Accuracy**: **96.2% category agreement (25/26)** on our self-labeled 26-file test set.
  *(Note: This is evaluated on our own self-labeled benchmark, not a generalized accuracy claim across arbitrary personal files. The single discrepancy was a corporate financial review document filed under `Receipts-Bills` rather than `Documents` due to dense revenue and margin metrics).*
- **Data Privacy**: **0 bytes sent to the internet**. Completely local.

---

## 🔒 Why Local & Open-Weight?

- **Absolute Privacy**: Desktop folders harbor sensitive bank invoices, tax PDFs, Slack chats, personal photos, and proprietary code. Sloth Sorter runs 100% on your machine—**0 bytes are sent to the internet**.
- **Completely Offline**: Sort your files on flights, trains, or off-grid cabins without an internet connection.
- **Free After Setup**: No recurring cloud subscriptions, metered per-token billing, or sudden rate-limit throttling.
- **Model Flexibility**: Built on open standards. Want to benchmark another model like `phi3:latest`, `llama3.2-vision`, or a specialized fine-tune? Just set an environment variable (`SLOTH_MODEL=...`)—zero code modifications required.

---

## 🏗️ How It Works

```text
  [ Messy Folder ]
         │
         ▼
  [ 🦥 File Scanner ] ──(Skips hidden files, .sloth_log, & existing category folders)
         │
         ▼
  [ Sequential Queue ] ──(Processes 1 file at a time; gentle configurable pause)
         │
    ┌────┴───────────────────────────────┐
    │                                    │
 [Images]                            [Text/Docs]
    │                                    │
    ▼                                    ▼
 (Pillow Resize ≤640px)          (Extract first 800 chars)
    │                                    │
    └────────────────┬───────────────────┘
                     │
                     ▼
          [ 🧠 Gemma 3:4B via Ollama ]
          (JSON schema constrained grammar decoding)
                     │
                     ▼
        [ Post-Processing & Validation ]
        ├── Date verification (strips unverified invented dates)
        ├── Deterministic corrections (.sql/.py -> Code, screenshots -> Screenshots)
        └── Honest confidence adjustment (low for memes/avatars, med for photos)
                     │
                     ▼
        [ Interactive UI Preview ] ──(Live Server-Sent Events stream)
        (User reviews, edits inline, approves or skips)
                     │
                     ▼
      [ Safe Move to Category Subfolder ] ──(Collision resolution -2, -3; logged to .sloth_log)
                     │
                     ▼
             [ ⏪ 1-Click Undo ]
```

---

## ⚡ Quickstart Setup in 4 Steps

### 1. Requirements
- **Python**: 3.9+
- **Ollama**: Installed from [ollama.com](https://ollama.com) and running (`ollama serve`).

### 2. Pull the Multimodal Gemma Model
```bash
ollama pull gemma3:4b
```

### 3. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/sloth-sorter.git
cd sloth-sorter
python -m pip install -r requirements.txt
```

### 4. Launch Sloth Sorter
```bash
python -m uvicorn app.main:app --reload
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser!

*(Optional: Run `python make_sample_mess.py` to create a realistic test folder with 26 sample files, or `python eval/run_eval.py` to run the evaluation suite).*

---

## 📸 Screenshots & Previews

### Dashboard & Interactive Approval
Review proposed kebab-case names, colored category chips, and reasoning before any file moves:
![Preview Dashboard](docs/screenshot-preview.png)

### The Sloth Report
Real-time breakdown of analysis duration, average pace, slowest file, and model vs. fallback counts:
![Sloth Report](docs/screenshot-report.png)

---

## ⚠️ Known Limitations (Honest)

1. **Slow First File**: The first file analyzed takes ~20–25s because Ollama must load model weights into VRAM. Subsequent files take ~4s. You can click **"Wake The Sloth"** in the UI to trigger a background warm-up before beginning analysis.
2. **Small 4B Model Judgments**: A 4B parameter model can occasionally misjudge ambiguous files (for example, categorizing a quarterly financial review under `Receipts-Bills` rather than `Documents`).
3. **Calibrated Confidence**: Decorative avatars, memes, and photos receive `low` or `med` confidence ratings by design to flag them for human review in the UI.
4. **Folder Depth**: Only top-level files in the selected directory are scanned by default, unless the **Recursive Scan** toggle is enabled in the UI.
5. **Vision & OCR**: There is no standalone OCR engine beyond what the multimodal vision model reads directly from resized images (max 640px dimension).
6. **Binary & Large Files**: Files over 20MB or unsupported archive/binary formats (`.iso`, `.exe`) bypass model inference and are categorized by file extension only.

---

## 🛡️ Safety Guarantees

1. **Dry-Run Mindset**: Analysis never touches or renames your files. Nothing moves until you explicitly click **Apply**.
2. **Never Overwrites**: If a file named `invoice-2026-10-18.pdf` already exists in the destination folder, Sloth Sorter automatically resolves collisions by appending `-2`, `-3`, etc.
3. **Never Deletes**: Files are only moved (`shutil.move`), never deleted or trashed.
4. **Path Traversal Protection**: All paths are validated and confined strictly within the user-selected root.
5. **Reversible (1-Click Undo)**: Every move is recorded in `<folder>/.sloth_log/run-<timestamp>.json`. Clicking **Undo** restores every file to its exact original path and cleans up any empty category directories.

---

## ⚙️ Configuration & Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SLOTH_MODEL` | `gemma3:4b` | Ollama model identifier to use for analysis |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint host |

---

## 🧪 Testing

Sloth Sorter includes an automated pytest suite covering health checks, missing dependency detection, path traversal safety, name sanitization, date stripping, deterministic category rules, and roundtrip undo operations:

```bash
pytest
```

---

## 📄 License

Distributed under the [MIT License](LICENSE).
