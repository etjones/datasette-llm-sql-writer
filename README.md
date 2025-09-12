# datasette-llm-sql-writer

[![PyPI](https://img.shields.io/pypi/v/datasette-llm-sql-writer.svg)](https://pypi.org/project/datasette-llm-sql-writer/)
[![Changelog](https://img.shields.io/github/v/release/etjones/datasette-llm-sql-writer?include_prereleases&label=changelog)](https://github.com/etjones/datasette-llm-sql-writer/releases)
[![Tests](https://github.com/etjones/datasette-llm-sql-writer/actions/workflows/test.yml/badge.svg)](https://github.com/etjones/datasette-llm-sql-writer/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/etjones/datasette-llm-sql-writer/blob/main/LICENSE)

Generate datasette SQL queries using plain language and an LLM

## Installation

Install this plugin in the same environment as Datasette.
```bash
datasette install datasette-llm-sql-writer
```
## Usage

1) Start Datasette with a database

Provide any SQLite database file when starting Datasette. Navigate to a table page to see the LLM panel above the table.

```bash
datasette path/to/your.db -p 8001
# Then visit http://127.0.0.1:8001/your/tablename
```

2) Configure the LLM model (optional but recommended)

By default, the plugin uses a model id from plugin configuration (see below). If not set, it defaults to `gpt-5` which likely does not exist in your `llm` setup. Configure a model via Datasette metadata:

`metadata.json`:

```json
{
  "plugins": {
    "datasette-llm-sql-writer": {
      "model": "openai:gpt-4o-mini"
    }
  }
}
```

Then start Datasette with `--metadata`:

```bash
datasette path/to/your.db --metadata metadata.json -p 8001
```

3) Use the panel

- Enter a natural-language prompt in the panel.
- Click "Generate SQL" to call the backend; the SQL will be inserted into the built-in SQL editor.
- Click "Insert SQL only" to copy the latest generated SQL into the editor without running it.
- Click "Insert and Run" to populate the editor and submit the form to run the query.

Notes:
- The panel appears only on table pages (`/{db}/{table}`).
- You need the [`llm`](https://llm.datasette.io/) package configured with an API key for your chosen provider.
- The backend enforces that generated SQL is read-only (SELECT/CTE).

## Development

To set up this plugin locally, first checkout the code. Then create a new virtual environment:
```bash
cd datasette-llm-sql-writer
python -m venv venv
source venv/bin/activate
```
Now install the dependencies and test dependencies:
```bash
pip install -e '.[test]'
```
To run the tests:
```bash
python -m pytest
```

