"""Read-only dataset coverage and dimension existence checks before aggregation."""
import calendar
from datetime import date

import psycopg
from psycopg import sql
import sqlglot
from sqlglot import exp

from config import db_kwargs

DIMENSIONS = {
    'customer_state':'customers','customer_city':'customers',
    'seller_state':'sellers','seller_city':'sellers',
    'product_category_name':'products',
    'product_category_name_english':'product_category_name_translation',
    'order_status':'orders','payment_type':'order_payments',
}


def coverage(start, end):
    """Coverage is observed dates, never a claim of complete data ingestion."""
    if start is None or end is None:return {'available':False}
    first,last=start.date(),end.date()
    partial=[]
    if first.day!=1:partial.append(first.strftime('%Y-%m'))
    if last.day!=calendar.monthrange(last.year,last.month)[1]:partial.append(last.strftime('%Y-%m'))
    years=[y for y in range(first.year,last.year+1) if first<=date(y,1,1) and last>=date(y,12,31)]
    return {'available':True,'purchase_start':str(start),'purchase_end':str(end),
            'start_date':str(first),'end_date':str(last),'partial_edge_months':sorted(set(partial)),
            'calendar_years_fully_inside_observed_range':years,
            'notice':'Only observed purchase-date coverage; this does not prove ingestion completeness. Edge years/months are partial.'}


def data_context():
    with psycopg.connect(**db_kwargs(role='reader')) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        version=conn.execute('SELECT data_version FROM data_imports ORDER BY import_id DESC LIMIT 1').fetchone()[0]
        dates=conn.execute('SELECT min(order_purchase_timestamp),max(order_purchase_timestamp) FROM orders').fetchone()
        states=[r[0] for r in conn.execute('SELECT DISTINCT customer_state FROM customers ORDER BY customer_state').fetchall()]
    return {'data_version':version,'coverage':coverage(*dates),'customer_states':states,
            'dimensions':list(DIMENSIONS),'tool_limits':{'max_result_rows':1000,'preview_rows':20}}


def check_value(conn, column, value, transform=None):
    table=DIMENSIONS[column]
    expression=sql.Identifier(column)
    if transform:expression=sql.SQL('{}({})').format(sql.SQL(transform),expression)
    found=conn.execute(sql.SQL('SELECT 1 FROM public.{} WHERE {}=%s LIMIT 1').format(sql.Identifier(table),expression),(value,)).fetchone()
    return {'dimension':column,'value':value,'exists':bool(found)}


def check_dimension(column, value):
    if column not in DIMENSIONS or not isinstance(value,str) or not value or len(value)>300:
        raise ValueError('Choose a supported dimension and a bounded exact value')
    with psycopg.connect(**db_kwargs(role='reader')) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        item=check_value(conn,column,value)
    return {**item,**({} if item['exists'] else {'error':'unknown_dimension','missing':[item]}),
            'notice':'值存在仅说明维度字典有此值，不说明指定时间/组合有记录。' if item['exists'] else '未找到该值，请核对名称或代码；不能把未知维度表述为零。'}


def dimension_filters(statement):
    """Exact literal filters only. LIKE discovery and null tests stay available."""
    tree=sqlglot.parse_one(statement,read='postgres');checks=[]
    aliases={t.alias_or_name:t.name for t in tree.find_all(exp.Table)}
    for predicate in tree.walk():
        if isinstance(predicate,exp.EQ):pairs=[(predicate.this,predicate.expression),(predicate.expression,predicate.this)]
        elif isinstance(predicate,exp.In) and not predicate.args.get('query'):pairs=[(predicate.this,v) for v in predicate.expressions]
        else:continue
        for left,right in pairs:
            transform=None
            if isinstance(left,(exp.Lower,exp.Upper)):
                transform='LOWER' if isinstance(left,exp.Lower) else 'UPPER';left=left.this
            if not isinstance(left,exp.Column) or left.name not in DIMENSIONS or not isinstance(right,exp.Literal) or not right.is_string:continue
            # A derived CTE may deliberately label an absent bucket. Do not
            # mistake it for a physical dimension with the same output name.
            if left.table and aliases.get(left.table) not in {DIMENSIONS[left.name],
                    'product_category_name_translation' if left.name=='product_category_name' else DIMENSIONS[left.name]}:continue
            check=(left.name,right.this,transform)
            if check not in checks:checks.append(check)
    return checks


def validate_filters(conn, statement):
    checks=[check_value(conn,*item) for item in dimension_filters(statement)]
    missing=[c for c in checks if not c['exists']]
    return checks,missing
