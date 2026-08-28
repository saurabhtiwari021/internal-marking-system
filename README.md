# Internal Marking System

A data pipeline + dashboard project built using FastAPI and Streamlit.

## 👨‍💻 Author
**Saurabh Tiwari**

The **Internal Marking System** is a data processing and analytics application designed to clean, validate, and analyze student marks efficiently.

It allows users to upload raw internal marks in CSV format, automatically performs data validation and cleaning through an ETL pipeline, and presents meaningful insights via an interactive dashboard.

---

## 🚀 Key Features

- **CSV Upload**
  - Upload raw student marks (`raw_marks.csv`) directly from the dashboard

-  **ETL Pipeline**
  - Extracts, transforms, and loads data into a structured database (SQLite locally, PostgreSQL when deployed)
  - Ensures data consistency and formatting

-  **Data Cleaning & Validation**
  - Detects and handles:
    - Missing student names
    - Non-numeric scores
    - Out-of-range values (e.g., >100)
    - Invalid/future exam dates
  - Invalid entries are moved to a **quarantine log**

-  **Interactive Dashboard (Streamlit)**
  - **Filtered Performance** section — KPI cards, subject analytics, grade distribution, score trend, and top students, all driven by the subject/exam-date filters
  - **Data Quality & Pipeline Monitoring** section — quarantine breakdown and ETL run history, always shown for the full pipeline history regardless of filters
  - Student performance search — look up a student_id for their average, high/low, per-subject breakdown, and score trend

-  **Error Tracking**
  - Detailed breakdown of validation errors
  - Transparent data quality monitoring
  - Duplicate detection — a repeated (student_id, subject, exam_date) in the same upload is quarantined, not silently overwritten
  - student_id format validation (required, 2-20 letters/digits/-/_)

-  **Export Clean Data**
  - Separate downloads for clean marks, subject report, and quarantine report — each button downloads exactly what it says

-  **Security**
  - Every endpoint except `GET /health` requires an `X-API-Key` header
  - `ENVIRONMENT=production` fails the API at startup if `ETL_API_KEY` was left at its default, instead of silently running with a known secret
  - Uploaded CSVs are capped at `MAX_UPLOAD_MB` (10 MB default) and rejected before being fully read into memory
  - CORS restricted to a configured origin list (not `*`) — protects future browser-based clients; the Streamlit dashboard itself talks to the API server-side, so the `X-API-Key` check (not CORS) is what protects that connection today

-  **Data lineage / versioning**
  - Marks are unique per `(run_id, student_id, subject, exam_date)`, not just `(student_id, subject, exam_date)` — every ETL run's rows are kept rather than a new upload silently overwriting the last
  - `GET /analytics` and `GET /records` read from the latest **completed** run only, so historical runs never get mixed into the current view
  - `GET /etl-runs` and the quarantine log still show the full history across every run

-  **Tests**
  - 23 automated tests covering:
    - row validation
    - schema validation
    - duplicate detection
    - quarantine handling
    - ETL loading
    - ETL run tracking

---

##  How It Works

1. Upload a raw CSV file containing student marks  
2. Run the ETL pipeline  
3. System validates and cleans the data  
4. Errors are quarantined and reported  
5. Clean data is stored and visualized  
6. Export the final processed dataset  

---

##  Tech Stack

- **Backend:** FastAPI  
- **Frontend:** Streamlit  
- **Database:** SQLite locally, PostgreSQL when deployed (see below)
- **Language:** Python  

> **SQLite vs. PostgreSQL** — Locally, with no further setup, the app uses a
> SQLite file (`marking.db`) — zero external services needed. Set the
> `DATABASE_URL` environment variable to a PostgreSQL connection string
> (this project uses Supabase's, but any Postgres provider's works) and the
> API automatically switches to it instead — same code, same endpoints,
> nothing else in the design changes. See `db.py` for how this works, and
> **Deploying** below for the concrete steps.

> **Synchronous ETL** — `POST /trigger-etl` runs the pipeline inline and returns the result, which is appropriate for the project's expected file sizes (a few MB, seconds to process). For much larger files this would move to background job processing with a task queue instead of blocking the HTTP request.

> **Rate limiting** — the in-memory limiter (5 calls/60s per IP) works correctly for a single API process. If this were ever horizontally scaled to multiple instances, each instance would track its own counter independently, so a shared store (e.g. Redis) would be needed for a true global limit.

---

##  Use Case

This system is useful for:
- Teachers managing internal marks
- Academic data processing
- Data engineering practice (ETL pipelines)
- Learning backend + dashboard integration

---

##  Setup Instructions

###  macOS / Linux

#### 1. Setup Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. Initialize Database
```bash
python init_db.py
```

#### 3. Start Backend (Terminal 1)
```bash
python api.py
# OR
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

#### 4. Start Frontend (Terminal 2)
```bash
source venv/bin/activate
streamlit run dashboard.py
```

### Windows

#### 1. Install Python

Make sure Python 3.11+ is installed and added to PATH.

#### 2. Setup Environment
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

#### 3. Initialize Database
```bash
python init_db.py
```

You should see:
```
[DB] SQLite database ready: marking.db
```

#### 4. Start Backend (Terminal 1)
```bash
python api.py
# OR
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Backend runs at: `http://localhost:8000`

#### 5. Start Frontend (Terminal 2)
```bash
venv\Scripts\activate
streamlit run dashboard.py
```

