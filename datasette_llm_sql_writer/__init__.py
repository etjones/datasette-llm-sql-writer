from datasette import hookimpl
from datasette.utils.asgi import Response
from typing import Any, Optional

from . import generator as generator_mod
import json


@hookimpl
def extra_js_urls(
    template: Optional[Any] = None,
    request: Optional[Any] = None,
    database: Optional[str] = None,
    table: Optional[str] = None,
    datasette: Optional[Any] = None,
    **kwargs: Any,
) -> list[str]:
    """Inject our front-end script on table pages only.

    We return the URL to our packaged static asset.
    """
    # Serve plugin static from the correct URL helper when available
    url = "/-/static-plugins/datasette_llm_sql_writer/app.js"
    if datasette is not None:
        try:
            url = datasette.urls.static_plugins("datasette_llm_sql_writer", "app.js")
        except Exception:
            # Fall back to default underscore path
            pass
    # Inject unconditionally for compatibility with different template contexts
    return [url]


async def _handle_generate(request: Any, datasette: Any) -> Response:
    """Handle POST /-/llm-sql-writer/generate

    Body: { db, table, prompt, history }
    Returns: { sql } or { error }
    """
    try:
        # ETJ DEBUG
        body_bytes = await request.post_body()
        body = json.loads(body_bytes.decode("utf-8"))
        # print(f"{body = }")
        # END DEBUG
    except Exception as e:
        return Response.json({"error": f"Invalid request: {e}"}, status=400)

    db_name: Optional[str] = body.get("db")
    prompt: str = (body.get("prompt") or "").strip()
    history: list[dict[str, str]] = body.get("history") or []

    if not db_name:
        return Response.json({"error": "Missing 'db'"}, status=400)
    if not prompt:
        return Response.json({"error": "Missing 'prompt'"}, status=400)

    schema_text = await generator_mod.collect_schema(datasette, db_name)

    # Plugin configuration for default model
    # Users can set in metadata.json under plugin name "datasette-llm-sql-writer":
    # {"plugins": {"datasette-llm-sql-writer": {"model": "openai:gpt-4o-mini"}}}
    config = datasette.plugin_config("datasette-llm-sql-writer") or {}
    model_id: str = config.get("model") or "gpt-5"

    try:
        sql = await generator_mod.generate_sql(
            prompt=prompt, schema_text=schema_text, history=history, model_id=model_id
        )
    except Exception as ex:  # bubble up errors in a safe JSON envelope
        return Response.json({"error": f"Generation failed: {ex}"}, status=500)

    if not generator_mod.is_select_only(sql):
        return Response.json(
            {
                "error": "Only read-only SELECT queries are allowed. Original SQL: "
                + sql
            },
            status=400,
        )

    return Response.json({"sql": sql})


@hookimpl
def register_routes() -> list[tuple[str, Any]]:
    """Register our JSON API route for SQL generation."""

    async def view(request: Any, datasette: Any) -> Response:
        return await _handle_generate(request, datasette)

    return [
        (r"^/-/llm-sql-writer/generate$", view),
    ]


@hookimpl
def extra_head(
    template: Any,
    request: Optional[Any] = None,
    database: Optional[str] = None,
    table: Optional[str] = None,
    datasette: Optional[Any] = None,
    **kwargs: Any,
) -> str:
    if not (database and table):
        return ""
    return '<script src="/-/static-plugins/datasette_llm_sql_writer/app.js"></script>'


@hookimpl
def extra_body_script(
    template: Any,
    request: Optional[Any] = None,
    database: Optional[str] = None,
    table: Optional[str] = None,
    view_name: Optional[str] = None,
    datasette: Optional[Any] = None,
    **kwargs: Any,
) -> str:
    """Fallback injection for environments where extra_js_urls isn't used.

    Returns a script tag on table pages.
    """
    if not (database and table):
        return ""
    # Return inline JS (Datasette wraps this in a <script> tag). This dynamically
    # loads our plugin script so tests can find the URL in the HTML.
    return (
        '(()=>{try{var s=document.createElement("script");'
        's.src="/-/static-plugins/datasette_llm_sql_writer/app.js";'
        "document.head.appendChild(s);}catch(e){}})();"
    )
