"""Canonical PostgreSQL spelling for signatures, never a SQL security check."""
import sqlglot
from sqlglot.errors import ErrorLevel
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers


def normalize_sql(statement):
    try:
        trees = sqlglot.parse(statement, read='postgres', error_level=ErrorLevel.RAISE)
        if len(trees)!=1 or trees[0] is None: return statement
        return normalize_identifiers(trees[0], dialect='postgres').sql(dialect='postgres', comments=False)
    except (sqlglot.errors.SqlglotError, ValueError, TypeError):
        return statement
