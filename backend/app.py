"""
Research Highlight Generator — Flask Backend
Run: python app.py
API available at http://localhost:5000
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os

from services.extractor import extract_text
from services.llm import generate_highlights

# ──────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)  # allow requests from the frontend

ALLOWED_EXTENSIONS = {"pdf", "txt"}
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB upload limit
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
# ──────────────────────────────────────────────


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed(file.filename):
        return jsonify({"error": "Only PDF and TXT files are supported"}), 400

    filename = secure_filename(file.filename)
    content = file.read()

    # 1. Extract raw text from the uploaded file
    try:
        paper_text = extract_text(content, filename)
    except Exception as e:
        return jsonify({"error": f"Text extraction failed: {str(e)}"}), 422

    if not paper_text.strip():
        return jsonify({"error": "The file appears to be empty or unreadable"}), 422

    # 2. Send text to Claude and get structured highlights
    try:
        highlights = generate_highlights(paper_text)
    except Exception as e:
        return jsonify({"error": f"LLM processing failed: {str(e)}"}), 500

    highlights["filename"] = filename
    highlights["char_count"] = len(paper_text)
    return jsonify(highlights), 200


# ─── Analyse plain text directly (no file) ───
@app.route("/api/analyse", methods=["POST"])
def analyse_text():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "JSON body must contain a 'text' field"}), 400

    paper_text = data["text"].strip()
    if not paper_text:
        return jsonify({"error": "Provided text is empty"}), 400

    try:
        highlights = generate_highlights(paper_text)
    except Exception as e:
        return jsonify({"error": f"LLM processing failed: {str(e)}"}), 500

    highlights["char_count"] = len(paper_text)
    return jsonify(highlights), 200


# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting Research Highlight Generator API...")
    print("API running at http://localhost:5000")
    print("Health check: http://localhost:5000/api/health")
    app.run(debug=True, host="0.0.0.0", port=5000)
