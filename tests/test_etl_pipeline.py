import sqlite3
import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import etl_pipeline as etl
import init_db

@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """A fresh SQLite DB per test, pointed to by etl_pipeline.DB_PATH."""
    path = str(tmp_path / "test_marking.db")
    init_db.init_db(path)
    monkeypatch.setattr(etl, "DB_PATH", path)
    return path


def make_csv(tmp_path, rows: str) -> str:
    """Write `rows` (header + data lines) to a temp CSV and return its path."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(rows)
    return str(csv_path)


def row(**kwargs) -> pd.Series:
    """Build a single-row pd.Series with sane defaults, overridden by kwargs."""
    defaults = {
        "student_id": "S001",
        "name": "Alice Smith",
        "subject": "Mathematics",
        "score": "85",
        "exam_date": "2024-01-01",
    }
    defaults.update(kwargs)
    return pd.Series(defaults)

def test_valid_score():
    assert etl._validate_row(row(score="85")) == []


def test_decimal_score_allowed():
    assert etl._validate_row(row(score="89.7")) == []


def test_negative_score():
    reasons = etl._validate_row(row(score="-5"))
    assert any("Out of bounds" in r for r in reasons)


def test_score_above_100():
    reasons = etl._validate_row(row(score="105"))
    assert any("Out of bounds" in r for r in reasons)


def test_non_numeric_score():
    reasons = etl._validate_row(row(score="B+"))
    assert any("Non-numeric score" in r for r in reasons)


def test_missing_name():
    reasons = etl._validate_row(row(name=""))
    assert any("Missing student name" in r for r in reasons)


def test_missing_subject():
    reasons = etl._validate_row(row(subject=""))
    assert any("Missing subject" in r for r in reasons)


def test_missing_student_id():
    reasons = etl._validate_row(row(student_id=""))
    assert any("Missing or blank student_id" in r for r in reasons)


def test_whitespace_only_student_id():
    reasons = etl._validate_row(row(student_id="   "))
    assert any("Missing or blank student_id" in r for r in reasons)


def test_invalid_student_id_format():
    reasons = etl._validate_row(row(student_id="S!@#"))
    assert any("Invalid student_id format" in r for r in reasons)


def test_invalid_date():
    reasons = etl._validate_row(row(exam_date="01/01/2024"))
    assert any("Invalid exam_date format" in r for r in reasons)


def test_future_date():
    future = (date.today() + timedelta(days=30)).isoformat()
    reasons = etl._validate_row(row(exam_date=future))
    assert any("Future exam date" in r for r in reasons)


# ══════════════════════════════════════════════════════════════════════════════
# Schema check
# ══════════════════════════════════════════════════════════════════════════════

def test_missing_columns(tmp_path):
    csv_path = make_csv(tmp_path, "student_id,name,score\nS001,John,90\n")
    with pytest.raises(etl.SchemaError, match="subject"):
        etl.check_required_columns(csv_path)


def test_empty_csv(tmp_path):
    csv_path = make_csv(tmp_path, "")
    with pytest.raises(etl.SchemaError):
        etl.check_required_columns(csv_path)


def test_valid_schema_passes(tmp_path):
    csv_path = make_csv(
        tmp_path, "student_id,name,subject,score,exam_date\nS001,John,Math,90,2024-01-01\n"
    )
    etl.check_required_columns(csv_path)  # should not raise


def test_duplicate_records():
    chunk = pd.DataFrame([
        {"student_id": "S001", "name": "Alice", "subject": "Math", "score": "85", "exam_date": "2024-01-01"},
        {"student_id": "S001", "name": "Alice", "subject": "Math", "score": "90", "exam_date": "2024-01-01"},
    ])
    valid_df, invalid_df = etl.transform(chunk)
    assert len(valid_df) == 1
    assert len(invalid_df) == 1
    assert "Duplicate record" in invalid_df.iloc[0]["_error"]


def test_no_false_duplicate_across_subjects():
    """Same student, same date, different subject is NOT a duplicate."""
    chunk = pd.DataFrame([
        {"student_id": "S001", "name": "Alice", "subject": "Math", "score": "85", "exam_date": "2024-01-01"},
        {"student_id": "S001", "name": "Alice", "subject": "Physics", "score": "90", "exam_date": "2024-01-01"},
    ])
    valid_df, invalid_df = etl.transform(chunk)
    assert len(valid_df) == 2
    assert invalid_df.empty


def test_valid_record_load(db_path, tmp_path):
    csv_path = make_csv(
        tmp_path, "student_id,name,subject,score,exam_date\nS001,Alice Smith,Math,85,2024-01-01\n"
    )
    result = etl.run_pipeline(csv_path)
    assert result["valid_loaded"] == 1
    assert result["quarantined"] == 0

    conn = sqlite3.connect(db_path)
    stored = conn.execute("SELECT student_id, score FROM student_marks").fetchall()
    conn.close()
    assert stored == [("S001", 85.0)]


def test_quarantine_load(db_path, tmp_path):
    csv_path = make_csv(
        tmp_path,
        "student_id,name,subject,score,exam_date\n"
        "S001,,Math,85,2024-01-01\n"          # missing name
        "S002,Bob,Physics,150,2024-01-01\n",  # score out of range
    )
    result = etl.run_pipeline(csv_path)
    assert result["valid_loaded"] == 0
    assert result["quarantined"] == 2

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM quarantine_log").fetchone()[0]
    conn.close()
    assert count == 2


def test_full_pipeline_run(db_path, tmp_path):
    """Mixed valid/invalid rows, matches the shape of the sample raw_marks.csv."""
    csv_path = make_csv(
        tmp_path,
        "student_id,name,subject,score,exam_date\n"
        "S001,Alice Smith,Mathematics,85,2023-10-01\n"
        "S002,Bob Jones,Physics,92,2023-10-02\n"
        "S004,,Mathematics,90,2023-10-01\n"          # missing name
        "S005,Eve Davis,Physics,105,2023-10-02\n",   # score > 100
    )
    result = etl.run_pipeline(csv_path)
    assert result["valid_loaded"] == 2
    assert result["quarantined"] == 2
    assert result["total_rows"] == 4


def test_etl_run_tracked(db_path, tmp_path):
    csv_path = make_csv(
        tmp_path, "student_id,name,subject,score,exam_date\nS001,Alice,Math,85,2024-01-01\n"
    )
    result = etl.run_pipeline(csv_path)

    conn = sqlite3.connect(db_path)
    run = conn.execute(
        "SELECT status, total_rows, valid_rows, invalid_rows FROM etl_runs WHERE run_id = ?",
        (result["run_id"],),
    ).fetchone()
    conn.close()
    assert run == ("completed", 1, 1, 0)


def test_repeated_upload_keeps_both_runs(db_path, tmp_path):

    csv_path = make_csv(
        tmp_path, "student_id,name,subject,score,exam_date\nS001,Alice Smith,Math,80,2024-01-01\n"
    )

    result_1 = etl.run_pipeline(csv_path)
    result_2 = etl.run_pipeline(csv_path)  # same file, uploaded again

    assert result_1["run_id"] != result_2["run_id"]
    assert result_1["valid_loaded"] == 1
    assert result_2["valid_loaded"] == 1

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT run_id, student_id, score FROM student_marks ORDER BY run_id"
    ).fetchall()
    conn.close()

    # Both runs' rows exist — the second upload did not delete the first's.
    assert rows == [
        (result_1["run_id"], "S001", 80.0),
        (result_2["run_id"], "S001", 80.0),
    ]


def test_missing_required_columns_raises_before_touching_db(db_path, tmp_path):
    csv_path = make_csv(tmp_path, "student_id,name,score\nS001,John,90\n")
    with pytest.raises(etl.SchemaError):
        etl.run_pipeline(csv_path)

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM etl_runs").fetchone()[0]
    conn.close()
    assert count == 0  # no run row created for a file that never passed schema check
