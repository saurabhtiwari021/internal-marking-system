import os

import db

DB_PATH = os.getenv("DB_PATH", "marking.db")

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT    NOT NULL,
    started_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    status       TEXT    NOT NULL DEFAULT 'running',
    total_rows   INTEGER NOT NULL DEFAULT 0,
    valid_rows   INTEGER NOT NULL DEFAULT 0,
    invalid_rows INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS student_marks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER REFERENCES etl_runs(run_id),
    student_id TEXT    NOT NULL,
    name       TEXT    NOT NULL,
    subject    TEXT    NOT NULL,
    score      REAL    NOT NULL,
    exam_date  TEXT    NOT NULL,
    loaded_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(run_id, student_id, subject, exam_date)
);

CREATE TABLE IF NOT EXISTS quarantine_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER REFERENCES etl_runs(run_id),
    raw_student_id TEXT,
    raw_name       TEXT,
    raw_subject    TEXT,
    raw_score      TEXT,
    raw_exam_date  TEXT,
    error_reason   TEXT NOT NULL,
    quarantined_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Same three tables, Postgres dialect: SERIAL instead of
# AUTOINCREMENT, TIMESTAMPTZ + NOW() instead of TEXT + datetime('now').
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id       SERIAL PRIMARY KEY,
    filename     TEXT        NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status       TEXT        NOT NULL DEFAULT 'running',
    total_rows   INTEGER     NOT NULL DEFAULT 0,
    valid_rows   INTEGER     NOT NULL DEFAULT 0,
    invalid_rows INTEGER     NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS student_marks (
    id         SERIAL PRIMARY KEY,
    run_id     INTEGER REFERENCES etl_runs(run_id),
    student_id TEXT        NOT NULL,
    name       TEXT        NOT NULL,
    subject    TEXT        NOT NULL,
    -- NUMERIC, not REAL/double precision: Postgres has no ROUND(double
    -- precision, integer) overload, and api.py's analytics queries do
    -- ROUND(AVG(score), 2). NUMERIC avoids needing a Postgres-only cast in
    -- every query. (SQLite's ROUND has no such restriction, so REAL is
    -- fine there — see SQLITE_SCHEMA above.)
    score      NUMERIC     NOT NULL,
    exam_date  TEXT        NOT NULL,
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, student_id, subject, exam_date)
);

CREATE TABLE IF NOT EXISTS quarantine_log (
    id             SERIAL PRIMARY KEY,
    run_id         INTEGER REFERENCES etl_runs(run_id),
    raw_student_id TEXT,
    raw_name       TEXT,
    raw_subject    TEXT,
    raw_score      TEXT,
    raw_exam_date  TEXT,
    error_reason   TEXT        NOT NULL,
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def init_db(db_path: str = DB_PATH) -> None:
    conn = db.get_connection(db_path)
    schema = POSTGRES_SCHEMA if db.IS_POSTGRES else SQLITE_SCHEMA

    if db.IS_POSTGRES:
        # psycopg's cursor.execute() takes one statement at a time (no
        # executescript() like sqlite3 has), so split on ';'.
        cur = conn.cursor()
        for statement in filter(None, (s.strip() for s in schema.split(";"))):
            cur.execute(statement)
    else:
        conn.executescript(schema)

    conn.commit()
    conn.close()

    where = db.DATABASE_URL.rsplit("@", 1)[-1] if db.IS_POSTGRES else db_path
    print(f"[DB] {db.backend_label()} database ready: {where}")


if __name__ == "__main__":
    init_db()
