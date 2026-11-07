"""Re-fetch wraps saved SQL with allowlisted fields, conditions, and sort."""

from nlq import history, runner
from nlq.api import app
from fastapi.testclient import TestClient


def test_compile_binds_a_condition_and_rejects_unknowns():
    sql, params, count = runner.compile_view(
        "SELECT status, n FROM orders",
        ["status", "n"],
        {
            "columns": ["status"],
            "filters": [{"col": "status", "op": "=", "value": "delivered"}],
            "sort": [{"col": "n", "dir": "desc"}],
            "page": 2,
            "page_size": 25,
        },
    )
    assert '"status"' in sql
    assert "LIMIT 25 OFFSET 25" in sql
    assert params == ["delivered"]
    assert "WHERE" not in count or '"status" = ?' in count

    try:
        runner.compile_view("SELECT 1 AS n", ["n"], {"columns": ["missing"]})
    except ValueError as exc:
        assert "Unknown column" in str(exc)
    else:
        raise AssertionError("expected unknown column")

    try:
        runner.compile_view("SELECT 1 AS n", ["n"], {"filters": [{"col": "n", "op": "or", "value": 1}]})
    except ValueError as exc:
        assert "operator" in str(exc)
    else:
        raise AssertionError("expected unknown operator")


def test_view_filters_orders_by_status():
    result = runner.view(
        "SELECT status, count(*) AS orders FROM orders GROUP BY status",
        ["status", "orders"],
        {"columns": ["status", "orders"], "filters": [{"col": "status", "op": "=", "value": "delivered"}]},
    )
    assert result["columns"] == ["status", "orders"]
    assert result["rows"][0][0] == "delivered"
    assert result["total"] == 1


def test_view_coerces_numeric_filters():
    assert runner.coerce_value("200", "DOUBLE", "<=") == 200.0
    assert runner.coerce_value("200", "BIGINT", "=") == 200
    assert runner.coerce_value("shipped", "VARCHAR", "=") == "shipped"
    result = runner.view(
        """
        SELECT order_id, status, channel, discount_amount, subtotal
        FROM orders
        """,
        ["order_id", "status", "channel", "discount_amount", "subtotal"],
        {
            "columns": ["order_id", "status", "channel", "discount_amount", "subtotal"],
            "filters": [
                {"col": "channel", "op": "=", "value": "marketplace"},
                {"col": "status", "op": "=", "value": "shipped"},
                {"col": "discount_amount", "op": "<=", "value": "200"},
            ],
            "sort": [{"col": "subtotal", "dir": "desc"}],
            "page": 1,
            "page_size": 25,
        },
    )
    assert result["total"] >= 0
    assert all(row[3] is None or float(row[3]) <= 200 for row in result["rows"])


def test_report_view_endpoint():
    report_id = history.save({
        "question": "orders by status",
        "title": "Orders by status",
        "sql": "SELECT status, count(*) AS orders FROM orders GROUP BY status",
        "columns": ["status", "orders"],
        "rows": [["delivered", 1], ["cancelled", 2]],
        "chart": {"type": "bar", "x": "status", "y": ["orders"]},
        "assumptions": [],
        "status": "ok",
        "answer_type": "sql",
        "database": "ecommerce",
    })
    client = TestClient(app)
    response = client.post(
        f"/reports/{report_id}/view",
        json={
            "columns": ["orders"],
            "filters": [{"col": "status", "op": "=", "value": "delivered"}],
            "sort": [],
            "page": 1,
            "page_size": 25,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["orders"]
    assert body["total"] == 1
    assert body["error"] is None

    rejected = client.post(f"/reports/{report_id}/view", json={"columns": ["nope"]})
    assert rejected.status_code == 400
