"""New Step13 runner: real evaluator/runtime, independent users and sealed trials.

Rehearsal replaces only the HTTP model endpoint. No edits to existing entrypoints.
"""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import subprocess
import threading
from time import perf_counter
from types import SimpleNamespace
from uuid import uuid4

from eval.step13_errors import ROOT,read,write as write_json,sha
from eval.step13_trials import (workload,paths,configuration,source_hashes,measured_usage,
    summarize_trials,validate_rehearsal,verify_protocol,claim_once)


def write(path, value):
    # PostgreSQL oracle values may contain Decimal/date values. Preserve their
    # exact spelling in receipts; scoring already used the original objects.
    write_json(path,json.loads(json.dumps(value,ensure_ascii=False,default=str)))


def model_double():
    from scripts.step12_rehearsal import response_message
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            message=response_message(body);calls.append({'json_mode':bool(body.get('response_format'))})
            if body.get('response_format') and any('以后统计销售额时，只计入delivered订单的商品金额，不含运费。' in (m.get('content') or '') for m in body.get('messages',[]) if m.get('role')=='user'):
                message={'role':'assistant','content':json.dumps({'preferences':[{'key':'sales_amount_definition',
                    'source_quote':'以后统计销售额时，只计入delivered订单的商品金额，不含运费。'}]},ensure_ascii=False)}
            if (not body.get('response_format') and message.get('tool_calls') and
                message['tool_calls'][0]['function']['name']=='run_sql' and
                any(m.get('role')=='user' and '评论文字样例' in (m.get('content') or '') for m in body.get('messages',[]))):
                message['tool_calls'].append({'id':uuid4().hex,'type':'function','function':
                    {'name':'describe_table','arguments':json.dumps({'name':'order_reviews'})}})
            payload={'id':'step13-double-'+uuid4().hex,'object':'chat.completion','created':0,'model':'step13-http-double',
                'choices':[{'index':0,'finish_reason':'tool_calls' if 'tool_calls' in message else 'stop','message':message}],
                'usage':{'prompt_tokens':900,'prompt_cache_hit_tokens':0,'completion_tokens':100,'total_tokens':1000}}
            data=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    for name in ('DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','DEEPSEEK_MODEL'):os.environ.pop(name,None)
    os.environ.update(OLIST_LOAD_DOTENV='0',OPENAI_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',
        OPENAI_MODEL='step13-http-double',SMALL_MODEL='step13-http-double')
    return server,calls


