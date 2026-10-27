"""Owner-serialized task controls and UTC daily request reservation accounting."""
import os
from uuid import UUID
from api.tasks import event

TERMINAL={'completed','failed','canceled'}


class TaskStopped(RuntimeError):
    pass


def settings():
    values={key:int(os.getenv(key,default)) for key,default in
            [('TASK_MAX_SECONDS','300'),('USER_MAX_RUNNING_TASKS','2'),('USER_DAILY_TOKEN_QUOTA','1000000')]}
    if min(values.values())<1:raise ValueError('Task limits must be positive integers')
    return values


def owner_lock(conn,owner):
    conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(owner,))


def lock_task(conn,ident):
    row=conn.execute('SELECT user_id FROM tasks WHERE task_id=%s',(ident,)).fetchone()
    if not row:raise TaskStopped('task_not_found')
    owner_lock(conn,row[0])
    cursor=conn.execute('SELECT task_id,user_id,status,lease_token,lease_expires_at>clock_timestamp() AS lease_alive,cancel_requested_at,deadline_at<=clock_timestamp() AS expired,run_config,deadline_at FROM tasks WHERE task_id=%s FOR UPDATE',(ident,))
    return dict(zip([c.name for c in cursor.description],cursor.fetchone()))


def quota(conn,owner):
    day=conn.execute("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date").fetchone()[0]
    row=conn.execute('SELECT used_tokens,held_tokens FROM user_token_days WHERE user_id=%s AND usage_day=%s',(owner,day)).fetchone() or (0,0)
    cap=settings()['USER_DAILY_TOKEN_QUOTA']
    return {'usage_day':day,'used_tokens':row[0],'held_tokens':row[1],'limit':cap,'available_tokens':max(0,cap-row[0]-row[1])}


def stop_task(conn,ident,reason,extra=None):
    status='canceled' if reason=='canceled' else 'failed'
    changed=conn.execute("UPDATE tasks SET status=%s,error=%s,lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE task_id=%s AND status NOT IN ('completed','failed','canceled') RETURNING task_id",(status,reason,ident)).fetchone()
    # In-flight calls may have consumed tokens. Keep their holds for their UTC
    # request day; never invent actual usage or release an uncertain charge.
    conn.execute("UPDATE model_reservations SET status='unknown' WHERE task_id=%s AND status='pending'",(ident,))
    from scripts.rate_limits import abandon_task
    abandon_task(conn,ident)
    if changed:event(conn,ident,'task_status',{'status':status,'error':reason,**(extra or {})})


def active(task,token):
    if task['cancel_requested_at'] or task['status']=='canceled':raise TaskStopped('canceled')
    if task['expired']:raise TaskStopped('task_timeout')
    if task['status'] not in {'planning','running'} or str(task['lease_token'])!=str(token) or not task['lease_alive']:
        raise TaskStopped('lease_lost')


def reserve(conn,ident,token,request):
    task=lock_task(conn,ident);active(task,token)
    call=UUID(request['call_id']);amount=request['reserved_tokens']
    if not isinstance(amount,int) or not 0<amount<=10_000_000:raise TaskStopped('invalid_reservation')
    existing=conn.execute('SELECT task_id,reserved_tokens FROM model_reservations WHERE call_id=%s',(call,)).fetchone()
    if existing:
        if existing!=(UUID(str(ident)),amount):raise TaskStopped('reservation_conflict')
        return
    available=quota(conn,task['user_id'])
    if amount>available['available_tokens']:raise TaskStopped('daily_token_quota')
    from scripts import provider_health
    model=request.get('requested_model') or os.getenv('OPENAI_MODEL') or 'unconfigured'
    provider,generation=provider_health.admit(conn,call,model,task['deadline_at'])
    from scripts import rate_limits
    rate_held=rate_limits.acquire(conn,provider,call,amount,task['deadline_at'])
    conn.execute('INSERT INTO user_token_days(user_id,usage_day,held_tokens) VALUES(%s,%s,%s) ON CONFLICT(user_id,usage_day) DO UPDATE SET held_tokens=user_token_days.held_tokens+excluded.held_tokens',
                 (task['user_id'],available['usage_day'],amount))
    conn.execute('INSERT INTO model_reservations(call_id,task_id,user_id,usage_day,reserved_tokens,provider,model,provider_generation,rate_held) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                 (call,ident,task['user_id'],available['usage_day'],amount,provider,model,generation,rate_held))
    event(conn,ident,'model_admitted',{'call_id':str(call),'reserved_tokens':amount,'usage_day':str(available['usage_day']),
                                      'role':request.get('role'),'step':request.get('step')})
    remaining=conn.execute('SELECT EXTRACT(EPOCH FROM (%s::timestamptz-clock_timestamp()))',(task['deadline_at'],)).fetchone()[0]
    return {'remaining_seconds':max(0,float(remaining))}


def settle(conn,ident,payload):
    call=payload.get('control_call_id')
    if not call:return
    row=conn.execute('SELECT user_id,usage_day,reserved_tokens,status,rate_held,provider FROM model_reservations WHERE call_id=%s AND task_id=%s FOR UPDATE',(UUID(call),ident)).fetchone()
    if not row or row[3]=='settled':return
    from scripts import provider_health
    provider_health.record(conn,UUID(call),payload)
    if row[4]:
        from scripts import rate_limits
        rate_limits.settle(conn,row[5],UUID(call),row[2],payload.get('usage'))
    actual=(payload.get('usage') or {}).get('total_tokens')
    if not isinstance(actual,int) or actual<0:
        conn.execute("UPDATE model_reservations SET status='unknown' WHERE call_id=%s",(UUID(call),))
        return
    conn.execute('UPDATE user_token_days SET used_tokens=used_tokens+%s,held_tokens=held_tokens-%s WHERE user_id=%s AND usage_day=%s',(actual,row[2],row[0],row[1]))
    conn.execute("UPDATE model_reservations SET status='settled',actual_tokens=%s WHERE call_id=%s",(actual,UUID(call)))
    if actual>row[2]:
        # A nonconforming provider is visible, and no new calls are admitted.
        stop_task(conn,ident,'provider_usage_exceeds_reservation')


def reap_owner(conn,owner):
    rows=conn.execute("SELECT task_id,cancel_requested_at IS NOT NULL FROM tasks WHERE user_id=%s AND background AND status IN ('pending','planning','running','awaiting_confirmation') AND (cancel_requested_at IS NOT NULL OR deadline_at<=now()) FOR UPDATE",(owner,)).fetchall()
    for ident,canceled in rows:stop_task(conn,ident,'canceled' if canceled else 'task_timeout')
