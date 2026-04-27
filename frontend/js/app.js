const API_BASE = "";

// ─── DOM refs ────────────────────────────────
const dropZone     = document.getElementById("drop-zone");
const fileInput    = document.getElementById("file-input");
const selectedFile = document.getElementById("selected-file");
const selectedName = document.getElementById("selected-name");
const paperText    = document.getElementById("paper-text");
const analyseBtn   = document.getElementById("analyse-btn");
const loader       = document.getElementById("loader");
const stepMsg      = document.getElementById("step-msg");
const errorBanner  = document.getElementById("error-banner");
const errorMsg     = document.getElementById("error-msg");
const results      = document.getElementById("results");
const resetBtn     = document.getElementById("reset-btn");
const copyBtn      = document.getElementById("copy-btn");
const historyList  = document.getElementById("history-list");
const userEmailEl  = document.getElementById("user-email");
const logoutBtn    = document.getElementById("logout-btn");

let selectedFileObj = null;
let activeArticleId = null;

// ─── Auth guard ──────────────────────────────
async function initAuth() {
  try {
    const res = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
    if (!res.ok) {
      window.location.href = "/login";
      return;
    }
    const data = await res.json();
    userEmailEl.textContent = data.user.email;
  } catch {
    window.location.href = "/login";
  }
}

logoutBtn.addEventListener("click", async () => {
  await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
  window.location.href = "/login";
});

// ─── History sidebar ─────────────────────────
async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/articles`, { credentials: "include" });
    if (!res.ok) return;
    const data = await res.json();
    renderHistory(data.articles);
  } catch {
    // Sidebar failure is non-fatal
  }
}

function renderHistory(articles) {
  if (!articles || articles.length === 0) {
    historyList.innerHTML = '<p class="sidebar-empty">No papers yet.<br>Upload your first paper!</p>';
    return;
  }

  historyList.innerHTML = "";
  articles.forEach((article) => {
    const item = document.createElement("div");
    item.className = "history-item" + (article.id === activeArticleId ? " active" : "");
    item.dataset.id = article.id;

    const title = article.title || "Untitled Paper";
    const source = article.filename || "Pasted text";
    const when = formatDate(article.created_at);

    item.innerHTML = `
      <div class="history-item-title" title="${escHtml(title)}">${escHtml(title)}</div>
      <div class="history-item-meta">${escHtml(source)} &middot; ${when}</div>
    `;

    item.addEventListener("click", () => loadArticle(article.id));
    historyList.appendChild(item);
  });
}

async function loadArticle(id) {
  try {
    const res = await fetch(`${API_BASE}/api/articles/${id}`, { credentials: "include" });
    if (!res.ok) return;
    const data = await res.json();
    activeArticleId = id;
    renderResults(data.highlights);
    updateActiveHistoryItem(id);
    // Scroll results into view on mobile
    results.scrollIntoView({ behavior: "smooth" });
  } catch {
    showError("Could not load article. Please try again.");
  }
}

function updateActiveHistoryItem(id) {
  document.querySelectorAll(".history-item").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.id) === id);
  });
}

// ─── File drop / select ──────────────────────
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelect(file);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFileSelect(fileInput.files[0]);
});

function handleFileSelect(file) {
  const allowed = [
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ];
  const ext = file.name.split(".").pop().toLowerCase();
  if (!allowed.includes(file.type) && !["pdf", "txt", "docx"].includes(ext)) {
    showError("Please upload a PDF, DOCX or TXT file.");
    return;
  }
  selectedFileObj = file;
  selectedName.textContent = `${file.name}  (${(file.size / 1024).toFixed(1)} KB)`;
  selectedFile.style.display = "flex";
  paperText.value = "";
  hideError();
}

// ─── Analyse ─────────────────────────────────
analyseBtn.addEventListener("click", async () => {
  hideError();
  const hasFile = !!selectedFileObj;
  const hasText = paperText.value.trim().length > 0;

  if (!hasFile && !hasText) {
    showError("Please upload a file or paste your paper text.");
    return;
  }

  setLoading(true);
  activeArticleId = null;

  try {
    let data;
    if (hasFile) {
      data = await uploadFile(selectedFileObj);
    } else {
      data = await analyseText(paperText.value.trim());
    }
    activeArticleId = data.article_id || null;
    renderResults(data);
    await loadHistory(); // refresh sidebar
    if (activeArticleId) updateActiveHistoryItem(activeArticleId);
  } catch (err) {
    showError(err.message || "An unexpected error occurred. Is the backend running?");
  } finally {
    setLoading(false);
  }
});

async function uploadFile(file) {
  setStep("Uploading and extracting text…");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: form,
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Server error ${res.status}`);
  }
  setStep("Analysing with AI…");
  return res.json();
}

