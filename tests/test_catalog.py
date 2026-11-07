import pytest

from nlq import catalog


@pytest.fixture(scope="module")
def info():
    return catalog.load(force=True)


def test_prompt_lists_foreign_keys(info):
    text = info.prompt_text
    for link in (
        "orders.customer_id -> customers.customer_id",
        "order_items.order_id -> orders.order_id",
        "order_items.product_id -> products.product_id",
        "payments.order_id -> orders.order_id",
        "shipments.order_id -> orders.order_id",
        "returns.order_item_id -> order_items.order_item_id",
    ):
        assert link in text


def test_prompt_includes_hint_status_samples(info):
    # From hints/ecommerce.json columns.orders.status.samples — not a live DB scan.
    assert "'delivered'" in info.prompt_text
    assert "<<<SAMPLE_VALUES>>>" in info.prompt_text


def test_schema_answer_has_no_sample_values(info):
    columns = info.schema_columns(["orders"])
    names = [column["name"] for column in columns]
    assert "status" in names
    assert "delivered" not in json_blob(columns)


def json_blob(columns):
    import json
    return json.dumps(columns)
