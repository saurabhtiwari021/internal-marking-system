# Internal Marking System

A production-style academic data platform for uploading, validating, processing, storing, and analyzing student internal marks through an end-to-end ETL workflow.

The application combines a **FastAPI backend** for data ingestion and processing with a **Streamlit dashboard** for interactive analysis and reporting.

## Overview

The Internal Marking System is designed to solve a common academic data-management problem: internal marks often arrive in inconsistent files and need to be validated, cleaned, processed, stored, and analyzed before they can be used reliably.

This project provides a complete workflow:

**Upload → Validate → Transform → Store → Analyze → Visualize**

It is built with a strong focus on data quality, traceability, and practical analytics.

## Key Features

- Upload student internal-mark datasets through the application.
- Validate input schemas and required columns.
- Validate:
  - Student IDs
  - Marks and score ranges
  - Dates
  - Duplicate records
  - Missing/invalid values
- Quarantine invalid records instead of silently dropping them.
- Maintain detailed validation/error information for rejected records.
- Execute a Pandas-based ETL pipeline for data cleaning and transformation.
- Persist validated data into a relational database.
- Maintain ETL run information for traceability and lineage.
- Expose backend functionality through REST APIs using FastAPI.
- Provide an interactive Streamlit dashboard for data exploration and analysis.
- Generate summary statistics and academic performance insights.
- Support a production-style separation between ingestion, processing, storage, API, and visualization layers.

## Architecture

```text
                    ┌─────────────────────┐
                    │   CSV / Data File   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     FastAPI API     │
                    │   File Ingestion    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Pandas ETL Layer  │
                    │                     │
                    │ Schema Validation   │
                    │ Data Cleaning       │
                    │ Business Rules      │
                    │ Duplicate Checks    │
                    │ Error Handling      │
                    └──────────┬──────────┘
                               │
                  ┌────────────┴────────────┐
                  │                         │
                  ▼                         ▼
        ┌───────────────────┐     ┌───────────────────┐
        │ Valid Records     │     │ Quarantined Data  │
        └─────────┬─────────┘     └───────────────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ Relational DB     │
        │ Student / Marks   │
        │ ETL Run Lineage   │
        └─────────┬─────────┘
                  │
                  ▼
        ┌───────────────────┐
        │ Streamlit         │
        │ Analytics         │
        │ Dashboard         │
        └───────────────────┘
```

## Tech Stack

### Backend & API
- Python
- FastAPI
- SQLAlchemy
- Uvicorn

### Data Engineering & Analytics
- Pandas
- NumPy
- ETL / data validation
- Data cleaning
- Data modeling
- Statistical analysis

### Database
- MySQL

### Dashboard
- Streamlit

### Development Tools
- Git
- GitHub

## ETL Workflow

The ETL pipeline is the core of the application.

### 1. Extract

The system accepts academic data files and loads the source dataset for processing.

### 2. Validate

The incoming dataset is checked for structural and business-rule issues, including:

- Required columns
- Data types
- Missing values
- Student ID validity
- Score/marks ranges
- Date validity
- Duplicate records

### 3. Quarantine

Invalid records are separated from valid data rather than being discarded.

Each rejected record can be associated with validation/error information, making the pipeline easier to debug and audit.

### 4. Transform

Valid records are cleaned and normalized using Pandas before being prepared for persistence.

### 5. Load

Cleaned records are stored in the database using the application's data model.

### 6. Lineage

ETL execution information is maintained so that individual processing runs can be tracked and reviewed.

## Project Structure

```text
internal-marking-system/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   │
│   └── requirements.txt
│
├── dashboard/
│   └── app.py
│
├── data/
│   └── sample/
│
├── tests/
│
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

> The exact folder structure may vary slightly depending on the current repository organization.

## Getting Started

### Prerequisites

Make sure the following are installed:

- Python 3.10+
- MySQL
- Git

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/internal-marking-system.git
cd internal-marking-system
```

### 2. Create a virtual environment

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If backend and dashboard dependencies are maintained separately, install their respective requirement files as well.

## Environment Variables

Create a `.env` file in the project root and configure the database/application settings required by your local setup.

Example:

```env
DATABASE_URL=mysql+pymysql://<username>:<password>@localhost:3306/<database_name>
```

Do **not** commit `.env` or other files containing secrets to GitHub.

A `.env.example` file should be included in the repository so that other developers know which variables are required.

## Database Setup

Create the required MySQL database before starting the application.

Example:

```sql
CREATE DATABASE internal_marking_system;
```

