import os, re, logging
from datetime import datetime, date, timezone
from typing import Any

import pandas as pd

import db

DB_PATH    = os.getenv("DB_PATH",  os.path.join(os.path.dirname(__file__), "marking.db"))
CSV_PATH   = os.getenv("CSV_PATH", os.path.join(os.path.dirname(__file__), "raw_marks.csv"))
CHUNK_SIZE = int(os.getenv("ETL_CHUNK_SIZE", "10000"))
TODAY      = date.today()

REQUIRED_COLUMNS  = ["student_id", "name", "subject", "score", "exam_date"]
STUDENT_ID_REGEX  = re.compile(r"^[A-Za-z0-9_-]{2,20}$")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("etl_pipeline")


class SchemaError(ValueError):
    """Raised when the uploaded CSV is missing required columns."""

def check_required_columns(csv_path: str) -> None:
    """Peek at the header only (nrows=0) before streaming the full file."""
    try:
        header_df = pd.read_csv(csv_path, nrows=0, dtype=str)
    except pd.errors.EmptyDataError:
        raise SchemaError("The uploaded file is empty or not a valid CSV.")

    missing = [c for c in REQUIRED_COLUMNS if c not in header_df.columns]
    if missing:
        raise SchemaError(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}."
        )

def extract_chunks(csv_path: str, chunk_size: int = CHUNK_SIZE):
    """Yield DataFrame chunks. All columns read as str to avoid type coercion."""
    log.info("[EXTRACT] Streaming %s in chunks of %d", csv_path, chunk_size)
    yield from pd.read_csv(csv_path, dtype=str, keep_default_na=False, chunksize=chunk_size)


def _validate_row(row: pd.Series) -> list[str]:
    """Run every check except the cross-row duplicate check. Returns a list of
    human-readable failure reasons (empty list = passes all single-row checks)."""
    reasons = []

    student_id = str(row.get("student_id", "")).strip()
    if not student_id:
        reasons.append("Missing or blank student_id")
    elif not STUDENT_ID_REGEX.match(student_id):
        reasons.append(
            f"Invalid student_id format '{student_id}' "
            "(expected 2-20 letters/digits/-/_ only)"
        )

    if not str(row.get("name", "")).strip():
        reasons.append("Missing student name")

    if not str(row.get("subject", "")).strip():
        reasons.append("Missing subject")

    raw_score = str(row.get("score", "")).strip()
    try:
        score = float(raw_score)
        if score < 0:
            reasons.append(f"Out of bounds score ({score} < 0)")
        elif score > 100:
            reasons.append(f"Out of bounds score ({score} > 100)")
    except ValueError:
        reasons.append(f"Non-numeric score '{raw_score}'")

    raw_date = str(row.get("exam_date", "")).strip()
    try:
        parsed = datetime.strptime(raw_date, "%Y-%m-%d").date()
        if parsed > TODAY:
            reasons.append(f"Future exam date ({raw_date})")
    except ValueError:
        reasons.append(f"Invalid exam_date format '{raw_date}'")

    return reasons


