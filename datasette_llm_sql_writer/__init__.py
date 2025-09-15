from datasette import hookimpl
from datasette.utils.asgi import Response
from typing import Any, Optional

from . import generator as generator_mod
import json
import os


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


def _get_plugin_config(datasette: Any) -> dict[str, Any]:
    """Return this plugin's configuration from metadata.json.

    Supports keys:
    - model: preferred llm model id (overrides env)
    - env_api_key_var: which ENV var to check for a provider key (default OPENAI_API_KEY)
    """
    try:
        cfg = datasette.plugin_config("datasette-llm-sql-writer") or {}
    except Exception:
        cfg = {}
    # Ensure type
    return dict(cfg)


def _resolve_model_id(datasette: Any) -> str:
    """Resolve the model id from plugin config, env var, or default.

    Precedence:
    1) metadata.json: plugins.datasette-llm-sql-writer.model
    2) env: LLM_SQL_WRITER_MODEL
    3) default: "gpt-5-mini" (OpenAI)
    """
    cfg = _get_plugin_config(datasette)
    model_from_cfg = cfg.get("model")
    if isinstance(model_from_cfg, str) and model_from_cfg.strip():
        return model_from_cfg.strip()
    env_model = os.getenv("LLM_SQL_WRITER_MODEL", "").strip()
    if env_model:
        return env_model
    return "gpt-5-mini"


def _env_api_key_var(datasette: Any) -> str:
    """Which environment variable should hold the API key? Defaults to OPENAI_API_KEY."""
    cfg = _get_plugin_config(datasette)
    val = cfg.get("env_api_key_var")
    if isinstance(val, str) and val.strip():
        return val.strip()
    return "OPENAI_API_KEY"


async def _handle_generate(request: Any, datasette: Any) -> Response:
    """Handle POST /-/llm-sql-writer/generate

    Body: { db, table, prompt, history }
    Returns: { sql } or { error }
    """
    try:
        body_bytes = await request.post_body()
        body = json.loads(body_bytes.decode("utf-8"))
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

    # Resolve model id with precedence: metadata.json > env > default
    # Users can set in metadata.json under plugin name "datasette-llm-sql-writer":
    # {"plugins": {"datasette-llm-sql-writer": {"model": "gpt-5-mini"}}}
    model_id: str = _resolve_model_id(datasette)

    # Bridge custom env var to OPENAI_API_KEY for OpenAI provider if needed
    env_var = _env_api_key_var(datasette)
    if env_var and env_var != "OPENAI_API_KEY":
        if not os.getenv("OPENAI_API_KEY") and os.getenv(env_var):
            os.environ["OPENAI_API_KEY"] = os.getenv(env_var, "")

    try:
        sql = await generator_mod.generate_sql(
            prompt=prompt, schema_text=schema_text, history=history, model_id=model_id
        )
    except Exception as ex:  # bubble up errors in a safe JSON envelope
        # Provide actionable guidance with README links
        readme = "https://github.com/etjones/datasette-llm-sql-writer#authentication-and-api-keys"
        diag = "/-/llm-sql-writer/diagnostics"
        return Response.json(
            {
                "error": f"Generation failed: {ex}",
                "help": {
                    "diagnostics": diag,
                    "auth_docs": readme,
                },
            },
            status=400,
        )

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

    async def diagnostics(request: Any, datasette: Any) -> Response:
        # Build diagnostics without leaking secrets
        info: dict[str, Any] = {}
        info["llm_installed"] = True
        try:
            import llm as _llm  # type: ignore
        except Exception:
            info["llm_installed"] = False
        model_id = _resolve_model_id(datasette)
        info["model_id"] = model_id
        env_var = _env_api_key_var(datasette)
        info["env_api_key_var"] = env_var
        info["env_api_key_present"] = bool(os.getenv(env_var))
        # Try to resolve model to check provider plugin presence
        model_available = False
        model_error = None
        if info["llm_installed"]:
            try:
                import llm as _llm  # type: ignore

                _ = _llm.get_model(model_id)
                model_available = True
            except Exception as e:  # noqa: BLE001
                model_error = str(e)
        info["model_available"] = model_available
        if model_error:
            info["model_error"] = model_error
        info["help"] = {
            "auth_docs": "https://github.com/etjones/datasette-llm-sql-writer#authentication-and-api-keys",
            "faq": "https://github.com/etjones/datasette-llm-sql-writer#faq",
        }
        info["ok"] = bool(info["llm_installed"]) and model_available
        return Response.json(info)

    return [
        (r"^/-/llm-sql-writer/generate$", view),
        (r"^/-/llm-sql-writer/diagnostics$", diagnostics),
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
