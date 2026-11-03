import pytest

from mcp_olist.sql_guard import UnsafeSQL, guard_sql, probe_sql


@pytest.mark.parametrize("statement", [
    "DROP TABLE orders", "DELETE FROM orders", "UPDATE orders SET order_status='x'",
    "SELECT 1; SELECT 2", "SELECT 1; /* hidden */ DROP TABLE orders",
    "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
    "SELECT * INTO copy_of_orders FROM orders", "SELECT * FROM orders FOR UPDATE",
    "SELECT pg_sleep(1)", "SELECT pg_catalog.pg_sleep(1)", 'SELECT "pg_sleep"(1)',
    "SELECT /*comment*/ pg_read_file('/etc/passwd')", "SELECT pg_ls_dir('/')",
    "SELECT dblink('secret','SELECT 1')", "SELECT set_config('statement_timeout','0',false)",
    "COPY orders TO STDOUT", "EXPLAIN ANALYZE SELECT * FROM orders", "SET statement_timeout=0",
    "SELECT * FROM pg_catalog.pg_authid", "SELECT * FROM information_schema.tables",
    "SELECT * FROM data_imports", "SELECT * FROM other.orders", "SELECT * FROM agent.public.tasks",
    "SELECT nextval('some_sequence')", "SELECT pg_advisory_lock(1)",
    "SELECT lo_import('/etc/passwd')", "SELECT query_to_xml('DELETE FROM orders',true,true,'')",
    "SELECT 'pg_authid'::regclass", "SELECT * FROM generate_series(1,100000000)",
    "SELECT * FROM orders LIMIT ALL", "SELECT * FROM orders LIMIT (SELECT 10000)",
    "SELECT * FROM orders LIMIT -1", "WITH x AS (SELECT pg_sleep(1)) SELECT * FROM x",
    "SELECT * FROM pg_settings WHERE EXISTS (WITH pg_settings AS (SELECT 1) SELECT * FROM pg_settings)",
    "WITH data_imports AS (SELECT 1) SELECT * FROM public.data_imports",
])
def test_attacks_are_rejected(statement):
    with pytest.raises(UnsafeSQL):
        guard_sql(statement)


@pytest.mark.parametrize("statement", [
    "SELECT count(*) AS orders FROM orders",
    "SELECT sum(price), avg(freight_value) FROM public.order_items",
    "WITH x AS (SELECT customer_state,count(*) AS n FROM customers GROUP BY 1) SELECT * FROM x",
    "SELECT count(*) FILTER (WHERE order_status='delivered') FROM orders",
    "SELECT date_trunc('month',order_purchase_timestamp) AS month FROM orders",
    "SELECT extract(epoch FROM (order_delivered_customer_date-order_purchase_timestamp))/86400.0 FROM orders",
    "SELECT 'DROP TABLE orders; pg_sleep(2)' AS untrusted_text",
    "SELECT 1 AS n UNION ALL SELECT 2 AS n",
])
def test_read_only_queries_are_capped(statement):
    assert guard_sql(statement).sql.endswith("LIMIT 1000")


def test_explicit_limit_is_enforced():
    assert guard_sql("SELECT * FROM orders LIMIT 2000").sql.endswith("LIMIT 1000")
    assert guard_sql("SELECT * FROM orders LIMIT 7").sql.endswith("LIMIT 7")


def test_sql_length_boundary():
    statement = "SELECT '" + "x" * (30000 - len("SELECT ''")) + "'"
    assert len(statement) == 30000
    assert guard_sql(statement).sql.endswith("LIMIT 1000")

    too_long = statement[:-1] + "x'"
    assert len(too_long) == 30001
    with pytest.raises(UnsafeSQL, match="at most 30000"):
        guard_sql(too_long)


def test_zero_limit_is_preserved_without_probe():
    guarded = guard_sql("SELECT * FROM orders LIMIT 0")
    assert guarded.sql.endswith("LIMIT 0")
    assert guarded.capped is False
    assert probe_sql(guarded.sql, guarded.capped) == guarded.sql


@pytest.mark.parametrize("limit", ["1.5", "1+1"])
def test_noninteger_or_expression_limit_is_rejected(limit):
    with pytest.raises(UnsafeSQL, match="LIMIT must be a nonnegative integer literal"):
        guard_sql(f"SELECT * FROM orders LIMIT {limit}")


def test_oversized_limit_is_capped_and_probed():
    guarded = guard_sql("SELECT * FROM orders LIMIT 2000")
    assert guarded.sql.endswith("LIMIT 1000")
    assert guarded.capped is True
    assert probe_sql(guarded.sql, guarded.capped).endswith("LIMIT 1001")


def test_nested_cte_does_not_authorize_outer_system_table():
    statement = "SELECT * FROM (WITH pg_settings AS (SELECT 1) SELECT * FROM pg_settings) AS a, pg_settings"
    with pytest.raises(UnsafeSQL, match="business allowlist"):
        guard_sql(statement)
