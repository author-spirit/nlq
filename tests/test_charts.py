from nlq.charts import choose


def test_bar_request_overrides_a_table_suggestion():
    spec = choose(
        ["order_label", "total_amount"],
        [
            ["Order #66336 (Patricia Baker)", 9618.96],
            ["Order #81879 (Matthew Payne)", 8002.89],
        ],
        {"type": "table", "x": "", "y": [], "series": None},
        "Give me top 5 highest orders made by customer put in bar chart",
    )
    assert spec["type"] == "bar"
    assert spec["x"] == "order_label"
    assert spec["y"] == ["total_amount"]


def test_valid_bar_suggestion_is_kept():
    spec = choose(
        ["status", "orders"],
        [["delivered", 10], ["shipped", 4]],
        {"type": "bar", "x": "status", "y": ["orders"], "series": None},
        "How many orders by status?",
    )
    assert spec["type"] == "bar"


def test_date_and_number_become_a_line():
    spec = choose(
        ["month", "revenue"],
        [["2025-01-01", 10.0], ["2025-02-01", 12.0]],
        None,
        "monthly revenue",
    )
    assert spec == {"type": "line", "x": "month", "y": ["revenue"], "series": None}


def test_two_numbers_become_a_scatter():
    spec = choose(["cost", "price"], [[1, 2], [3, 4]], None, "")
    assert spec["type"] == "scatter"
    assert spec["x"] == "cost"
    assert spec["y"] == ["price"]


def test_mixed_columns_stay_a_table():
    spec = choose(["name", "amount", "city"], [["Ada", 3, "Paris"]], None, "")
    assert spec["type"] == "table"
