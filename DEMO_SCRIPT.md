# 🎥 Sloth Sorter — 60–90 Second Screen Recording Demo Script

This script walks through an engaging, crisp 60–90 second product demonstration of **Sloth Sorter** using the included `sample_mess` folder.

---

## 🎬 Pre-Recording Setup (5 seconds before hitting Record)
1. Run `python make_sample_mess.py` in your terminal to ensure `sample_mess/` is populated with 26 fresh sample files.
2. Ensure Ollama is running (`ollama serve`).
3. Open `http://localhost:8000` in your browser. Verify the green badge: **"Gemma 3:4B Ready (Ollama)"**.
4. Set browser zoom to 100% (clean 1920x1080 or 1366x768 layout).

---

## ⏱️ Timeline & Script

### [00:00 - 00:15] The Hook & The Problem
- **Action**: Mouse hover over the sleeping sloth mascot and the tagline. Point at the folder input.
- **Voiceover**:
  > *"Every developer and power user has that one chaotic desktop or downloads folder full of random screenshots, cryptic bills, and half-baked code files. Moving them to the cloud for AI sorting risks your privacy and costs money. Meet **Sloth Sorter**—an offline desktop organizer powered 100% locally by Google's Gemma 3:4B through Ollama."*

---

### [00:15 - 00:35] Waking The Sloth (Analysis in Action)
- **Action**:
  1. Click **"⚡ Quick Demo: Use sample_mess"**.
  2. Point at the folder input now filled with `sample_mess`.
  3. Click **"🦥 Wake The Sloth"**.
- **Visuals**: The sloth's eyes open, the vine progress bar smoothly crawls forward with the sloth head, and cards begin streaming in sequentially one by one via Server-Sent Events.
- **Voiceover**:
  > *"True to its name, Sloth Sorter operates 'slow and steady'—processing files strictly one at a time with a gentle delay so it never hogs your GPU or freezes your laptop. For screenshots, it resizes the image and visually inspects it. For PDFs, Word documents, and code, it reads the text and extracts key details like dates and vendors."*

---

### [00:35 - 00:55] Interactive Review & Inline Tweak
- **Action**:
  1. Filter by clicking the **"Receipts-Bills"** category chip. Show how `electric_bill_unpaid_urgent.txt` became `electric-bill-2026-11-05.txt`.
  2. Click the **"Screenshots"** category chip. Click a thumbnail to pop open the high-res image modal preview, then press **Esc** to close.
  3. Click the pencil icon on one card and tweak the name inline (e.g. add `-reviewed`).
  4. Point out the confidence badges (`high`, `med`, `low`).
- **Voiceover**:
  > *"You are always in total control. The dry-run preview lets you inspect the AI's proposed lowercase-kebab-case names, colored category chips, and reasoning. You can filter by category, preview image thumbnails, or edit any proposed name inline."*

---

### [00:55 - 01:15] The Sloth Report & Zero Data Loss
- **Action**:
  1. Scroll up to show the **Sloth Report card** showing total time, average speed per file, slowest file, and the badge: **"🔒 0 bytes sent to the internet"**.
  2. Click **"✨ Apply Organization"**. Click **OK** on the confirmation prompt.
  3. Watch the celebration card appear with category counts.
- **Voiceover**:
  > *"Check out the Sloth Report: complete breakdown of classification types, and an absolute guarantee that 0 bytes left your machine. When you're ready, click Apply. Sloth Sorter moves each file into neat category subfolders without ever deleting or overwriting."*

---

### [01:15 - 01:30] 1-Click Undo & Wrap-Up
- **Action**:
  1. Click **"⏪ Undo This Run"**.
  2. Show that all files are instantly restored to their exact original locations and empty category folders are cleaned up.
  3. Scroll down to show the Past Runs list with the collapsible Sloth Report.
- **Voiceover**:
  > *"Made a mistake? Just click 'Undo This Run', and every single file is restored to its exact original path. Sloth Sorter: does the chore so you don't have to. Slowly, privately, and reliably. Give it a spin on GitHub!"*

---

## 🎯 Recording Tips
- **Pacing**: Speak at a relaxed, friendly tempo—embrace the sloth persona!
- **Resolution**: Record at 1080p 60fps with clear audio.
- **Key Highlight**: Emphasize that it's running on local hardware (e.g. RTX 3050 laptop GPU) with zero cloud dependencies.
