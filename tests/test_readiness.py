"""Readiness checks cover the required databases with bounded acquisition."""
from contextlib import contextmanager
from types import SimpleNamespace
import db_pool
import pytest


def test_mcp_readiness_checks_reader_but_worker_does_not(monkeypatch):
    calls=[]
    @contextmanager
    def connection(component,database='agent',role='app',**kwargs):
        calls.append((component,database,role))
        if database=='olist':raise OSError('business database unavailable')
        yield SimpleNamespace(execute=lambda *_:None)
    monkeypatch.setattr(db_pool,'connection',connection)
    assert db_pool.ready('mcp') is False
    assert calls==[('mcp','agent','app'),('mcp','olist','reader')]
    calls.clear()
    assert db_pool.ready('worker') is True
    assert calls==[('worker','agent','app')]


@pytest.mark.parametrize('component',['api','mcp','worker'])
def test_readiness_uses_one_second_acquisition_timeout(component,monkeypatch):
    timeouts=[]
    @contextmanager
    def acquire(**kwargs):
        timeouts.append(kwargs.get('timeout'))
        yield SimpleNamespace(execute=lambda *_:None)
    monkeypatch.setattr(db_pool,'pool',lambda *a:SimpleNamespace(connection=acquire))
    assert db_pool.ready(component)
    assert timeouts==[1.0]*(2 if component=='mcp' else 1)