Update the connection string in `.env` to match your local MySQL configuration.

The application can then initialize/use the required database tables through its SQLAlchemy models and startup/database logic.

## Running the Backend

Start the FastAPI application with:

```bash
uvicorn backend.app.main:app --reload
```

The API will normally be available at:

```text
http://127.0.0.1:8000
```

FastAPI also provides interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

and:

```text
http://127.0.0.1:8000/redoc
```

## Running the Dashboard

Start Streamlit with:

```bash
streamlit run dashboard/app.py
```

The dashboard will normally be available at:

```text
http://localhost:8501
```

## Dashboard

The Streamlit dashboard is intended to provide an easy-to-use analytics layer over the processed academic data.

Typical dashboard capabilities include:

- Dataset overview
- Student-level performance analysis
- Subject/assessment summaries
- Score distributions
- Aggregated statistics
- Data-quality indicators
- ETL processing information
- Interactive filtering and exploration

### Live Dashboard

**Dashboard:** `https://<your-streamlit-deployment-url>`

Replace the placeholder above with the deployed Streamlit URL before publishing the repository.

## API

The FastAPI backend exposes endpoints for the application's data and ETL workflow.

Typical API responsibilities include:

- Uploading datasets
- Triggering/handling ETL processing
- Accessing student/marks data
- Retrieving validation results
- Inspecting ETL run information
- Serving processed data to the dashboard

Use the interactive Swagger UI at:

```text
http://127.0.0.1:8000/docs
```

to view the exact endpoints and request/response schemas implemented in the current version.

## Data Quality & Reliability

A major design goal of this system is to avoid treating uploaded academic data as automatically trustworthy.

Instead, the pipeline explicitly validates incoming records and preserves information about invalid data.

This provides several benefits:

- Bad records do not silently enter the database.
- Validation failures are traceable.
- ETL runs can be audited.
- Data-processing issues are easier to diagnose.
- The resulting analytics are based on controlled, validated data.

## Example Input

A typical input dataset may contain fields such as:

```text
student_id,student_name,subject,marks,assessment_date
2026001,Aarav Sharma,DBMS,86,2026-08-01
2026002,Riya Singh,DBMS,91,2026-08-01
2026003,Arjun Mehta,DBMS,74,2026-08-01
```

The exact schema should match the validation rules implemented by the current application.

## Error Handling

The pipeline is designed to distinguish between valid and invalid records.

Examples of possible validation failures:

```text
Invalid student ID
Missing required field
Marks outside permitted range
Invalid date
Duplicate record
Incorrect data type
```

Rather than removing these rows without explanation, the system can retain them in a quarantine/error flow with associated validation information.

## Deployment

The project can be deployed as separate services:

### Backend
Deploy the FastAPI service on a platform that supports Python web applications.

### Dashboard
Deploy the Streamlit application separately and configure it to communicate with the deployed backend.

### Database
Use a managed MySQL-compatible database for production workloads.

For deployment, make sure:

- Environment variables are configured securely.
- Database credentials are never committed.
- CORS is configured appropriately.
- The backend URL used by the dashboard points to the deployed API.
- Production services use stable database credentials and connection settings.

## Production Considerations

For a production deployment, consider adding:

- Authentication and authorization
- Role-based access control
- Structured application logging
- Rate limiting
- API versioning
- Automated tests and CI/CD
- Database migrations
- Monitoring and health checks
- More granular audit logging
- Stronger file-size/type validation
- Object storage for uploaded source files
- Secure secret management

## Future Improvements

Possible future enhancements include:

- Faculty/admin authentication
- Role-based dashboards
- Automated report generation
- Export to Excel/PDF
- Student performance forecasting
- Attendance and marks integration
- More advanced anomaly detection
- Email/report notifications
- Background ETL jobs
- Containerized deployment with Docker
- CI/CD automation

## Why This Project?

This project demonstrates practical skills across several areas:

**Backend Development**
- REST API development with FastAPI
- Database integration with SQLAlchemy
- Service-oriented application structure

**Data Engineering**
- ETL pipeline design
- Schema and business-rule validation
- Data cleaning
- Error quarantine
- ETL lineage

**Data Analytics**
- Pandas-based transformation
- Statistical analysis
- Interactive dashboard development

**Software Engineering**
- Modular project architecture
- Environment-based configuration
- Git/GitHub workflow
- Production-oriented thinking

## Author

**Saurabh Tiwari**

Built as an academic data engineering and analytics project combining backend development, ETL, database management, and interactive reporting.
