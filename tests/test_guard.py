import json

import pytest

from nlq.guard import GuardError, check_sql


def test_accepts_select_and_with():
    assert check_sql("SELECT 1") == "SELECT 1"
    assert check_sql("SELECT 1;") == "SELECT 1"
    assert check_sql("WITH t AS (SELECT 1 AS n) SELECT n FROM t").startswith("WITH")


def test_rejects_drop_and_multiple_statements():
    with pytest.raises(GuardError):
        check_sql("DROP TABLE orders")
    with pytest.raises(GuardError):
        check_sql("SELECT 1; DROP TABLE x")


def test_rejects_read_csv():
    with pytest.raises(GuardError):
        check_sql("SELECT * FROM read_csv('/etc/passwd')")


def test_keeps_semicolon_inside_a_string():
    sql = "SELECT ';' AS mark"
    assert check_sql(sql) == sql