def run_cases(questions,tag):
    """New source-file support around unchanged adapter/checker/scorer."""
    import psycopg
    from psycopg.types.json import Jsonb
    from config import db_kwargs
    from contracts import FinalAnswer
    from eval.adapters import make_adapter,public_case
    from eval.dataset import execute_gold
    from eval.checker import DatabaseEvidence,check
    from eval.scoring import score
    from scripts.common import start_log,record
    from api.tasks import event
    logger,path=start_log('eval_'+tag);results=[]
    adapter=make_adapter('single')
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as db, psycopg.connect(**db_kwargs(role='reader')) as oracle:
        if not db.execute('SELECT pg_try_advisory_lock(730018)').fetchone()[0]:raise RuntimeError('Another evaluation is running')
        oracle.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        oracle.execute("SET LOCAL app.allowed_states='ALL'")
        version=oracle.execute('SELECT current_data_version()').fetchone()[0]
        gold={q['id']:execute_gold(oracle,q)[0] for q in questions if q.get('gold_sql')}
        for q in questions:
            uid=db.execute("INSERT INTO users(username,data_scope) VALUES(%s,ARRAY['ALL']) RETURNING user_id",('step13-'+uuid4().hex,)).fetchone()[0]
            setup=None
            if q.get('setup_turns'):
                setup=db.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,%s,'running') RETURNING task_id",(uid,'\n'.join(q['setup_turns']))).fetchone()[0]
            tid=db.execute("INSERT INTO tasks(user_id,question,status) VALUES(%s,%s,'running') RETURNING task_id",(uid,q['question'])).fetchone()[0]
            row={'question_id':q['id'],'category':q['category'],'task_id':str(tid),'user_id':str(uid),
                'setup_task_id':str(setup) if setup else None,'events':[],
                'pair_id':q.get('pair_id'),'side':q.get('side'),'success_kind':q.get('success_kind')}
            def emit(kind,payload,tokens=0,latency_ms=0):
                record(logger,kind,question_id=q['id'],task_id=str(tid),payload=payload,tokens=tokens,latency_ms=latency_ms)
                event(db,tid,kind,payload,tokens,latency_ms)
                row['events'].append({'type':kind,'payload':payload})
                if kind=='termination' and payload.get('scope')=='task':row['termination']=payload['reason']
            started=perf_counter();fixture_process=None;fixture_log=None;original_url=os.environ.get('MCP_URL')
            try:
                if q.get('comment_fixture'):
                    from eval.step13_comment_fixture import start_process,transform
                    fixture_process,url,fixture_log=start_process(q['comment_fixture'],tag+'-'+q['id'])
                    os.environ['MCP_URL']=url
                response=FinalAnswer.model_validate(adapter.run(public_case(q,uid,setup,tid),emit))
                fetch=DatabaseEvidence(db)
                if q.get('comment_fixture'):
                    original_fetch=fetch
                    def fetch(ids):
                        # Project exactly the same synthetic text into the audit
                        # view; original persisted SQL results remain untouched.
                        return {key:{**value,'rows':transform(value['rows'],q['comment_fixture'])[0]}
                                for key,value in original_fetch(ids).items()}
                audit=check(response,fetch,str(tid),version)
                row.update(response=response.model_dump(),evidence=audit)
                if q.get('success_kind'):
                    from eval.step13_pairs import grade
                    deliveries=[json.loads(line) for line in fixture_log.read_text(encoding='utf-8').splitlines()] if fixture_log and fixture_log.exists() else []
                    if fixture_log:
                        row['comment_fixture']={'mode':q['comment_fixture'],'deliveries':deliveries,
                            'source_log':fixture_log.relative_to(ROOT).as_posix(),'sha256':sha(fixture_log) if fixture_log.exists() else None,
                            'audit_projection':'same transformed comment text as model tool view; business DB and original query_results unchanged'}
                    row.update(grade(q,response,gold.get(q['id']),audit,row.get('termination'),row['events'],exposed=bool(deliveries)))
                else:row.update(score(q,response,gold[q['id']],audit))
                if row.get('termination')!='final_answer':row['error']=row.get('termination','missing_termination')
            except Exception as exc:
                row.update(correct=False,error=type(exc).__name__,engineering_error=True,
                    evidence={'unsupported_claims':0,'unsupported_numbers':0})
            finally:
                if original_url:os.environ['MCP_URL']=original_url
                if fixture_process:
                    fixture_process.terminate()
                    try:fixture_process.wait(timeout=20)
                    except subprocess.TimeoutExpired:fixture_process.kill();fixture_process.wait()
            row['latency_ms']=(perf_counter()-started)*1000
            for task in (tid,setup):
                if task:db.execute('UPDATE tasks SET status=%s,result=%s,error=%s,updated_at=now() WHERE task_id=%s',
                    ('failed' if row.get('error') else 'completed',Jsonb(row.get('response')),row.get('error'),task))
            row['saved_results']=[{'result_id':str(r[0]),'sql':r[1],'rows':r[2],'data_version':r[3]} for r in db.execute(
                'SELECT result_id,sql,rows,data_version FROM query_results WHERE task_id=%s ORDER BY created_at',(tid,))]
            record(logger,'eval_result',**row);results.append(row)
    report={'tag':tag,'cases':results,'data_version':version,'oracle_values':gold,
        'source_log':path.name,'source_log_sha256':sha(path)}
    write(ROOT/'evidence'/(path.stem+'.summary.json'),report)
    return report


def normalize(summary,repeat,prices):
    import psycopg
    from config import db_kwargs
    result=[]
    with psycopg.connect(**db_kwargs('agent','app')) as db:
        db.execute('SET TRANSACTION READ ONLY')
        for row in summary['cases']:
            events=db.execute('SELECT type,payload FROM events WHERE task_id=%s ORDER BY seq',(row['task_id'],)).fetchall()
            usages=[payload.get('usage') for kind,payload in events if kind=='model_call']
            audit=row.get('evidence',{})
            result.append({**row,'id':row['question_id'],'repeat':repeat,
                'strict_pass':row['correct'] and audit.get('unsupported_claims')==0 and audit.get('unsupported_numbers')==0,
                'sql_events':sum(kind=='sql_execution' for kind,_ in events),
                'elapsed_ms':row['latency_ms'],**measured_usage(usages,prices)})
    return result


