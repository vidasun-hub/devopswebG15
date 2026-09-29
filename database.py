"""SQLite connection and schema setup, kept separate from the Flask routes."""

from pathlib import Path
import sqlite3

from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
);

CREATE TABLE IF NOT EXISTS calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    dataset TEXT NOT NULL,
    count INTEGER NOT NULL,
    total REAL NOT NULL,
    mean REAL NOT NULL,
    median REAL NOT NULL,
    mode TEXT NOT NULL,
    minimum REAL NOT NULL,
    maximum REAL NOT NULL,
    value_range REAL NOT NULL,
    variance REAL NOT NULL,
    standard_deviation REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS calculations_user_date
    ON calculations(user_id, created_at DESC, id DESC);
"""


def get_db():
    """Open one connection per request, with named columns and foreign keys."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app):
    """Create the database and tables automatically when the app starts."""
    database_path = Path(app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        connection = get_db()
        connection.executescript(SCHEMA)
        connection.commit()
