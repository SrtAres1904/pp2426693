"""
Research Highlight Generator — Flask Backend
Run: python app.py
API available at http://localhost:5000
"""

import json
import logging
import os
import secrets
import time
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.exceptions import BadRequest, NotFound, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from models import db, User, Article
from services.extractor import extract_text
from services.llm import generate_highlights

# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)
# ──────────────────────────────────────────────

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# Secret key — sessions won't persist across restarts if not set in .env
_secret = os.getenv("SECRET_KEY")
if not _secret:
    _secret = secrets.token_hex(32)
    logger.warning("SECRET_KEY not set in .env — sessions will not survive server restarts")
app.config["SECRET_KEY"] = _secret

# Database (SQLite, stored next to app.py)
_db_path = os.path.join(BASE_DIR, "data.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{_db_path}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Create tables on startup (safe to run repeatedly)
with app.app_context():
    db.create_all()
    logger.info("Database ready at: %s", _db_path)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

CORS(app, supports_credentials=True)

ALLOWED_EXTENSIONS = {"pdf", "txt", "docx"}
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Error handlers ──────────────────────────
@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(e):
    return jsonify({"error": "File is too large. Maximum upload size is 20 MB."}), 413


@app.errorhandler(BadRequest)
def handle_bad_request(e):
    return jsonify({"error": f"Bad request: {e.description}"}), 400


@app.errorhandler(NotFound)
def handle_not_found(e):
    return jsonify({"error": f"Endpoint '{request.path}' not found"}), 404


@app.errorhandler(Exception)
def handle_unexpected_error(e):
    logger.exception("Unhandled exception on %s %s", request.method, request.path)
    return jsonify({"error": "An unexpected server error occurred. Please try again later."}), 500


# ─── Serve frontend pages ─────────────────────
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/login")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")


@app.route("/signup")
def signup_page():
    return send_from_directory(FRONTEND_DIR, "signup.html")


# ─── Health check ────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Research Highlight Generator API is running"})


# ─── Auth endpoints ──────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    if "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Invalid email address"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session["user_id"] = user.id
    logger.info("New user registered: %s", email)
    return jsonify({"message": "Account created successfully", "user": user.to_dict()}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user.id
    logger.info("User logged in: %s", email)
    return jsonify({"message": "Logged in successfully", "user": user.to_dict()}), 200


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/api/auth/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user = User.query.get(session["user_id"])
    if not user:
        session.clear()
        return jsonify({"error": "User not found"}), 401
    return jsonify({"user": user.to_dict()}), 200


# ─── Article history ─────────────────────────
@app.route("/api/articles", methods=["GET"])
@login_required
def list_articles():
    articles = (
        Article.query
        .filter_by(user_id=session["user_id"])
        .order_by(Article.created_at.desc())
        .all()
    )
    return jsonify({"articles": [a.to_dict() for a in articles]}), 200


@app.route("/api/articles/<int:article_id>", methods=["GET"])
@login_required
def get_article(article_id):
    article = Article.query.filter_by(id=article_id, user_id=session["user_id"]).first()
    if not article:
        return jsonify({"error": "Article not found"}), 404
    return jsonify(article.to_dict(include_highlights=True)), 200


# ─── Upload & analyse paper ──────────────────
@app.route("/api/upload", methods=["POST"])
@login_required
def upload_paper():
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not _allowed(file.filename):
        return jsonify({"error": "Only PDF, DOCX and TXT files are supported"}), 400

    filename = secure_filename(file.filename)
    content = file.read()
    logger.info("Received file: %s (%.1f KB)", filename, len(content) / 1024)

    try:
        t0 = time.monotonic()
        paper_text = extract_text(content, filename)
        logger.info("Text extraction completed in %.2fs — %d chars", time.monotonic() - t0, len(paper_text))
    except Exception:
        logger.exception("Text extraction failed for: %s", filename)
        return jsonify({"error": "Text extraction failed. The file may be corrupt or password-protected."}), 422

    if not paper_text.strip():
        return jsonify({"error": "The file appears to be empty or unreadable"}), 422

    try:
        highlights = generate_highlights(paper_text)
    except Exception:
        logger.exception("LLM processing failed for: %s", filename)
        return jsonify({"error": "AI processing failed. Please try again."}), 500

    highlights["filename"] = filename
    highlights["char_count"] = len(paper_text)

    article = Article(
        user_id=session["user_id"],
        filename=filename,
        title=highlights.get("title", "Untitled Paper"),
        char_count=len(paper_text),
        highlights_json=json.dumps(highlights),
    )
    db.session.add(article)
    db.session.commit()
    highlights["article_id"] = article.id

    logger.info("Processed and saved file: %s (article_id=%d)", filename, article.id)
    return jsonify(highlights), 200


# ─── Analyse plain text directly (no file) ───
@app.route("/api/analyse", methods=["POST"])
@login_required
def analyse_text():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "JSON body must contain a 'text' field"}), 400

    paper_text = data["text"].strip()
    if not paper_text:
        return jsonify({"error": "Provided text is empty"}), 400

    logger.info("Received plain text (%d characters)", len(paper_text))

    try:
        highlights = generate_highlights(paper_text)
    except Exception:
        logger.exception("LLM processing failed for plain text input")
        return jsonify({"error": "AI processing failed. Please try again."}), 500

    highlights["char_count"] = len(paper_text)

    article = Article(
        user_id=session["user_id"],
        filename=None,
        title=highlights.get("title", "Untitled Paper"),
        char_count=len(paper_text),
        highlights_json=json.dumps(highlights),
    )
    db.session.add(article)
    db.session.commit()
    highlights["article_id"] = article.id

    logger.info("Processed plain text (article_id=%d)", article.id)
    return jsonify(highlights), 200


# ──────────────────────────────────────────────
if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Research Highlight Generator API (debug=%s)", debug)
    app.run(debug=debug, host="0.0.0.0", port=5000)
