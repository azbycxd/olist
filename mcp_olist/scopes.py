"""Trusted scope lookup, transaction-local RLS context and conservative precheck."""
from uuid import UUID
import sqlglot
from sqlglot import exp
from psycopg import sql
from db_pool import connection

PROTECTED={'customers','orders','order_items','order_payments','order_reviews'}


def task_scope(task_id,component='mcp'):
    with connection(component) as conn:
        row=conn.execute('SELECT u.data_scope FROM users u JOIN tasks t USING(user_id) WHERE t.task_id=%s',(UUID(str(task_id)),)).fetchone()
    if not row:raise ValueError('Unknown task')
    return row[0]


def current_scope():
    from mcp_olist.auth import IDENTITY
    identity=IDENTITY.get()
    if not identity:return []
    with connection('mcp') as conn:
        row=conn.execute('SELECT data_scope FROM users WHERE user_id=%s',(identity['sub'],)).fetchone()
    return row[0] if row else []


def apply_scope(conn,states):
    conn.execute(sql.SQL('SET LOCAL app.allowed_states = {}').format(sql.Literal(','.join(states))))


def forbidden():
    return {'error':'forbidden_dimension','notice':'无权限查询该州或全国范围；请在WHERE中明确限定有权限的customer_state。'}


def check_sql(statement,states):
    if states==['ALL']:return None
    tree=sqlglot.parse_one(statement,read='postgres')
    if not states:return forbidden()
    from mcp_olist.boundaries import dimension_filters
    values=[v.upper() for col,v,_ in dimension_filters(statement) if col in {'customer_state','seller_state'}]
    if any(v not in states for v in values):return forbidden()
    if not any(t.name in PROTECTED for t in tree.find_all(exp.Table)):return None
    # Fail closed for ambiguous broad scopes. RLS independently enforces rows.
    # A positive customer-state filter must occur in WHERE; OR/NOT cannot prove
    # that the requested population is limited to the permitted states.
    for select in tree.find_all(exp.Select):
        tables=[t for t in select.find_all(exp.Table) if t.find_ancestor(exp.Select) is select]
        if not any(t.name in PROTECTED for t in tables):continue
        where=select.args.get('where')
        if where is None or any(isinstance(n,(exp.Or,exp.Not)) for n in where.walk()):return forbidden()
        aliases={t.alias_or_name for t in tables if t.name=='customers'}
        allowed=False
        for node in where.walk():
            if isinstance(node,exp.EQ):pairs=[(node.this,node.expression),(node.expression,node.this)]
            elif isinstance(node,exp.In) and not node.args.get('query'):pairs=[(node.this,v) for v in node.expressions]
            else:continue
            if any(isinstance(c,exp.Column) and c.name=='customer_state' and
                   (c.table in aliases or not c.table and aliases) and
                   isinstance(v,exp.Literal) and v.is_string and v.this.upper() in states for c,v in pairs):allowed=True
        if not allowed:return forbidden()
    return None
