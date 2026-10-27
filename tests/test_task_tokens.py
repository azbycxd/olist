"""Task-bound MCP tokens: fixed algorithm, claims, role and lease fencing."""
import asyncio
import json
import time
from uuid import uuid4
import jwt
import pytest


KEY='scripted-mcp-signing-key-with-at-least-32-bytes'


def claims(**changes):
    return {'sub':str(uuid4()),'task_id':str(uuid4()),'lease_token':str(uuid4()),
            'roles':{'reviewer':['get_result','state_read','state_write']},'aud':'mcp-olist',
            'iat':int(time.time()),'exp':int(time.time())+300,'jti':str(uuid4()),**changes}


@pytest.mark.parametrize('changes,algorithm',[({'exp':int(time.time())-120},'HS256'),({'aud':'wrong'},'HS256'),({},'none')])
def test_invalid_task_token_rejected(monkeypatch,changes,algorithm):
    from mcp_olist.auth import decode
    monkeypatch.setenv('MCP_TOKEN_SECRET',KEY)
    token=jwt.encode(claims(**changes),KEY if algorithm!='none' else '',algorithm=algorithm)
    with pytest.raises((jwt.PyJWTError,ValueError)):decode(token)


def test_role_tokens_reject_sql_and_wrong_state_role():
    from mcp_olist.auth import authorize
    value=claims()
    assert authorize(value,'get_result',{})
    assert not authorize(value,'run_sql',{'sql':'SELECT 1'})
    assert not authorize(value,'state_write',{'role':'planner'})
    assert authorize(value,'state_write',{'role':'reviewer'})


def test_runtime_allowlist_removes_static_bearer(monkeypatch):
    from scripts.runtime import runtime_environment,RUNTIME_ENV
    monkeypatch.setenv('MCP_BEARER_TOKEN','must-not-cross-task-runtime')
    assert 'MCP_BEARER_TOKEN' not in RUNTIME_ENV
    assert 'MCP_BEARER_TOKEN' not in runtime_environment()


def test_signed_identity_overrides_headers_and_role_denial_is_http_403(monkeypatch):
    from mcp_olist import auth
    from mcp_olist.server import BearerAuth
    monkeypatch.setenv('MCP_TOKEN_SECRET',KEY)
    value=claims();seen=[]
    monkeypatch.setattr(auth,'validate_identity',lambda *_:None)
    async def app(scope,receive,send):
        seen.append(dict(scope['headers']))
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'{}'})
    token=jwt.encode(value,KEY,algorithm='HS256')
    async def call(tool,args):
        payload=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':tool,'arguments':args}}).encode()
        messages=[{'type':'http.request','body':payload,'more_body':False}];response=[]
        async def receive():return messages.pop(0)
        async def send(msg):response.append(msg)
        scope={'type':'http','method':'POST','path':'/mcp','headers':[(b'authorization',('Bearer '+token).encode()),(b'x-task-id',str(uuid4()).encode()),(b'x-lease-token',b'forged')]}
        await BearerAuth(app,'local-static-fixture-token-only')(scope,receive,send)
        return response[0]['status']
    assert asyncio.run(call('get_result',{}))==200
    assert seen[0][b'x-task-id'].decode()==value['task_id']
    assert seen[0][b'x-lease-token'].decode()==value['lease_token']
    assert asyncio.run(call('run_sql',{'sql':'SELECT 1'}))==403


def test_task_identity_validation_rejects_other_owner_and_lease(monkeypatch):
    from mcp_olist.auth import validate_identity
    from contextlib import contextmanager
    import mcp_olist.auth as auth
    value=claims()
    class Conn:
        def execute(self,*_):return self
        def fetchone(self):return (uuid4(),True)  # A different task owner.
    @contextmanager
    def connection(*_):yield Conn()
    monkeypatch.setattr(auth,'connection',connection)
    with pytest.raises(PermissionError):validate_identity(value)
