import csv

import pytest

from scripts.load_olist import TABLES, csv_path, inspect_sources


def write_sources(directory):
    for table, columns in TABLES.items():
        with csv_path(directory, table).open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(columns.split())


def test_missing_files_fail_before_database_connection(tmp_path):
    with pytest.raises(ValueError, match="Missing CSV"):
        inspect_sources(tmp_path)


def test_bad_headers_fail_before_database_connection(tmp_path):
    write_sources(tmp_path)
    csv_path(tmp_path, "customers").write_text("wrong,header\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected CSV header"):
        inspect_sources(tmp_path)


def test_fingerprint_and_csv_record_count(tmp_path):
    write_sources(tmp_path)
    manifest, before = inspect_sources(tmp_path)
    assert all(v["rows"] == 0 for v in manifest.values())
    with csv_path(tmp_path, "order_reviews").open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerow(["review", "order", 5, "title", "two\nlines", "2018-01-01", "2018-01-02"])
    manifest, after = inspect_sources(tmp_path)
    assert manifest["order_reviews"]["rows"] == 1
    assert before != after
