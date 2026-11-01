"""Read-only oracle capture and offline, outcome-only multi-grader diagnostics.

This new entry point never imports an Agent or invokes the old eval runner.
Historical Agent answers are not inputs: these are constructed reference answers.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time
from uuid import NAMESPACE_URL, uuid5

from contracts import FinalAnswer
from eval.checker import check, number
from eval.dataset import load_questions
from eval.scoring import gold_answer, score
from eval.step13_errors import ROOT, read, sha, write

KINDS = ('offset_5pct','negate_sign','remove_evidence','foreign_evidence',
         'replace_label','unsupported_number')


def plain(value):
    return json.loads(json.dumps(value, default=lambda x: float(x) if isinstance(x,Decimal) else str(x)))


def make_record(question, rows, version):
    rows=plain(rows);gold=gold_answer(question,rows)
    task=str(uuid5(NAMESPACE_URL,'step13/reference/task/'+question['id']))
    rid=str(uuid5(NAMESPACE_URL,'step13/reference/result/'+question['id']))
    value=gold if question['answer_type']!='key_facts' else rows[0]
    response=FinalAnswer(answer=gold if question['answer_type']!='key_facts' else '参考事实见证据。',
        claims=[{'text':'只读查询结果。','value':value,'evidence':[rid]}])
    return {'question':question,'rows':rows,'gold':gold,'task_id':task,
        'result_id':rid,'data_version':version,'response':response.model_dump()}


def load_fixture(path='evidence/step13_gold_reference.json'):
    bundle=read(ROOT/path)
    # CI uses the committed rows; raw logs may be local/ignored. Bind the rows
    # themselves as well as the raw capture and source question file.
    payload=json.dumps(bundle['records'],ensure_ascii=False,sort_keys=True).encode()
    if hashlib.sha256(payload).hexdigest()!=bundle['records_sha256']:
        raise ValueError('Saved reference records hash mismatch')
    if sha(ROOT/bundle['question_file'])!=bundle['question_file_sha256']:
        snapshot=ROOT/'evidence/source_snapshots'/bundle['question_file_sha256']
        if not snapshot.exists() or sha(snapshot)!=bundle['question_file_sha256']:
            raise ValueError('Question file changed after reference capture without its exact historical snapshot')
    return bundle


def evaluate(bundle, qid, response=None, records=None):
    rec=next(r for r in bundle['records'] if r['question']['id']==qid)
    store={r['result_id']:{'task_id':r['task_id'],'data_version':r['data_version'],'rows':r['rows']}
           for r in (records or bundle['records'])}
    response=FinalAnswer.model_validate(response or rec['response'])
    evidence=check(response,lambda ids:{i:store[i] for i in ids if i in store},rec['task_id'],rec['data_version'])
    scored=score(rec['question'],response,rec['gold'],evidence)
    return {'score':scored,'audit':evidence,'strict_pass':scored['correct'] and
        evidence['unsupported_claims']==0 and evidence['unsupported_numbers']==0}


def leaves(value, path=()):
    if isinstance(value,dict):
        for k,v in value.items():yield from leaves(v,path+(k,))
    elif isinstance(value,list):
        for k,v in enumerate(value):yield from leaves(v,path+(k,))
    else:yield path,value


def replace(value,path,new):
    if not path:return new
    value=deepcopy(value);target=value
    for key in path[:-1]:target=target[key]
    target[path[-1]]=new
    return value


def mutate(rec,kind,other):
    response=deepcopy(rec['response']);q=rec['question']
    value=response['claims'][0]['value']
    if kind in {'offset_5pct','negate_sign'}:
        target=next(((p,v) for p,v in leaves(value) if number(v) not in (None,Decimal(0))),None)
        if target is None:return None,'无非零数值；零的乘法/取反为恒等变换，不能算有效变异'
        path,old=target;new=float(number(old)*(Decimal('1.05') if kind=='offset_5pct' else -1))
        value=replace(value,path,new)
        response['claims'][0]['value']=value
        if q['answer_type']!='key_facts':response['answer']=value
    elif kind=='remove_evidence':
        for c in response['claims']:c['evidence']=[]
    elif kind=='foreign_evidence':
        for c in response['claims']:c['evidence']=[other['result_id']]
    elif kind=='unsupported_number':
        # Scalar/list answers cannot gain prose while preserving answer_type.
        # Their public claim.text is report text scanned by the same checker.
        text=' 另有未经查询的业务收入 9876543210123 元。'
        if q['answer_type']=='key_facts':response['answer']+=text
        else:response['claims'][0]['text']+=text
    elif kind=='replace_label':
        targets=[]
        for p,v in leaves(value):
            if not isinstance(v,str) or number(v) is not None:continue
            field=' '.join(str(k) for k in p).lower()
            is_state=len(v)==2 and v in {'SP','RJ','MG','RS','PR','SC','BA','DF','GO','ES','PE','CE','PA','MT','MA','MS','PB','PI','RN','AL','SE','TO','RO','AM','AC','AP','RR'}
            is_category=('category' in field or '品类' in q['question']) and len(v)!=32
            if is_state:
                targets.append((p,v,'RJ' if v=='SP' else 'SP'))
            elif is_category:
                choices=('beleza_saude','cama_mesa_banho') if '原始葡文' in q['question'] else ('health_beauty','bed_bath_table')
                targets.append((p,v,choices[0] if v!=choices[0] else choices[1]))
        if not targets:return None,'答案中没有可替换的品类/州名；题干标签不当作答案标签'
        path,old,new=targets[0];value=replace(value,path,new)
        response['claims'][0]['value']=value
        if q['answer_type']!='key_facts':response['answer']=value
    else:raise ValueError(kind)
    return response,None


def ambiguity(rec):
    import sqlglot
    from sqlglot import exp
    q=rec['question'];kind=q['answer_type'];qid=q['id']
    hidden=[]
    common=['数值相对容差1%（floor 1e-8）未逐题写出；证据单元相对容差1e-6'] if kind!='list' else ['list按canonical集合精确相等；不检查排序和重复次数']
    if qid in {'D01','D04'}:hidden.append('变化/相差使用后期减前期；题干未明确带符号方向')
    if qid=='D02':hidden.extend(['下降金额gold为非负幅度，公开字段未写正负约定',
        '最大降幅若并列，gold按品类名升序取一个；题干未说明并列处理（不代表本数据实际并列）'])
    if kind=='key_facts':hidden.append('同一事实键出现矛盾副本不计命中；score还要求全部证据无告警')
    tree=sqlglot.parse_one(q['gold_sql'],read='postgres') if q.get('gold_sql') else None
    # A/B/E typed numeric/list contracts and D field names are public, not hidden.
    return {'id':qid,'question':q['question'],
        'public_contract':{'answer_type':kind,'required_facts':q.get('required_facts',[]),
            'setup_turns':q.get('setup_turns',[]),'source':'eval/adapters.py:SingleAdapter.run; contracts.py; kb/metrics.md'},
        'actual_checks':{'fields':q.get('required_facts',[]),'expected_values':rec['gold'],
            'sign':'signed numeric comparison; prose magnitude matched by absolute value',
            'precision':'score number/key_facts: relative 1%, abs floor 1e-8; list: exact canonical set; evidence cells: relative 1e-6',
            'shape':{'number':'finite scalar','list':'set equality, order and duplicate count ignored',
                'key_facts':'nonempty prose plus exact public keys in claim row(s); contradictory duplicates rejected'}[kind],
            'range_and_semantics':{'sql':q.get('gold_sql'),'parameters':q.get('parameters'),
                'gold_where_predicates':[w.sql(dialect='postgres') for w in tree.find_all(exp.Where)] if tree else [],
                'gold_having_predicates':[w.sql(dialect='postgres') for w in tree.find_all(exp.Having)] if tree else [],
                'note':'范围、状态、连接粒度只由最终数值间接约束；不审工具顺序，不强制特定SQL'},
            'not_checked':['业务解释/原因是否正确','list排名顺序及重复次数'] if kind=='list' else ['业务解释/原因是否正确']},
        'checked_not_stated_in_question':hidden,
        'shared_implicit_grader_conventions':common,
        'public_but_not_literal_question':['answer_type']+(['required_facts exact names'] if kind=='key_facts' else []),
        'clarifications':'C口径来自公开KB，E来自公开setup；不把它们伪称私有要求。容差和证据所有权属于通用评测/输出约定。'}


def equivalents(rec):
    q=rec['question'];response=deepcopy(rec['response']);variants=[]
    if q['answer_type']=='key_facts':
        long=deepcopy(rec);long['rows']=[{'fact':k,'value':v} for k,v in rec['gold'].items()]
        long['response']['claims'][0]['value']=long['rows']
        variants.append(('wide_to_long',long['response'],long,
            '信息和值不变、列名换为fact/value；诊断表示依赖，不宣称满足现行exact-key契约'))
    else:variants.append(('wide_to_long',None,None,'非宽表key_facts答案，不适用'))
    text=' 时间示例：2018 年 Q2；1 月到 3 月。'
    # Lexical robustness probe, not a change to the question's actual period.
    if q['answer_type']=='key_facts':response['answer']+=text
    else:response['claims'][0]['text']+=text
    variants.append(('date_prose',response,None,'仅日期词法说明；不新增业务量、不改变实际取数时间'))
    candidates=[(p,v) for p,v in leaves(rec['gold']) if number(v) is not None and
        (number(v)<0 or any('drop' in str(k) for k in p))]
    if candidates:
        response=deepcopy(rec['response']);v=candidates[0][1]
        response['claims'][0]['text']+=' 下降 '+str(abs(number(v)))+'。'
        variants.append(('decline_prose',response,None,'claim保留SQL符号；正文使用下降加正幅度'))
    else:variants.append(('decline_prose',None,None,'没有下降量或负变化量，不适用'))
    return variants


def tally(rows,field):
    out=[]
    for kind in dict.fromkeys(r['kind'] for r in rows):
        applicable=[r for r in rows if r['kind']==kind and r['applicable']]
        bad=[r['id'] for r in applicable if not r[field]]
        out.append({'kind':kind,'applicable':len(applicable),'not_applicable':sum(r['kind']==kind and not r['applicable'] for r in rows),
            'passed':len(applicable)-len(bad),'rate':(len(applicable)-len(bad))/len(applicable) if applicable else None,'failed_ids':bad})
    return out


def audit_bundle(bundle):
    references=[];mutations=[];equiv=[]
    for i,rec in enumerate(bundle['records']):
        qid=rec['question']['id'];references.append({'id':qid,**evaluate(bundle,qid)})
        for kind in KINDS:
            response,reason=mutate(rec,kind,bundle['records'][(i+1)%len(bundle['records'])])
            item={'id':qid,'kind':kind,'applicable':response is not None,'not_applicable_reason':reason}
            if response:
                result=evaluate(bundle,qid,response);grader='score' if kind in KINDS[:2]+('replace_label',) else 'evidence'
                item.update(result,response=response,grader=grader,killed=not result['score']['correct'] if grader=='score' else
                    result['audit']['unsupported_claims']>0 or result['audit']['unsupported_numbers']>0)
            mutations.append(item)
        for kind,response,override,note in equivalents(rec):
            item={'id':qid,'kind':kind,'applicable':response is not None,'note':note}
            if response:
                records=[override if r['question']['id']==qid else r for r in bundle['records']] if override else None
                item.update(evaluate(bundle,qid,response,records),response=response)
            equiv.append(item)
    return {'kind':'Constructed reference/grader diagnostic; no historical rescoring',
        'model_calls':0,'references':references,'reference_passed':sum(r['strict_pass'] for r in references),
        'mutations':mutations,'mutation_summary':tally(mutations,'killed'),
        'equivalents':equiv,'equivalent_summary':tally(equiv,'strict_pass'),
        'ambiguity':[ambiguity(r) for r in bundle['records']]}


def capture(question_file,output):
    import psycopg
    from config import db_kwargs
    qs=read(question_file) if str(question_file).endswith('.json') else load_questions(question_file)
    path=ROOT/'logs'/(Path(output).stem+'_capture.jsonl')
    if (ROOT/output).exists() or path.exists():raise FileExistsError('Capture is immutable; choose a new output explicitly')
    records=[]
    with psycopg.connect(**db_kwargs(role='reader')) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL app.allowed_states = 'ALL'")
        conn.execute("SET LOCAL statement_timeout = '30s'")
        role,readonly=conn.execute("SELECT current_user, current_setting('transaction_read_only')").fetchone()
        version=conn.execute('SELECT public.current_data_version()').fetchone()[0]
        with path.open('w',encoding='utf-8',newline='\n') as log:
            for q in qs:
                start=time.perf_counter();cur=conn.execute(q['gold_sql']);columns=[c.name for c in cur.description]
                rows=[dict(zip(columns,r)) for r in cur.fetchall()]
                rec=make_record(q,rows,version);rec.update(sql_sha256=hashlib.sha256(q['gold_sql'].encode()).hexdigest(),duration_ms=(time.perf_counter()-start)*1000)
                records.append(rec);log.write(json.dumps(rec,ensure_ascii=False)+'\n');log.flush()
    bundle={'created_at':datetime.now(timezone.utc).isoformat(),'database_role':role,'transaction_read_only':readonly,
        'question_file':question_file.relative_to(ROOT).as_posix(),'question_file_sha256':sha(question_file),
        'source_log':path.relative_to(ROOT).as_posix(),'source_log_sha256':sha(path),'model_calls':0,
        'records':records,'records_sha256':hashlib.sha256(json.dumps(records,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
    write(ROOT/output,bundle)
    return bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',action='store_true');parser.add_argument('--supplement',action='store_true')
    args=parser.parse_args();stem='step13_supplement' if args.supplement else 'step13_gold'
    fixture=f'evidence/{stem}_reference.json'
    if args.capture:capture(ROOT/('eval/step13_supplement_cases.json' if args.supplement else 'eval/questions.jsonl'),fixture)
    bundle=load_fixture(fixture);report=audit_bundle(bundle)
    report['source_fixture']={'path':fixture,'sha256':sha(ROOT/fixture),'source_log':bundle['source_log'],'source_log_sha256':bundle['source_log_sha256']}
    report['grader_sources']={p:sha(ROOT/p) for p in ['eval/checker.py','eval/scoring.py','contracts.py','eval/step13_grader.py']}
    output='evidence/step13_supplement_grader_audit.json' if args.supplement else 'evidence/step13_grader_audit.json'
    write(ROOT/output,report)
    print(json.dumps({'reference_passed':report['reference_passed'],'total':len(bundle['records']),
        'mutations':report['mutation_summary'],'equivalents':report['equivalent_summary']},ensure_ascii=False))


if __name__=='__main__':main()
