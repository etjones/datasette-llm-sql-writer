from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from datasette.app import Datasette

import datasette_llm_sql_writer.generator as gen


@pytest.mark.asyncio
async def test_model_from_metadata(monkeypatch: Any, basic_test_db: Path) -> None:
    metadata = {
        "plugins": {
            "datasette-llm-sql-writer": {
                "model": "test-model-from-metadata",
            }
        }
    }
    ds = Datasette([str(basic_test_db)], metadata=metadata)

    async def fake_generate_sql(
        prompt: str,
        schema_text: str,
        history: list[dict[str, str]] | None,
        model_id: str,
    ) -> str:  # type: ignore[override]
        assert model_id == "test-model-from-metadata"
        return "select 1"

    import datasette_llm_sql_writer.generator as generator_mod

    monkeypatch.setattr(generator_mod, "generate_sql", fake_generate_sql)

    payload = {"db": "basic", "table": "items", "prompt": "count rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", json=payload)
    assert r.status_code == 200
    assert r.json()["sql"].strip().lower().startswith("select")


@pytest.mark.asyncio
async def test_model_from_env_var(monkeypatch: Any, basic_test_db: Path) -> None:
    monkeypatch.setenv("LLM_SQL_WRITER_MODEL", "test-model-from-env")
    ds = Datasette([str(basic_test_db)])

    async def fake_generate_sql(
        prompt: str,
        schema_text: str,
        history: list[dict[str, str]] | None,
        model_id: str,
    ) -> str:  # type: ignore[override]
        assert model_id == "test-model-from-env"
        return "select 1"

    import datasette_llm_sql_writer.generator as generator_mod

    monkeypatch.setattr(generator_mod, "generate_sql", fake_generate_sql)

    payload = {"db": "basic", "table": "items", "prompt": "count rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", json=payload)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_default_model_is_openai_mini(
    monkeypatch: Any, basic_test_db: Path
) -> None:
    monkeypatch.delenv("LLM_SQL_WRITER_MODEL", raising=False)
    ds = Datasette([str(basic_test_db)])

    async def fake_generate_sql(
        prompt: str,
        schema_text: str,
        history: list[dict[str, str]] | None,
        model_id: str,
    ) -> str:  # type: ignore[override]
        assert model_id == "gpt-5-mini"
        return "select 1"

    import datasette_llm_sql_writer.generator as generator_mod

    monkeypatch.setattr(generator_mod, "generate_sql", fake_generate_sql)

    payload = {"db": "basic", "table": "items", "prompt": "count rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", json=payload)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_env_api_key_bridging_from_custom_var(
    monkeypatch: Any, basic_test_db: Path
) -> None:
    # Ensure OPENAI_API_KEY is unset, set a custom env var and configure metadata to use it
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MY_OPENAI_KEY", "abc123")
    metadata = {
        "plugins": {
            "datasette-llm-sql-writer": {
                "env_api_key_var": "MY_OPENAI_KEY",
            }
        }
    }
    ds = Datasette([str(basic_test_db)], metadata=metadata)

    async def fake_generate_sql(
        prompt: str,
        schema_text: str,
        history: list[dict[str, str]] | None,
        model_id: str,
    ) -> str:  # type: ignore[override]
        # The handler should have bridged MY_OPENAI_KEY -> OPENAI_API_KEY
        assert os.getenv("OPENAI_API_KEY") == "abc123"
        return "select 1"

    import datasette_llm_sql_writer.generator as generator_mod

    monkeypatch.setattr(generator_mod, "generate_sql", fake_generate_sql)

    payload = {"db": "basic", "table": "items", "prompt": "count rows", "history": []}
    r = await ds.client.post("/-/llm-sql-writer/generate", json=payload)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_generate_sql_unknown_model_error_message(monkeypatch: Any) -> None:
    # Simulate llm raising for unknown model
    class Unknown(Exception):
        pass

    def fake_get_model(_model_id: str) -> Any:
        raise Unknown("unknown model")

    monkeypatch.setattr(gen.llm, "get_model", fake_get_model)

    with pytest.raises(RuntimeError) as ex:
        await gen.generate_sql(
            prompt="p",
            schema_text="s",
            history=[],
            model_id="does-not-exist",
        )
    msg = str(ex.value)
    assert "Unknown or unavailable model" in msg


@pytest.mark.asyncio
async def test_generate_sql_missing_api_key_hint(monkeypatch: Any) -> None:
    # Simulate a provider error during prompt due to missing/invalid key
    class FakeModel:
        def prompt(self, _full_prompt: str) -> Any:
            raise Exception("401 Unauthorized")

    def fake_get_model(_model_id: str) -> Any:
        return FakeModel()

    monkeypatch.setattr(gen.llm, "get_model", fake_get_model)

    with pytest.raises(RuntimeError) as ex:
        await gen.generate_sql(
            prompt="p",
            schema_text="s",
            history=[],
            model_id="gpt-5-mini",
        )
    msg = str(ex.value)
    assert "missing or invalid API key" in msg
