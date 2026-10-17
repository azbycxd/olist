"""Load the nine CSV files atomically; unchanged input is safe to run again."""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from config import DATA_DIR, ROOT, db_kwargs
from scripts.common import record, start_log

TABLES = {
    "customers": "customer_id customer_unique_id customer_zip_code_prefix customer_city customer_state",
    "geolocation": "geolocation_zip_code_prefix geolocation_lat geolocation_lng geolocation_city geolocation_state",
    "product_category_name_translation": "product_category_name product_category_name_english",
    "products": "product_id product_category_name product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm",
    "sellers": "seller_id seller_zip_code_prefix seller_city seller_state",
    "orders": "order_id customer_id order_status order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date",
    "order_items": "order_id order_item_id product_id seller_id shipping_limit_date price freight_value",
    "order_payments": "order_id payment_sequential payment_type payment_installments payment_value",
    "order_reviews": "review_id order_id review_score review_comment_title review_comment_message review_creation_date review_answer_timestamp",
}


def csv_path(directory: Path, table: str) -> Path:
    name = table if table == "product_category_name_translation" else f"olist_{table}_dataset"
    return directory / f"{name}.csv"


def inspect_sources(directory: Path):
    manifest = {}
    for table, columns in TABLES.items():
        path = csv_path(directory, table)
        if not path.is_file():
            raise ValueError(f"Missing CSV: {path}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            if next(reader, None) != columns.split():
                raise ValueError(f"Unexpected CSV header: {path.name}")
            row_count = sum(1 for _ in reader)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest[table] = {"file": path.name, "sha256": digest, "rows": row_count}
    version = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return manifest, version


def load(directory: Path, replace: bool, logger):
    manifest, version = inspect_sources(directory)
    record(logger, "sources_validated", data_version=version, manifest=manifest)
    with psycopg.connect(**db_kwargs()) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(730016)")
        conn.execute((ROOT / "sql" / "olist.sql").read_text(encoding="utf-8"))
        previous = conn.execute("SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()
        counts = {table: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
                  for table in TABLES}
        if previous and previous[0] == version and all(counts[t] == manifest[t]["rows"] for t in TABLES):
            record(logger, "already_loaded", data_version=version, rows=counts)
            return version
        if (previous or any(counts.values())) and not replace:
            raise ValueError("Existing data differs from this import. Inspect it before explicitly using --replace.")
        if replace:
            conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY").format(
                sql.SQL(", ").join(sql.Identifier(table) for table in TABLES)))
        for table, columns in TABLES.items():
            statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')").format(
                sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, columns.split())))
            with conn.cursor().copy(statement) as copy, csv_path(directory, table).open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    copy.write(chunk)
            count = conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
            if count != manifest[table]["rows"]:
                raise ValueError(f"Row count mismatch in {table}")
            # Verify the bytes actually imported still match the preflight manifest.
            with csv_path(directory, table).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != manifest[table]["sha256"]:
                    raise ValueError(f"Source changed during import: {table}")
            record(logger, "table_loaded", table=table, rows=count)
        conn.execute("INSERT INTO data_imports (data_version, manifest) VALUES (%s, %s)", (version, Jsonb(manifest)))
        conn.execute("ANALYZE")
    record(logger, "import_committed", data_version=version)
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--replace", action="store_true", help="Explicitly replace existing business data in one transaction")
    parser.add_argument("--profile", action="store_true", help="Generate docs/data_profile.md after import")
    args = parser.parse_args()
    logger, path = start_log("load_olist")
    try:
        load(args.data_dir, args.replace, logger)
        if args.profile:
            from scripts.profile_data import generate
            generate(import_log=path.name)
    except Exception as exc:
        record(logger, "failed", error=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
