/**
 * Sloth Sorter — Frontend Client Logic
 * Single-Page Vanilla JavaScript Application (Zero Build Step)
 */

document.addEventListener("DOMContentLoaded", () => {
  // -------------------------------------------------------------------------
  // Application State
  // -------------------------------------------------------------------------
  const state = {
    folderPath: "",
    isAnalyzing: false,
    eventSource: null,
    totalFiles: 0,
    currentIndex: 0,
    proposals: [], // Array of item objects
    activeCategoryFilter: "ALL",
    allowedCategories: [
      "Screenshots",
      "Documents",
      "Receipts-Bills",
      "Study-Notes",
      "Code",
      "Images",
      "Media",
      "Archives",
      "Other",
    ],
    lastRunId: null,
    lastReport: null,
  };

  // -------------------------------------------------------------------------
  // DOM Elements
  // -------------------------------------------------------------------------
  const elements = {
    folderInput: document.getElementById("folder-input"),
    btnUseSample: document.getElementById("btn-use-sample"),
    btnScan: document.getElementById("btn-scan"),
    btnWake: document.getElementById("btn-wake"),
    wakeBtnLabel: document.getElementById("wake-btn-label"),
    chkRecursive: document.getElementById("chk-recursive"),
    rangeDelay: document.getElementById("range-delay"),
    lblDelay: document.getElementById("lbl-delay"),

    // Health
    healthBadge: document.getElementById("health-badge"),
    healthText: document.getElementById("health-text"),
    themeToggle: document.getElementById("theme-toggle"),
    themeIcon: document.getElementById("theme-icon"),

    // Mascot
    slothSvg: document.getElementById("sloth-svg"),
    eyesSleeping: document.getElementById("eyes-sleeping"),
    eyesAwake: document.getElementById("eyes-awake"),
    eyesHappy: document.getElementById("eyes-happy"),
    sleepBubbles: document.getElementById("sleep-bubbles"),
    slothSpeech: document.getElementById("sloth-speech"),

    // Progress
    progressSection: document.getElementById("progress-section"),
    progressText: document.getElementById("progress-text"),
    progressCounter: document.getElementById("progress-counter"),
    progressPercent: document.getElementById("progress-percent"),
    progressFill: document.getElementById("progress-fill"),

    // Sloth Report
    slothReportCard: document.getElementById("sloth-report-card"),
    btnCloseReport: document.getElementById("btn-close-report"),
    repTotalFiles: document.getElementById("rep-total-files"),
    repTotalTime: document.getElementById("rep-total-time"),
    repAvgTime: document.getElementById("rep-avg-time"),
    repSlowestTime: document.getElementById("rep-slowest-time"),
    repSlowestLabel: document.getElementById("rep-slowest-label"),
    repModelCount: document.getElementById("rep-model-count"),
    repExtCount: document.getElementById("rep-ext-count"),
    repFallbackCount: document.getElementById("rep-fallback-count"),

    // Preview
    previewSection: document.getElementById("preview-section"),
    categoryFilterBar: document.getElementById("category-filter-bar"),
    catCountAll: document.getElementById("cat-count-all"),
    proposalsList: document.getElementById("proposals-list"),
    btnSelectAll: document.getElementById("btn-select-all"),
    btnDeselectAll: document.getElementById("btn-deselect-all"),
    btnApply: document.getElementById("btn-apply"),
    applyBtnText: document.getElementById("apply-btn-text"),
    stickyApplyBar: document.getElementById("sticky-apply-bar"),
    btnStickyApply: document.getElementById("btn-sticky-apply"),
    stickySelectedCount: document.getElementById("sticky-selected-count"),

    // Success Banner
    successBanner: document.getElementById("success-banner"),
    successTitle: document.getElementById("success-title"),
    successMessage: document.getElementById("success-message"),
    successStats: document.getElementById("success-stats"),
    btnUndoLatest: document.getElementById("btn-undo-latest"),
    btnSortAnother: document.getElementById("btn-sort-another"),

    // History
    historySection: document.getElementById("history-section"),
    historyList: document.getElementById("history-list"),
    historyCountBadge: document.getElementById("history-count-badge"),
    btnRefreshHistory: document.getElementById("btn-refresh-history"),

    // Image Modal
    imageModal: document.getElementById("image-modal"),
    modalImg: document.getElementById("modal-img"),
    modalCaption: document.getElementById("modal-caption"),
    modalClose: document.getElementById("modal-close"),

    // Toast Container
    toastContainer: document.getElementById("toast-container"),
  };

  // -------------------------------------------------------------------------
  // Toast Notifications
  // -------------------------------------------------------------------------
  function showToast(message, type = "info", duration = 4000) {
    if (!elements.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    const icon = type === "error" ? "❌" : type === "success" ? "✅" : "ℹ️";
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      setTimeout(() => toast.remove(), 250);
    }, duration);
  }

  // -------------------------------------------------------------------------
  // Theme Management
  // -------------------------------------------------------------------------
  function initTheme() {
    const savedTheme = localStorage.getItem("sloth_theme") || "forest-dark";
    document.body.className = savedTheme;
    updateThemeIcon(savedTheme);

    elements.themeToggle.addEventListener("click", () => {
      const isDark = document.body.classList.contains("forest-dark");
      const nextTheme = isDark ? "warm-meadow" : "forest-dark";
      document.body.className = nextTheme;
      localStorage.setItem("sloth_theme", nextTheme);
      updateThemeIcon(nextTheme);
    });
  }

  function updateThemeIcon(theme) {
    elements.themeIcon.textContent = theme === "forest-dark" ? "🌙" : "☀️";
  }

  // -------------------------------------------------------------------------
  // Sloth Mascot State Animations
  // -------------------------------------------------------------------------
  function setMascotState(stateName, speechText = null) {
    elements.slothSvg.classList.remove("state-sleeping", "state-awake", "state-happy");
    elements.eyesSleeping.style.display = "none";
    elements.eyesAwake.style.display = "none";
    elements.eyesHappy.style.display = "none";
    elements.sleepBubbles.style.display = "none";

    if (stateName === "sleeping") {
      elements.slothSvg.classList.add("state-sleeping");
      elements.eyesSleeping.style.display = "block";
      elements.sleepBubbles.style.display = "block";
      if (speechText) elements.slothSpeech.textContent = speechText;
    } else if (stateName === "awake") {
      elements.slothSvg.classList.add("state-awake");
      elements.eyesAwake.style.display = "block";
      if (speechText) elements.slothSpeech.textContent = speechText;
    } else if (stateName === "happy") {
      elements.slothSvg.classList.add("state-happy");
      elements.eyesHappy.style.display = "block";
      if (speechText) elements.slothSpeech.textContent = speechText;
    }
  }

  // -------------------------------------------------------------------------
  // Health Inspection
  // -------------------------------------------------------------------------
  let hasShownDepWarning = false;

  async function checkHealth() {
    try {
      const resp = await fetch("/api/health");
      const data = await resp.json();

      elements.healthBadge.className = "health-badge";
      if (data.missing_dependencies && data.missing_dependencies.length > 0) {
        elements.healthBadge.classList.add("degraded");
        elements.healthText.textContent = `Missing: ${data.missing_dependencies.join(", ")}`;
        elements.healthBadge.title = `Missing packages: ${data.missing_dependencies.join(", ")}. Fix command: ${data.fix_command}`;
        if (!hasShownDepWarning) {
          showToast(`⚠️ Missing packages: ${data.missing_dependencies.join(", ")}. Run: ${data.fix_command}`, "warning", 10000);
          hasShownDepWarning = true;
        }
      } else if (data.status === "ok") {
        elements.healthBadge.classList.add("ready");
        elements.healthText.textContent = "Gemma 3:4B Ready (Ollama)";
        elements.healthBadge.title = "Local multimodal model is online and ready.";
      } else if (data.status === "degraded") {
        elements.healthBadge.classList.add("degraded");
        elements.healthText.textContent = "Model degraded";
        elements.healthBadge.title = data.error_message || data.tip;
      } else {
        elements.healthBadge.classList.add("error");
        elements.healthText.textContent = "Ollama Offline";
        elements.healthBadge.title = data.error_message || "Start Ollama with: ollama serve";
      }
    } catch (e) {
      elements.healthBadge.className = "health-badge error";
      elements.healthText.textContent = "Backend Offline";
      elements.healthBadge.title = "Could not connect to Sloth Sorter server.";
    }
  }

  // -------------------------------------------------------------------------
  // Folder Pre-Fill & Scanning
  // -------------------------------------------------------------------------
  elements.btnUseSample.addEventListener("click", () => {
    elements.folderInput.value = "sample_mess";
    state.folderPath = "sample_mess";
    scanFolder();
    loadPastRuns();
  });

  elements.folderInput.addEventListener("change", () => {
    state.folderPath = elements.folderInput.value.trim();
    if (state.folderPath) {
      loadPastRuns();
    }
  });

  elements.rangeDelay.addEventListener("input", (e) => {
    elements.lblDelay.textContent = `${e.target.value}ms`;
  });

  elements.btnScan.addEventListener("click", () => {
    scanFolder();
  });

  // Keyboard accessibility: Enter key on folder input wakes the sloth
  elements.folderInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      elements.btnWake.click();
    }
  });

  async function scanFolder() {
    const path = elements.folderInput.value.trim();
    if (!path) {
      showToast("Please provide a folder path first.", "error");
      elements.folderInput.focus();
      return;
    }

    try {
      const resp = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: path,
          recursive: elements.chkRecursive.checked,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Failed to scan folder.");
      }

      setMascotState(
        "sleeping",
        `Found ${data.count} file(s) in "${data.folder_path}". Click 'Wake The Sloth' to inspect each one!`
      );
      state.folderPath = data.folder_path;
      elements.folderInput.value = data.folder_path;
      showToast(`Scanned ${data.count} candidate file(s).`, "info");
      loadPastRuns();
    } catch (err) {
      showToast(`Scan error: ${err.message}`, "error");
    }
  }

  // -------------------------------------------------------------------------
  // Sequential AI Analysis (SSE Streaming)
  // -------------------------------------------------------------------------
  elements.btnWake.addEventListener("click", () => {
    if (state.isAnalyzing) {
      stopAnalysis();
    } else {
      startAnalysis();
    }
  });

  function startAnalysis() {
    const path = elements.folderInput.value.trim();
    if (!path) {
      showToast("Please specify a folder path to sort.", "error");
      elements.folderInput.focus();
      return;
    }

    state.folderPath = path;
    state.isAnalyzing = true;
    state.proposals = [];
    state.currentIndex = 0;
    state.totalFiles = 0;
    state.lastReport = null;

    // UI Updates
    elements.wakeBtnLabel.textContent = "Pause Sloth";
    elements.btnWake.classList.add("btn-secondary");
    elements.btnWake.classList.remove("btn-primary");
    elements.progressSection.style.display = "block";
    elements.previewSection.style.display = "block";
    elements.slothReportCard.style.display = "none";
    elements.successBanner.style.display = "none";
    elements.proposalsList.innerHTML = "";
    elements.progressFill.style.width = "0%";
    elements.progressPercent.textContent = "0%";
    elements.progressCounter.textContent = "0 / ...";

    setMascotState("awake", "Sloth is awake! Carefully inspecting files one by one at gentle GPU load...");

    // Send gentle model warmup request so first file does not cold-start
    fetch("/api/warmup", { method: "POST" }).catch(() => {});

    // Setup SSE connection
    const delayMs = parseInt(elements.rangeDelay.value, 10) || 300;
    const recursive = elements.chkRecursive.checked;
    const sseUrl = `/api/analyze?folder_path=${encodeURIComponent(path)}&delay_ms=${delayMs}&recursive=${recursive}`;

    if (state.eventSource) {
      state.eventSource.close();
    }

    state.eventSource = new EventSource(sseUrl);

    state.eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleStreamEvent(payload);
      } catch (e) {
        console.error("Error parsing SSE event data:", e, event.data);
      }
    };

    state.eventSource.onerror = (err) => {
      console.warn("SSE stream ended or disconnected:", err);
      finishAnalysis();
    };
  }

  function stopAnalysis() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    finishAnalysis();
  }

  function finishAnalysis() {
    state.isAnalyzing = false;
    elements.wakeBtnLabel.textContent = "Wake The Sloth";
    elements.btnWake.classList.remove("btn-secondary");
    elements.btnWake.classList.add("btn-primary");

    setMascotState(
      "happy",
      `All done! I inspected ${state.proposals.length} file(s). Review the proposed names and categories below, then click Apply.`
    );
    elements.progressText.textContent = "Sloth has finished inspecting all files!";
    updateCategoryFilters();
    updateApplyButton();
  }

  function handleStreamEvent(payload) {
    if (payload.event === "start") {
      state.totalFiles = payload.total;
      elements.progressCounter.textContent = `0 / ${payload.total}`;
      elements.progressText.textContent = `Sloth is getting started on ${payload.total} file(s)...`;
    } else if (payload.event === "progress") {
      state.currentIndex = payload.current;
      const total = payload.total || state.totalFiles;
      const pct = payload.percent || Math.round((payload.current / total) * 100);

      elements.progressFill.style.width = `${pct}%`;
      elements.progressPercent.textContent = `${pct}%`;
      elements.progressCounter.textContent = `${payload.current} / ${total}`;
      elements.progressText.textContent = `Sloth is carefully inspecting file ${payload.current} of ${total}: "${payload.item.original}"`;

      // Add item to proposal state
      payload.item.selected = true;
      state.proposals.push(payload.item);

      // Render card
      renderProposalCard(payload.item);
      updateCategoryFilters();
      updateApplyButton();
    } else if (payload.event === "done") {
      state.lastReport = payload.report;
      renderSlothReport(payload.report);
      finishAnalysis();
    } else if (payload.event === "error") {
      showToast(`Analysis notice: ${payload.message}`, "error");
      // Keep partial results, do not wipe
      finishAnalysis();
    }
  }

  // -------------------------------------------------------------------------
  // Sloth Report Rendering
  // -------------------------------------------------------------------------
  function renderSlothReport(report) {
    if (!report) return;

    elements.repTotalFiles.textContent = report.total_files || state.proposals.length;
    elements.repTotalTime.textContent = `${report.total_duration_sec || 0}s`;
    elements.repAvgTime.textContent = `${report.avg_duration_sec || 0}s`;

    if (report.slowest_file) {
      elements.repSlowestTime.textContent = `${report.slowest_duration_sec}s`;
      elements.repSlowestLabel.title = `Slowest file: ${report.slowest_file}`;
      elements.repSlowestLabel.textContent =
        report.slowest_file.length > 22
          ? report.slowest_file.slice(0, 20) + "..."
          : report.slowest_file;
    } else {
      elements.repSlowestTime.textContent = "-";
      elements.repSlowestLabel.textContent = "Slowest File";
    }

    elements.repModelCount.textContent = `🤖 Model Classified: ${report.model_classified || 0}`;
    elements.repExtCount.textContent = `📁 Extension Only: ${report.extension_only || 0}`;
    elements.repFallbackCount.textContent = `⚠️ Rule Fallback: ${report.fallback_count || 0}`;

    elements.slothReportCard.style.display = "block";
  }

  elements.btnCloseReport.addEventListener("click", () => {
    elements.slothReportCard.style.display = "none";
  });

  // -------------------------------------------------------------------------
  // Proposal Cards Rendering & Inline Editing
  // -------------------------------------------------------------------------
  function renderProposalCard(item) {
    const card = document.createElement("div");
    card.className = "proposal-card";
    card.id = `card-${item.index}`;
    card.dataset.category = item.category;

    // Subtle outline on low-confidence rows
    if (item.confidence === "low") {
      card.classList.add("low-confidence");
    }

    // Checkbox
    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.className = "card-checkbox";
    chk.checked = item.selected;
    chk.title = "Include or exclude this file from being organized";
    chk.addEventListener("change", (e) => {
      item.selected = e.target.checked;
      card.classList.toggle("excluded", !item.selected);
      updateApplyButton();
    });

    // Preview Icon / Thumbnail
    const thumb = document.createElement("div");
    thumb.className = "card-preview-thumb";
    if (item.is_image) {
      const img = document.createElement("img");
      img.src = `/api/thumbnail?folder_path=${encodeURIComponent(state.folderPath)}&relative_path=${encodeURIComponent(item.relative_path)}`;
      img.alt = item.original;
      img.loading = "lazy";
      img.addEventListener("click", () => {
        openImageModal(img.src, `${item.original} ➜ ${item.new_name}${item.extension}`);
      });
      thumb.appendChild(img);
    } else {
      thumb.textContent = getFileEmoji(item.extension, item.category);
    }

    // Details Column
    const details = document.createElement("div");
    details.className = "card-details";

    const namesRow = document.createElement("div");
    namesRow.className = "card-names-row";

    const origSpan = document.createElement("span");
    origSpan.className = "orig-name";
    origSpan.textContent = item.original;
    origSpan.title = item.original;

    const arrow = document.createElement("span");
    arrow.className = "name-arrow";
    arrow.textContent = "➔";

    // Inline Editable Input
    const editWrap = document.createElement("div");
    editWrap.className = "editable-name-wrap";

    const pencil = document.createElement("span");
    pencil.className = "pencil-icon";
    pencil.textContent = "✏️";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "editable-name-input";
    input.value = item.new_name;
    input.title = "Click to edit new filename (lowercase-kebab-case)";
    input.spellcheck = false;

    input.addEventListener("input", (e) => {
      const raw = e.target.value.toLowerCase().replace(/[^a-z0-9-]+/g, "-");
      item.new_name = raw;
    });

    const extBadge = document.createElement("span");
    extBadge.className = "extension-badge";
    extBadge.textContent = item.extension;

    editWrap.appendChild(pencil);
    editWrap.appendChild(input);
    editWrap.appendChild(extBadge);

    // Confidence badge
    const confBadge = document.createElement("span");
    confBadge.className = `confidence-chip ${item.confidence || "high"}`;
    confBadge.textContent = item.confidence || "high";
    confBadge.title = `Model confidence: ${item.confidence || "high"}`;

    namesRow.appendChild(origSpan);
    namesRow.appendChild(arrow);
    namesRow.appendChild(editWrap);
    namesRow.appendChild(confBadge);

    // Fallback badge if applicable
    if (item.classification_type === "fallback") {
      const fbBadge = document.createElement("span");
      fbBadge.className = "fallback-badge";
      fbBadge.textContent = "FALLBACK";
      fbBadge.title = "Rule-based fallback was used for this file";
      namesRow.appendChild(fbBadge);
    }

    const reason = document.createElement("div");
    reason.className = "card-reason";
    reason.textContent = `💡 ${item.reason}`;
    reason.title = item.reason;

    details.appendChild(namesRow);
    details.appendChild(reason);

    // Category Selector
    const catWrap = document.createElement("div");
    catWrap.className = "category-select-wrap";

    const catChip = document.createElement("div");
    catChip.className = `cat-chip ${getCategoryClass(item.category)}`;

    const catSelect = document.createElement("select");
    catSelect.className = "cat-select";

    state.allowedCategories.forEach((cat) => {
      const opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = cat;
      if (cat.toLowerCase() === item.category.toLowerCase()) {
        opt.selected = true;
      }
      catSelect.appendChild(opt);
    });

    catSelect.addEventListener("change", (e) => {
      item.category = e.target.value;
      card.dataset.category = item.category;
      catChip.className = `cat-chip ${getCategoryClass(item.category)}`;
      updateCategoryFilters();
    });

    catChip.appendChild(catSelect);
    catWrap.appendChild(catChip);

    // Meta (size)
    const meta = document.createElement("div");
    meta.className = "card-meta";
    meta.textContent = item.size_human;

    // Assemble Card
    card.appendChild(chk);
    card.appendChild(thumb);
    card.appendChild(details);
    card.appendChild(catWrap);
    card.appendChild(meta);

    elements.proposalsList.appendChild(card);
  }

  function getFileEmoji(ext, cat) {
    if (ext === ".pdf") return "📄";
    if (ext === ".docx") return "📝";
    if (ext === ".zip" || ext === ".tar" || ext === ".gz") return "📦";
    if (cat === "Code") return "💻";
    if (cat === "Receipts-Bills") return "🧾";
    if (cat === "Study-Notes") return "🎓";
    if (cat === "Media") return "🎵";
    return "📁";
  }

  function getCategoryClass(cat) {
    const c = (cat || "").toLowerCase();
    if (c.includes("screenshot")) return "cat-screenshots";
    if (c.includes("document")) return "cat-documents";
    if (c.includes("receipt") || c.includes("bill")) return "cat-receipts";
    if (c.includes("study") || c.includes("note")) return "cat-study";
    if (c.includes("code")) return "cat-code";
    if (c.includes("image")) return "cat-images";
    if (c.includes("media")) return "cat-media";
    if (c.includes("archive")) return "cat-archives";
    return "cat-other";
  }

  // -------------------------------------------------------------------------
  // Category Filters
  // -------------------------------------------------------------------------
  function updateCategoryFilters() {
    const counts = {};
    state.proposals.forEach((p) => {
      counts[p.category] = (counts[p.category] || 0) + 1;
    });

    elements.catCountAll.textContent = state.proposals.length;

    elements.categoryFilterBar.querySelectorAll(".cat-filter-chip:not([data-cat='ALL'])").forEach((el) => el.remove());

    Object.keys(counts).sort().forEach((cat) => {
      const chip = document.createElement("button");
      chip.className = `cat-filter-chip ${state.activeCategoryFilter === cat ? "active" : ""}`;
      chip.dataset.cat = cat;
      chip.innerHTML = `${cat} (${counts[cat]})`;

      chip.addEventListener("click", () => {
        state.activeCategoryFilter = cat;
        elements.categoryFilterBar.querySelectorAll(".cat-filter-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        filterCards();
      });

      elements.categoryFilterBar.appendChild(chip);
    });

    const allChip = elements.categoryFilterBar.querySelector("[data-cat='ALL']");
    allChip.onclick = () => {
      state.activeCategoryFilter = "ALL";
      elements.categoryFilterBar.querySelectorAll(".cat-filter-chip").forEach((c) => c.classList.remove("active"));
      allChip.classList.add("active");
      filterCards();
    };
  }

  function filterCards() {
    const filter = state.activeCategoryFilter;
    const cards = elements.proposalsList.querySelectorAll(".proposal-card");
    cards.forEach((card) => {
      if (filter === "ALL" || card.dataset.category === filter) {
        card.style.display = "grid";
      } else {
        card.style.display = "none";
      }
    });
  }

  // -------------------------------------------------------------------------
  // Select All / Deselect All
  // -------------------------------------------------------------------------
  elements.btnSelectAll.addEventListener("click", () => {
    state.proposals.forEach((p) => (p.selected = true));
    elements.proposalsList.querySelectorAll(".card-checkbox").forEach((cb) => (cb.checked = true));
    elements.proposalsList.querySelectorAll(".proposal-card").forEach((c) => c.classList.remove("excluded"));
    updateApplyButton();
  });

  elements.btnDeselectAll.addEventListener("click", () => {
    state.proposals.forEach((p) => (p.selected = false));
    elements.proposalsList.querySelectorAll(".card-checkbox").forEach((cb) => (cb.checked = false));
    elements.proposalsList.querySelectorAll(".proposal-card").forEach((c) => c.classList.add("excluded"));
    updateApplyButton();
  });

  function updateApplyButton() {
    const selectedCount = state.proposals.filter((p) => p.selected).length;
    elements.applyBtnText.textContent = `Apply Organization (${selectedCount} files)`;
    elements.stickySelectedCount.textContent = `${selectedCount} of ${state.proposals.length} files selected`;
    elements.btnApply.disabled = selectedCount === 0;
    elements.btnStickyApply.disabled = selectedCount === 0;

    elements.stickyApplyBar.style.display = state.proposals.length > 3 ? "flex" : "none";
  }

  // -------------------------------------------------------------------------
  // Applying Organization Plan
  // -------------------------------------------------------------------------
  elements.btnApply.addEventListener("click", executeApply);
  elements.btnStickyApply.addEventListener("click", executeApply);

  async function executeApply() {
    const selectedItems = state.proposals.filter((p) => p.selected);
    if (selectedItems.length === 0) {
      showToast("No files selected to organize.", "error");
      return;
    }

    const confirmed = confirm(
      `Ready to gently organize ${selectedItems.length} file(s) into category folders?\n\n(No files will be overwritten or deleted. You can undo this at any time.)`
    );
    if (!confirmed) return;

    elements.btnApply.disabled = true;
    elements.applyBtnText.textContent = "Sloth is sorting...";

    const plan = selectedItems.map((item) => ({
      original: item.relative_path,
      new_name: item.new_name,
      category: item.category,
    }));

    try {
      const resp = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: state.folderPath,
          plan: plan,
          report: state.lastReport,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Failed to apply organization plan.");
      }

      state.lastRunId = data.run_id;
      showToast(`Successfully organized ${data.moves_count} file(s)!`, "success");
      showSuccessBanner(data);
      loadPastRuns();
    } catch (err) {
      showToast(`Error applying organization: ${err.message}`, "error");
    } finally {
      elements.btnApply.disabled = false;
      elements.applyBtnText.textContent = `Apply Organization (${selectedItems.length} files)`;
    }
  }

  function showSuccessBanner(runData) {
    elements.successBanner.style.display = "flex";
    elements.previewSection.style.display = "none";
    elements.progressSection.style.display = "none";
    elements.slothReportCard.style.display = "none";

    elements.successTitle.textContent = `Successfully Organized ${runData.moves_count} File(s)! 🎉`;
    elements.successMessage.textContent = `Files have been placed into neat category folders inside "${runData.folder_path}". Run ID: ${runData.run_id}`;

    elements.successStats.innerHTML = "";
    const catCounts = {};
    (runData.moves || []).forEach((m) => {
      catCounts[m.category] = (catCounts[m.category] || 0) + 1;
    });

    Object.entries(catCounts).forEach(([cat, count]) => {
      const chip = document.createElement("span");
      chip.className = "success-stat-chip";
      chip.textContent = `${cat}: ${count} files`;
      elements.successStats.appendChild(chip);
    });

    setMascotState("happy", "A place for everything, and everything in its place. Take a nap, you earned it!");
    window.scrollTo({ top: elements.successBanner.offsetTop - 80, behavior: "smooth" });
  }

  elements.btnSortAnother.addEventListener("click", () => {
    elements.successBanner.style.display = "none";
    elements.folderInput.value = "";
    elements.folderInput.focus();
    state.proposals = [];
    setMascotState("sleeping", "Waiting for the next folder chore...");
  });

  // -------------------------------------------------------------------------
  // Undo Operations
  // -------------------------------------------------------------------------
  elements.btnUndoLatest.addEventListener("click", () => {
    if (state.lastRunId) {
      undoRun(state.lastRunId);
    }
  });

  async function undoRun(runId) {
    const confirmed = confirm(`Are you sure you want to reverse all file moves from run "${runId}"?`);
    if (!confirmed) return;

    try {
      const resp = await fetch("/api/undo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_path: state.folderPath,
          run_id: runId,
        }),
      });

      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Failed to undo run.");
      }

      showToast(`Restored ${data.reversed_count} file(s) to original locations.`, "success");
      elements.successBanner.style.display = "none";
      loadPastRuns();
      setMascotState("awake", `Undid run ${runId}. Files are back where they started.`);
    } catch (err) {
      showToast(`Undo failed: ${err.message}`, "error");
    }
  }

  // -------------------------------------------------------------------------
  // Past Runs History & Collapsible Sloth Report
  // -------------------------------------------------------------------------
  elements.btnRefreshHistory.addEventListener("click", loadPastRuns);

  async function loadPastRuns() {
    const path = elements.folderInput.value.trim() || state.folderPath;
    if (!path) return;

    try {
      const resp = await fetch(`/api/runs?folder_path=${encodeURIComponent(path)}`);
      if (!resp.ok) return;

      const data = await resp.json();
      const runs = data.runs || [];
      elements.historyCountBadge.textContent = `${runs.length} run(s)`;

      if (runs.length === 0) {
        elements.historyList.innerHTML =
          '<div class="history-empty">No previous organization runs recorded in this folder yet.</div>';
        return;
      }

      elements.historyList.innerHTML = "";
      runs.forEach((run) => {
        const item = document.createElement("div");
        item.className = "history-item";

        const details = document.createElement("div");
        details.className = "history-item-details";

        const idRow = document.createElement("div");
        idRow.className = "history-item-id";
        idRow.textContent = `📋 ${run.run_id}`;

        const statusTag = document.createElement("span");
        statusTag.className = `history-status-tag ${run.status}`;
        statusTag.textContent = run.status;
        idRow.appendChild(statusTag);

        const meta = document.createElement("div");
        meta.className = "history-item-meta";
        const dateStr = new Date(run.timestamp).toLocaleString();
        meta.textContent = `${dateStr} • ${run.moves_count} files organized • Categories: ${(run.created_categories || []).join(", ") || "None"}`;

        details.appendChild(idRow);
        details.appendChild(meta);

        // If run includes a Sloth Report, add collapsible stats
        if (run.report && run.report.total_duration_sec) {
          const toggleBtn = document.createElement("button");
          toggleBtn.className = "history-report-toggle";
          toggleBtn.textContent = "📊 View Sloth Report";

          const repBox = document.createElement("div");
          repBox.className = "history-report-box";
          repBox.style.display = "none";
          repBox.innerHTML = `
            <div>⏱️ Duration: <strong>${run.report.total_duration_sec}s</strong> (${run.report.avg_duration_sec}s/file)</div>
            <div>🐢 Slowest: <strong>${run.report.slowest_file}</strong> (${run.report.slowest_duration_sec}s)</div>
            <div>🤖 Model: ${run.report.model_classified || 0} • 📁 Extension: ${run.report.extension_only || 0} • ⚠️ Fallback: ${run.report.fallback_count || 0}</div>
          `;

          toggleBtn.addEventListener("click", () => {
            const isShown = repBox.style.display === "flex";
            repBox.style.display = isShown ? "none" : "flex";
            toggleBtn.textContent = isShown ? "📊 View Sloth Report" : "▲ Hide Sloth Report";
          });

          details.appendChild(toggleBtn);
          details.appendChild(repBox);
        }

        item.appendChild(details);

        if (run.status === "applied" && run.can_undo) {
          const btnUndo = document.createElement("button");
          btnUndo.className = "btn-undo";
          btnUndo.innerHTML = "<span>⏪ Undo</span>";
          btnUndo.addEventListener("click", () => undoRun(run.run_id));
          item.appendChild(btnUndo);
        }

        elements.historyList.appendChild(item);
      });
    } catch (err) {
      console.warn("Could not load past runs:", err);
    }
  }

  // -------------------------------------------------------------------------
  // Image Thumbnail Modal & Keyboard Escape
  // -------------------------------------------------------------------------
  function openImageModal(imgSrc, captionText) {
    elements.modalImg.src = imgSrc;
    elements.modalCaption.textContent = captionText;
    elements.imageModal.style.display = "flex";
  }

  elements.modalClose.addEventListener("click", () => {
    elements.imageModal.style.display = "none";
  });

  elements.imageModal.addEventListener("click", (e) => {
    if (e.target === elements.imageModal) {
      elements.imageModal.style.display = "none";
    }
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      elements.imageModal.style.display = "none";
    }
  });

  // -------------------------------------------------------------------------
  // Initialization
  // -------------------------------------------------------------------------
  initTheme();
  checkHealth();
  setInterval(checkHealth, 10000);
});
