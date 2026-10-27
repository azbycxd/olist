"""Task JWT signing in trusted parents and verification in MCP; never in Agent."""
from contextvars import ContextVar
from datetime import datetime,timezone
import os
from uuid import UUID,uuid4
import jwt
from db_pool import connection
from config import MCP_TOKEN_CLOCK_SKEW_SECONDS,mcp_token_secret

IDENTITY=ContextVar('mcp_identity',default=None)
BUSINESS=['list_tables','describe_table','run_sql','get_result','search_knowledge','data_context','check_dimension']
ROLE_TOOLS={
    'agent':BUSINESS,
    'orchestrator':[x for x in BUSINESS if x!='run_sql']+['state_read'],
    'planner':['list_tables','describe_table','search_knowledge','data_context','check_dimension','state_read','state_write'],
    'analyst':BUSINESS+['state_read','state_write'],
    'reviewer':['get_result','state_read','state_write'],
    'writer':['get_result','state_read','state_write'],
}


def issue_tokens(owner,task_id,lease_token,deadline,mode='single'):
    roles=['agent'] if mode=='single' else ['orchestrator','planner','analyst','reviewer','writer']
    now=int(datetime.now(timezone.utc).timestamp())
    return {role:jwt.encode({'sub':str(owner),'task_id':str(task_id),
        'lease_token':str(lease_token) if lease_token else '','roles':{role:ROLE_TOOLS[role]},
        'aud':'mcp-olist','exp':int(deadline.timestamp()),'iat':now,'jti':str(uuid4())},
        mcp_token_secret(),algorithm='HS256') for role in roles}


def decode(token):
    value=jwt.decode(token,mcp_token_secret(),algorithms=['HS256'],audience='mcp-olist',
        leeway=MCP_TOKEN_CLOCK_SKEW_SECONDS,options={'require':['sub','task_id','lease_token','roles','aud','exp','iat','jti'],'strict_aud':True})
    for key in ('sub','task_id','jti'):UUID(value[key])
    if value['lease_token']:UUID(value['lease_token'])
    roles=value['roles']
    if not isinstance(roles,dict) or len(roles)!=1:raise ValueError('Exactly one role per token')
    for role,tools in roles.items():
        if role not in ROLE_TOOLS or not isinstance(tools,list) or not tools or not all(isinstance(t,str) for t in tools) or not set(tools)<=set(ROLE_TOOLS[role]):
            raise ValueError('Invalid tool scope')
    return value


def authorize(value,tool,arguments):
    roles=value['roles']
    if not isinstance(arguments,dict):return False
    return any(tool in tools for tools in roles.values()) and (tool!='state_write' or arguments.get('role') in roles)


def validate_identity(value):
    from mcp_olist.leases import validate
    with connection('mcp') as conn:
        row=conn.execute('SELECT user_id,background FROM tasks WHERE task_id=%s',(value['task_id'],)).fetchone()
        if not row or str(row[0])!=value['sub']:raise PermissionError('Task owner mismatch')
        if row[1] and not value['lease_token']:raise PermissionError('Background task requires a lease')
        try:validate(conn,value['task_id'],value['lease_token'],states=('running','planning'))
        except ValueError as exc:raise PermissionError('Task lease is no longer valid') from exc


def static_identity(headers):
    ident=headers.get(b'x-task-id',b'').decode()
    if not ident:return None  # Health/discovery has no task identity.
    with connection('mcp') as conn:
        row=conn.execute('SELECT user_id,background FROM tasks WHERE task_id=%s',(str(UUID(ident)),)).fetchone()
    if not row:return None  # Tool-specific task checks still reject nonexistent tasks.
    if row[1]:raise PermissionError('Static token is restricted to local foreground CLI/evaluation')
    return {'sub':str(row[0]),'task_id':ident,'lease_token':None,'static':True}
