"""Operational modules must retain their import-time documentation."""
import ast
from pathlib import Path
import pytest


@pytest.mark.parametrize('filename',[
    'api/tasks.py','scripts/task_worker.py',
    'mcp_olist/idempotency.py','mcp_olist/service.py',
])
def test_operational_module_has_docstring(filename):
    assert ast.get_docstring(ast.parse(Path(filename).read_text(encoding='utf8'))),filename
