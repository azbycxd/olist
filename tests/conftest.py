"""The CI unit suite cannot silently depend on a service or model endpoint."""
import os
import socket
import pytest


@pytest.fixture(autouse=True)
def offline_services(monkeypatch):
    if os.getenv('CI_OFFLINE')!='1':return
    import psycopg
    def denied(*a,**k):raise AssertionError('CI unit tests must not connect to a model, database or network service')
    monkeypatch.setattr(psycopg,'connect',denied)
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket.socket,'connect_ex',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
