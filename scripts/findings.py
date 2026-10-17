"""Trusted, owner-scoped storage and import of reviewed historical evidence."""
import hashlib
import json
import os
from uuid import UUID
import psycopg
from psycopg.types.json import Jsonb
from config import db_kwargs
from agent.state import Board
from mcp_olist.knowledge import embed, MODEL, REVISION


def current_version():
    with psycopg.connect(**db_kwargs(role='reader')) as conn:
        return conn.execute('SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1').fetchone()[0]


def save_reviewed(task_id,lease_token=None):
    version=current_version()
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        row=conn.execute('SELECT t.user_id,t.question,s.plan,s.subtasks,s.report FROM tasks t JOIN task_state s USING(task_id) WHERE t.task_id=%s',(UUID(str(task_id)),)).fetchone()
        if not row or not row[4]:return []
        owner,question=row[:2];board=Board(plan=row[2],subtasks=row[3],report=row[4])
        conn.execute('SELECT user_id FROM users WHERE user_id=%s FOR UPDATE',(owner,))
        ids=[]
        for part in board.subtasks.values():
            for i,claim in enumerate(part.claims):
                if not any(d.claim_index==i and d.approved for d in part.review):continue
                if claim not in board.report.claims or not claim.evidence:continue
                refs=conn.execute('SELECT r.result_id,r.data_version,r.source_result_id FROM query_results r JOIN tasks t USING(task_id) WHERE r.result_id=ANY(%s) AND r.task_id=%s AND t.user_id=%s',
                    ([UUID(r) for r in claim.evidence],UUID(str(task_id)),owner)).fetchall()
                if len(refs)!=len(claim.evidence) or any(r[1]!=version or r[2] for r in refs):continue
                value={'text':claim.text,'value':claim.value,'question':question}
                key=hashlib.sha256(json.dumps([version,value],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                existing=conn.execute("SELECT memory_id FROM memories WHERE user_id=%s AND type='finding' AND key=%s AND superseded_at IS NULL",(owner,key)).fetchone()
                if existing:ids.append(str(existing[0]));continue
                vector=embed([question+'\n'+claim.text])[0]
                if lease_token:
                    from mcp_olist.leases import validate
                    validate(conn,task_id,lease_token,lock=True)
                ident=conn.execute("INSERT INTO memories(user_id,type,key,value,source_quote,evidence,data_version,embedding,embedding_model,embedding_revision,source_task_id) VALUES(%s,'finding',%s,%s,%s,%s,%s,%s::vector,%s,%s,%s) RETURNING memory_id",
                    (owner,key,Jsonb(value),claim.text,Jsonb(claim.evidence),version,json.dumps(vector),MODEL,REVISION,UUID(str(task_id)))).fetchone()[0]
                ids.append(str(ident))
        return ids


def retrieve(task_id,question,lease_token=None):
    version=current_version();threshold=float(os.getenv('FINDING_MIN_SIMILARITY','0.78'))
    if not 0<=threshold<=1:raise ValueError('Invalid finding similarity threshold')
    with psycopg.connect(**db_kwargs('agent','app')) as conn:
        owner=conn.execute('SELECT user_id FROM tasks WHERE task_id=%s',(UUID(str(task_id)),)).fetchone()
        if not owner:raise ValueError('Unknown task')
        exists=conn.execute("SELECT 1 FROM memories WHERE user_id=%s AND type='finding' AND superseded_at IS NULL LIMIT 1",(owner[0],)).fetchone()
        if not exists:return []
        vector=json.dumps(embed([question],query=True)[0])
        rows=conn.execute("SELECT memory_id,value,evidence,data_version,source_task_id,1-(embedding <=> %s::vector) AS similarity FROM memories WHERE user_id=%s AND type='finding' AND superseded_at IS NULL AND embedding_model=%s AND embedding_revision=%s AND vector_dims(embedding)=%s ORDER BY embedding <=> %s::vector,memory_id LIMIT 3",
            (vector,owner[0],MODEL,REVISION,len(json.loads(vector)),vector)).fetchall()
        if lease_token:
            from mcp_olist.leases import validate
            validate(conn,task_id,lease_token,states=('running','planning'),lock=True)
        found=[]
        for ident,value,evidence,old_version,source_task,similarity in rows:
            if similarity<threshold:continue
            item={'memory_id':str(ident),'similarity':similarity,'source_task_id':str(source_task),'data_version':old_version}
            if old_version!=version:
                # Do not expose the old conclusion, values, or result IDs to the model.
                found.append({**item,'status':'stale_clue','question':value['question'],'notice':'历史数据版本已过期，只能作为分析方向，必须重新查询。'})
                continue
            sources=conn.execute('SELECT r.result_id,r.sql,r.columns,r.rows,r.row_count,r.data_version FROM query_results r JOIN tasks t USING(task_id) WHERE r.result_id=ANY(%s) AND r.task_id=%s AND t.user_id=%s',
                ([UUID(ref) for ref in evidence],source_task,owner[0])).fetchall()
            if len(sources)!=len(evidence) or any(r[5]!=version for r in sources):continue
            imported=[]
            for ref,sql,columns,result_rows,count,data_version in sources:
                prior=conn.execute('SELECT result_id FROM query_results WHERE task_id=%s AND source_result_id=%s',(UUID(str(task_id)),ref)).fetchone()
                if prior:imported.append(str(prior[0]));continue
                copied=conn.execute('INSERT INTO query_results(task_id,sql,columns,rows,row_count,data_version,source_result_id) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING result_id',
                    (UUID(str(task_id)),sql,Jsonb(columns),Jsonb(result_rows),count,data_version,ref)).fetchone()[0]
                imported.append(str(copied))
            found.append({**item,'status':'current','claim':{'text':value['text'],'value':value['value'],'evidence':imported},
                'source_evidence':evidence,'question':value['question']})
        return found
