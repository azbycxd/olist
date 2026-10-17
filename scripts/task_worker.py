"""Database queue with expiring leases, fenced events and subtask checkpoints."""
import os
import threading
import time
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb
from config import db_kwargs
from api.tasks import event
from scripts.runtime import run_runtime

LEASE_SECONDS=int(os.getenv('WORKER_LEASE_SECONDS','30'))


def claim(task_id=None):
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        row=conn.execute("SELECT task_id,question,confirmed_at,run_config,status FROM tasks WHERE background AND (%s::uuid IS NULL OR task_id=%s::uuid) AND (status='pending' OR (status IN ('planning','running') AND lease_expires_at<now())) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1",(task_id,task_id)).fetchone()
        if not row:return None
        ident,question,confirmed,settings,previous=row;token=uuid4()
        phase='execute' if confirmed else 'plan'
        conn.execute("UPDATE tasks SET status=%s,lease_token=%s,lease_expires_at=now()+%s*interval '1 second',heartbeat_at=now(),claim_count=claim_count+1,updated_at=now() WHERE task_id=%s",
            ('running' if confirmed else 'planning',token,LEASE_SECONDS,ident))
        recovered=previous in {'planning','running'}
        event(conn,ident,'worker_claimed',{'phase':phase,'recovered':recovered})
        state=conn.execute('SELECT plan,subtasks,report FROM task_state WHERE task_id=%s',(ident,)).fetchone()
        budget=conn.execute("SELECT COALESCE(SUM(tokens),0) FROM events WHERE task_id=%s AND type='model_call'",(ident,)).fetchone()[0]
        board=dict(zip(['plan','subtasks','report'],state)) if state else None
        return {'task_id':ident,'question':question,'token':token,'phase':phase,'settings':settings,'board':board,'budget_used':budget}


def heartbeat(ident,token):
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        return conn.execute("UPDATE tasks SET heartbeat_at=now(),lease_expires_at=now()+%s*interval '1 second' WHERE task_id=%s AND lease_token=%s AND lease_expires_at>now() AND status IN ('planning','running') RETURNING task_id",
            (LEASE_SECONDS,ident,token)).fetchone() is not None


def check_lease(conn,ident,token):
    row=conn.execute("SELECT 1 FROM tasks WHERE task_id=%s AND lease_token=%s AND lease_expires_at>now() AND status IN ('planning','running') FOR UPDATE",(ident,token)).fetchone()
    if not row:raise RuntimeError('Worker lease lost')


def process(job):
    ident,token=job['task_id'],job['token'];stop=threading.Event();lost=threading.Event();child=[]
    def beat():
        while not stop.wait(max(1,LEASE_SECONDS/4)):
            try:alive=heartbeat(ident,token)
            except Exception:alive=False
            if not alive:
                lost.set()
                if child and child[0].poll() is None:child[0].kill()
                return
    thread=threading.Thread(target=beat,daemon=True);thread.start()
    termination=None
    def emit(kind,payload,tokens=0,latency_ms=0):
        nonlocal termination
        if lost.is_set():raise RuntimeError('Worker lease lost')
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            check_lease(conn,ident,token)
            event(conn,ident,kind,payload,tokens,latency_ms)
        if kind=='termination' and payload.get('scope')=='task':termination=payload['reason']
    try:
        for key,value in job['settings'].items():os.environ[key]=str(value)
        response=run_runtime(job['question'],ident,emit,phase=job['phase'],resume_board=job['board'],
            lease_token=str(token),budget_used=job['budget_used'],on_process=lambda p:child.append(p))
        status='awaiting_confirmation' if termination=='awaiting_confirmation' else 'completed' if termination=='final_answer' else 'failed'
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            check_lease(conn,ident,token)
            conn.execute('UPDATE tasks SET status=%s,result=%s,error=%s,lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE task_id=%s',
                (status,Jsonb(response.model_dump()) if status=='completed' else None,None if status!='failed' else termination,ident))
            event(conn,ident,'task_status',{'status':status})
    except Exception as exc:
        if not lost.is_set():
            with psycopg.connect(**db_kwargs('agent','app')) as conn:
                try:check_lease(conn,ident,token)
                except RuntimeError:return
                conn.execute("UPDATE tasks SET status='failed',error=%s,lease_token=NULL,lease_expires_at=NULL,updated_at=now() WHERE task_id=%s",(type(exc).__name__,ident))
                event(conn,ident,'task_status',{'status':'failed','error':type(exc).__name__})
    finally:
        stop.set();thread.join(timeout=2)


def main():
    while True:
        job=claim()
        if job:process(job)
        else:time.sleep(1)


if __name__=='__main__':main()
