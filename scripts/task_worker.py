from db_pool import connection
"""Owner-serialized admission, fenced leases and a cancellable runtime process."""
import os
import signal
import threading
import time
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
from config import WORKER_GRACE_SECONDS, WORKER_HEARTBEAT_SECONDS
from db_pool import close_all, validate_settings, ready
from api.tasks import event
from scripts.runtime import run_runtime
from scripts import task_limits as limits

LEASE_SECONDS=int(os.getenv('WORKER_LEASE_SECONDS','30'))
MAX_CLAIMS=3


def claim(task_id=None):
    with connection('worker') as conn:
        owners=conn.execute("SELECT DISTINCT user_id FROM tasks WHERE background AND (%s::uuid IS NULL OR task_id=%s::uuid) AND status IN ('pending','planning','running','awaiting_confirmation')",(task_id,task_id)).fetchall()
        for (owner,) in owners:
            if not conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE SKIP LOCKED',(owner,)).fetchone():continue
            limits.reap_owner(conn,owner)
            while True:
                row=conn.execute("SELECT task_id,question,confirmed_at,run_config,status,claim_count,released_count FROM tasks WHERE user_id=%s AND background AND (%s::uuid IS NULL OR task_id=%s::uuid) AND (status='pending' OR (status IN ('planning','running') AND lease_expires_at<now())) ORDER BY created_at,task_id FOR UPDATE SKIP LOCKED LIMIT 1",(owner,task_id,task_id)).fetchone()
                if not row:break
                ident,question,confirmed,settings,previous,count,released=row
                if count-released>=MAX_CLAIMS:
                    reason=f'claim_limit_exceeded: {count} leases already issued; maximum {MAX_CLAIMS}'
                    limits.stop_task(conn,ident,reason,extra={'attempted_claim':count+1,'max_claims':MAX_CLAIMS})
                    continue
                running=conn.execute("SELECT count(*) FROM tasks WHERE user_id=%s AND task_id!=%s AND status IN ('planning','running') AND lease_expires_at>now()",(owner,ident)).fetchone()[0]
                if running>=limits.settings()['USER_MAX_RUNNING_TASKS']:break
                if not limits.quota(conn,owner)['available_tokens']:
                    limits.stop_task(conn,ident,'daily_token_quota');continue
                token=uuid4()
                phase='execute' if confirmed or settings.get('AGENT_MODE')=='single' else 'plan'
                conn.execute("UPDATE tasks SET deadline_at=COALESCE(deadline_at,now()+%s*interval '1 second') WHERE task_id=%s",(limits.settings()['TASK_MAX_SECONDS'],ident))
                conn.execute("UPDATE tasks SET status=%s,lease_token=%s,lease_expires_at=LEAST(deadline_at,now()+%s*interval '1 second'),heartbeat_at=now(),claim_count=claim_count+1,updated_at=now() WHERE task_id=%s",('running' if phase=='execute' else 'planning',token,LEASE_SECONDS,ident))
                event(conn,ident,'worker_claimed',{'phase':phase,'recovered':previous in {'planning','running'},'claim_count':count+1,'worker_id':os.getenv('WORKER_ID') or f'{os.getenv("HOSTNAME","local")}:{os.getpid()}'})
                state=conn.execute('SELECT plan,subtasks,report FROM task_state WHERE task_id=%s',(ident,)).fetchone()
                budget=conn.execute("SELECT COALESCE(SUM(tokens),0) FROM events WHERE task_id=%s AND type='model_call'",(ident,)).fetchone()[0]
                return {'task_id':ident,'question':question,'token':token,'phase':phase,'settings':settings,'board':dict(zip(['plan','subtasks','report'],state)) if state else None,'budget_used':budget}
        return None


def check_lease(conn,ident,token):
    limits.active(limits.lock_task(conn,ident),token)


def heartbeat(ident,token):
    with connection('worker') as conn:
        try:check_lease(conn,ident,token)
        except limits.TaskStopped as exc:
            if str(exc) in {'task_timeout','canceled'}:limits.stop_task(conn,ident,str(exc))
            return False
        conn.execute("UPDATE tasks SET heartbeat_at=now(),lease_expires_at=LEAST(deadline_at,now()+%s*interval '1 second') WHERE task_id=%s",(LEASE_SECONDS,ident))
        return True


def release(job):
    """Fence the old worker and requeue without charging a recovery attempt."""
    ident,token=job['task_id'],job['token']
    with connection('worker') as conn:
        task=limits.lock_task(conn,ident)
        if task['status'] in limits.TERMINAL or str(task['lease_token'])!=str(token):
            return False
        if task['expired'] or task['cancel_requested_at']:
            limits.stop_task(conn,ident,'task_timeout' if task['expired'] else 'canceled')
            return False
        conn.execute("UPDATE tasks SET status='pending',lease_token=NULL,lease_expires_at=NULL,released_count=released_count+1,updated_at=clock_timestamp() WHERE task_id=%s",(ident,))
        conn.execute("UPDATE model_reservations SET status='unknown' WHERE task_id=%s AND status='pending'",(ident,))
        event(conn,ident,'released',{'reason':'worker_shutdown','worker_id':worker_id()})
        return True


