# datasette-llm-sql-writer

[![PyPI](https://img.shields.io/pypi/v/datasette-llm-sql-writer.svg)](https://pypi.org/project/datasette-llm-sql-writer/)
[![Changelog](https://img.shields.io/github/v/release/etjones/datasette-llm-sql-writer?include_prereleases&label=changelog)](https://github.com/etjones/datasette-llm-sql-writer/releases)
[![Tests](https://github.com/etjones/datasette-llm-sql-writer/actions/workflows/test.yml/badge.svg)](https://github.com/etjones/datasette-llm-sql-writer/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/etjones/datasette-llm-sql-writer/blob/main/LICENSE)

Generate Datasette SQL queries using plain language and an LLM.

This plugin adds an "LLM SQL Writer" panel to Datasette pages that helps you write read‑only SQL (SELECT/CTE) from a natural‑language prompt. It keeps a per‑database chat history, lets you copy or re‑run previously generated queries, and respects Datasette’s built‑in SQL editor when present.

## Installation

Install this plugin in the same environment as Datasette.
```bash
datasette install datasette-llm-sql-writer
```
## Usage

1) Start Datasette with a database

Provide any SQLite database file when starting Datasette. Navigate to a table page to see the LLM panel above the table. On non‑table pages the panel is inserted below the first page header so you can still generate and run queries.

```bash
datasette path/to/your.db -p 8001
# Then visit http://127.0.0.1:8001/your/tablename
```

2) Configure the LLM model (optional but recommended)

By default, the plugin targets OpenAI and uses `gpt-5-mini` unless you override it. You can configure a model via Datasette metadata or an environment variable (see below):

`metadata.json`:

```json
{
  "plugins": {
    "datasette-llm-sql-writer": {
      "model": "gpt-5-mini"
    }
  }
}
```

Then start Datasette with `--metadata`:

```bash
datasette path/to/your.db --metadata metadata.json -p 8001
```

3) Use the panel

- Enter a natural‑language prompt in the panel.
- Click "Generate Only" to request SQL from the LLM and preview it in the panel. If the SQL editor is visible, the latest SQL is also inserted there.
- Click "Generate & Run" to generate (if needed) and immediately execute the SQL.
- Each assistant SQL card includes icon buttons:
  - Copy (clipboard icon): copies the SQL to your clipboard.
  - Run (triangle icon): runs that specific SQL—either by inserting it into the editor and submitting, or by redirecting to the query page if the editor is hidden.

Notes:
- The backend enforces that generated SQL is read‑only. See `datasette_llm_sql_writer/generator.py:is_select_only()`.
- The panel tracks whether the current prompt/SQL has already been run—if you change the prompt or the SQL in the editor, "Generate & Run" will regenerate before running.


## CAUTION CAUTION CAUTION - THIS GRANTS OTHERS USE OF YOUR LLM ACCOUNT
This plugin uses your API key to generate SQL queries. If you're using this plugin locally, that's exactly what you want. If you're using this plugin to share a dataset with others, be aware that you're letting them run up LLM bills on your behalf. 

(In practice, these prompts will be effectively free, but it's still a good idea to be aware of this. And somebody is likely to be able to find some extra use for free API calls if they work hard enough. )

## Authentication and API Keys

This plugin relies on the [`llm`](https://llm.datasette.io/) package for model execution and authentication. To minimize friction and keep secrets management simple, you have two supported options:

1) Use `llm`'s built-in key store (best for local development)

```bash
llm keys set openai
```

This stores your key securely for your user account. The plugin will just work if `llm` can access the model you specify.

2) Provide an environment variable (best for containers/CI)

- Default env var: `OPENAI_API_KEY`
- You can change which env var to read via `metadata.json` under this plugin's config:

```json
{
  "plugins": {
    "datasette-llm-sql-writer": {
      "model": "anthropic/claude-sonnet-4-0",
      "env_api_key_var": "ANTHROPIC_API_KEY"
    }
  }
}
```
- No configuration file is needed to use the default model, `gpt-5-mini`.

Quick check:

```bash
export OPENAI_API_KEY="sk-..."
datasette path/to/your.db -p 8001
```

If you see authentication errors, visit the [diagnostics](#Diagnostics) section of this page.

## Model selection

The model id is resolved with this precedence:

1) `metadata.json` plugin config: `plugins.datasette-llm-sql-writer.model`
2) Environment variable: `LLM_SQL_WRITER_MODEL`
3) Default: `gpt-5-mini` (OpenAI)

Examples:

```json
{
  "plugins": {
    "datasette-llm-sql-writer": {
      "model": "gpt-5-mini"
    }
  }
}
```

or

```bash
export LLM_SQL_WRITER_MODEL=gpt-5-mini
```

## Configuration

- You need the [`llm`](https://llm.datasette.io/) package configured with an API key for your chosen provider. Install the model/provider you want to use (e.g., OpenAI) per the `llm` docs.
- The default model id can be set in `metadata.json` as shown above; otherwise the plugin uses a placeholder and will error if the model does not exist in your `llm` setup.

## Front‑end state and persistence

The panel persists small UI state and chat history in `localStorage`, scoped per database:

- State key: `llm_sql_writer:state:v1:db:{db}`
  - `panelCollapsed` (bool): whether the panel is collapsed.
  - `lastPrompt` (str): last prompt used to generate SQL.
  - `lastSql` (str): last SQL returned by the LLM.
  - `lastRanSql` (str): last SQL that was executed.
- History key: `llm_sql_writer:history:v1:db:{db}`
  - The chat history associated with that database (trimmed to a bounded length).
- Changes propagate across tabs via the `storage` event.

No secrets are stored in `localStorage`—API keys should be configured with the `llm` package on the server side.

## Development

To set up this plugin locally, clone the repo and use `uv` to manage the environment and dependencies:

```bash
git clone https://github.com/etjones/datasette-llm-sql-writer
cd datasette-llm-sql-writer
uv venv
source .venv/bin/activate
uv sync --all-extras # installs runtime and test dependencies from pyproject.toml
```

Run the tests:

```bash
pytest -q
```

Launch Datasette against an example DB to try the panel:

```bash
datasette path/to/your.db -p 8001
# Visit http://127.0.0.1:8001/{db}/{table}
```

## How it works

- Backend route: `/-/llm-sql-writer/generate` accepts `{db, table, prompt, history}` and returns `{sql}`.
- The LLM prompt includes the schema context (table/column names) and optional chat history.
- Returned SQL is validated to be read‑only before being emitted to the UI.
- On table pages the panel uses the Datasette 1.x JavaScript plugin panel API; on non‑table pages it is inserted under the main header.

## Diagnostics

Visit `http://localhost:8001/-/llm-sql-writer/diagnostics` to quickly check whether:

- `llm` is installed
- The resolved `model_id` is available
- Your environment variable for the API key is present

The endpoint returns JSON with helpful hints and links to docs.

## FAQ

- Can I put my API key in `metadata.json`?

  Nope. Keep secrets in `llm`'s key store or environment variables.

- I get an error about unknown or unavailable model

  Install the appropriate `llm` provider plugin and confirm the model/alias exists. For Claude:

  ```bash
  uv add llm-anthropic
  llm keys set anthropic
  ```

  See [llm docs](https://llm.datasette.io/en/stable/other-models.html) for more info on provider plugins.

- I set a key but it still fails

  Ensure Datasette is running as the same user and virtual environment where you configured `llm`. If you use an env var, make sure it is set in the same process environment as the Datasette server.

- Local usage notes and privacy

  This plugin is commonly used locally. Be mindful that prompts and schema context are sent to the model provider. Use provider-side controls and review your data handling policies if you work with sensitive data.

