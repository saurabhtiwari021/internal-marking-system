import os

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres")

if IS_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row

    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
else:
    import sqlite3


def get_connection(db_path: str | None = None):

    if IS_POSTGRES:
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _translate(sql: str) -> str:
    return sql.replace("?", "%s") if IS_POSTGRES else sql


def query(conn, sql: str, params: tuple = ()):
    cur = conn.cursor()
    cur.execute(_translate(sql), params)
    return cur


def query_many(conn, sql: str, seq_of_params):
    cur = conn.cursor()
    cur.executemany(_translate(sql), seq_of_params)
    return cur


def backend_label() -> str:
    return "PostgreSQL" if IS_POSTGRES else "SQLite"
