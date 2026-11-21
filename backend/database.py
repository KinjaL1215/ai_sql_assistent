import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

load_dotenv(Path(__file__).with_name(".env"))

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is required.")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

parsed_url = make_url(database_url)
if parsed_url.host and parsed_url.host.endswith(".render.com"):
    parsed_url = parsed_url.update_query_dict({"sslmode": "require"})

engine = create_engine(parsed_url)

try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    print("Database connection successful!")
except Exception as exc:
    print(f"Database connection failed: {type(exc).__name__}")
    raise
finally:
    engine.dispose()
