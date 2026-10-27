"""PostgreSQL provider admission; callers must roll back before any waiting."""
from config import provider_rate_settings,MODEL_TIMEOUT


class RateWait(Exception):
    def __init__(self,seconds):
        self.seconds=max(0.001,seconds)
        super().__init__('provider_rate_capacity_unavailable')


def refill(balance,capacity,seconds):
    return min(capacity,balance+max(0,seconds)*capacity/60)


def refund_amount(reserved,usage):
    actual=(usage or {}).get('total_tokens')
    return reserved-actual if isinstance(actual,int) and not isinstance(actual,bool) and actual>=0 else None


def acquire(conn,provider,call,amount,deadline):
    settings=provider_rate_settings()
    rpm,tpm,maximum=(settings[k] for k in ('PROVIDER_RPM','PROVIDER_TPM','PROVIDER_MAX_INFLIGHT'))
    if not any((rpm,tpm,maximum)):return False
    conn.execute('INSERT INTO rate_buckets(provider,rpm_capacity,tpm_capacity,rpm_tokens,tpm_tokens) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(provider,rpm,tpm,rpm,tpm))
    # Lock one provider row before expiring its request leases. It never takes
    # task/reservation locks, so expiry cannot deadlock settlement's task locks.
    row=conn.execute('SELECT rpm_capacity,tpm_capacity FROM rate_buckets WHERE provider=%s FOR UPDATE',(provider,)).fetchone()
    if row!=(rpm,tpm):
        # A coordinated configuration rollout keeps already-spent capacity.
        # Enabling a previously unlimited bucket initializes it to its new cap.
        conn.execute("""UPDATE rate_buckets SET
            rpm_tokens=CASE WHEN rpm_capacity=0 THEN %s ELSE LEAST(%s,rpm_tokens+GREATEST(0,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)))*rpm_capacity/60) END,
            tpm_tokens=CASE WHEN tpm_capacity=0 THEN %s ELSE LEAST(%s,tpm_tokens+GREATEST(0,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)))*tpm_capacity/60) END,
            rpm_capacity=%s,tpm_capacity=%s,updated_at=clock_timestamp() WHERE provider=%s""",(rpm,rpm,tpm,tpm,rpm,tpm,provider))
    expired=conn.execute('DELETE FROM rate_leases WHERE provider=%s AND expires_at<=clock_timestamp() RETURNING call_id',(provider,)).fetchall()
    if expired:conn.execute('UPDATE rate_buckets SET inflight=inflight-%s WHERE provider=%s',(len(expired),provider))
    rpm_fill="LEAST(rpm_capacity,rpm_tokens+GREATEST(0,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)))*rpm_capacity/60)"
    tpm_fill="LEAST(tpm_capacity,tpm_tokens+GREATEST(0,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)))*tpm_capacity/60)"
    # One UPDATE both refills and debits, using PostgreSQL wall time. A denied
    # request changes neither bucket; RateWait rolls back the entire admission.
    accepted=conn.execute(f"""UPDATE rate_buckets SET
        rpm_tokens=CASE WHEN rpm_capacity=0 THEN 0 ELSE {rpm_fill}-1 END,
        tpm_tokens=CASE WHEN tpm_capacity=0 THEN 0 ELSE {tpm_fill}-%s END,
        updated_at=clock_timestamp(),inflight=inflight+1
        WHERE provider=%s AND (rpm_capacity=0 OR {rpm_fill}>=1)
        AND (tpm_capacity=0 OR {tpm_fill}>=%s) AND (%s=0 OR inflight<%s)
        RETURNING provider""",(amount,provider,amount,maximum,maximum)).fetchone()
    if not accepted:
        balance=conn.execute('SELECT rpm_tokens,tpm_tokens,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)),inflight FROM rate_buckets WHERE provider=%s',(provider,)).fetchone()
        seconds=float(balance[2]);waits=[settings['RATE_POLL_SECONDS']]
        if rpm:waits.append(max(0,1-refill(balance[0],rpm,seconds))*60/rpm)
        if tpm:waits.append(max(0,amount-refill(balance[1],tpm,seconds))*60/tpm)
        raise RateWait(max(waits))
    conn.execute("INSERT INTO rate_leases(call_id,provider,expires_at) VALUES(%s,%s,LEAST(%s,clock_timestamp()+%s*interval '1 second'))",(call,provider,deadline,MODEL_TIMEOUT))
    return True


def settle(conn,provider,call,reserved,usage):
    row=conn.execute('SELECT tpm_capacity FROM rate_buckets WHERE provider=%s FOR UPDATE',(provider,)).fetchone()
    if not row:return
    released=conn.execute('DELETE FROM rate_leases WHERE call_id=%s AND provider=%s RETURNING call_id',(call,provider)).fetchone()
    if released:conn.execute('UPDATE rate_buckets SET inflight=inflight-1 WHERE provider=%s',(provider,))
    difference=refund_amount(reserved,usage)
    if difference is not None and row[0]:
        conn.execute("""UPDATE rate_buckets SET
            rpm_tokens=LEAST(rpm_capacity,rpm_tokens+GREATEST(0,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)))*rpm_capacity/60),
            tpm_tokens=LEAST(tpm_capacity,tpm_tokens+GREATEST(0,EXTRACT(EPOCH FROM(clock_timestamp()-updated_at)))*tpm_capacity/60+%s),
            updated_at=clock_timestamp() WHERE provider=%s""",(difference,provider))


def abandon_task(conn,ident):
    # Unknown remote usage keeps its TPM debit; only local in-flight slots are
    # released on cancellation/requeue. Expiry also recovers hard-crashed workers.
    rows=conn.execute('SELECT call_id,provider FROM model_reservations WHERE task_id=%s AND rate_held',(ident,)).fetchall()
    for call,provider in rows:settle(conn,provider,call,0,None)
