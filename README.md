# Expense Tracker

FastAPI expense tracker with a plain HTML/CSS/JavaScript frontend and Neon
PostgreSQL storage. The SQLite database is retained as a read-only migration
source and backup.

## Requirements

- Python 3.14
- A Neon PostgreSQL project

## Local setup

From the project root, create and activate a virtual environment and install
the Python dependencies:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Copy the placeholder environment file, then replace `DATABASE_URL` with the
**pooled** connection string and `DATABASE_URL_UNPOOLED` with the direct
connection string for your Neon development branch. Keep `sslmode=require` in
both URLs. `DATABASE_URL` is only read by the Python backend; never put it in
frontend JavaScript.

```powershell
Copy-Item backend\.env.example .env
```

The root `.env` is ignored by Git. The backend also loads `DATABASE_URL` from
the hosting environment, so do not commit a real connection string.

## Neon database and schema

Create or select a Neon PostgreSQL project and branch. Use a pooled connection
string (hostname containing `-pooler`) for the app. Keep the unpooled URL for
migrations or database administration. The schema contains expenses, recurring
income, recurring bills, and bill payments with their checks, unique
constraints, identity columns, and cascading foreign keys.

Initialize the schema on the configured branch. Schema changes and the import
use `DATABASE_URL_UNPOOLED`; normal API requests use the pooled
`DATABASE_URL`.

```powershell
python -m backend.database.db
```

Schema initialization creates missing tables; it does not migrate or delete
existing records. Do not point local test runs at the production branch.

## Importing the existing SQLite database

The importer reads `backend\database\expenses.db` in SQLite read-only mode; the
original file and `expenses_backup.db` remain untouched. It refuses to import
into non-empty application tables unless it finds its own matching migration
record, and repeated imports verify that the previously imported source rows
still match.

First configure `DATABASE_URL` for an empty Neon development branch and
initialize its schema. Then run:

```powershell
python -m backend.database.neon_postgres
```

To import a different SQLite snapshot:

```powershell
python -m backend.database.neon_postgres path\to\expenses.db
```

The importer transfers expenses, recurring income, recurring bills, and bill
payments in dependency order, preserving IDs, date values, amounts, notes, and
timestamps. It verifies all four row counts and advances the PostgreSQL
identity sequences. Re-running it for the same unchanged source reports
`already_imported`. Review the report before changing any production
`DATABASE_URL`; production import is a separate, deliberate operation.

## Run locally

Start FastAPI from the project root:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001
```

In another terminal, serve the existing frontend:

```powershell
python -m http.server 5500 --bind 127.0.0.1 --directory frontend
```

Open <http://127.0.0.1:5500>. The frontend uses the local API at port 8001 in
this setup, or same-origin API paths when hosted together. The API docs are at
<http://127.0.0.1:8001/docs>.

## Tests

The API-surface tests run without a database:

```powershell
python -m unittest discover -s tests -v
```

Database integration tests make writes and therefore require an explicitly
configured, isolated test branch. Set both variables only after confirming
that `.env` points to that disposable/development branch:

```powershell
$env:EXPENSE_TRACKER_TEST_DATABASE_URL = $env:DATABASE_URL
$env:EXPENSE_TRACKER_TEST_ALLOW_WRITES = "expense-tracker-dev"
python -m unittest discover -s tests -v
```

The integration suite exercises expense CRUD and reports, income validation
and filtering, bill payment/undo, foreign-key enforcement, transaction
rollback, and static frontend/API compatibility.

## Vercel preparation

The FastAPI application is exposed as `backend.main:app` for Vercel's Python
runtime via `pyproject.toml`. Runtime packages are declared in both
`pyproject.toml` (for Vercel builds) and `requirements.txt` (for local setup).
Python 3.14 is declared, and the frontend is served by the FastAPI static
mount. Configure the Vercel project's
`DATABASE_URL` as a secret environment variable using the pooled Neon
connection string; do not upload `.env` or expose database credentials to the
browser. Vercel's Python runtime and static-file behavior should be verified
with a preview deployment before production use.

This project is not automatically deployed. Configure a Vercel project,
environment variables, and domain separately, then test the preview before
production deployment.
