from fastapi import HTTPException

FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE"
]

def validate_sql(sql: str):
    sql = sql.strip()
    sql_upper = sql.upper()

    # Allow only SELECT queries
    if not sql_upper.startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed."
        )

    # Block dangerous keywords
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            raise HTTPException(
                status_code=400,
                detail=f"{keyword} queries are not allowed."
            )

    return True