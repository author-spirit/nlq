# Adding data

NLQ queries DuckDB under `data/duckdb/`. Labels live in `hints/<id>.json`.

## Ship sample

```bash
python -m nlq.build_db
```

Builds `data/duckdb/ecommerce.duckdb` from `data/csv/ecommerce/`. Notes: `hints/ecommerce.json`. Starters: `recommendations/ecommerce.json`.

## Garage example

Fixture: `fixtures/garage/mysql.sql` → dataset `garage_my`.

Local:

```bash
python -m nlq.import_dataset --id garage_my --sql fixtures/garage/mysql.sql
```

Docker (container from `./bin/start.sh`; fixture is in the image):

```bash
docker exec nlq python -m nlq.import_dataset --id garage_my --sql fixtures/garage/mysql.sql
./bin/stop.sh && ./bin/start.sh
```

Postgres twin: `fixtures/garage/postgres.sql` with `--id garage_pg`.

## New dump or CSVs

No UI upload. Import on the host or copy into the container, then select the id in Settings → Datasets.

Local:

```bash
python -m nlq.import_dataset --id sales --sql ./sales_dump.sql
python -m nlq.import_dataset --id sales --csv-dir ./sales_csvs/
```

Docker (`./sales_dump.sql` is a host path; `/tmp/...` is inside container `nlq`):

```bash
docker cp ./sales_dump.sql nlq:/tmp/sales_dump.sql
docker exec nlq python -m nlq.import_dataset --id sales --sql /tmp/sales_dump.sql
./bin/stop.sh && ./bin/start.sh
```

Writes `data/duckdb/<id>.duckdb`, `data/datasets.json`, and `hints/<id>.json`. Optional: `recommendations/<id>.json`, or let the LLM generate on first visit.

## Planned

- Parquet import CLI.
- Live Postgres or MySQL without importing into DuckDB.
