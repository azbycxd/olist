import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from agent.preferences import grounded
from api.memories import app,issue
from scripts.preferences import save,list_active
from config import db_kwargs


def test_quote_grounding_and_no_model_invented_value():
    items=[{'key':'default_state','source_quote':'以后默认看 SP 州。'}]
    assert grounded(items,'以后默认看 SP 州。')[0]['value']=='以后默认看 SP 州。'
    with pytest.raises(ValueError): grounded(items,'请看 RJ 州。')
    with pytest.raises(ValueError): grounded(items*2,'以后默认看 SP 州。')
    with pytest.raises(ValueError): grounded([{'key':'default_state','source_quote':'查看 SP 州。'}],'查看 SP 州。')


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='requires database')
def test_memory_supersession_isolation_and_authenticated_delete(monkeypatch):
    monkeypatch.setenv('MEMORY_API_SECRET','test-only-secret-with-more-than-32-characters')
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
        users=[conn.execute('INSERT INTO users(username) VALUES(%s) RETURNING user_id',('memory-test-'+str(uuid4()),)).fetchone()[0] for _ in range(2)]
        task=conn.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,'test','running') RETURNING task_id",(users[0],)).fetchone()[0]
        try:
            first=save(task,[{'key':'default_state','source_quote':'以后默认 SP。'}],'以后默认 SP。')[0]
            second=save(task,[{'key':'default_state','source_quote':'以后默认 RJ。'}],'以后默认 RJ。')[0]
            assert first!=second and list_active(users[0])[0]['source_quote']=='以后默认 RJ。'
            assert conn.execute('SELECT superseded_at FROM memories WHERE memory_id=%s',(first,)).fetchone()[0] is not None
            assert list_active(users[1])==[]
            client=TestClient(app)
            assert client.get('/memories').status_code==401
            assert client.get('/memories',headers={'Authorization':'Bearer invalid'}).status_code==401
            other={'Authorization':'Bearer '+issue(users[1])}
            owner={'Authorization':'Bearer '+issue(users[0])}
            assert client.delete('/memories/'+second,headers=other).status_code==404
            assert client.get('/memories',headers=owner).json()['memories'][0]['memory_id']==second
            assert client.delete('/memories/'+second,headers=owner).status_code==204
            assert client.get('/memories',headers=owner).json()['memories']==[]
        finally:
            conn.execute('DELETE FROM memories WHERE user_id=ANY(%s)',(users,))
            conn.execute('DELETE FROM tasks WHERE task_id=%s',(task,))
            conn.execute('DELETE FROM users WHERE user_id=ANY(%s)',(users,))
