# QueryPilot - AI SQL Assistant

QueryPilot lets you upload a CSV or Excel workbook, ask questions in plain English, and view the generated PostgreSQL query and results in a browser.

## Features

- Upload `.csv`, `.xls`, and `.xlsx` datasets into PostgreSQL
- Automatically normalise column names and handle data files with missing headers
- View the active table's schema
- Convert natural-language questions into read-only SQL
- Use deterministic query handling for common filters, counts, sorting, and distinct values
- Fall back to Groq (recommended for deployment) or a local Ollama model for more open-ended questions
- Copy generated SQL and export returned rows as CSV
- Light/dark interface

## Tech stack

- Frontend: React 19, Vite
- Backend: FastAPI, SQLAlchemy, pandas
- Database: PostgreSQL
- AI providers: Groq API or Ollama

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- PostgreSQL database
- Either a Groq API key or [Ollama](https://ollama.com/) with a compatible local model

## Local setup

### 1. Create a PostgreSQL database

Create a database, for example `ai_sql_db`, then note its connection URL:

```text
postgresql://POSTGRES_USER:POSTGRES_PASSWORD@localhost:5432/ai_sql_db
```

### 2. Configure and run the backend

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DATABASE_URL=postgresql://POSTGRES_USER:POSTGRES_PASSWORD@localhost:5432/ai_sql_db

# Choose one AI provider.
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.1-8b-instant

# Used only when GROQ_API_KEY is not set.
OLLAMA_MODEL=llama3.2:1b

# Optional: comma-separated browser origins for deployed frontend(s).
ALLOWED_ORIGINS=http://localhost:5173
```

Start the API:

```powershell
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`; interactive API documentation is at `/docs`.

### 3. Configure and run the frontend

In a second terminal:

```powershell
cd frontend
npm install
```

Optionally create `frontend/.env` when the API is not running at the default local address:

```env
VITE_API_URL=https://your-api.example.com
```

Start the development server:

```powershell
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5173`).

## Using the app

1. Upload a CSV or Excel dataset.
2. Confirm the generated table name and inspect its detected columns.
3. Ask a question, such as `Show the top 10 rows sorted by sales descending`.
4. Review the generated SQL and result table, then copy the SQL or export the results as CSV.

Uploaded data replaces any table with the same filename-derived name. For example, uploading `Sales 2026.csv` creates/replaces the `sales_2026` table.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Service health message |
| `POST` | `/upload` | Upload a `file` field containing CSV or Excel data |
| `GET` | `/schema/{table_name}` | Get the table's column names |
| `POST` | `/ask?prompt=...&table_name=...` | Generate and execute a read-only SQL query |

Example query:

```powershell
Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/ask?table_name=sales_2026&prompt=Count%20all%20rows'
```

## AI provider behaviour

The backend first recognises several common question patterns without contacting an AI provider, including counts, distinct values, basic text/numeric filters, and sorting/limits. Other questions use:

1. Groq when `GROQ_API_KEY` is configured.
2. Local Ollama otherwise.

For Ollama, install and start Ollama, then pull a model such as:

```powershell
ollama pull llama3.2:1b
```

## Security notes

- The API only accepts SQL beginning with `SELECT` and rejects common write/DDL keywords.
- Do not commit `.env` files, database passwords, or API keys.
- Restrict `ALLOWED_ORIGINS` to your actual frontend origins in production.
- This is a development-oriented SQL validator. For a public production deployment, use a database role limited to `SELECT` on only the intended schema/tables and add authentication, rate limits, upload limits, and stronger SQL parsing/authorization.

## Deployment

`render.yaml` defines a Render PostgreSQL database and FastAPI web service. The backend requires SSL automatically when connecting to a Render-hosted PostgreSQL URL. Set the required `GROQ_API_KEY` and `ALLOWED_ORIGINS` values in Render's environment settings. Deploy the frontend separately, set `VITE_API_URL` to the backend URL during its build, and include that frontend URL in `ALLOWED_ORIGINS`.

## Project structure

```text
backend/
  main.py           # FastAPI routes, upload processing, SQL generation/execution
  sql_validator.py  # Read-only SQL validation
  requirements.txt
frontend/
  src/App.jsx       # React application
  package.json
render.yaml         # Render backend/database blueprint
```
