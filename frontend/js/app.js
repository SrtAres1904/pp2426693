const API_BASE = "";

const dropZone      = document.getElementById("drop-zone");
const fileInput     = document.getElementById("file-input");
const selectedFile  = document.getElementById("selected-file");
const selectedName  = document.getElementById("selected-name");
const paperText     = document.getElementById("paper-text");
const analyseBtn    = document.getElementById("analyse-btn");
const loader        = document.getElementById("loader");
const stepMsg       = document.getElementById("step-msg");
const errorBanner   = document.getElementById("error-banner");
const errorMsg      = document.getElementById("error-msg");
const results       = document.getElementById("results");
const resetBtn      = document.getElementById("reset-btn");
const printBtn      = document.getElementById("print-btn");
const copyBtn       = document.getElementById("copy-btn");

let selectedFileObj = null;

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

analyseBtn.addEventListener("click", async () => {
  hideError();
  const hasFile = !!selectedFileObj;
  const hasText = paperText.value.trim().length > 0;

  if (!hasFile && !hasText) {
    showError("Please upload a file or paste your paper text.");
    return;
  }

  setLoading(true);

  try {
    let data;
    if (hasFile) {
      data = await uploadFile(selectedFileObj);
    } else {
      data = await analyseText(paperText.value.trim());
    }
    renderResults(data);
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

  const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
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
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Server error ${res.status}`);
  }
  setStep("Generating highlights…");
  return res.json();
}

function renderResults(data) {
  document.getElementById("stat-filename").textContent = data.filename || "Pasted text";
  document.getElementById("stat-chars").textContent    = (data.char_count || 0).toLocaleString();

  document.getElementById("paper-title-display").textContent = data.title || "Research Paper";

  document.getElementById("hl-objective").textContent = data.objective || "—";

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
  results.scrollIntoView({ behavior: "smooth" });
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

resetBtn.addEventListener("click", () => {
  selectedFileObj = null;
  selectedFile.style.display = "none";
  fileInput.value = "";
  paperText.value = "";
  results.style.display = "none";
  hideError();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

printBtn.addEventListener("click", () => window.print());

copyBtn.addEventListener("click", async () => {
  const title   = document.getElementById("paper-title-display").textContent;
  const obj = {
    title,
    objective:      document.getElementById("hl-objective").textContent,
    methodology:    document.getElementById("hl-methodology").textContent,
    key_findings:   [...document.querySelectorAll("#hl-findings li")].map(l => l.textContent),
    conclusions:    document.getElementById("hl-conclusions").textContent,
    contributions:  [...document.querySelectorAll("#hl-contributions li")].map(l => l.textContent),
    limitations:    [...document.querySelectorAll("#hl-limitations li")].map(l => l.textContent),
    keywords:       [...document.querySelectorAll("#hl-keywords .chip")].map(c => c.textContent),
    summary:        document.getElementById("hl-summary").textContent,
  };
  await navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
  copyBtn.textContent = "✅ Copied!";
  setTimeout(() => (copyBtn.textContent = "📋 Copy JSON"), 2000);
});

function setLoading(on) {
  loader.style.display    = on ? "flex" : "none";
  analyseBtn.disabled     = on;
  results.style.display   = on ? "none" : results.style.display;
}

function setStep(msg) {
  if (stepMsg) stepMsg.textContent = msg;
}

function showError(msg) {
  errorMsg.textContent        = msg;
  errorBanner.style.display   = "block";
}

function hideError() {
  errorBanner.style.display = "none";
}
