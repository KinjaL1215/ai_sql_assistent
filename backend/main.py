from pathlib import Path
import os
import re
import subprocess

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sql_validator import validate_sql

try:
    import ollama
except ImportError:  # pragma: no cover - handled at runtime
    ollama = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Configure Gemini if API key is available
if GEMINI_API_KEY and genai:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# Configure CORS origins
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]
if not allowed_origins:
    allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
else:
    allowed_origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

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


def quote_identifier(identifier: str) -> str:
    escaped = str(identifier).replace('"', '""')
    return f'"{escaped}"'


def has_data_like_headers(columns: list[object]) -> bool:
    if not columns:
        return False

    suspicious_count = 0
    for column in columns:
        value = str(column).strip()
        if not value:
            suspicious_count += 1
        elif value.lower().startswith("unnamed"):
            suspicious_count += 1
        elif isinstance(column, (int, float)):
            suspicious_count += 1
        elif re.fullmatch(r"\d+(?:\.\d+)?", value):
            suspicious_count += 1

    return suspicious_count >= max(1, len(columns) // 2)


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    if has_data_like_headers(list(df.columns)):
        first_row = pd.DataFrame([list(df.columns)], columns=df.columns)
        df = pd.concat([first_row, df], ignore_index=True)
        df.columns = [f"column_{index}" for index in range(1, len(df.columns) + 1)]
        return df

    df.columns = [
        str(column).strip() or f"column_{index}"
        for index, column in enumerate(df.columns, start=1)
    ]
    return df

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
        df = normalize_dataframe_columns(df)
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


@app.get("/schema/{table_name}")
def read_table_schema(table_name: str):
    return {"table_name": table_name, "columns": get_table_columns(table_name)}


SYSTEM_PROMPT = (
    "You are a PostgreSQL SQL generator. "
    "You MUST respond with ONLY a single valid PostgreSQL SELECT query. "
    "Do NOT include any explanation, comments, markdown, or extra text. "
    "Just output the raw SQL query starting with SELECT."
)


def build_sql_prompt(table_name: str, columns: list[str], user_prompt: str) -> str:
    quoted_table_name = quote_identifier(table_name)
    column_list = "\n".join(f"- {quote_identifier(column)}" for column in columns)
    return (
        f"Table name: {quoted_table_name}\n"
        f"Columns, already quoted for PostgreSQL:\n{column_list}\n\n"
        f"Always use the quoted table name and quoted column names exactly as shown above. "
        f"Do not remove double quotes from identifiers.\n\n"
        f"Write a PostgreSQL SELECT query for this request: {user_prompt.strip()}\n\n"
        f"Example — if someone asks 'show all rows', respond with:\n"
        f"SELECT * FROM {quoted_table_name};\n\n"
        f"Now write the query:"
    )


def extract_sql_from_response(content: str) -> str:
    # Strip leading/trailing whitespace
    content = content.strip()

    # Try to extract from markdown code block
    code_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", content, re.S | re.I)
    if code_match:
        sql = code_match.group(1).strip()
    else:
        # Try to find a SELECT or WITH statement anywhere in the text
        select_match = re.search(r"((?:WITH|SELECT)\b[^;]+;?)", content, re.S | re.I)
        if select_match:
            sql = select_match.group(1).strip()
        else:
            # Last resort: if the entire content looks like it could be SQL (no long prose)
            if len(content) < 500 and re.search(r"\b(?:FROM|WHERE|JOIN)\b", content, re.I):
                sql = content.strip()
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama did not return a valid SQL query. Raw response: {content[:300]}"
                )

    # Clean up: remove trailing semicolons and re-add one
    sql = sql.rstrip(";").strip()
    sql += ";"
    return sql


def quote_known_identifiers(sql: str, table_name: str, columns: list[str]) -> str:
    identifiers = [table_name, *columns]
    identifier_lookup = {
        str(identifier).lower(): quote_identifier(str(identifier))
        for identifier in identifiers
    }
    identifier_names = sorted(identifier_lookup, key=len, reverse=True)
    pattern = re.compile(
        r'(?<![\w"])(%s)(?![\w"])' % "|".join(re.escape(name) for name in identifier_names),
        re.I,
    )

    parts = re.split(r'("[^"]*(?:""[^"]*)*"|\'[^\']*(?:\'\'[^\']*)*\')', sql)
    for index, part in enumerate(parts):
        if not part or part.startswith(('"', "'")):
            continue

        parts[index] = pattern.sub(
            lambda match: identifier_lookup[match.group(1).lower()],
            part,
        )

    return "".join(parts)


