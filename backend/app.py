"""
Research Highlight Generator — Flask Backend
Run: python app.py
API available at http://localhost:5000
"""

import logging
import os
import time

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import BadRequest, NotFound, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from services.extractor import extract_text
from services.llm import generate_highlights

# ──────────────────────────────────────────────
# Logging — writes to stdout so Render captures it automatically
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)
# ──────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
# ──────────────────────────────────────────────


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Error handlers ──────────────────────────
@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(e):
    logger.warning("Upload rejected: file exceeds 20 MB limit")
    return jsonify({"error": "File is too large. Maximum upload size is 20 MB."}), 413


@app.errorhandler(BadRequest)
def handle_bad_request(e):
    logger.warning("Bad request: %s", e.description)
    return jsonify({"error": f"Bad request: {e.description}"}), 400


@app.errorhandler(NotFound)
def handle_not_found(e):
    logger.warning("404 Not found: %s", request.path)
    return jsonify({"error": f"Endpoint '{request.path}' not found"}), 404


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.exception("Unhandled exception on %s %s", request.method, request.path)
    return jsonify({"error": "An unexpected server error occurred. Please try again later."}), 500


# ─── Serve frontend ──────────────────────────
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


# ─── Health check ────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Research Highlight Generator API is running"})


# ─── Upload & analyse paper ──────────────────
@app.route("/api/upload", methods=["POST"])
def upload_paper():
    if "file" not in request.files:
        logger.warning("Upload request missing file part")
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]

    if file.filename == "":
        logger.warning("Upload request had empty filename")
        return jsonify({"error": "No file selected"}), 400

    if not _allowed(file.filename):
        logger.warning("Rejected unsupported file type: %s", file.filename)
        return jsonify({"error": "Only PDF, DOCX and TXT files are supported"}), 400

    filename = secure_filename(file.filename)
    content = file.read()
    file_size_kb = len(content) / 1024
    logger.info("Received file: %s (%.1f KB)", filename, file_size_kb)

    # 1. Extract raw text
    try:
        t0 = time.monotonic()
        paper_text = extract_text(content, filename)
        logger.info(
            "Text extraction completed in %.2fs — %d characters extracted",
            time.monotonic() - t0,
            len(paper_text),
        )
    except Exception:
        logger.exception("Text extraction failed for file: %s", filename)
        return jsonify({"error": "Text extraction failed. The file may be corrupt or password-protected."}), 422

    if not paper_text.strip():
        logger.warning("Extracted text is empty for file: %s", filename)
        return jsonify({"error": "The file appears to be empty or unreadable"}), 422

    # 2. Send to Claude
    try:
        highlights = generate_highlights(paper_text)
    except Exception:
        logger.exception("LLM processing failed for file: %s", filename)
        return jsonify({"error": "AI processing failed. Please try again."}), 500

    highlights["filename"] = filename
    highlights["char_count"] = len(paper_text)
    logger.info("Successfully processed file: %s", filename)
    return jsonify(highlights), 200


# ─── Analyse plain text directly (no file) ───
@app.route("/api/analyse", methods=["POST"])
def analyse_text():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        logger.warning("Analyse request missing 'text' field")
        return jsonify({"error": "JSON body must contain a 'text' field"}), 400

    paper_text = data["text"].strip()
    if not paper_text:
        logger.warning("Analyse request had empty text")
        return jsonify({"error": "Provided text is empty"}), 400

    logger.info("Received plain text for analysis (%d characters)", len(paper_text))

    try:
        highlights = generate_highlights(paper_text)
    except Exception:
        logger.exception("LLM processing failed for plain text input")
        return jsonify({"error": "AI processing failed. Please try again."}), 500

    highlights["char_count"] = len(paper_text)
    logger.info("Successfully processed plain text input")
    return jsonify(highlights), 200


# ──────────────────────────────────────────────
if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Research Highlight Generator API (debug=%s)", debug)
    app.run(debug=debug, host="0.0.0.0", port=5000)
