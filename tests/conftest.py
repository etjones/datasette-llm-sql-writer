from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def basic_test_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a reusable SQLite database with a simple schema for tests.

    Schema:
      - items(id INTEGER PRIMARY KEY, name TEXT)
    """
    db_dir = tmp_path_factory.mktemp("basic_db")
    db_path = db_dir / "basic.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("create table items (id integer primary key, name text)")
        conn.executemany(
            "insert into items (name) values (?)",
            [("a",), ("b",), ("c",)],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path