def normalize_column_name(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", column.lower())


def find_column(columns: list[str], requested_column: str) -> str | None:
    requested_key = normalize_column_name(requested_column)
    for column in columns:
        if normalize_column_name(column) == requested_key:
            return column
    return None


def escape_sql_literal(value: str) -> str:
    return value.strip().strip("'\"").replace("'", "''")


def column_regex(column: str) -> str:
    words = [re.escape(word) for word in re.findall(r"[a-z0-9]+", column.lower())]
    if not words:
        return re.escape(column)

    spaced = r"\s+".join(words)
    compact = "".join(words)
    if spaced == compact:
        return spaced
    return rf"(?:{spaced}|{compact})"


def find_columns_in_prompt(columns: list[str], user_prompt: str) -> list[str]:
    normalized_prompt = normalize_column_name(user_prompt)
    matching_columns = [
        column
        for column in columns
        if normalize_column_name(column) and normalize_column_name(column) in normalized_prompt
    ]
    return sorted(matching_columns, key=lambda value: len(normalize_column_name(value)), reverse=True)


def clean_prompt_value(value: str) -> str:
    value = re.split(
        r"\b(?:and|or|order by|sort by|group by|limit|show|display|return)\b",
        value,
        maxsplit=1,
        flags=re.I,
    )[0]
    return escape_sql_literal(value.rstrip(" ?.;,"))


def build_starts_with_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    prompt = user_prompt.strip()
    prefix_match = re.search(
        r"(?:start(?:s|ing)?\s+(?:from|with)|begin(?:s|ning)?\s+with)\s+['\"]?([a-z0-9])['\"]?\b",
        prompt,
        re.I,
    )
    if not prefix_match:
        return None

    normalized_prompt = normalize_column_name(prompt)
    matching_columns = [
        column
        for column in columns
        if normalize_column_name(column) in normalized_prompt
    ]
    if not matching_columns:
        return None

    column = max(matching_columns, key=lambda value: len(normalize_column_name(value)))
    prefix = prefix_match.group(1).replace("'", "''")
    return (
        f"SELECT * FROM {quote_identifier(table_name)} "
        f"WHERE {quote_identifier(column)}::text ILIKE '{prefix}%';"
    )


def build_text_match_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    prompt = user_prompt.strip()
    matching_columns = find_columns_in_prompt(columns, prompt)
    if not matching_columns:
        return None

    for column in matching_columns:
        pattern = column_regex(column)

        contains_match = re.search(
            rf"{pattern}\s+(?:contains|contain|has|include(?:s)?)\s+['\"]?(.+?)['\"]?$",
            prompt,
            re.I,
        )
        if contains_match:
            value = clean_prompt_value(contains_match.group(1))
            return (
                f"SELECT * FROM {quote_identifier(table_name)} "
                f"WHERE {quote_identifier(column)}::text ILIKE '%{value}%';"
            )

        ends_match = re.search(
            rf"{pattern}\s+(?:end(?:s|ing)?\s+with)\s+['\"]?(.+?)['\"]?$",
            prompt,
            re.I,
        )
        if ends_match:
            value = clean_prompt_value(ends_match.group(1))
            return (
                f"SELECT * FROM {quote_identifier(table_name)} "
                f"WHERE {quote_identifier(column)}::text ILIKE '%{value}';"
            )

        equals_match = re.search(
            rf"{pattern}\s+(?:is|=|equals|equal\s+to|are)\s+['\"]?(.+?)['\"]?$",
            prompt,
            re.I,
        )
        if equals_match:
            value = clean_prompt_value(equals_match.group(1))
            return (
                f"SELECT * FROM {quote_identifier(table_name)} "
                f"WHERE {quote_identifier(column)}::text ILIKE '{value}';"
            )

    return None


def build_numeric_comparison_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    prompt = user_prompt.strip()
    matching_columns = find_columns_in_prompt(columns, prompt)
    if not matching_columns:
        return None

    operators = [
        (r"(?:greater\s+than|more\s+than|above|over|>)", ">"),
        (r"(?:less\s+than|below|under|<)", "<"),
        (r"(?:greater\s+than\s+or\s+equal\s+to|at\s+least|>=)", ">="),
        (r"(?:less\s+than\s+or\s+equal\s+to|at\s+most|<=)", "<="),
    ]
    for column in matching_columns:
        pattern = column_regex(column)
        for phrase, operator in operators:
            match = re.search(
                rf"{pattern}.*?{phrase}\s+(-?\d+(?:\.\d+)?)",
                prompt,
                re.I,
            )
            if match:
                value = match.group(1)
                return (
                    f"SELECT * FROM {quote_identifier(table_name)} "
                    f"WHERE NULLIF({quote_identifier(column)}::text, '')::numeric {operator} {value};"
                )

    return None


def build_distinct_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    if not re.search(r"\b(?:distinct|unique|different)\b", user_prompt, re.I):
        return None

    matching_columns = find_columns_in_prompt(columns, user_prompt)
    if not matching_columns:
        return None

    column = matching_columns[0]
    return (
        f"SELECT DISTINCT {quote_identifier(column)} FROM {quote_identifier(table_name)} "
        f"ORDER BY {quote_identifier(column)};"
    )


def build_count_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    if not re.search(r"\b(?:count|how many|total)\b", user_prompt, re.I):
        return None

    condition_query = (
        build_starts_with_query(table_name, columns, user_prompt)
        or build_text_match_query(table_name, columns, user_prompt)
        or build_numeric_comparison_query(table_name, columns, user_prompt)
    )
    if condition_query:
        where_match = re.search(r"\bWHERE\b\s+(.+);$", condition_query, re.I | re.S)
        if where_match:
            return (
                f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)} "
                f"WHERE {where_match.group(1)};"
            )

    return f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)};"


