from datasette import hookimpl
from datasette.responses import JSONResponse
from typing import Any, Optional

from .generator import collect_schema, generate_sql, is_select_only


@hookimpl
def extra_js_urls(
    template: Any,
    request: Optional[Any] = None,
    database: Optional[str] = None,
    table: Optional[str] = None,
    datasette: Optional[Any] = None,
    **kwargs: Any,
) -> list[str]:
    """Inject our front-end script on table pages only.

    We return the URL to our packaged static asset.
    """
    if not (database and table):
        return []
    # Serve plugin static from /-/static-plugins/{package}/app.js
    return ["/-/static-plugins/datasette_llm_sql_writer/app.js"]


async def _handle_generate(request: Any, datasette: Any) -> JSONResponse:
    """Handle POST /-/llm-sql-writer/generate

    Body: { db, table, prompt, history }
    Returns: { sql } or { error }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status=400)

    db_name: Optional[str] = body.get("db")
    prompt: str = (body.get("prompt") or "").strip()
    history: list[dict[str, str]] = body.get("history") or []

    if not db_name:
        return JSONResponse({"error": "Missing 'db'"}, status=400)
    if not prompt:
        return JSONResponse({"error": "Missing 'prompt'"}, status=400)

    schema_text = await collect_schema(datasette, db_name)

    # Plugin configuration for default model
    # Users can set in metadata.json under plugin name "datasette-llm-sql-writer":
    # {"plugins": {"datasette-llm-sql-writer": {"model": "openai:gpt-4o-mini"}}}
    config = datasette.plugin_config("datasette-llm-sql-writer") or {}
    model_id: str = config.get("model") or "gpt-5"

    try:
        sql = await generate_sql(prompt=prompt, schema_text=schema_text, history=history, model_id=model_id)
    except Exception as ex:  # bubble up errors in a safe JSON envelope
        return JSONResponse({"error": f"Generation failed: {ex}"}, status=500)

    if not is_select_only(sql):
        return JSONResponse({"error": "Only read-only SELECT queries are allowed"}, status=400)

    return JSONResponse({"sql": sql})


@hookimpl
def register_routes() -> list[tuple[str, Any]]:
    """Register our JSON API route for SQL generation."""

    async def view(request: Any, datasette: Any) -> JSONResponse:
        return await _handle_generate(request, datasette)

    return [
        (r"^/-/llm-sql-writer/generate$", view),
    ]
