from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from datasette.app import Datasette


@pytest.mark.asyncio
async def test_js_injected_on_table_page(tmp_path: Path) -> None:
    # Create a temporary SQLite db with one table
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("create table items (id integer primary key, name text)")
        conn.execute("insert into items (name) values ('a'), ('b')")
        conn.commit()
    finally:
        conn.close()

    ds = Datasette([str(db_path)])
    # Table page
    r = await ds.client.get("/test/items")
    assert r.status_code == 200
    html = r.text
    # Our app.js should be included via extra_js_urls on table pages
    assert "/-/static-plugins/datasette_llm_sql_writer/app.js" in html


@pytest.mark.asyncio
async def test_generate_endpoint_ok(monkeypatch: Any, tmp_path: Path) -> None:
    # Datasette instance with a small db (schema is used by generator)
    db_path = tmp_path / "test2.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("create table t (id integer primary key, name text)")
        conn.commit()
    finally:
        conn.close()

    ds = Datasette([str(db_path)])

    async def fake_generate_sql(prompt: str, schema_text: str, history: list[dict[str, str]] | None, model_id: str) -> str:  # type: ignore[override]
        return "select 1"

    import datasette_llm_sql_writer.generator as gen

    monkeypatch.setattr(gen, "generate_sql", fake_generate_sql)

    payload = {"db": "test2", "table": "t", "prompt": "count rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", data=json.dumps(payload))
    assert r.status_code == 200
    assert r.json()["sql"].strip().lower().startswith("select")


@pytest.mark.asyncio
async def test_generate_endpoint_rejects_non_select(monkeypatch: Any, tmp_path: Path) -> None:
    db_path = tmp_path / "test3.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("create table t (id integer primary key, name text)")
        conn.commit()
    finally:
        conn.close()

    ds = Datasette([str(db_path)])

    async def fake_generate_sql(prompt: str, schema_text: str, history: list[dict[str, str]] | None, model_id: str) -> str:  # type: ignore[override]
        return "delete from t"

    import datasette_llm_sql_writer.generator as gen

    monkeypatch.setattr(gen, "generate_sql", fake_generate_sql)

    payload = {"db": "test3", "table": "t", "prompt": "delete rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", data=json.dumps(payload))
    assert r.status_code == 400
    assert "Only read-only SELECT" in r.json()["error"]