async function analyseText(text) {
  setStep("Sending text to AI…");
  const res = await fetch(`${API_BASE}/api/analyse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Server error ${res.status}`);
  }
  setStep("Generating highlights…");
  return res.json();
}

// ─── Render results ──────────────────────────
function renderResults(data) {
  document.getElementById("stat-filename").textContent = data.filename || "Pasted text";
  document.getElementById("stat-chars").textContent    = (data.char_count || 0).toLocaleString();
  document.getElementById("paper-title-display").textContent = data.title || "Research Paper";
  document.getElementById("hl-objective").textContent   = data.objective || "—";
  document.getElementById("hl-methodology").textContent = data.methodology || "—";
  renderList("hl-findings", data.key_findings);
  document.getElementById("hl-conclusions").textContent = data.conclusions || "—";
  renderList("hl-contributions", data.novel_contributions);
  renderList("hl-limitations", data.limitations);

  const chips = document.getElementById("hl-keywords");
  chips.innerHTML = "";
  (data.keywords || []).forEach((kw) => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = kw;
    chips.appendChild(span);
  });

  document.getElementById("hl-summary").textContent = data.summary || "—";

  results.style.display = "block";
}

function renderList(id, items) {
  const ul = document.getElementById(id);
  ul.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    ul.appendChild(li);
  });
}

// ─── Action buttons ──────────────────────────
resetBtn.addEventListener("click", () => {
  selectedFileObj = null;
  activeArticleId = null;
  selectedFile.style.display = "none";
  fileInput.value = "";
  paperText.value = "";
  results.style.display = "none";
  hideError();
  document.querySelectorAll(".history-item").forEach((el) => el.classList.remove("active"));
  window.scrollTo({ top: 0, behavior: "smooth" });
});


copyBtn.addEventListener("click", async () => {
  const obj = {
    title:         document.getElementById("paper-title-display").textContent,
    objective:     document.getElementById("hl-objective").textContent,
    methodology:   document.getElementById("hl-methodology").textContent,
    key_findings:  [...document.querySelectorAll("#hl-findings li")].map(l => l.textContent),
    conclusions:   document.getElementById("hl-conclusions").textContent,
    contributions: [...document.querySelectorAll("#hl-contributions li")].map(l => l.textContent),
    limitations:   [...document.querySelectorAll("#hl-limitations li")].map(l => l.textContent),
    keywords:      [...document.querySelectorAll("#hl-keywords .chip")].map(c => c.textContent),
    summary:       document.getElementById("hl-summary").textContent,
  };
  await navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
  copyBtn.textContent = "✅ Copied!";
  setTimeout(() => (copyBtn.textContent = "📋 Copy JSON"), 2000);
});

// ─── Helpers ─────────────────────────────────
function setLoading(on) {
  loader.style.display  = on ? "flex" : "none";
  analyseBtn.disabled   = on;
  results.style.display = on ? "none" : results.style.display;
}

function setStep(msg) { if (stepMsg) stepMsg.textContent = msg; }

function showError(msg) {
  errorMsg.textContent       = msg;
  errorBanner.style.display  = "block";
}

function hideError() { errorBanner.style.display = "none"; }

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatDate(isoString) {
  const date = new Date(isoString);
  const now  = new Date();
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1)  return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24)   return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7)    return `${diffD}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ─── Boot ─────────────────────────────────────
(async () => {
  await initAuth();
  await loadHistory();
})();
