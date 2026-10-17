"""Two real sessions for a predeclared five-question dev subset."""
import hashlib
from argparse import Namespace
from uuid import uuid4
import psycopg
from config import ROOT,db_kwargs
from scripts.common import start_log,record
from scripts.evidence import write_evidence


def execute_reuse(args,execute):
    logger,path=start_log('eval_'+args.tag)
    group='finding-'+uuid4().hex
    ids='D01,D02,D03,D04,D05'
    record(logger,'protocol',questions=ids.split(','),sessions=2,threshold=.78,
        note='First five D dev IDs chosen before runs; same owner per pair, independent tasks. No holdout.')
    settings={**vars(args),'categories':['D'],'question_ids':ids,'split':'dev','user_group':group,
        'adapter':'single','agent_mode':'multi','number_gate':'true','use_memory':'true','rag_mode':'inject',
        'judge':'model','context_limit':16000,'context_summary_threshold':6000,'context_strategy':'none','token_budget':100000}
    first=execute(Namespace(**{**settings,'tag':args.tag+'-first'}))
    second=execute(Namespace(**{**settings,'tag':args.tag+'-second'}))
    pairs=[]
    for a,b in zip(first['cases'],second['cases']):
        assert a['question_id']==b['question_id'] and a['user_id']==b['user_id'] and a['task_id']!=b['task_id']
        at=a['agent_usage']['total_tokens'];bt=b['agent_usage']['total_tokens']
        pairs.append({'question_id':a['question_id'],'first_task':a['task_id'],'second_task':b['task_id'],
            'first_steps':a.get('steps'),'second_steps':b.get('steps'),
            'first_sql_calls':a.get('sql_calls',0),'second_sql_calls':b.get('sql_calls',0),
            'first_agent_tokens':at,'second_agent_tokens':bt,'token_reduction':at-bt if at is not None and bt is not None else None,
            'first_correct':a['correct'],'second_correct':b['correct'],
            'first_fact_hits':a['fact_hits'],'second_fact_hits':b['fact_hits'],'fact_total':a['fact_total'],
            'first_agent_latency_ms':a.get('agent_latency_ms'),'second_agent_latency_ms':b.get('agent_latency_ms'),
            'reuse_events':[e for e in b.get('finding_events',[]) if e['event']=='finding_reused']})
    # Exercise the actual version lookup with an inserted, deliberately changed version.
    # Restore the temporary committed metadata marker in finally; business rows never change.
    # Holding the shared evaluation lock avoids overlapping evaluators during this boundary test.
    from scripts import findings
    from psycopg.types.json import Jsonb
    import os
    stale=[]
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as agent_conn:
        if not agent_conn.execute('SELECT pg_try_advisory_lock(730018)').fetchone()[0]:raise ValueError('Another evaluation is running')
        with psycopg.connect(**db_kwargs(),autocommit=True) as business:
            # Test metadata row is committed so independent runtime connections see it.
            old=findings.current_version();changed='version-test-'+uuid4().hex
            marker=business.execute('INSERT INTO data_imports(data_version,manifest) VALUES(%s,%s) RETURNING import_id',(changed,Jsonb({'test':'reviewed-finding-expiry','original':old}))).fetchone()[0]
            try:
                for case in second['cases']:
                    # Use the exact saved source question to ensure the semantic match is exercised.
                    question=agent_conn.execute('SELECT question FROM tasks WHERE task_id=%s',(case['task_id'],)).fetchone()[0]
                    items=findings.retrieve(case['task_id'],question)
                    assert all(i['status']=='stale_clue' and 'claim' not in i and 'source_evidence' not in i for i in items)
                    stale.append({'question_id':case['question_id'],'matched':len(items),'items':items})
                if not any(x['matched'] for x in stale):raise AssertionError('Expiry test did not match any finding')
            finally:business.execute('DELETE FROM data_imports WHERE import_id=%s AND data_version=%s',(marker,changed))
            assert findings.current_version()==old
    summary={'pairs':pairs,'version_test':{'restored':True,'cases':stale},'threshold':.78,
        'embedding':first['embedding'],'sources':[first['source_log'],second['source_log']],'source_log':path.name,
        'code_sha256':first['code_sha256']}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    lines=['# 已审核结论跨会话复用','',f"真实运行日志：`{path.name}`；[证据](../evidence/{receipt.name})。",
        '', '| 题号 | 首次 / 再次步骤 | 首次 / 再次 SQL 调用 | 首次 / 再次 Agent token | 首次 / 再次事实命中 | 首次 / 再次正确 |', '| --- | --- | --- | --- | --- | --- |']
    for p in pairs:
        tokens=' / '.join('' if p[k] is None else str(p[k]) for k in ['first_agent_tokens','second_agent_tokens'])
        lines.append(f"| {p['question_id']} | {p['first_steps']} / {p['second_steps']} | {p['first_sql_calls']} / {p['second_sql_calls']} | {tokens} | {p['first_fact_hits']} / {p['second_fact_hits']}（分母 {p['fact_total']}） | {p['first_correct']} / {p['second_correct']} |")
    lines+=['','步骤为编排阶段实际模型调用次数，不含离线评分和结束时偏好抽取；SQL 调用另列；未知 token 留空，不能据此计算下降。历史结论不足时仍查 SQL，不能强制复用。',
        '', '数据版本测试临时插入新的导入版本记录，验证独立读取连接只返回 stale_clue，随后移除测试记录并核对恢复；业务原始行未改动。','',
        *[f"- `{r['source_log']}` → [逐题证据](../evidence/{r['source_log'].removesuffix('.jsonl')}.summary.json)" for r in [first,second]]]
    (ROOT/'docs/FINDING_REUSE.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Reuse evidence:',receipt.name)
