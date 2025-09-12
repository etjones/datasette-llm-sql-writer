from pathlib import Path
from typing import Any

import pytest
from datasette.app import Datasette


@pytest.mark.asyncio
async def test_js_injected_on_table_page(basic_test_db: Path) -> None:
    ds = Datasette([str(basic_test_db)])
    # Table page
    r = await ds.client.get("/basic/items")
    assert r.status_code == 200
    html = r.text
    # Our app.js should be included via extra_js_urls on table pages
    assert "/-/static-plugins/datasette_llm_sql_writer/app.js" in html


@pytest.mark.asyncio
async def test_js_injected_on_query_page(basic_test_db: Path) -> None:
    ds = Datasette([str(basic_test_db)])
    # Query page (must include an SQL parameter)
    r = await ds.client.get("/basic/-/query?sql=select+1")
    assert r.status_code == 200
    html = r.text
    # Use Datasette helper to compute the expected static plugin URL
    expected_url = ds.urls.static_plugins("datasette_llm_sql_writer", "app.js")
    assert expected_url in html


@pytest.mark.asyncio
async def test_generate_endpoint_ok(monkeypatch: Any, basic_test_db: Path) -> None:
    # Datasette instance with the reusable basic test db
    ds = Datasette([str(basic_test_db)])

    async def fake_generate_sql(
        prompt: str,
        schema_text: str,
        history: list[dict[str, str]] | None,
        model_id: str,
    ) -> str:  # type: ignore[override]
        return "select 1"

    import datasette_llm_sql_writer.generator as gen

    monkeypatch.setattr(gen, "generate_sql", fake_generate_sql)

    payload = {"db": "basic", "table": "items", "prompt": "count rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", json=payload)
    assert r.status_code == 200
    assert r.json()["sql"].strip().lower().startswith("select")


@pytest.mark.asyncio
async def test_generate_endpoint_rejects_non_select(
    monkeypatch: Any, basic_test_db: Path
) -> None:
    ds = Datasette([str(basic_test_db)])

    async def fake_generate_sql(
        prompt: str,
        schema_text: str,
        history: list[dict[str, str]] | None,
        model_id: str,
    ) -> str:  # type: ignore[override]
        return "delete from t"

    import datasette_llm_sql_writer.generator as gen

    monkeypatch.setattr(gen, "generate_sql", fake_generate_sql)

    payload = {"db": "basic", "table": "items", "prompt": "delete rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", json=payload)
    assert r.status_code == 400
    assert "Only read-only SELECT" in r.json()["error"]
