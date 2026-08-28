import io, os
from dotenv import load_dotenv
import pandas as pd
import requests
import streamlit as st

load_dotenv()

try:
    for _key in ("API_BASE_URL", "DASHBOARD_API_KEY"):
        if _key in st.secrets and not os.getenv(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass  

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("DASHBOARD_API_KEY", "").strip()
if not API_KEY:
    st.error("DASHBOARD_API_KEY is not configured. Copy .env.example to .env for local development or set the Streamlit Cloud secret.")
    st.stop()
PASS_MARK = 40  

st.set_page_config(
    page_title="Internal Marking System",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stButton > button {
      width:100%; background:#4f46e5; color:white;
      border-radius:8px; border:none; padding:.6rem 1rem; font-weight:600;
  }
  .stButton > button:hover { background:#4338ca; }
  .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)



AUTH_HEADERS = {"X-API-Key": API_KEY}   # every GET below requires this too


def fetch_analytics() -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/analytics", headers=AUTH_HEADERS, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot reach the API. Run: `uvicorn api:app --port 8000`")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            st.error("❌ Unauthorized — DASHBOARD_API_KEY doesn't match the API's ETL_API_KEY.")
        else:
            st.error(f"❌ API error {e.response.status_code}: {e.response.text}")
        return None


def fetch_json(path: str) -> list[dict]:
    """Fetch a list-of-records endpoint (/records, /quarantine, /etl-runs)."""
    try:
        r = requests.get(f"{API_BASE}{path}", headers=AUTH_HEADERS, timeout=60)
        r.raise_for_status()
        body = r.json()
        return body.get("records") or body.get("runs") or []
    except requests.exceptions.RequestException:
        return []


def trigger_etl(uploaded_bytes: bytes | None, filename: str | None) -> dict | None:
    """Call /trigger-etl and wait for the synchronous result (no polling needed)."""
    try:
        headers = {"X-API-Key": API_KEY}
        if uploaded_bytes:
            files = {"file": (filename, uploaded_bytes, "text/csv")}
            resp  = requests.post(f"{API_BASE}/trigger-etl", files=files, headers=headers, timeout=120)
        else:
            resp  = requests.post(f"{API_BASE}/trigger-etl", headers=headers, timeout=120)

        if resp.status_code == 401:
            st.error("❌ Unauthorized — DASHBOARD_API_KEY doesn't match the API's ETL_API_KEY.")
            return None

        if resp.status_code == 429:
            d = resp.json().get("detail", {})
            st.warning(
                f"⚠️ Rate limit hit — max {RATE_LIMIT_CALLS} calls per minute. "
                f"Retry in **{d.get('retry_after', '?')}s**."
            )
            return None

        if resp.status_code == 400:
            detail = resp.json().get("detail", "The uploaded file doesn't match the expected format.")
            st.error(f"❌ {detail}")
            return None

        resp.raise_for_status()
        return resp.json()   # summary dict: valid_loaded, quarantined, total_rows

    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot reach the API.")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ Trigger error: {e.response.text}")
        return None


RATE_LIMIT_CALLS = 5   # shown in sidebar info only


with st.sidebar:
    st.title("📊 Control Panel")
    st.markdown("---")

    st.markdown("### 📁 Upload Marks CSV")
    uploaded_file = st.file_uploader(
        "Upload Marks (CSV)",
        type=["csv"],
        help="Columns: student_id, name, subject, score, exam_date",
        label_visibility="collapsed",
    )
    if uploaded_file:
        st.success(f"File ready: **{uploaded_file.name}**")
    else:
        st.caption("No file selected — will use server-side `raw_marks.csv`.")

    st.markdown("### 🔄 ETL Pipeline")
    run_clicked = st.button("▶ Run ETL Pipeline")

    if run_clicked:
        file_bytes = uploaded_file.read() if uploaded_file else None
        file_name  = uploaded_file.name   if uploaded_file else None

        with st.spinner("⏳ Running ETL pipeline…"):
            result = trigger_etl(file_bytes, file_name)

        if result:
            st.success(
                f"✅ Done — {result.get('valid_loaded', 0)} loaded, "
                f"{result.get('quarantined', 0)} quarantined."
            )
            # Force dashboard to refresh from the API
            st.session_state["refresh"] = True

    st.markdown("---")
    st.markdown("### ℹ️ Rate Limit")
    st.info(f"ETL trigger: **{RATE_LIMIT_CALLS} calls / 60 s** per IP.")
    st.markdown("---")
    st.caption("Internal Marking System v4.0")


