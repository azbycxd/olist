"""Owner-serialized admission, fenced leases and a cancellable runtime process."""
import os
import threading
import time
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
from config import db_kwargs
from api.tasks import event
from scripts.runtime import run_runtime
from scripts import task_limits as limits

LEASE_SECONDS=int(os.getenv('WORKER_LEASE_SECONDS','30'))
MAX_CLAIMS=3


def claim(task_id=None):
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owners=conn.execute("SELECT DISTINCT user_id FROM tasks WHERE background AND (%s::uuid IS NULL OR task_id=%s::uuid) AND status IN ('pending','planning','running','awaiting_confirmation')",(task_id,task_id)).fetchall()
        for (owner,) in owners:
            if not conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE SKIP LOCKED',(owner,)).fetchone():continue
            limits.reap_owner(conn,owner)
            while True:
                row=conn.execute("SELECT task_id,question,confirmed_at,run_config,status,claim_count FROM tasks WHERE user_id=%s AND background AND (%s::uuid IS NULL OR task_id=%s::uuid) AND (status='pending' OR (status IN ('planning','running') AND lease_expires_at<now())) ORDER BY created_at,task_id FOR UPDATE SKIP LOCKED LIMIT 1",(owner,task_id,task_id)).fetchone()
                if not row:break
                ident,question,confirmed,settings,previous,count=row
                if count>=MAX_CLAIMS:
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
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        try:check_lease(conn,ident,token)
        except limits.TaskStopped as exc:
            if str(exc) in {'task_timeout','canceled'}:limits.stop_task(conn,ident,str(exc))
            return False
        conn.execute("UPDATE tasks SET heartbeat_at=now(),lease_expires_at=LEAST(deadline_at,now()+%s*interval '1 second') WHERE task_id=%s",(LEASE_SECONDS,ident))
        return True


def process(job):
    ident,token=job['task_id'],job['token'];stop=threading.Event();lost=threading.Event();child=[]
    def attach(process):
        child.append(process)
        if lost.is_set() and process.poll() is None:process.kill()
    def beat():
        while not stop.wait(.5):
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
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            try:admission=limits.reserve(conn,ident,token,request)
            except limits.TaskStopped as exc:
                error=exc
                if str(exc) not in {'lease_lost','provider_unavailable'}:limits.stop_task(conn,ident,str(exc))
        if error:raise error
        return admission
    def emit(kind,payload,tokens=0,latency_ms=0):
        nonlocal termination
        if lost.is_set():raise limits.TaskStopped('lease_lost')
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            check_lease(conn,ident,token)
            if kind=='model_call':limits.settle(conn,ident,payload)
            event(conn,ident,kind,payload,tokens,latency_ms)
        if kind=='termination' and payload.get('scope')=='task':termination=payload['reason']
    try:
        for key,value in job['settings'].items():
            if key not in limits.settings():os.environ[key]=str(value)
        response=run_runtime(job['question'],ident,emit,phase=job['phase'],resume_board=job['board'],lease_token=str(token),budget_used=job['budget_used'],on_process=attach,control_check=admit)
        status='awaiting_confirmation' if termination=='awaiting_confirmation' else 'completed' if termination=='final_answer' else 'failed'
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            check_lease(conn,ident,token)
            conn.execute('UPDATE tasks SET status=%s,result=%s,error=%s,lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE task_id=%s',(status,Jsonb(response.model_dump()) if status=='completed' else None,None if status!='failed' else termination,ident))
            event(conn,ident,'task_status',{'status':status})
    except Exception as exc:
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            task=limits.lock_task(conn,ident)
            if task['status'] not in limits.TERMINAL and str(task['lease_token'])==str(token):
                reason='task_timeout' if task['expired'] else 'canceled' if task['cancel_requested_at'] else type(exc).__name__
                limits.stop_task(conn,ident,reason)
    finally:
        stop.set();thread.join(timeout=2)


def main():
    while True:
        job=claim()
        if job:process(job)
        else:time.sleep(1)


if __name__=='__main__':main()