def worker_id():
    return os.getenv('WORKER_ID') or f'{os.getenv("HOSTNAME","local")}:{os.getpid()}'


def worker_heartbeat(status):
    with connection('worker') as conn:
        conn.execute('INSERT INTO worker_heartbeats(worker_id,status) VALUES(%s,%s) ON CONFLICT(worker_id) DO UPDATE SET last_seen=clock_timestamp(),status=excluded.status',(worker_id(),status))
    from scripts.worker_health import write_heartbeat
    write_heartbeat(status)


def process(job,shutdown=None):
    ident,token=job['task_id'],job['token'];stop=threading.Event();lost=threading.Event();child=[]
    shutdown=shutdown or threading.Event()
    releasing=threading.Event()
    def attach(process):
        child.append(process)
        if lost.is_set() and process.poll() is None:process.kill()
    def beat():
        drain_started=None
        while not stop.wait(.5):
            if shutdown.is_set():
                if drain_started is None:drain_started=time.monotonic()
                if time.monotonic()-drain_started>=WORKER_GRACE_SECONDS:
                    releasing.set();lost.set()
                    if child and child[0].poll() is None:child[0].kill()
                    release(job)
                    return
            try:alive=heartbeat(ident,token)
            except Exception:alive=False
            if not alive:
                lost.set()
                if child and child[0].poll() is None:child[0].kill()
                return
    thread=threading.Thread(target=beat,daemon=True);thread.start()
    termination=None
    def admit(request):
        error=None
        with connection('worker') as conn:
            try:admission=limits.reserve(conn,ident,token,request)
            except limits.TaskStopped as exc:
                error=exc
                if str(exc) not in {'lease_lost','provider_unavailable'}:limits.stop_task(conn,ident,str(exc))
        if error:raise error
        return admission
    def emit(kind,payload,tokens=0,latency_ms=0):
        nonlocal termination
        if lost.is_set():raise limits.TaskStopped('lease_lost')
        with connection('worker') as conn:
            check_lease(conn,ident,token)
            if kind=='model_call':limits.settle(conn,ident,payload)
            event(conn,ident,kind,payload,tokens,latency_ms)
        if kind=='termination' and payload.get('scope')=='task':termination=payload['reason']
    try:
        for key,value in job['settings'].items():
            if key not in limits.settings():os.environ[key]=str(value)
        response=run_runtime(job['question'],ident,emit,phase=job['phase'],resume_board=job['board'],lease_token=str(token),budget_used=job['budget_used'],on_process=attach,control_check=admit)
        status='awaiting_confirmation' if termination=='awaiting_confirmation' else 'completed' if termination=='final_answer' else 'failed'
        with connection('worker') as conn:
            check_lease(conn,ident,token)
            conn.execute('UPDATE tasks SET status=%s,result=%s,error=%s,lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE task_id=%s',(status,Jsonb(response.model_dump()) if status=='completed' else None,None if status!='failed' else termination,ident))
            event(conn,ident,'task_status',{'status':status})
    except Exception as exc:
        if releasing.is_set():
            release(job)
        else:
          with connection('worker') as conn:
            task=limits.lock_task(conn,ident)
            if task['status'] not in limits.TERMINAL and str(task['lease_token'])==str(token):
                reason='task_timeout' if task['expired'] else 'canceled' if task['cancel_requested_at'] else type(exc).__name__
                limits.stop_task(conn,ident,reason)
    finally:
        stop.set();thread.join(timeout=2)


def main():
    validate_settings('worker')
    shutdown=threading.Event();done=threading.Event()
    old={sig:signal.signal(sig,lambda *_:shutdown.set()) for sig in (signal.SIGTERM,signal.SIGINT)}
    def report():
        while not done.is_set():
            try:worker_heartbeat('draining' if shutdown.is_set() else 'ready')
            except Exception:pass  # Healthcheck becomes unhealthy until DB recovers.
            done.wait(WORKER_HEARTBEAT_SECONDS)
    reporter=threading.Thread(target=report,daemon=True);reporter.start()
    try:
        while not shutdown.is_set():
            job=claim()
            if job:
                if shutdown.is_set():release(job)
                else:process(job,shutdown)
            else:shutdown.wait(1)
    finally:
        done.set();reporter.join(timeout=WORKER_HEARTBEAT_SECONDS+1)
        try:worker_heartbeat('stopped')
        finally:
            close_all('worker')
            for sig,handler in old.items():signal.signal(sig,handler)


if __name__=='__main__':main()
