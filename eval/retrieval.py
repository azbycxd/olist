"""Retrieval-only measurements invoked exclusively through eval/run.py."""
import hashlib
import json
from pathlib import Path

import psycopg
from config import ROOT,db_kwargs
from eval.dataset import load_questions,QUESTION_FILE
from mcp_olist.knowledge import search,MODEL,REVISION
from mcp_olist.embedding_config import provenance
from scripts.common import start_log,record
from scripts.evidence import write_evidence


def execute_retrieval(args,header):
    labels=json.loads((ROOT/'eval/retrieval_labels.json').read_text(encoding='utf-8'))
    questions=[q for q in load_questions() if q['category']=='C' and q['split']==args.split]
    logger,path=start_log('eval_'+args.tag)
    rows=[]
    embedding=provenance(used=True)
    record(logger,'retrieval_started',embedding=embedding)
    with psycopg.connect(**db_kwargs('agent','app'),autocommit=True) as conn:
        if not conn.execute('SELECT pg_try_advisory_lock(730018)').fetchone()[0]: raise ValueError('Another evaluation is running')
        for q in questions:
            expected=set(labels[q['id']]); row={'question_id':q['id'],'expected':sorted(expected),'methods':{}}
            for method in ('bm25','vector','hybrid','weighted'):
                found=search(q['question'],method)['chunks'];ids=[c['chunk_id'] for c in found]
                row['methods'][method]={'retrieved':ids,'recall_at_3':len(expected & set(ids))/len(expected)}
            rows.append(row);record(logger,'retrieval_case',**row)
        metrics={m:sum(r['methods'][m]['recall_at_3'] for r in rows)/len(rows) for m in ('bm25','vector','hybrid','weighted')}
        summary={'tag':args.tag,'split':args.split,'total':len(rows),'metrics':metrics,'cases':rows,'embedding_model':MODEL,
            'embedding_revision':REVISION,'embedding':embedding,
            'question_file_sha256':hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
            'labels_sha256':hashlib.sha256((ROOT/'eval/retrieval_labels.json').read_bytes()).hexdigest(),
            'knowledge':conn.execute('SELECT chunk_id,content_sha256,embedding_model,dimensions,embedding_revision FROM knowledge_chunks ORDER BY chunk_id').fetchall(),
            'rrf_weights':{'hybrid':[1,1],'weighted':[0.25,1]},'rrf_k':60,'source_log':path.name,'holdout_policy':'Labels cover every C case; only requested split executed, no answer generation'}
        record(logger,'run_summary',**summary)
        summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        receipt=write_evidence(path.stem+'.summary.json',summary)
        results=ROOT/'docs/RESULTS.md'
        if not results.read_text(encoding='utf-8').startswith(header): raise ValueError('RESULTS header mismatch')
        values=[args.tag,'C retrieval',args.split]+['']*12+[f'{metrics[m]*100:.2f}%' for m in ('bm25','vector','hybrid')]+[f'`{path.name}`',f'[{receipt.name}](../evidence/{receipt.name})']
        with results.open('a',encoding='utf-8',newline='\n') as stream: stream.write('| '+' | '.join(values)+' |\n')
        weighted=[args.tag+'-weighted','C retrieval',args.split]+['']*14+[f"{metrics['weighted']*100:.2f}%",f'`{path.name}`',f'[{receipt.name}](../evidence/{receipt.name})']
        with results.open('a',encoding='utf-8',newline='\n') as stream: stream.write('| '+' | '.join(weighted)+' |\n')
        print('Evidence:',receipt.name)
