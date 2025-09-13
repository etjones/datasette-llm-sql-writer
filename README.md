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

By default, the plugin uses a model id from plugin configuration (see below). If not set, it defaults to `gpt-5` which likely does not exist in your `llm` setup. Configure an alternate model via Datasette metadata if you like. Default model id is `gpt-5`:

`metadata.json`:

```json
{
  "plugins": {
    "datasette-llm-sql-writer": {
      "model": "gpt-5"
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
uv sync  # installs runtime and test dependencies from pyproject.toml
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

