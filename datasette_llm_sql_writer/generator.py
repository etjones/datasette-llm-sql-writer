from typing import Any, Optional

import re

import llm  # type: ignore


def is_select_only(sql: str) -> bool:
    """Conservative check that the SQL contains only read-only statements.

    Allows:
    - Statements starting with SELECT
    - Statements starting with WITH ... SELECT

    Rejects if any statement starts with one of the known mutating/DDL keywords.
    This is not a full SQL parser, but it should be sufficient as a guardrail.
    """
    tokens = re.split(r";\s*", sql.strip(), flags=re.IGNORECASE)
    disallowed = (
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "REPLACE",
        "TRUNCATE",
        "ATTACH",
        "DETACH",
        "VACUUM",
        "ANALYZE",
        "PRAGMA",  # treat pragma as disallowed in generated SQL
    )
    for t in tokens:
        st = t.strip()
        if not st:
            continue
        # Remove comments (line and block)
        st = re.sub(r"^--.*$", "", st, flags=re.MULTILINE)
        st = re.sub(r"/\*.*?\*/", "", st, flags=re.DOTALL).strip()
        if not st:
            continue
        # Reject if the statement starts with any disallowed keyword, allowing for newlines/whitespace
        for bad in disallowed:
            if re.match(rf"^\s*{bad}\b", st, flags=re.IGNORECASE):
                return False
        # Allow SELECT or WITH ... SELECT, tolerant of newlines/parentheses
        if re.match(r"^\s*WITH\b", st, flags=re.IGNORECASE):
            if not re.search(r"\bSELECT\b", st, flags=re.IGNORECASE):
                return False
        elif not re.match(r"^\s*\(*\s*SELECT\b", st, flags=re.IGNORECASE):
            return False
    return True


async def collect_schema(datasette: Any, db_name: Optional[str]) -> str:
    """Return a simple textual schema description to help the LLM.

    Includes table names and column names/types for the target database, if available.
    """
    if not db_name:
        return ""
    try:
        db = datasette.get_database(db_name)
    except Exception:
        return ""
    try:
        table_names = await db.table_names()
    except Exception:
        return ""
    lines: list[str] = [f"Database: {db_name}", "Tables:"]
    for table in table_names:
        try:
            columns = await db.execute(f"PRAGMA table_info([{table}])")
            col_desc = ", ".join(f"{row['name']} {row['type']}" for row in columns)
        except Exception:
            col_desc = ""
        lines.append(f"- {table}: {col_desc}")
    return "\n".join(lines)


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return ""
    parts: list[str] = []
    for m in history:
        role = m.get("role", "user")
        content = m.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


async def generate_sql(
    prompt: str,
    schema_text: str,
    history: list[dict[str, str]] | None,
    model_id: str,
) -> str:
    """Generate SQL text using the configured LLM.

    This function is intentionally pure with respect to external state: it takes
    all context as parameters. Tests can monkeypatch this function to return a
    known SQL string without touching the LLM SDK.
    """
    system = (
        "You are a careful SQL assistant for Datasette. "
        "Return only SQL code in your final answer. Do not include explanations. "
        "Only produce read-only queries (SELECT or WITH ... SELECT)."
    )

    history_text = _format_history(history or [])
    parts = [
        system,
        "\nSCHEMA CONTEXT:\n",
        schema_text or "(schema unavailable)",
        "\n\nUSER PROMPT:\n",
        prompt,
    ]
    if history_text:
        parts.insert(2, "\nCHAT HISTORY:\n" + history_text + "\n")

    full_prompt = "".join(parts)

    # Request deterministic output
    try:
        model = llm.get_model(model_id)
    except Exception as e:  # noqa: BLE001
        docs = (
            f"Unknown or unavailable model '{model_id}'. Ensure the model/provider is installed in 'llm' "
            "and available. For OpenAI, install the provider plugin and configure keys:\n"
            "  uv add llm-openai\n  llm keys set openai\n"
            "See docs: https://github.com/etjones/datasette-llm-sql-writer#authentication-and-api-keys"
        )
        raise RuntimeError(docs) from e

    try:
        response = model.prompt(full_prompt)  # type: ignore[attr-defined]
        text = response.text() if hasattr(response, "text") else str(response)
    except Exception as e:  # noqa: BLE001
        # Provide a helpful hint for missing/invalid keys without leaking details
        hint = (
            "LLM request failed. This often indicates a missing or invalid API key. "
            "Configure a key using 'llm keys set openai' or set the OPENAI_API_KEY environment variable.\n"
            "See docs: https://github.com/etjones/datasette-llm-sql-writer#authentication-and-api-keys"
        )
        raise RuntimeError(hint) from e

    # Strip common Markdown fences if present
    cleaned = re.sub(r"^```sql\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned
