"""Independent-oracle comparison and grain regression tests, without a DB."""

import ast
from pathlib import Path

import pandas as pd
import pytest

from eval.cross_check import RawAnswers, differences, plain


@pytest.mark.parametrize("actual,expected,matched", [
    (101, "100", True), (101.01, "100", False),
    (-101, "-100", True), (100, "-100", False),
    (0, "0", True), (1, "0", False),
    (["SP", "RJ"], ["RJ", "SP"], True),
    (["SP"], ["RJ", "SP"], False),
    ({"change": -5}, {"change": "-5"}, True),
    ({"change": -5}, {"other": "-5"}, False),
    ({"change": -5}, {"change": "5"}, False),
])
def test_comparison(actual, expected, matched):
    assert (not differences(actual, expected)) == matched


def test_nested_difference_identifies_fact():
    assert differences({"rate": 5}, {"rate": 6})[0]["path"] == "answer.rate"


def test_calculators_ignore_sql_and_preserve_join_grain():
    # Two orders by the same buyer; two payment rows must not double item sales.
    raw = RawAnswers.__new__(RawAnswers)
    raw.o = pd.DataFrame({"order_id": ["a", "b"], "buyer": ["same", "same"],
                          "state": ["SP", "SP"], "order_status": ["delivered", "canceled"],
                          "order_purchase_timestamp": pd.to_datetime(["2018-05-01", "2018-05-02"])})
    raw.i = pd.DataFrame({"order_id": ["a", "b"], "price": [100.0, 20.0]})
    raw.p = pd.DataFrame({"order_id": ["a", "a", "b"]})
    q = {"id": "C99", "parameters": {"start": "2018-04-01", "end": "2018-07-01", "state": "SP"},
         "gold_sql": "THIS IS NOT SQL", "naive_sql": "MUST NEVER BE READ"}
    assert plain(raw.calculate({**q, "template_id": "C_unique_customer"})) == 1
    assert plain(raw.calculate({**q, "template_id": "C_gmv_status"})) == 100
    assert plain(raw.calculate({**q, "template_id": "C_join_grain"})) == 120
    assert plain(raw.calculate({"id": "D10"})) == {"correct_price": 120, "naive_price": 220, "overcount": 100}


def test_cross_check_has_no_database_or_sql_oracle_imports():
    source = Path("eval/cross_check.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not modules & {"psycopg", "sqlalchemy", "sqlite3", "eval.dataset", "eval.templates", "eval.handwritten", "eval.scoring"}