def build_sort_limit_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    limit_match = re.search(r"\b(?:top|first|limit)\s+(\d+)\b", user_prompt, re.I)
    sort_match = re.search(r"\b(?:sort|order)\s+by\b", user_prompt, re.I)
    if not limit_match and not sort_match:
        return None

    matching_columns = find_columns_in_prompt(columns, user_prompt)
    order_clause = ""
    if matching_columns:
        direction = "DESC" if re.search(r"\b(?:desc|descending|highest|largest|top)\b", user_prompt, re.I) else "ASC"
        order_clause = f" ORDER BY {quote_identifier(matching_columns[0])} {direction}"

    limit_clause = f" LIMIT {int(limit_match.group(1))}" if limit_match else ""
    return f"SELECT * FROM {quote_identifier(table_name)}{order_clause}{limit_clause};"


def build_direct_query(table_name: str, columns: list[str], user_prompt: str) -> str | None:
    builders = [
        build_count_query,
        build_distinct_query,
        build_starts_with_query,
        build_text_match_query,
        build_numeric_comparison_query,
        build_sort_limit_query,
    ]
    for builder in builders:
        query = builder(table_name, columns, user_prompt)
        if query:
            return query

    if re.search(r"\b(?:show|display|get|list)\b.*\b(?:all|data|rows|records)\b", user_prompt, re.I):
        return f"SELECT * FROM {quote_identifier(table_name)} LIMIT 500;"

    return None


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


def generate_sql_with_gemini(sql_prompt: str) -> str:
    """Generate SQL using Google Gemini API (for deployment)."""
    if genai is None:
        raise HTTPException(status_code=500, detail="google-generativeai package is not installed.")

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            f"{SYSTEM_PROMPT}\n\n{sql_prompt}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=512,
            ),
        )
        return response.text or ""
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini API request failed: {exc}")


def generate_sql_with_ollama(sql_prompt: str) -> str:
    """Generate SQL using local Ollama model (for local development)."""
    if ollama is None:
        raise HTTPException(status_code=500, detail="Ollama Python package is not installed.")

    model_name = os.getenv("OLLAMA_MODEL") or get_available_model() or "llama3.2:1b"
    try:
        response = ollama.chat(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": sql_prompt},
            ],
        )
        content = response.get("message", {}).get("content", "")
        if not content:
            raise HTTPException(status_code=502, detail="Ollama returned an empty response.")
        return content
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


@app.post("/ask")
def ask_ai(prompt: str, table_name: str = "heart"):
    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    columns = get_table_columns(table_name)
    if not columns:
        raise HTTPException(status_code=400, detail=f"Table '{table_name}' has no columns or does not exist.")

    direct_sql_query = build_direct_query(table_name, columns, prompt)
    if direct_sql_query:
        sql_query = direct_sql_query
    else:
        sql_prompt = build_sql_prompt(table_name, columns, prompt)

        # Use Gemini if API key is configured, otherwise fall back to Ollama
        if GEMINI_API_KEY and genai:
            content = generate_sql_with_gemini(sql_prompt)
        else:
            content = generate_sql_with_ollama(sql_prompt)

        sql_query = extract_sql_from_response(content)
        sql_query = quote_known_identifiers(sql_query, table_name, columns)
    validate_sql(sql_query)

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = [dict(row) for row in result.mappings()]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not run a reliable SQL query for this question. "
                "Please use the exact column name shown in your table and a simple condition, "
                "for example: Branch is CSE, Full Name starts with A, or Age greater than 20."
            ),
        ) from exc

    return {
        "sql": sql_query,
        "rows": rows,
        "row_count": len(rows)
    }
