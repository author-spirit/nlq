"""Build the read-only ecommerce DuckDB file from the CSV sample."""

from __future__ import annotations

import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "csv" / "ecommerce"
DB_PATH = ROOT / "data" / "duckdb" / "ecommerce.duckdb"

TABLES: list[tuple[str, str, str]] = [
    (
        "customers",
        """
        CREATE TABLE customers (
            customer_id BIGINT PRIMARY KEY,
            first_name VARCHAR NOT NULL,
            last_name VARCHAR NOT NULL,
            email VARCHAR NOT NULL,
            phone VARCHAR,
            country VARCHAR NOT NULL,
            city VARCHAR NOT NULL,
            signup_date DATE NOT NULL,
            loyalty_tier VARCHAR NOT NULL,
            marketing_opt_in BOOLEAN NOT NULL
        )
        """,
        """
        INSERT INTO customers
        SELECT
            customer_id::BIGINT,
            first_name,
            last_name,
            email,
            NULLIF(trim(phone), ''),
            country,
            city,
            signup_date::DATE,
            loyalty_tier,
            marketing_opt_in::BOOLEAN
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
    (
        "products",
        """
        CREATE TABLE products (
            product_id BIGINT PRIMARY KEY,
            sku VARCHAR NOT NULL,
            product_name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            brand VARCHAR NOT NULL,
            unit_price DOUBLE NOT NULL,
            unit_cost DOUBLE NOT NULL,
            weight_kg DOUBLE,
            is_active BOOLEAN NOT NULL,
            created_at DATE NOT NULL
        )
        """,
        """
        INSERT INTO products
        SELECT
            product_id::BIGINT,
            sku,
            product_name,
            category,
            brand,
            unit_price::DOUBLE,
            unit_cost::DOUBLE,
            NULLIF(trim(weight_kg), '')::DOUBLE,
            is_active::BOOLEAN,
            created_at::DATE
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
    (
        "orders",
        """
        CREATE TABLE orders (
            order_id BIGINT PRIMARY KEY,
            customer_id BIGINT NOT NULL,
            order_date TIMESTAMP NOT NULL,
            status VARCHAR NOT NULL,
            channel VARCHAR NOT NULL,
            subtotal DOUBLE NOT NULL,
            discount_amount DOUBLE NOT NULL,
            shipping_fee DOUBLE NOT NULL,
            tax_amount DOUBLE NOT NULL,
            total_amount DOUBLE NOT NULL,
            currency VARCHAR NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
        """,
        """
        INSERT INTO orders
        SELECT
            order_id::BIGINT,
            customer_id::BIGINT,
            order_date::TIMESTAMP,
            status,
            channel,
            subtotal::DOUBLE,
            discount_amount::DOUBLE,
            shipping_fee::DOUBLE,
            tax_amount::DOUBLE,
            total_amount::DOUBLE,
            currency
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
    (
        "order_items",
        """
        CREATE TABLE order_items (
            order_item_id BIGINT PRIMARY KEY,
            order_id BIGINT NOT NULL,
            product_id BIGINT NOT NULL,
            quantity BIGINT NOT NULL,
            unit_price DOUBLE NOT NULL,
            line_total DOUBLE NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
        """,
        """
        INSERT INTO order_items
        SELECT
            order_item_id::BIGINT,
            order_id::BIGINT,
            product_id::BIGINT,
            quantity::BIGINT,
            unit_price::DOUBLE,
            line_total::DOUBLE
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
    (
        "payments",
        """
        CREATE TABLE payments (
            payment_id BIGINT PRIMARY KEY,
            order_id BIGINT NOT NULL,
            method VARCHAR NOT NULL,
            amount DOUBLE NOT NULL,
            paid_at TIMESTAMP NOT NULL,
            status VARCHAR NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )
        """,
        """
        INSERT INTO payments
        SELECT
            payment_id::BIGINT,
            order_id::BIGINT,
            method,
            amount::DOUBLE,
            paid_at::TIMESTAMP,
            status
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
    (
        "shipments",
        """
        CREATE TABLE shipments (
            shipment_id BIGINT PRIMARY KEY,
            order_id BIGINT NOT NULL,
            carrier VARCHAR NOT NULL,
            tracking_number VARCHAR NOT NULL,
            shipped_at TIMESTAMP NOT NULL,
            delivered_at TIMESTAMP,
            status VARCHAR NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )
        """,
        """
        INSERT INTO shipments
        SELECT
            shipment_id::BIGINT,
            order_id::BIGINT,
            carrier,
            tracking_number,
            shipped_at::TIMESTAMP,
            NULLIF(trim(delivered_at), '')::TIMESTAMP,
            status
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
    (
        "returns",
        """
        CREATE TABLE returns (
            return_id BIGINT PRIMARY KEY,
            order_item_id BIGINT NOT NULL,
            reason VARCHAR NOT NULL,
            refund_amount DOUBLE NOT NULL,
            requested_at TIMESTAMP NOT NULL,
            status VARCHAR NOT NULL,
            FOREIGN KEY (order_item_id) REFERENCES order_items(order_item_id)
        )
        """,
        """
        INSERT INTO returns
        SELECT
            return_id::BIGINT,
            order_item_id::BIGINT,
            reason,
            refund_amount::DOUBLE,
            requested_at::TIMESTAMP,
            status
        FROM read_csv('{csv}', header = true, all_varchar = true)
        """,
    ),
]


def build(path: Path = DB_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    for extra in (path, Path(str(path) + ".wal")):
        if extra.exists():
            extra.unlink()
    con = duckdb.connect(str(path))
    try:
        for name, create_sql, insert_sql in TABLES:
            csv_path = str(CSV_DIR / f"{name}.csv").replace("'", "''")
            con.execute(create_sql)
            con.execute(insert_sql.format(csv=csv_path))
            count = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            print(f"{name}: {count}")
    finally:
        con.close()
    return path


def build_demo_scale(modules: int = 220) -> Path:
    """Small dummy DuckDB with many tables for UI scalability checks."""
    from nlq import db

    path = db.DEMO_SCALE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    for extra in (path, Path(str(path) + ".wal")):
        if extra.exists():
            extra.unlink()
    con = duckdb.connect(str(path))
    try:
        for index in range(modules):
            name = f"module_{index:03d}"
            con.execute(f'CREATE TABLE "{name}" (id BIGINT, name VARCHAR)')
            con.execute(f"INSERT INTO \"{name}\" VALUES ({index}, '{name}')")
        count = con.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
            """
        ).fetchone()[0]
        print(f"demo_scale tables: {count}")
    finally:
        con.close()
    return path


def main() -> None:
    path = build()
    print(path)
    demo = build_demo_scale()
    print(demo)
    # Curated recommendations/ecommerce.json ships with the repo. When a new
    # dataset is registered at runtime, call recommend.on_dataset_loaded(name).
    try:
        from nlq import recommend

        if recommend.path_for("ecommerce").exists():
            recommend.load("ecommerce")
    except Exception as exc:
        print(f"recommendations: {exc}")


if __name__ == "__main__":
    main()
