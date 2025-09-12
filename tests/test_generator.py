from __future__ import annotations

import pytest

from datasette_llm_sql_writer.generator import is_select_only


def test_is_select_only_accepts_multiline_select() -> None:
    sql = (
        """
        SELECT
          id,
          name
        FROM
          items
        WHERE
          name IN (
            SELECT
              name
            FROM
              items
          )
        ORDER BY
          id DESC
        LIMIT
          2
        """
    )
    assert is_select_only(sql) is True


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("DELETE FROM items", False),
        ("PRAGMA table_info(items)", False),
        ("WITH cte AS (SELECT name FROM items) SELECT name FROM cte", True),
    ],
)
def test_is_select_only_various(sql: str, expected: bool) -> None:
    assert is_select_only(sql) is expected
