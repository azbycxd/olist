"""RLS plans must avoid nested protected tables; mappings remain transactional."""
import os
from uuid import uuid4
import pytest


def test_scope_mapping_is_not_a_model_table():
    from mcp_olist.sql_guard import guard_sql,UnsafeSQL
    with pytest.raises(UnsafeSQL):guard_sql('SELECT * FROM order_scope')


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='local database required')
def test_child_policy_plan_does_not_reenter_orders_or_customers():
    import psycopg
    from config import db_kwargs
    with psycopg.connect(**db_kwargs('olist','reader')) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL app.allowed_states='ALL'")
        plan=conn.execute('EXPLAIN (FORMAT JSON) SELECT count(*) FROM order_items').fetchone()[0][0]['Plan']
    def relations(node):
        return {node.get('Relation Name')} | set().union(*(relations(p) for p in node.get('Plans',[])))
    assert not ({'orders','customers'} & relations(plan)), 'RLS reenters protected parent tables'


@pytest.mark.integration
@pytest.mark.skipif(os.getenv('RUN_DB_TESTS')!='1',reason='isolated database required')
def test_mapping_tracks_import_updates_deletes_and_scope_changes():
    import psycopg
    from psycopg import sql
    from config import db_kwargs,ROOT
    from scripts.migrate import discover,LEDGER,apply_one
    name='test_scope_map_'+uuid4().hex
    with psycopg.connect(**db_kwargs('postgres'),autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            with psycopg.connect(**db_kwargs(name)) as conn:
                conn.execute(LEDGER);conn.commit()
                for m in discover(ROOT/'sql/migrations'):
                    if m.database=='olist':apply_one(conn,m)
                conn.execute("INSERT INTO data_imports(data_version,manifest) VALUES('source','{}')")
                conn.execute("INSERT INTO customers VALUES('sp','s','1','city','SP'),('rj','r','2','city','RJ')")
                # COPY is the real import path, and must populate the mapping.
                with conn.cursor().copy('COPY orders(order_id,customer_id,order_status,order_purchase_timestamp,order_estimated_delivery_date) FROM STDIN') as copy:
                    copy.write_row(('o-sp','sp','delivered','2018-01-01','2018-01-02'))
                    copy.write_row(('o-rj','rj','delivered','2018-01-01','2018-01-02'))
                conn.execute("INSERT INTO order_payments VALUES('o-sp',1,'credit_card',1,10),('o-rj',1,'credit_card',1,20)")
                assert conn.execute('SELECT * FROM order_scope ORDER BY order_id').fetchall()==[('o-rj','RJ'),('o-sp','SP')]
            with psycopg.connect(**db_kwargs(name,'reader')) as reader:
                # Force the same generic prepared plan to survive scope changes.
                reader.execute('SET LOCAL plan_cache_mode=force_generic_plan')
                reader.execute('PREPARE scoped AS SELECT order_id FROM order_payments ORDER BY order_id')
                for scope,expected in [('ALL',[('o-rj',),('o-sp',)]),('SP',[('o-sp',)]),('',[])]:
                    reader.execute(sql.SQL('SET LOCAL app.allowed_states={}').format(sql.Literal(scope)))
                    assert reader.execute('EXECUTE scoped').fetchall()==expected
                assert not reader.execute("SELECT has_table_privilege(current_user,'order_scope','INSERT,UPDATE,DELETE,TRUNCATE')").fetchone()[0]
            with psycopg.connect(**db_kwargs(name)) as conn:
                before=conn.execute('SELECT current_data_version()').fetchone()[0]
                conn.execute("UPDATE customers SET customer_state='MG' WHERE customer_id='sp'")
                assert conn.execute("SELECT customer_state FROM order_scope WHERE order_id='o-sp'").fetchone()[0]=='MG'
                assert conn.execute('SELECT current_data_version()').fetchone()[0]!=before
                conn.rollback()
                assert conn.execute('SELECT current_data_version()').fetchone()[0]==before
                conn.execute("UPDATE orders SET customer_id='rj' WHERE order_id='o-sp'")
                assert conn.execute("SELECT customer_state FROM order_scope WHERE order_id='o-sp'").fetchone()[0]=='RJ'
                conn.execute("DELETE FROM order_payments WHERE order_id='o-sp'")
                conn.execute("DELETE FROM orders WHERE order_id='o-sp'")
                assert not conn.execute("SELECT 1 FROM order_scope WHERE order_id='o-sp'").fetchone()
                conn.execute('TRUNCATE order_items,order_payments,order_reviews,orders,order_scope')
                assert conn.execute('SELECT count(*) FROM order_scope').fetchone()[0]==0
        finally:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
