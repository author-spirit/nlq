import pytest

from nlq import db, runner
from nlq.runner import QueryTimeout


def test_caps_rows_at_1000():
    result = runner.run("SELECT * FROM range(5000)")
    assert result["columns"] == ["range"]
    assert len(result["rows"]) == 1000


def test_serializes_dates():
    result = runner.run("SELECT DATE '2025-01-02' AS d, TIMESTAMP '2025-01-02 03:04:05' AS t")
    assert result["rows"] == [["2025-01-02", "2025-01-02T03:04:05"]]


def test_read_only_blocks_external_reads_and_writes():
    con = db.connect()
    try:
        with pytest.raises(Exception):
            con.execute("CREATE TABLE should_fail (id BIGINT)")
        with pytest.raises(Exception):
            con.execute("SELECT * FROM read_csv('/etc/passwd')").fetchall()
    finally:
        con.close()


def test_timeout_interrupts_a_long_query():
    with pytest.raises(QueryTimeout):
        runner.run(
            "SELECT sum(random()) FROM range(20000000) a, range(20) b",
            timeout=0.2,
        )