Dashboard runs at: `http://localhost:8501`

---

## 🔐 Environment Variables

Copy `.env.example` to `.env` for local development (or export the variables in your shell).
Never commit `.env`; it is intentionally ignored by Git.

> ⚠️ **Never deploy without setting `ETL_API_KEY` and `DASHBOARD_API_KEY` to the same strong random secret.** The application has no hard-coded API-key fallback; it refuses to start the API when `ETL_API_KEY` is missing.

| Variable            | Used by      | Value / default                    | Purpose                                  |
|---------------------|--------------|--------------------------------------|-------------------------------------------|
| `ETL_API_KEY`        | api.py    | *(required)*                    | Strong secret required in `X-API-Key` on every endpoint except `/health` |
| `DASHBOARD_API_KEY`  | dashboard.py | *(required; same as ETL_API_KEY)* | Dashboard-to-API authentication key |
| `ENVIRONMENT`        | api.py    | `development`                   | Informational environment label; production deployments should use `production` |
| `MAX_UPLOAD_MB`      | api.py    | `10`                             | Maximum accepted CSV upload size          |
| `ALLOWED_ORIGINS`    | api.py    | `http://localhost:8501`         | Comma-separated CORS allow-list           |
| `API_BASE_URL`       | dashboard.py | `http://localhost:8000`      | Where the dashboard finds the API         |
| `DATABASE_URL`       | api.py, etl_pipeline.py, init_db.py | *(unset)* | PostgreSQL connection string. Unset = SQLite (local dev). Set = Postgres (deployed). |

## ✅ Running Tests

```bash
pytest
```

You should see all tests pass, e.g. `23 passed`. Tests always run against a
temporary SQLite database regardless of `DATABASE_URL` — they don't touch
Postgres.

---

## ☁️ Deploying

The plan: **FastAPI → Render**, **PostgreSQL → Supabase**, **Streamlit
dashboard → Streamlit Community Cloud**, **code → GitHub**. Push this repo
to GitHub first — all platforms deploy from it.

### 1. Database, on Supabase

1. Create a project at [supabase.com](https://supabase.com) (free tier is
   fine to start).
2. In the project, go to **Settings → Database → Connection string** and
   copy the **connection pooling** string (not the direct connection) —
   it looks like
   `postgresql://postgres.xxxxxxxx:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:6543/postgres`.
   Use the pooler URL rather than the direct one: Render's free plan can
   spin your service down between requests, and the pooler handles the
   resulting burst of reconnects far better than a direct connection does.
3. Fill in your database password in place of `[YOUR-PASSWORD]`. Keep this
   full string handy — it's what you'll paste into `DATABASE_URL` on
   Render in the next step. `db.py` accepts it as-is (see `db.py` for how
   the `postgres://` / `postgresql://` prefix is handled automatically).

### 2. API, on Render

The included `render.yaml` defines the web service (a Render "Blueprint"),
so this is mostly point-and-click:

1. In the Render dashboard: **New +** → **Blueprint** → connect this GitHub repo.
   Render reads `render.yaml` and provisions the web service
   (`marking-system-api`).
2. When prompted, set two values `render.yaml` deliberately leaves for you
   to fill in:
   - `DATABASE_URL` — the Supabase pooler connection string from step 1.
   - `ETL_API_KEY` — a long random string. You'll copy this same value to
     Streamlit Cloud in step 3.
   `ENVIRONMENT` is already set to `production`, so the API will refuse to
   start if `ETL_API_KEY` is left at the default — that's intentional.
3. Deploy. Render runs `python init_db.py` (creates the tables in Supabase
   — safe to re-run on every future deploy) and then starts the API with
   `uvicorn api:app --host 0.0.0.0 --port $PORT`.
4. Once it's live, note the service URL Render gives you
   (`https://marking-system-api-xxxx.onrender.com` or similar) — check
   `https://<that-url>/health` returns `{"status":"ok", ..., "db":"PostgreSQL"}`.

> **Any Postgres provider works.** Since the app only needs a standard
> `DATABASE_URL`, Supabase isn't special-cased — Render's own managed
> Postgres, Neon, or anywhere else would be a drop-in replacement. Supabase
> is just the one this project is configured for above.

### 3. Dashboard, on Streamlit Community Cloud

1. In Streamlit Community Cloud: **New app** → point it at this repo,
   main file path `dashboard.py`.
2. In the app's **Settings → Secrets**, paste the two values from
   `.streamlit/secrets.toml.example`, filled in for real:
   ```toml
   API_BASE_URL = "https://<your-render-api-url>"
   DASHBOARD_API_KEY = "<the same ETL_API_KEY you set on Render>"
   ```
   (Streamlit Cloud exposes these via `st.secrets`, not as OS environment
   variables — `dashboard.py` bridges them into `os.environ` at startup,
   so nothing else needs to change between local and deployed.)
3. Deploy. Once it's live, go back to the Render service's environment
   variables and add `ALLOWED_ORIGINS` set to the Streamlit app's URL, so
   CORS is scoped to it instead of the `localhost:8501` default (this
   doesn't affect the dashboard-to-API connection either way — see the
   Security section above — but it's the correct thing to tighten before
   calling this "deployed").

### 4. Everyday redeploys

Both platforms auto-deploy on push to the branch you connected, so after
the first setup, shipping a change is just `git push`.
