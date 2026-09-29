"""Basic Statistics Calculator: Flask routes, authentication, and history."""

from functools import wraps
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_app as init_database
from stats import calculate_statistics, format_number, parse_dataset


# A development fallback is generated once per process, never committed to disk.
# Set SECRET_KEY in the environment for sessions that survive server restarts.
DEVELOPMENT_SECRET = secrets.token_hex(32)
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,30}")
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def login_required(view):
    """Keep authentication checks consistent on every private route."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or DEVELOPMENT_SECRET,
        DATABASE=str(Path(app.root_path) / "statistics.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower()
        in {"1", "true", "yes"},
        MAX_CONTENT_LENGTH=1_000_000,
        MAX_FORM_MEMORY_SIZE=1_000_000,
    )
    if test_config:
        app.config.update(test_config)
    init_database(app)

    def csrf_token():
        """A random token in each session protects every submitted POST form."""
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return session["csrf_token"]

    @app.context_processor
    def template_helpers():
        return {"csrf_token": csrf_token}

    app.jinja_env.filters["number"] = format_number
    app.jinja_env.filters["dataset_values"] = json.loads

    @app.template_filter("modes")
    def format_modes(value):
        values = json.loads(value) if isinstance(value, str) else value
        return ", ".join(format_number(item) for item in values) if values else "No mode"

    @app.before_request
    def load_user_and_check_csrf():
        user_id = session.get("user_id")
        g.user = get_db().execute(
            "SELECT id, username, email FROM users WHERE id = ?", (user_id,)
        ).fetchone() if user_id is not None else None

        if request.method == "POST":
            expected = session.get("csrf_token", "")
            submitted = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(
                expected.encode("utf-8"), submitted.encode("utf-8")
            ):
                return render_template(
                    "error.html", title="Please try again",
                    message="This form expired or could not be verified. Refresh the page and try again.",
                ), 400

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    def dashboard_context(dataset="", result=None, calculation=None):
        """The same template displays a new dataset or a saved calculation."""
        connection = get_db()
        recent = connection.execute(
            "SELECT * FROM calculations WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 3",
            (g.user["id"],),
        ).fetchall()
        history_count = connection.execute(
            "SELECT COUNT(*) FROM calculations WHERE user_id = ?", (g.user["id"],)
        ).fetchone()[0]
        return {
            "dataset": dataset, "result": result, "calculation": calculation,
            "recent_calculations": recent, "history_count": history_count,
        }

    @app.get("/")
    def index():
        return redirect(url_for("dashboard" if g.user else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")
            error = None
            if not USERNAME_PATTERN.fullmatch(username):
                error = "Use 3–30 letters, numbers, or underscores for your username."
            elif len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
                error = "Enter a valid email address."
            elif not 8 <= len(password) <= 128:
                error = "Choose a password between 8 and 128 characters."
            elif password != confirmation:
                error = "Your passwords do not match."

            if error:
                flash(error, "error")
                return render_template("register.html"), 400

            connection = get_db()
            try:
                connection.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, generate_password_hash(password)),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
                flash("That username or email is already registered. Try another or log in.", "error")
                return render_template("register.html"), 400

            flash("Your account is ready. Log in to start calculating.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            identifier = request.form.get("identifier", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE",
                (identifier, identifier),
            ).fetchone()
            if len(password) > 128 or user is None or not check_password_hash(user["password_hash"], password):
                flash("The username/email or password is incorrect.", "error")
                return render_template("login.html"), 401

            # Clear pre-login session data and rotate its CSRF token on sign-in.
            session.clear()
            session["user_id"] = user["id"]
            csrf_token()
            flash(f"Welcome back, {user['username']}!", "success")
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", **dashboard_context())

    @app.post("/calculate")
    @login_required
    def calculate():
        dataset = request.form.get("dataset", "")
        try:
            values = parse_dataset(dataset)
            result = calculate_statistics(values)
        except ValueError as error:
            flash(str(error), "error")
            return render_template("dashboard.html", **dashboard_context(dataset=dataset)), 400

        connection = get_db()
        cursor = connection.execute(
            """INSERT INTO calculations (
                user_id, dataset, count, total, mean, median, mode, minimum,
                maximum, value_range, variance, standard_deviation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (g.user["id"], json.dumps(values), result["count"], result["sum"],
             result["mean"], result["median"], json.dumps(result["mode"]),
             result["min"], result["max"], result["range"], result["variance"],
             result["standard_deviation"]),
        )
        connection.commit()
        flash("Calculation complete and saved to your history.", "success")
        # Redirect after saving so refreshing the result does not insert it twice.
        return redirect(url_for("view_calculation", calculation_id=cursor.lastrowid))

    @app.get("/history")
    @login_required
    def history():
        calculations = get_db().execute(
            "SELECT * FROM calculations WHERE user_id = ? ORDER BY created_at DESC, id DESC",
            (g.user["id"],),
        ).fetchall()
        return render_template("history.html", calculations=calculations, history_count=len(calculations))

    @app.get("/history/<int:calculation_id>")
    @login_required
    def view_calculation(calculation_id):
        # Never look up a history row by its id alone: include its owner too.
        calculation = get_db().execute(
            "SELECT * FROM calculations WHERE id = ? AND user_id = ?",
            (calculation_id, g.user["id"]),
        ).fetchone()
        if calculation is None:
            abort(404)
        values = json.loads(calculation["dataset"])
        dataset = ", ".join(str(value) for value in values)
        return render_template(
            "dashboard.html",
            **dashboard_context(dataset, calculate_statistics(values), calculation),
        )

    @app.post("/delete-history/<int:calculation_id>")
    @login_required
    def delete_history(calculation_id):
        connection = get_db()
        cursor = connection.execute(
            "DELETE FROM calculations WHERE id = ? AND user_id = ?",
            (calculation_id, g.user["id"]),
        )
        if cursor.rowcount == 0:
            abort(404)
        connection.commit()
        flash("The calculation was deleted.", "success")
        return redirect(url_for("history"))

    @app.route("/clear-history", methods=["GET", "POST"])
    @login_required
    def clear_history():
        connection = get_db()
        if request.method == "POST":
            # A separate confirmation page also works when JavaScript is off.
            if request.form.get("confirm") != "yes":
                return redirect(url_for("clear_history"))
            connection.execute("DELETE FROM calculations WHERE user_id = ?", (g.user["id"],))
            connection.commit()
            flash("Your calculation history was cleared.", "success")
            return redirect(url_for("history"))

        history_count = connection.execute(
            "SELECT COUNT(*) FROM calculations WHERE user_id = ?", (g.user["id"],)
        ).fetchone()[0]
        return render_template("clear_history.html", history_count=history_count)

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template(
            "error.html", title="Page not found",
            message="That page or calculation is not available. Use the navigation to continue.",
        ), 404

    @app.errorhandler(413)
    def too_large(_error):
        return render_template(
            "error.html", title="That submission is too large",
            message="Use at most 10,000 numbers and 200,000 characters in your dataset.",
        ), 413

    @app.errorhandler(sqlite3.Error)
    def database_error(error):
        app.logger.error("A database operation failed: %s", error)
        connection = g.get("db")
        if connection:
            connection.rollback()
        return render_template(
            "error.html", title="We could not save that change",
            message="The database is temporarily unavailable. Please try again shortly.",
        ), 500

    return app


if __name__ == "__main__":
    # The local server is deliberately bound to this computer, with debug off.
    create_app().run(host="127.0.0.1", port=5000, debug=False)
