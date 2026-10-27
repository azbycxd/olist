"""Conservative PostgreSQL AST allowlist, followed by database enforcement."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError
from sqlglot.optimizer.scope import traverse_scope

from mcp_olist.catalog import TABLES

MAX_ROWS = 1000
SAFE_FUNCTIONS = set("""ABS AVG CEIL CEILING FLOOR ROUND SUM MIN MAX COUNT COALESCE NULLIF
    LOWER UPPER LENGTH CHAR_LENGTH SUBSTRING TRIM LTRIM RTRIM REPLACE CONCAT CONCAT_WS
    DATE_TRUNC TIMESTAMP_TRUNC TIME_TO_STR TO_CHAR EXTRACT DATE_PART CAST TRY_CAST
    CURRENT_DATE CURRENT_TIMESTAMP ROW_NUMBER RANK DENSE_RANK LAG LEAD FIRST_VALUE LAST_VALUE
    STDDEV STDDEV_POP STDDEV_SAMP VARIANCE VAR_POP VAR_SAMP GREATEST LEAST
    ARRAY_AGG STRING_AGG GROUP_CONCAT PERCENTILE_CONT PERCENTILE_DISC
    CASE IF AND OR NOT""".split())
SAFE_TYPES = set("""TEXT VARCHAR CHAR BPCHAR INT SMALLINT BIGINT TINYINT DECIMAL FLOAT DOUBLE
    BOOLEAN DATE TIMESTAMP TIMESTAMPTZ TIME TIMETZ INTERVAL""".split())


class UnsafeSQL(ValueError):
    pass


def guard_sql(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 30000:
        raise UnsafeSQL("SQL must be nonempty and at most 30000 characters")
    try:
        parsed = [q for q in sqlglot.parse(sql, read="postgres", error_level=ErrorLevel.RAISE) if q is not None]
    except (ParseError, ValueError) as exc:
        raise UnsafeSQL("SQL could not be parsed as PostgreSQL") from exc
    if len(parsed) != 1 or not isinstance(parsed[0], (exp.Select, exp.SetOperation)):
        raise UnsafeSQL("Only one SELECT or WITH ... SELECT is allowed")
    tree = parsed[0]
    for node in tree.walk():
        if isinstance(node, (exp.DDL, exp.DML, exp.Command, exp.Into, exp.Lock, exp.Dot)):
            raise UnsafeSQL("Writes, locks, commands and qualified functions are forbidden")
        if isinstance(node, exp.CTE) and not isinstance(node.this, (exp.Select, exp.SetOperation)):
            raise UnsafeSQL("CTEs must contain read-only SELECTs")
        if isinstance(node, exp.Table):
            if not isinstance(node.this, exp.Identifier) or node.catalog or node.db not in ("", "public"):
                raise UnsafeSQL("Only public business tables are allowed")
        if isinstance(node, exp.Func):
            name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name()
            if name not in SAFE_FUNCTIONS:
                raise UnsafeSQL(f"Function is not allowed: {name}")
        if isinstance(node, exp.DataType) and getattr(node.this, "name", None) not in SAFE_TYPES:
            raise UnsafeSQL("Cast type is not allowed")
    # Resolve CTE visibility by scope: a nested alias must not authorize a
    # same-named physical system table elsewhere in the query.
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table) and source.name not in TABLES:
                raise UnsafeSQL("Table is outside the business allowlist")
    limit = tree.args.get("limit")
    if limit:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) < 0:
            raise UnsafeSQL("LIMIT must be a nonnegative integer literal")
        if int(value.this) > MAX_ROWS:
            tree = tree.limit(MAX_ROWS)
    else:
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="postgres", unsupported_level=ErrorLevel.RAISE)


def probe_sql(public_sql):
    """Internal fetch sentinel; never returned, persisted or content-hashed."""
    tree=sqlglot.parse_one(public_sql,read='postgres')
    if int(tree.args['limit'].expression.this)==MAX_ROWS:
        tree=tree.limit(MAX_ROWS+1)
    return tree.sql(dialect='postgres',unsupported_level=ErrorLevel.RAISE)
