from pathlib import Path
import os
import re
import subprocess

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sql_validator import validate_sql

try:
    import ollama
except ImportError:  # pragma: no cover - handled at runtime
    ollama = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine(
    "postgresql://postgres:Kinjal%409824@localhost:5432/ai_sql_db"
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

SUPPORTED_EXTENSIONS = {".csv", ".xls", ".xlsx"}


def build_table_name(filename: str) -> str:
    stem = Path(filename).stem.lower()
    table_name = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return table_name or "uploaded_data"


def read_uploaded_file(file_path: str) -> pd.DataFrame:
    extension = Path(file_path).suffix.lower()

    if extension == ".csv":
        return pd.read_csv(file_path)

    if extension in {".xls", ".xlsx"}:
        return pd.read_excel(file_path)

    raise HTTPException(
        status_code=400,
        detail="Unsupported file type. Please upload a CSV or Excel file.",
    )

@app.get("/")
def read_root():
    return {"message": "AI SQL ASSISTANT Backend is running!"}

@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a CSV or Excel file.",
        )

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    try:
        df = read_uploaded_file(file_path)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read uploaded file: {exc}")

    table_name = build_table_name(file.filename)

    try:
        df.to_sql(
            table_name,
            engine,
            if_exists="replace",
            index=False
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save data to database: {exc}")

    return {
        "message": "File uploaded successfully",
        "table_name": table_name,
        "rows": len(df)
    }

def get_table_columns(table_name: str) -> list[str]:
    inspector = inspect(engine)
    try:
        columns = inspector.get_columns(table_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not inspect table '{table_name}': {exc}")
    return [column["name"] for column in columns]


def build_sql_prompt(table_name: str, columns: list[str], user_prompt: str) -> str:
    column_list = ", ".join(columns)
    return (
        "You are a SQL generator. Respond with exactly one valid PostgreSQL SELECT query only. "
        "Do not include any explanation, markdown formatting, or additional text. "
        "Use only the table schema provided below.\n\n"
        f"Table: {table_name}\n"
        f"Columns: {column_list}\n\n"
        "User request: "
        f"{user_prompt.strip()}"
    )


def extract_sql_from_response(content: str) -> str:
    code_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", content, re.S | re.I)
    if code_match:
        sql = code_match.group(1).strip()
    else:
        select_match = re.search(r"((?:WITH|SELECT)\b.+)", content, re.S | re.I)
        if select_match:
            sql = select_match.group(1).strip()
        else:
            raise HTTPException(status_code=502, detail="Ollama did not return a valid SQL query.")

    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    return sql

def get_available_model() -> str | None:
    preferred = os.getenv("OLLAMA_MODEL") or "llama3.2:1b"
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) <= 1:
            return preferred

        names = []
        for line in lines[1:]:
            if line:
                names.append(line.split()[0])

        if preferred in names:
            return preferred
        return names[0] if names else preferred
    except Exception:
        return preferred


@app.post("/ask")
def ask_ai(prompt: str, table_name: str = "heart"):
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    if ollama is None:
        raise HTTPException(status_code=500, detail="Ollama Python package is not installed.")

    model_name = os.getenv("OLLAMA_MODEL") or get_available_model() or "llama3.2:1b"
    columns = get_table_columns(table_name)
    if not columns:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' has no columns or does not exist.")

    sql_prompt = build_sql_prompt(table_name, columns, prompt)

    try:
        response = ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": sql_prompt}],
        )
        content = response.get("message", {}).get("content", "")

        if not content:
            raise HTTPException(status_code=502, detail="Ollama returned an empty response.")

        sql_query = extract_sql_from_response(content)
        validate_sql(sql_query)

        try:
            with engine.connect() as conn:
                result = conn.execute(text(sql_query))
                rows = [dict(row) for row in result.mappings()]
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"SQL execution failed: {exc}")

        return {
            "sql": sql_query,
            "rows": rows,
            "row_count": len(rows)
        }

    except HTTPException:
        raise
    except Exception as exc:
        detail = str(exc)
        if "not found" in detail.lower() or "404" in detail:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No compatible Ollama model is available. "
                    "Pull a model such as 'llama3.2:1b' or set OLLAMA_MODEL to an installed model."
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {detail}")
