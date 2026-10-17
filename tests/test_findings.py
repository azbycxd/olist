import os
from uuid import uuid4
import psycopg
import pytest
from psycopg.types.json import Jsonb
from config import db_kwargs
from scripts import findings
from agent.state import Plan,Board,Subtask,Decision
from contracts import Claim,FinalAnswer

pytestmark=pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='database integration opt-in')


def test_only_approved_findings_cross_sessions_and_old_version_is_clue(monkeypatch):
    monkeypatch.setattr(findings,'embed',lambda texts,query=False:[[1.,0.,0.] for _ in texts])
    version=findings.current_version()
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
        owner=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('finding-test-'+uuid4().hex,)).fetchone()[0]
        other=conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('finding-other-'+uuid4().hex,)).fetchone()[0]
        def task(user):return conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'same question','running') RETURNING task_id",(user,)).fetchone()[0]
        first,second,foreign=task(owner),task(owner),task(other)
        ref=conn.execute("INSERT INTO query_results(task_id,sql,columns,rows,row_count,data_version) VALUES(%s,'SELECT 42 AS n',%s,%s,1,%s) RETURNING result_id",(first,Jsonb(['n']),Jsonb([{'n':42}]),version)).fetchone()[0]
        good=Claim(text='reviewed finding',value={'n':42},evidence=[str(ref)])
        bad=Claim(text='rejected finding',value=99,evidence=[str(ref)])
        plan=Plan(subtasks=[{'id':'a','question':'q'}]);part=Subtask(question='q',depends_on=[],status='unverified',attempt=1,claims=[good,bad],review=[Decision(claim_index=0,approved=True,reason='ok'),Decision(claim_index=1,approved=False,reason='bad')])
        conn.execute('INSERT INTO task_state(task_id,plan,subtasks,report) VALUES(%s,%s,%s,%s)',(first,Jsonb(plan.model_dump()),Jsonb({'a':part.model_dump()}),Jsonb(FinalAnswer(answer='42',claims=[good]).model_dump())))
        ids=findings.save_reviewed(first)
        assert len(ids)==1 and findings.save_reviewed(first)==ids
        found=findings.retrieve(second,'same question')
        assert len(found)==1 and found[0]['status']=='current'
        copied=found[0]['claim']['evidence'][0]
        assert copied!=str(ref) and found[0]['source_evidence']==[str(ref)]
        assert findings.retrieve(second,'same question')[0]['claim']['evidence']==[copied]
        assert findings.retrieve(foreign,'same question')==[]
        # A real current-version boundary change, without altering the business data.
        monkeypatch.setattr(findings,'current_version',lambda:'next-import-version')
        stale=findings.retrieve(second,'same question')
        assert stale[0]['status']=='stale_clue' and 'claim' not in stale[0] and 'source_evidence' not in stale[0]
        assert set(stale[0])=={'memory_id','similarity','source_task_id','data_version','status','question','notice'}
        assert stale[0]['question']=='same question'
        assert 'reviewed finding' not in stale[0]['notice']
