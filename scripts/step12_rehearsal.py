"""HTTP model double through the real evaluator, MCP, PostgreSQL and gold checker."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from uuid import uuid4


def response_message(body):
    if body.get('response_format'):
        return {'role':'assistant','content':json.dumps({'preferences':[]})}
    has_sql=any(m.get('role')=='tool' and 'result_id' in (m.get('content') or '') for m in body.get('messages',[]))
    actions=[('final_answer',{'answer':'替身演练完成','claims':[]})] if has_sql else [
        ('run_sql',{'sql':'SELECT 42 AS value'}),('run_sql',{'sql':'SELECT 43 AS value'})]
    return {'role':'assistant','content':None,'tool_calls':[
        {'id':uuid4().hex,'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}} for name,args in actions]}


def validate_rehearsal(rows,ids,sql_events):
    if len(rows)!=31 or [r['question_id'] for r in rows]!=ids:
        raise ValueError('Rehearsal must complete all 31 selected dev cases')
    if any(r.get('error') or r.get('termination')!='final_answer' for r in rows):
        raise ValueError('Rehearsal contains engineering failures')
    if any(sql_events.get(r['task_id'],0)<2 for r in rows):
        raise ValueError('Each rehearsal case must persist parallel MCP SQL execution events')


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=1)
    attempt=parser.parse_args().attempt
    suffix='' if attempt==1 else f'_attempt{attempt}'
    root=Path(__file__).resolve().parents[1]
    with (root/f'evidence/step12_rehearsal{suffix}_started.json').open('x') as stream:
        json.dump({'kind':'模型替身；不是成绩'},stream,ensure_ascii=False)
    # Load .env credentials, then remove provider aliases before importing evaluator/config.
    import config
    frozen=json.loads((root/'evidence/step12_regression_protocol.json').read_text())
    os.environ.update(frozen['config'])
    for key in ('DEEPSEEK_MODEL','DEEPSEEK_BASE_URL','DEEPSEEK_API_KEY'):
        os.environ.pop(key,None)
    os.environ['OLIST_LOAD_DOTENV']='0'
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            message=response_message(body)
            calls.append({'path':self.path,'json_mode':bool(body.get('response_format'))})
            data=json.dumps({'id':'rehearsal-'+uuid4().hex,'object':'chat.completion','created':0,'model':'step12-http-double',
                'choices':[{'index':0,'finish_reason':'tool_calls' if 'tool_calls' in message else 'stop','message':message}],
                'usage':{'prompt_tokens':900,'prompt_cache_hit_tokens':0,'completion_tokens':100,'total_tokens':1000}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    os.environ.update(OPENAI_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',OPENAI_MODEL='step12-http-double')
    from eval.robustness import start_private_mcp
    from eval.run import execute
    process,url=start_private_mcp();os.environ['MCP_URL']=url
    try:
        summary=execute(SimpleNamespace(adapter='single',judge='off',categories=['C','D','E'],split='dev',
            tag='step12-v2-rehearsal-model-double-not-score'+suffix,schema_mode='on_demand',context_strategy='none',
            context_limit=16000,context_summary_threshold=6000,rag_mode='inject',use_memory='true',
            agent_mode='single',number_gate='true',token_budget=100000,question_ids=None,user_group=None))
    finally:
        process.terminate()
        try:process.wait(timeout=30)
        except Exception:process.kill();process.wait()
        server.shutdown();server.server_close()
    import psycopg
    ids=[r['task_id'] for r in summary['cases']]
    with psycopg.connect(**config.db_kwargs('agent','app')) as conn:
        counts={str(task):n for task,n in conn.execute("SELECT task_id,count(*) FROM events WHERE task_id=ANY(%s::uuid[]) AND type='sql_execution' GROUP BY task_id",(ids,))}
    report={'kind':'模型替身；替身演练，不是成绩','real_model_calls':0,'planned':31,'completed':len(summary['cases']),
        'engineering_errors':[{'id':r['question_id'],'error':r['error']} for r in summary['cases'] if r.get('error')],
        'http_requests':len(calls),'sql_execution_events':counts,'gold_checker':'unchanged eval.run.execute, execute_gold, check, score',
        'source_log':'logs/'+summary['source_log'],'source_log_sha256':summary['source_log_sha256'],
        'source_receipt':'evidence/'+summary['source_log'].replace('.jsonl','.summary.json'),
        'source_receipt_sha256':hashlib.sha256((root/'evidence'/summary['source_log'].replace('.jsonl','.summary.json')).read_bytes()).hexdigest(),
        'cases':[{'id':r['question_id'],'task_id':r['task_id'],'error':r.get('error'),'termination':r.get('termination')} for r in summary['cases']]}
    (root/f'evidence/step12_rehearsal{suffix}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    validate_rehearsal(summary['cases'],frozen['question_ids'],counts)
    print(json.dumps({'kind':report['kind'],'completed':report['completed'],'engineering_errors':len(report['engineering_errors']),'http_requests':len(calls)},ensure_ascii=False))


if __name__=='__main__':main()
