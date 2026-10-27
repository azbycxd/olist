"""Shared bucket admission and accounting; never contact a real provider."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import psycopg
import pytest
from config import db_kwargs
from scripts import task_limits as limits,task_worker as worker
from test_task_controls import new

integration=pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local PostgreSQL required')


def test_refill_is_fractional_capped_and_never_goes_backwards():
    from scripts.rate_limits import refill
    assert refill(1,10,12)==3
    assert refill(9,10,60)==10
    assert refill(2,10,-10)==2


def test_usage_difference_preserves_unknown_and_overage():
    from scripts.rate_limits import refund_amount
    assert refund_amount(100,{'total_tokens':40})==60
    assert refund_amount(100,{'total_tokens':150})==-50
    assert refund_amount(100,None) is None


@pytest.fixture
def rate_job(monkeypatch):
    monkeypatch.setenv('OPENAI_BASE_URL','http://rate-'+uuid4().hex+'/v1')
    monkeypatch.setenv('OPENAI_MODEL','rate-fixture')
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('rate-'+uuid4().hex,)).fetchone()[0]
    job=worker.claim(new(owner))
    yield job
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn,job['task_id']);limits.stop_task(conn,job['task_id'],'canceled')


def reserve(job,amount=100):
    call=uuid4()
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.reserve(conn,job['task_id'],job['token'],{'call_id':str(call),'requested_model':'rate-fixture','reserved_tokens':amount})
    return call


@pytest.mark.integration
@integration
def test_atomic_shared_rpm_and_tpm_do_not_over_admit(rate_job,monkeypatch):
    from scripts.rate_limits import RateWait
    monkeypatch.setenv('PROVIDER_RPM','3');monkeypatch.setenv('PROVIDER_TPM','300')
    def attempt(_):
        try:return reserve(rate_job)
        except RateWait:return None
    with ThreadPoolExecutor(max_workers=8) as pool:admitted=list(pool.map(attempt,range(8)))
    assert len([x for x in admitted if x])==3


@pytest.mark.integration
@integration
def test_inflight_limit_and_exactly_once_tpm_refund(rate_job,monkeypatch):
    from scripts.rate_limits import RateWait
    from scripts.provider_health import provider_key
    monkeypatch.setenv('PROVIDER_TPM','100');monkeypatch.setenv('PROVIDER_MAX_INFLIGHT','1')
    call=reserve(rate_job)
    with pytest.raises(RateWait):reserve(rate_job,1)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        limits.lock_task(conn,rate_job['task_id'])
        payload={'control_call_id':str(call),'error_class':None,'usage':{'total_tokens':40}}
        limits.settle(conn,rate_job['task_id'],payload)
        limits.settle(conn,rate_job['task_id'],payload)
        tokens,inflight=conn.execute('SELECT tpm_tokens,inflight FROM rate_buckets WHERE provider=%s',(provider_key(),)).fetchone()
        assert 60<=tokens<61 and inflight==0
    assert reserve(rate_job,60)


@pytest.mark.integration
@integration
def test_database_clock_refills_and_expired_inflight_is_reclaimed(rate_job,monkeypatch):
    from scripts.provider_health import provider_key
    monkeypatch.setenv('PROVIDER_RPM','1');monkeypatch.setenv('PROVIDER_TPM','100');monkeypatch.setenv('PROVIDER_MAX_INFLIGHT','1')
    reserve(rate_job)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        conn.execute("UPDATE rate_buckets SET updated_at=clock_timestamp()-interval '61 seconds' WHERE provider=%s",(provider_key(),))
        conn.execute("UPDATE rate_leases SET expires_at=clock_timestamp()-interval '1 second' WHERE provider=%s",(provider_key(),))
    assert reserve(rate_job)


@pytest.mark.integration
@integration
def test_disabled_limits_preserve_unrestricted_admission(rate_job,monkeypatch):
    for key in ['PROVIDER_RPM','PROVIDER_TPM','PROVIDER_MAX_INFLIGHT']:monkeypatch.delenv(key,raising=False)
    for _ in range(12):assert reserve(rate_job)