def transform(
    chunk: pd.DataFrame, seen_keys: set[tuple[str, str, str]] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:

    if seen_keys is None:
        seen_keys = set()

    chunk["student_id"] = chunk["student_id"].str.strip()
    chunk["name"]       = chunk["name"].str.strip().str.title()
    chunk["subject"]    = chunk["subject"].str.strip().str.title()
    chunk["score"]      = chunk["score"].str.strip()
    chunk["exam_date"]  = chunk["exam_date"].str.strip()

    valid_flags: list[bool] = []
    error_msgs:  list[str]  = []

    for _, row in chunk.iterrows():
        reasons = _validate_row(row)

        if not reasons:
            key = (row["student_id"], row["subject"], row["exam_date"])
            if key in seen_keys:
                reasons.append(
                    f"Duplicate record for student_id={key[0]}, "
                    f"subject={key[1]}, exam_date={key[2]} (already loaded in this run)"
                )
            else:
                seen_keys.add(key)

        valid_flags.append(not reasons)
        error_msgs.append("; ".join(reasons))

    chunk["_valid"] = valid_flags
    chunk["_error"] = error_msgs

    valid_df   = chunk[chunk["_valid"]].copy()
    invalid_df = chunk[~chunk["_valid"]].copy()

    if not valid_df.empty:
        # Scores are kept as floats — no truncation of decimal marks (e.g. 89.7).
        valid_df["score"] = valid_df["score"].astype(float)

    return valid_df, invalid_df

_UPSERT_SQLITE = """
    INSERT OR REPLACE INTO student_marks
        (run_id, student_id, name, subject, score, exam_date)
    VALUES (?,?,?,?,?,?)
"""
_UPSERT_POSTGRES = """
    INSERT INTO student_marks
        (run_id, student_id, name, subject, score, exam_date)
    VALUES (?,?,?,?,?,?)
    ON CONFLICT (run_id, student_id, subject, exam_date)
    DO UPDATE SET name = EXCLUDED.name, score = EXCLUDED.score
"""


def load_chunk(
    valid_df: pd.DataFrame,
    invalid_df: pd.DataFrame,
    conn,
    run_id: int,
) -> tuple[int, int]:

    inserted_valid       = 0
    inserted_quarantine  = 0

    try:
        if not valid_df.empty:
            rows = [
                (run_id, row["student_id"], row["name"], row["subject"],
                 float(row["score"]), row["exam_date"])
                for _, row in valid_df.iterrows()
            ]
            upsert_sql = _UPSERT_POSTGRES if db.IS_POSTGRES else _UPSERT_SQLITE
            db.query_many(conn, upsert_sql, rows)
            inserted_valid = len(rows)

        if not invalid_df.empty:
            q_rows = [
                (
                    run_id,
                    str(row.get("student_id", ""))[:50],
                    str(row.get("name",       ""))[:255],
                    str(row.get("subject",    ""))[:255],
                    str(row.get("score",      ""))[:50],
                    str(row.get("exam_date",  ""))[:50],
                    row["_error"][:500],
                )
                for _, row in invalid_df.iterrows()
            ]
            db.query_many(
                conn,
                "INSERT INTO quarantine_log "
                "(run_id, raw_student_id, raw_name, raw_subject, raw_score, raw_exam_date, error_reason) "
                "VALUES (?,?,?,?,?,?,?)",
                q_rows,
            )
            inserted_quarantine = len(q_rows)

        conn.commit()
        log.info("[LOAD] Chunk done — valid: %d  quarantined: %d", inserted_valid, inserted_quarantine)

    except Exception as exc:
        conn.rollback()
        log.error("[LOAD] Chunk rolled back: %s", exc)
        raise

    return inserted_valid, inserted_quarantine


def _start_run(conn, filename: str) -> int:
    if db.IS_POSTGRES:
        cur = db.query(
            conn,
            "INSERT INTO etl_runs (filename, status) VALUES (?, 'running') RETURNING run_id",
            (filename,),
        )
        run_id = cur.fetchone()["run_id"]
    else:
        cur = db.query(conn, "INSERT INTO etl_runs (filename, status) VALUES (?, 'running')", (filename,))
        run_id = cur.lastrowid
    conn.commit()
    return run_id


def _finish_run(conn, run_id: int, status: str,
                 total_rows: int, valid_rows: int, invalid_rows: int) -> None:
    completed_at = datetime.now(timezone.utc).isoformat()
    db.query(
        conn,
        """UPDATE etl_runs
           SET status = ?, completed_at = ?,
               total_rows = ?, valid_rows = ?, invalid_rows = ?
           WHERE run_id = ?""",
        (status, completed_at, total_rows, valid_rows, invalid_rows, run_id),
    )
    conn.commit()

def run_pipeline(csv_path: str = CSV_PATH) -> dict[str, Any]:
    """
    Extract → Transform → Load, tracked as a numbered etl_runs record.
    Returns a summary dict. Raises SchemaError for bad CSV shape,
    or the underlying exception for unrecoverable errors.
    """
    total_valid   = 0
    total_invalid = 0
    chunk_count   = 0
    filename      = os.path.basename(csv_path)

    log.info("=" * 60)
    log.info("ETL PIPELINE STARTED — %s", csv_path)
    log.info("=" * 60)

    # Fail fast on a malformed/incomplete CSV before touching the database.
    check_required_columns(csv_path)

    conn = db.get_connection(DB_PATH)
    run_id = _start_run(conn, filename)
    seen_keys: set[tuple[str, str, str]] = set()
    try:
        for chunk in extract_chunks(csv_path):
            chunk_count += 1
            valid_df, bad_df = transform(chunk, seen_keys)
            iv, iq           = load_chunk(valid_df, bad_df, conn, run_id)
            total_valid   += iv
            total_invalid += iq
        _finish_run(conn, run_id, "completed", total_valid + total_invalid, total_valid, total_invalid)
    except FileNotFoundError:
        log.error("[PIPELINE] CSV not found: %s", csv_path)
        _finish_run(conn, run_id, "failed", total_valid + total_invalid, total_valid, total_invalid)
        raise
    except Exception as exc:
        log.error("[PIPELINE] Fatal: %s", exc)
        _finish_run(conn, run_id, "failed", total_valid + total_invalid, total_valid, total_invalid)
        raise
    finally:
        conn.close()

    summary = {
        "status":       "completed",
        "run_id":       run_id,
        "valid_loaded": total_valid,
        "quarantined":  total_invalid,
        "total_rows":   total_valid + total_invalid,
    }
    log.info("ETL COMPLETE — %s", summary)
    return summary


if __name__ == "__main__":
    result = run_pipeline()
    for k, v in result.items():
        print(f"  {k:<20} {v}")
