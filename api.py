import os, logging, tempfile, time
from dotenv import load_dotenv
from collections import defaultdict, deque

load_dotenv()
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

import db
from etl_pipeline import run_pipeline, CSV_PATH, DB_PATH, SchemaError
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("api")

ETL_API_KEY = os.getenv("ETL_API_KEY", "").strip()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

if not ETL_API_KEY:
    raise RuntimeError(
        "[SECURITY] ETL_API_KEY is not set. Copy .env.example to .env for local development "
        "or configure ETL_API_KEY in your deployment environment before starting the API."
    )

log.info("[DB] Using %s backend", db.backend_label())


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != ETL_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")


ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",") if o.strip()
]

MAX_UPLOAD_MB    = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

RATE_LIMIT_CALLS  = 5
RATE_LIMIT_WINDOW = 60   # seconds
_timestamps: dict[str, deque] = defaultdict(deque)


def is_rate_limited(client_ip: str) -> tuple[bool, int]:
    now   = time.monotonic()
    queue = _timestamps[client_ip]
    while queue and now - queue[0] > RATE_LIMIT_WINDOW:
        queue.popleft()
    if len(queue) >= RATE_LIMIT_CALLS:
        retry_after = int(RATE_LIMIT_WINDOW - (now - queue[0])) + 1
        return True, retry_after
    queue.append(now)
    return False, 0

def get_db():
    return db.get_connection(DB_PATH)


def latest_completed_run_id(conn) -> int | None:

    row = db.query(
        conn,
        "SELECT run_id FROM etl_runs WHERE status = 'completed' "
        "ORDER BY run_id DESC LIMIT 1"
    ).fetchone()
    return row["run_id"] if row else None


app = FastAPI(
    title="Internal Marking System API",
    description="v6 — SQLite locally / PostgreSQL when deployed, synchronous ETL, "
                "API-key-protected on every endpoint except /health.",
    version="6.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*", "X-API-Key"],
)

@app.get("/analytics", summary="Subject-level performance analytics", dependencies=[Depends(verify_api_key)])
def get_analytics() -> dict[str, Any]:
    conn = get_db()
    try:
        run_id = latest_completed_run_id(conn)


        if run_id is None:
            subjects, top_students, score_trend = [], [], []
            overall = {"total_students": 0, "total_records": 0, "overall_avg": None}
        else:
            subjects = [dict(r) for r in db.query(conn, """
                SELECT subject,
                       COUNT(*)            AS student_count,
                       ROUND(AVG(score),2) AS avg_score,
                       MIN(score)          AS min_score,
                       MAX(score)          AS max_score
                FROM student_marks
                WHERE run_id = ?
                GROUP BY subject
                ORDER BY avg_score DESC
            """, (run_id,)).fetchall()]

            overall = dict(db.query(conn, """
                SELECT COUNT(DISTINCT student_id) AS total_students,
                       COUNT(*)                   AS total_records,
                       ROUND(AVG(score),2)        AS overall_avg
                FROM student_marks
                WHERE run_id = ?
            """, (run_id,)).fetchone())

            top_students = [dict(r) for r in db.query(conn, """
                SELECT student_id, name, ROUND(AVG(score),2) AS avg_score
                FROM student_marks
                WHERE run_id = ?
                GROUP BY student_id, name
                ORDER BY avg_score DESC
                LIMIT 5
            """, (run_id,)).fetchall()]

            score_trend = [dict(r) for r in db.query(conn, """
                SELECT exam_date,
                       ROUND(AVG(score),2) AS avg_score,
                       COUNT(*)            AS record_count
                FROM student_marks
                WHERE run_id = ?
                GROUP BY exam_date
                ORDER BY exam_date
            """, (run_id,)).fetchall()]

        quarantined = db.query(conn, "SELECT COUNT(*) AS n FROM quarantine_log").fetchone()["n"]

        quarantine_breakdown = [dict(r) for r in db.query(conn, """
            SELECT error_reason, COUNT(*) AS count
            FROM quarantine_log
            GROUP BY error_reason
            ORDER BY count DESC
        """).fetchall()]

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()

    return {
        "run_id":               run_id,
        "subjects":             subjects,
        "overall":              overall,
        "quarantined_total":    quarantined,
        "top_students":         top_students,
        "quarantine_breakdown": quarantine_breakdown,
        "score_trend":          score_trend,
    }

@app.post("/trigger-etl", summary="Upload CSV and run ETL (requires X-API-Key, rate-limited: 5/min)")
async def trigger_etl(
    request: Request,
    file: UploadFile | None = File(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:

    verify_api_key(x_api_key)

    client_ip = request.client.host if request.client else "unknown"
    limited, retry_after = is_rate_limited(client_ip)

    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "Rate limit exceeded.", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )

    if file and file.filename:
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
        if file.content_type not in (None, "text/csv", "application/vnd.ms-excel", "application/octet-stream"):
            raise HTTPException(status_code=400, detail=f"Unexpected content type: {file.content_type}")

        contents = bytearray()
        while chunk := await file.read(1024 * 1024):
            contents.extend(chunk)
            if len(contents) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the {MAX_UPLOAD_MB} MB upload limit.",
                )

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".csv", prefix="ims_")
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(contents)
        try:
            result = run_pipeline(tmp_path)
        except SchemaError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            os.remove(tmp_path)
    else:
        try:
            result = run_pipeline(CSV_PATH)
        except SchemaError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return result

@app.get("/records", summary="Clean student mark records from the latest completed run", dependencies=[Depends(verify_api_key)])
def get_records() -> dict[str, Any]:
    conn = get_db()
    try:
        run_id = latest_completed_run_id(conn)
        if run_id is None:
            rows = []
        else:
            rows = [dict(r) for r in db.query(conn, """
                SELECT run_id, student_id, name, subject, score, exam_date, loaded_at
                FROM student_marks
                WHERE run_id = ?
                ORDER BY loaded_at DESC
            """, (run_id,)).fetchall()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
    return {"records": rows, "count": len(rows)}

@app.get("/quarantine", summary="All quarantined (rejected) rows", dependencies=[Depends(verify_api_key)])
def get_quarantine() -> dict[str, Any]:
    conn = get_db()
    try:
        rows = [dict(r) for r in db.query(conn, """
            SELECT run_id, raw_student_id, raw_name, raw_subject, raw_score,
                   raw_exam_date, error_reason, quarantined_at
            FROM quarantine_log
            ORDER BY quarantined_at DESC
        """).fetchall()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
    return {"records": rows, "count": len(rows)}

@app.get("/etl-runs", summary="ETL run history (ingestion lineage)", dependencies=[Depends(verify_api_key)])
def get_etl_runs() -> dict[str, Any]:
    conn = get_db()
    try:
        rows = [dict(r) for r in db.query(conn, """
            SELECT run_id, filename, started_at, completed_at, status,
                   total_rows, valid_rows, invalid_rows
            FROM etl_runs
            ORDER BY run_id DESC
        """).fetchall()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        conn.close()
    return {"runs": rows, "count": len(rows)}

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "version": "6.0.0", "db": db.backend_label()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
