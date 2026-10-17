"""Task-scoped state with transactional typed role updates, never arbitrary patches."""
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from config import db_kwargs
from contracts import Claim,FinalAnswer
from agent.state import Plan,Board,Subtask,Review


def read_state(task_id):
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        row=conn.execute('SELECT plan,subtasks,report FROM task_state WHERE task_id=%s',(UUID(task_id),)).fetchone()
    if not row:raise ValueError('No state for this task')
    return Board(plan=row[0],subtasks=row[1],report=row[2]).model_dump()


def write_state(task_id,role,payload,lease_token=None):
    ident=UUID(task_id)
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        from mcp_olist.leases import validate
        validate(conn,ident,lease_token,states=('running','planning') if role=='planner' else ('running',),lock=True)
        row=conn.execute('SELECT plan,subtasks,report FROM task_state WHERE task_id=%s FOR UPDATE',(ident,)).fetchone()
        if role=='planner':
            plan=Plan.model_validate(payload)
            if row:
                if row[0]!=plan.model_dump():raise ValueError('Cannot overwrite existing plan')
                return Board(plan=row[0],subtasks=row[1],report=row[2]).model_dump()
            board=Board(plan=plan,subtasks={p.id:Subtask(question=p.question,depends_on=p.depends_on) for p in plan.subtasks})
            conn.execute('INSERT INTO task_state(task_id,plan,subtasks) VALUES(%s,%s,%s)',
                (ident,Jsonb(plan.model_dump()),Jsonb({k:v.model_dump() for k,v in board.subtasks.items()})))
            return board.model_dump()
        if not row:raise ValueError('Planner must initialize state')
        board=Board(plan=row[0],subtasks=row[1],report=row[2])
        if role=='writer':
            board.report=FinalAnswer.model_validate(payload)
            eligible=[]
            for part in board.subtasks.values():
                if part.status not in {'completed','failed','unverified'}:raise ValueError('Subtasks still running')
                eligible.extend(c.model_dump() for i,c in enumerate(part.claims)
                    if (not part.review and part.status=='completed') or any(d.claim_index==i and d.approved for d in part.review))
            if any(c.model_dump() not in eligible for c in board.report.claims):raise ValueError('Writer invented or used a rejected claim')
        elif role in {'analyst','reviewer'}:
            key=payload['id']
            if key not in board.subtasks:raise ValueError('Unknown subtask')
            part=board.subtasks[key]
            if role=='analyst':
                if set(payload)-{'id','status','attempt','claims','error'}:raise ValueError('Analyst cannot write review fields')
                changes={k:v for k,v in payload.items() if k!='id'}
                if changes.get('attempt',part.attempt)<part.attempt:raise ValueError('Attempt cannot decrease')
                if changes.get('status')=='running':
                    if any(board.subtasks[d].status not in {'completed','unverified','failed'} for d in part.depends_on):raise ValueError('Dependencies are not finished')
                    changes['review']=[]
                board.subtasks[key]=Subtask.model_validate({**part.model_dump(),**changes})
            else:
                if set(payload)!={'id','decisions'}:raise ValueError('Reviewer may only write decisions')
                decisions=Review(decisions=payload['decisions']).decisions
                if sorted(d.claim_index for d in decisions)!=list(range(len(part.claims))):raise ValueError('Each claim needs exactly one decision')
                part.review=decisions
                part.status='completed' if decisions and all(d.approved for d in decisions) else 'unverified'
        else:raise ValueError('Unknown state role')
        conn.execute('UPDATE task_state SET subtasks=%s,report=%s,updated_at=now() WHERE task_id=%s',
            (Jsonb({k:v.model_dump() for k,v in board.subtasks.items()}),Jsonb(board.report.model_dump()) if board.report else None,ident))
        return board.model_dump()