st.title("📊 Internal Marking System — Dashboard")
st.markdown("Live view of validated student performance data.")
st.markdown("---")

if st.session_state.pop("refresh", False):
    st.rerun()   # Streamlit re-runs the whole script, fetching fresh data

data = fetch_analytics()

if not data:
    st.info("No data yet. Upload a CSV and click **Run ETL Pipeline** in the sidebar.")
    st.stop()

quarantined = data.get("quarantined_total", 0)

records = fetch_json("/records")
df_records = pd.DataFrame(records)
if not df_records.empty:
    df_records["score"]     = df_records["score"].astype(float)
    df_records["exam_date"] = pd.to_datetime(df_records["exam_date"])

st.subheader("🔎 Filters")
st.caption("Everything under **Filtered Performance** below respects these filters.")
if df_records.empty:
    st.caption("No clean records yet — filters will appear once data is loaded.")
    filtered_df = df_records
else:
    all_subjects = sorted(df_records["subject"].unique().tolist())
    min_date, max_date = df_records["exam_date"].min().date(), df_records["exam_date"].max().date()

    f1, f2 = st.columns([2, 2])
    with f1:
        chosen_subjects = st.multiselect("Subject", options=all_subjects, default=all_subjects)
    with f2:
        date_range = st.date_input(
            "Exam date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
        )

    filtered_df = df_records[df_records["subject"].isin(chosen_subjects)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        filtered_df = filtered_df[
            (filtered_df["exam_date"].dt.date >= start) & (filtered_df["exam_date"].dt.date <= end)
        ]

st.markdown("---")

st.header("📈 Filtered Performance")

c1, c2, c3 = st.columns(3)
if filtered_df.empty:
    c1.metric("👥 Students",    "—")
    c2.metric("📝 Records",     "—")
    c3.metric("📈 Overall Avg", "—")
else:
    c1.metric("👥 Students",    int(filtered_df["student_id"].nunique()))
    c2.metric("📝 Records",     len(filtered_df))
    c3.metric("📈 Overall Avg", f"{filtered_df['score'].mean():.2f} / 100")

st.markdown("---")

st.subheader("📚 Subject Analytics")
if filtered_df.empty:
    st.caption("No records match the current filters.")
else:
    grouped = filtered_df.groupby("subject")["score"]
    df_sub = grouped.agg(
        Count="count", **{"Avg Score": "mean", "Highest": "max", "Lowest": "min"}
    ).reset_index().rename(columns={"subject": "Subject"})
    df_sub["Avg Score"] = df_sub["Avg Score"].round(2)
    df_sub["Pass %"] = filtered_df.groupby("subject")["score"].apply(
        lambda s: round((s >= PASS_MARK).mean() * 100, 1)
    ).values
    df_sub["Fail %"] = (100 - df_sub["Pass %"]).round(1)
    df_sub = df_sub.sort_values("Avg Score", ascending=False)

    st.bar_chart(df_sub.set_index("Subject")["Avg Score"], use_container_width=True, height=300)
    st.dataframe(df_sub, use_container_width=True, hide_index=True)

    st.markdown(f"**Grade distribution** _(pass mark: {PASS_MARK})_")
    dist_subject = st.selectbox("Show distribution for", options=["All filtered subjects"] + df_sub["Subject"].tolist())
    dist_df = filtered_df if dist_subject == "All filtered subjects" else filtered_df[filtered_df["subject"] == dist_subject]

    bins   = [0, 60, 70, 80, 90, 101]
    labels = ["<60", "60–69", "70–79", "80–89", "90–100"]
    grade_counts = pd.cut(dist_df["score"], bins=bins, labels=labels, right=False).value_counts().reindex(labels, fill_value=0)
    st.bar_chart(grade_counts, use_container_width=True, height=240)

st.markdown("---")

st.subheader("📅 Score Trend by Exam Date")
if filtered_df.empty:
    st.caption("No records match the current filters.")
else:
    df_trend = (
        filtered_df.groupby("exam_date")["score"]
        .agg(**{"Avg Score": "mean", "Records": "count"})
        .reset_index()
        .rename(columns={"exam_date": "Exam Date"})
        .sort_values("Exam Date")
    )
    df_trend["Avg Score"] = df_trend["Avg Score"].round(2)
    st.line_chart(df_trend.set_index("Exam Date")["Avg Score"], use_container_width=True, height=260)

st.markdown("---")
st.subheader("🏆 Top 5 Students")
if filtered_df.empty:
    st.caption("No records match the current filters.")
else:
    df_top = (
        filtered_df.groupby(["student_id", "name"])["score"]
        .mean()
        .round(2)
        .reset_index()
        .sort_values("score", ascending=False)
        .head(5)
        .rename(columns={"student_id": "ID", "name": "Name", "score": "Avg Score"})
    )
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    df_top.index = medals[:len(df_top)]
    st.dataframe(df_top, use_container_width=True)

st.markdown("---")
st.subheader("🎓 Student Performance")
search_id = st.text_input("Search by Student ID", placeholder="e.g. S001")
if search_id:
    student_df = df_records[df_records["student_id"].str.lower() == search_id.strip().lower()]
    if student_df.empty:
        st.warning(f"No records found for student_id `{search_id}`.")
    else:
        name = student_df["name"].iloc[0]
        st.markdown(f"### {name}  ·  `{search_id}`")
        s1, s2, s3 = st.columns(3)
        s1.metric("Overall Average", f"{student_df['score'].mean():.1f}")
        s2.metric("Highest Score",   f"{student_df['score'].max():.0f}")
        s3.metric("Lowest Score",    f"{student_df['score'].min():.0f}")

        st.markdown("**By subject**")
        by_subject = student_df.groupby("subject")["score"].mean().round(1).sort_values(ascending=False)
        st.dataframe(by_subject.rename("Avg Score"), use_container_width=True)

        st.markdown("**Trend over time**")
        trend_series = student_df.sort_values("exam_date").set_index("exam_date")["score"]
        st.line_chart(trend_series, use_container_width=True, height=220)

st.markdown("---")

st.subheader("💾 Exports")
exp_a, exp_b, exp_c = st.columns(3)

with exp_a:
    if records:
        buf = io.StringIO()
        pd.DataFrame(records).to_csv(buf, index=False)
        st.download_button(
            "⬇ Clean Marks (CSV)",
            data=buf.getvalue().encode(),
            file_name="clean_marks.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.caption("No clean records yet.")

with exp_b:
    if not df_records.empty:
        full_sub = df_records.groupby("subject")["score"].agg(
            Count="count", **{"Avg Score": "mean", "Highest": "max", "Lowest": "min"}
        ).reset_index().rename(columns={"subject": "Subject"})
        full_sub["Avg Score"] = full_sub["Avg Score"].round(2)
        buf = io.StringIO()
        full_sub.to_csv(buf, index=False)
        st.download_button(
            "⬇ Subject Report (CSV)",
            data=buf.getvalue().encode(),
            file_name="subject_performance_report.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.caption("No subject data yet.")

quarantine_records = fetch_json("/quarantine")
with exp_c:
    if quarantine_records:
        buf = io.StringIO()
        pd.DataFrame(quarantine_records).to_csv(buf, index=False)
        st.download_button(
            "⬇ Quarantine Report (CSV)",
            data=buf.getvalue().encode(),
            file_name="quarantine_report.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.caption("No quarantined rows.")

st.markdown("---")

st.header("🛡️ Data Quality & Pipeline Monitoring")

st.metric("🚫 Quarantined (all runs)", quarantined)

qb = data.get("quarantine_breakdown", [])
if qb:
    st.subheader("Quarantine Log — Error Breakdown")
    df_q = pd.DataFrame(qb).rename(columns={"error_reason": "Error Reason", "count": "Count"})
    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.bar_chart(df_q.set_index("Error Reason")["Count"], use_container_width=True, height=240)
    with col_b:
        st.dataframe(df_q, use_container_width=True, hide_index=True)
    st.warning(f"⚠️ {quarantined} rows failed validation and were quarantined.")

st.markdown("---")

runs = fetch_json("/etl-runs")
if runs:
    st.subheader("ETL Run History")
    df_runs = pd.DataFrame(runs).rename(columns={
        "run_id": "Run", "filename": "File", "started_at": "Started",
        "completed_at": "Completed", "status": "Status",
        "total_rows": "Total", "valid_rows": "Valid", "invalid_rows": "Quarantined",
    })
    st.dataframe(df_runs, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption(
    "Data sourced from the FastAPI `/analytics` endpoint (SQLite locally, "
    "PostgreSQL when deployed). Filtered Performance reflects the latest "
    "completed ETL run only."
)