def run(suite,rehearsal=False):
    import config
    p=paths(suite);questions=workload(suite);os.environ.update(configuration(),SCHEMA_MODE='on_demand')
    if rehearsal:
        if p['rehearsal'].exists():raise FileExistsError('Rehearsal receipt exists; preserve it')
        marker=p['rehearsal'].with_name(p['rehearsal'].stem+'_started.json')
        claim_once(marker,'model-double','not-a-score')
        server,requests=model_double();prices={k:0 for k in ('TOKEN_PRICE_INPUT','TOKEN_PRICE_CACHED_INPUT','TOKEN_PRICE_OUTPUT')}
        commit=None
    else:
        protocol,commit,prices=verify_protocol(suite)
        server=None;requests=[]
        claim_once(p['started'],commit,sha(p['protocol']))
    from eval.robustness import start_private_mcp
    process,url=start_private_mcp();os.environ['MCP_URL']=url
    all_rows=[];sources=[];engineering=[];started=perf_counter()
    output=p['rehearsal'] if rehearsal else p['results']
    try:
        for repeat in range(1,4):
            tag=f'step13-{suite}-'+('rehearsal-not-score' if rehearsal else 'once')+f'-r{repeat}'
            if suite=='dev':
                from eval.run import execute
                summary=execute(SimpleNamespace(adapter='single',judge='off',categories=list('ABCDE'),split='dev',
                    tag=tag,schema_mode='on_demand',context_strategy='none',context_limit=16000,context_summary_threshold=6000,
                    rag_mode='inject',use_memory='true',agent_mode='single',number_gate='true',token_budget=100000,
                    question_ids=None,user_group=None))
            else:summary=run_cases(questions,tag)
            rows=normalize(summary,repeat,prices);all_rows.extend(rows)
            if rehearsal and suite in {'paired','capability'}:
                for row in rows:
                    if row['id'].startswith('P04') and not any(e['type']=='memory_read' and e['payload'].get('count',0)>0 for e in row.get('events',[])):
                        engineering.append({'id':row['id'],'repeat':repeat,'error':'rehearsal_preference_not_loaded'})
                    if row['id'].startswith('P06') and not row.get('comment_fixture',{}).get('deliveries'):
                        engineering.append({'id':row['id'],'repeat':repeat,'error':'rehearsal_comment_not_exposed'})
            sources.append({'receipt':'evidence/'+summary['source_log'].replace('.jsonl','.summary.json'),
                'log':'logs/'+summary['source_log'],'log_sha256':summary['source_log_sha256']})
            engineering.extend({'id':r['id'],'repeat':repeat,'error':r.get('error')} for r in rows if
                (rehearsal and (r.get('error') or r.get('termination')!='final_answer' or r['sql_events']<2)) or
                (not rehearsal and r.get('error') in {'RuntimeError','ValueError','TypeError','KeyError','OSError','missing_termination'}))
            write(output.with_name(output.stem+'_partial.json'),{'cases':all_rows,'sources':sources,'engineering_errors':engineering})
            if engineering:raise RuntimeError('Engineering failure; preserve partial receipt and stop; no automatic rerun')
        report={'kind':'模型替身；替身演练，不是成绩' if rehearsal else '真实模型；预注册三次试验，不重跑',
            'suite':suite,'cases':all_rows,'sources':sources,'source_hashes':source_hashes(),
            'engineering_errors':engineering,'protocol_commit':commit,'configuration':configuration(),
            'pricing_yuan_per_million':prices,'elapsed_seconds':perf_counter()-started,
            'real_model_calls':0 if rehearsal else sum(r['model_calls'] for r in all_rows),
            'http_double_requests':len(requests) if rehearsal else None,**summarize_trials(all_rows)}
        if len({r['user_id'] for r in all_rows})!=len(all_rows):raise ValueError('Users reused across trials')
        write(output,report)
        if rehearsal:validate_rehearsal(report,[q['id'] for q in questions])
        print(json.dumps({'suite':suite,'rehearsal':rehearsal,'completed':len(all_rows),'engineering_errors':len(engineering),
            'overall':report['overall']},ensure_ascii=False))
    finally:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        if server:server.shutdown();server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--suite',choices=['dev','supplement','paired'],required=True)
    parser.add_argument('--rehearsal',action='store_true');args=parser.parse_args();run(args.suite,args.rehearsal)
