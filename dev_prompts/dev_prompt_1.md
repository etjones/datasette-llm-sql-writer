# Datasette LLM Query Writer Plugin

I want to write a plugin for Datasette. Here are the docs for writing plugins:
https://docs.datasette.io/en/stable/writing_plugins.html

Normal Datasette pages provide a view into a database and a (normally hidden ) field for adding SQL to the page. I would like my plugin to create a pair of text fields at the top of the page. The top field would be a normal LLM chat response log, and the bottom field would be for entering text prompts to an LLM. 

The idea is that instead of explicitly entering SQL in the existing SQL window, the user can enter a prompt in the bottom field, and the plugin will generate the SQL for them. The plugin will then execute the SQL and display the results in the normal Datasette way. We will use the LLM to generate the SQL, and the LLM will use the database schema to generate the SQL. We'd also like to enable refining the SQL query as they refine their prompt. 

I'd like tests to be written for the plugin. We should define a dummy user query and dummy SQL response so that we don't have to to make actual API calls to the LLM. We should also define a small test database with a single table and a few rows so that we can test the plugin. 

We'll use pytest for testing. We'll use `llm` to make API calls to the LLM. We'll use httpx to make API calls to the datasette server if needed. 

## Initial Questions (ranked by importance)

NOTE: The docs recommend using a cookiecutter project to scaffold the plugin. Here are the instructions:
"""Starting an installable plugin using cookiecutter

Plugins that can be installed should be written as Python packages using a setup.py file.

The quickest way to start writing one an installable plugin is to use the datasette-plugin cookiecutter template. This creates a new plugin structure for you complete with an example test and GitHub Actions workflows for testing and publishing your plugin.

Install cookiecutter and then run this command to start building a plugin using the template:

cookiecutter gh:simonw/datasette-plugin

Read a cookiecutter template for writing Datasette plugins for more information about this template.
"""

- Critical: Target Datasette version?
  - 1.x (stable) vs 0.64.x. This affects hook APIs and the preferred way to inject JS (e.g., JavaScript plugin panels vs extra_js_urls).
  - A: 1.x is preferred.


- Critical: Where should the UI appear?
  - Only on table pages (`/{db}/{table}`)? Also on database pages (`/{db}`)? On the index?
  - A: Just on table pages is preferred.

- Critical: Default LLM model via `llm`?
  - Example: `llm.get_model("openai:gpt-5-mini")`, `openai:gpt-3.5-turbo`, or another? Should we read from a plugin config key (e.g., in `metadata.json`) or environment variable (e.g., `LLM_MODEL`)?
  - A: Let's read a plugin config key from metadata.json, but default to `gpt-5` if not specified.

- High: Persistence of chat UI across page reloads?
  - OK to keep chat state in `localStorage` keyed by path (`db/table`)? Or should it reset on each page load?
  - A: Let's keep chat state in `localStorage` keyed by path (`db/table`).

- High: Endpoint behavior and scope
  - Endpoint to only generate SQL and the front-end then writes to the SQL textarea and submits the form? Or should the endpoint execute and return results directly? I recommend generate-only, then let the existing SQL workflow execute.
  - A: Endpoint to only generate SQL and the front-end then writes to the SQL textarea and submits the form.

- High: Schema context for prompting
  - Should we include full schema (tables + columns + types) of the current database in the prompt automatically? For table pages, include the specific table details as well?
  - A: Let's include full schema (tables + columns + types) of the current database in the prompt automatically.

- Medium: Safety constraints on generated SQL
  - Should we enforce generated SQL to start with SELECT (reject anything else)? This is easy to enforce and test.
  - A: We'd like to enforce generated SQL apply only to SELECT queries, but there might be multiple SELECT queries in a single SQL statement. (For example, see this generated monstrosity. If we're going to do any filtering, we'll have to do it carefully.: WITH base AS (
  SELECT
    COALESCE(
      CAST(strftime('%Y', [Original Issue Date]) AS INT),
      CAST(substr([Original Issue Date], -4) AS INT)
    ) AS year,
    [County] AS county
  FROM [licenses]
  WHERE [State] = 'TX'
    AND [Original Issue Date] IS NOT NULL
    AND TRIM([Original Issue Date]) <> ''
    AND TRIM([County]) <> ''
),
counts AS (
  SELECT year, county, COUNT(*) AS license_count
  FROM base
  GROUP BY year, county
),
ranked AS (
  SELECT
    year,
    county,
    license_count,
    SUM(license_count) OVER (PARTITION BY year) AS year_total,
    ROW_NUMBER() OVER (PARTITION BY year ORDER BY license_count DESC, county) AS rnk
  FROM counts
)
SELECT
  year,
  county,
  license_count,
  year_total,
  ROUND(100.0 * license_count / NULLIF(year_total, 0), 2) AS pct_of_year
FROM ranked
WHERE rnk <= 5
  AND year >= CAST(strftime('%Y','now') AS INT) - 9
ORDER BY year DESC, license_count DESC, county;

- Medium: Plugin name and route
  - Package name: `datasette-llm-sql-writer`? Route path: `/-/llm-sql-writer/generate`?

- Medium: UI ergonomics
  - Keep the existing SQL editor visible or leave it hidden as Datasette defaults? Do you want a button to “Insert SQL only” vs “Insert and Run”?
  - A: Keep the existing SQL editor visible and add a button to “Insert SQL only” as well as "Insert and Run".

- Low: Tests
  - I’ll stub the SQL generator (pure function) to avoid real API calls and use a small SQLite test db with one table. Any preference for the example schema and dummy prompt/SQL?
  - A: No. A couple tables and a few rows is fine. 

Proposed architecture (concise)
- Back end (Python):
  - Hook: `register_routes()` to add POST `/-/llm-sql-writer/generate`.
  - Hook: `extra_js_urls()` (or JS panel plugin, per Datasette version) to inject front-end script on relevant pages.
  - SQL generator module that uses `llm` with pluggable function for tests (pure, typed).
  - Safety: enforce SELECT-only SQL.
- Front end (JS):
  - UI panel with two fields: chat log (top) and prompt input (bottom).
  - On submit: POST to `/-/llm-sql-writer/generate` with page context (db/table, prompt, history).
  - On response: insert SQL into the existing SQL textarea and optionally auto-submit the form.
  - Optional persistence: store chat in localStorage keyed by page.
- Tests (pytest):
  - Spin up Datasette with a small SQLite db.
  - Monkeypatch the SQL generator to return a known SQL for a known prompt.
  - Assert route works, SQL is returned, and non-SELECT is rejected.
  - Assert `extra_js_urls()` (or the JS panel hook) is wired for table pages.

Next steps after your answers
- Create git branch `feature/llm_query_writer_plugin`.
- Scaffold plugin package, tests, and static JS.
- Configure `pyproject.toml` for entry points and dependencies (`datasette`, `llm`, `httpx`, `pytest`).
- Use `uv add` to install deps and run tests.

Let me know your preferences on the questions above—especially Datasette version, target pages, and default LLM model.