"""Predeclared release protocol: isolated users, one holdout launch, no retries.

Invoked only through eval/run.py. Rendering reads receipts and makes no model calls.
"""
import hashlib
import json
import os
import zipfile
from argparse import Namespace
from collections import Counter
from pathlib import Path

from config import ROOT, FINAL_CONFIG
from eval.dataset import QUESTION_FILE, load_questions
from scripts.common import start_log, record
from scripts.evidence import write_evidence


BASE = dict(adapter='single',schema_mode='on_demand',judge='model',agent_mode='single',
    rag_mode='inject',use_memory='true',number_gate='true',context_strategy='none',
    context_limit=16000,context_summary_threshold=6000,token_budget=100000,
    question_ids=None,user_group=None)


def specifications(stage):
    if stage=='holdout':
        return [(f'holdout-r{i}',dict(BASE,split='holdout',categories=list('ABCDE'))) for i in range(1,4)]
    return [(name,{**BASE,'split':'dev',**changes}) for name,changes in [
        ('dev-final',dict(categories=list('CDE'))),
        ('dev-minus-rag',dict(categories=['C'],rag_mode='off')),
        ('dev-minus-memory',dict(categories=['E'],use_memory='false')),
        ('dev-minus-gate',dict(categories=['D'],number_gate='false')),
        ('dev-multi-gate',dict(categories=['D'],agent_mode='multi')),
        ('dev-pressure-mask',dict(categories=['D'],context_limit=6000,context_strategy='mask')),
        ('dev-pressure-none',dict(categories=['D'],context_limit=6000))]]


def source_hashes():
    files=[ROOT/'config.py',ROOT/'contracts.py',ROOT/'pyproject.toml',ROOT/'Dockerfile',ROOT/'docker-compose.yml',ROOT/'.env.example']
    for directory in ['agent','eval','api','scripts','mcp_olist','embeddings','kb','sql']:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc'})
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))}


def execute_suite(args,execute):
    stage=args.final_suite
    if stage=='holdout' and len([q for q in load_questions() if q['split']=='holdout'])!=22:
        raise ValueError('Holdout protocol requires exactly 22 questions')
    marker=ROOT/'evidence'/f'step9_{stage}_protocol.json'
    if marker.exists():
        raise ValueError('Protocol already started; do not rerun or remove its marker. Inspect retained logs.')
    if stage=='holdout':
        existing=[]
        for p in (ROOT/'evidence').glob('eval_*.summary.json'):
            v=json.loads(p.read_text(encoding='utf-8'))
            if v.get('split')=='holdout' and v.get('adapter')!='zero':existing.append(p.name)
        if existing:raise ValueError('Prior holdout evidence exists; review before any new run: '+str(existing))
    os.environ['RETRIEVAL_METHOD']='vector'
    specs=specifications(stage)
    logger,path=start_log('eval_'+args.tag)
    hashes=source_hashes()
    archive=None
    if stage=='holdout':
        archive='step9_holdout_frozen_source.zip'
        with zipfile.ZipFile(ROOT/'evidence'/archive,'x',zipfile.ZIP_DEFLATED) as z:
            for name in hashes:z.write(ROOT/name,name)
    protocol={'stage':stage,'source_log':path.name,'specifications':dict(specs),'code_sha256':hashes,
        'question_file_sha256':hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
        'source_archive':archive,'final_config':FINAL_CONFIG,'retries':0,
        'isolation':'New random run_id and new user per question per repetition; E setup/new session only shares its own user.',
        'rules':['All failures count; no selective retries','No holdout-driven prompt or code tuning',
                 'One holdout protocol with three complete passes; source checked before each pass',
                 'Dev pressure pair differs only in none/mask; limit 6000; separate from ordinary none baseline']}
    # Exclusive create is the one-shot guard, including when a process crashes.
    marker.parent.mkdir(exist_ok=True)
    with marker.open('x',encoding='utf-8',newline='\n') as f:json.dump(protocol,f,ensure_ascii=False,indent=2);f.write('\n')
    record(logger,'protocol_started',**protocol)
    runs={}
    for label,settings in specs:
        if source_hashes()!=hashes:raise ValueError('Source changed after protocol freeze; execution stopped')
        print('Starting:',label,flush=True)
        record(logger,'pass_started',label=label)
        summary=execute(Namespace(**settings,tag='step9-'+label))
        runs[label]=summary['source_log'].replace('.jsonl','.summary.json')
        record(logger,'pass_completed',label=label,evidence=runs[label])
    summary={**protocol,'runs':runs,'complete':True}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    print('Protocol evidence:',receipt.name,flush=True)
    return summary


def interval(values):
    if not values or any(v is None for v in values):return None
    return {'mean':sum(values)/len(values),'min':min(values),'max':max(values)}


def measure(rows):
    from eval.run import summarize
    result=summarize(rows)
    tokens=[r.get('agent_usage',{}).get('total_tokens') for r in rows]
    result['average_agent_tokens']=sum(tokens)/len(rows) if rows and all(v is not None for v in tokens) else None
    return result


def group(runs,category=None):
    rows=[[c for c in r['cases'] if category is None or c['category']==category] for r in runs]
    measured=[measure(r) for r in rows]
    fields=['accuracy','fact_hit_rate','unsupported_claim_ratio','d_unsupported_number_ratio','judge_mean',
        'average_agent_latency_ms','average_agent_tokens','completion_rate','peak_context_tokens']
    return {'intervals':{f:interval([m[f] for m in measured]) for f in fields},
        'correct_per_run':[m['correct'] for m in measured],'total_per_run':[m['total'] for m in measured],
        'pooled_correct':sum(m['correct'] for m in measured),'pooled_total':sum(m['total'] for m in measured),
        'per_run':measured}


def render(args):
    def read(p):return json.loads(p.read_text(encoding='utf-8'))
    suite=read(args.final_report)
    if suite['stage']!='holdout' or not suite['complete']:raise ValueError('Completed holdout protocol required')
    dev_paths=[p for p in (ROOT/'evidence').glob('eval_*.summary.json') if (lambda v:v.get('stage')=='dev' and v.get('complete'))(read(p))]
    if len(dev_paths)!=1:raise ValueError('Expected exactly one completed Step 9 dev protocol')
    dev=read(dev_paths[0])
    sources={}
    for name in [*suite['runs'].values(),*dev['runs'].values()]:
        p=ROOT/'evidence'/name;r=read(p)
        if hashlib.sha256((ROOT/'logs'/r['source_log']).read_bytes()).hexdigest()!=r['source_log_sha256']:
            raise ValueError('Source log hash mismatch')
        sources[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_log':r['source_log']}
    holdout=[read(ROOT/'evidence'/name) for name in suite['runs'].values()]
    # Check receipt identity and isolation; never silently pool different protocols.
    ids=[{c['question_id'] for c in r['cases']} for r in holdout]
    if len(holdout)!=3 or any(x!=ids[0] or len(x)!=22 for x in ids):raise ValueError('Incomplete repetitions')
    for key in ['code_sha256','data_version','question_file_sha256','embedding']:
        if any(r[key]!=holdout[0][key] for r in holdout):raise ValueError('Mismatched '+key)
    users=[c['user_id'] for r in holdout for c in r['cases']]
    if len(set(users))!=len(users):raise ValueError('Repetition users must be isolated')
    groups={c:group(holdout,None if c=='all' else c) for c in ['all',*'ABCDE']}
    questions=[]
    for ident in sorted(ids[0]):
        cases=[next(c for c in r['cases'] if c['question_id']==ident) for r in holdout]
        questions.append({'question_id':ident,'correct':sum(c['correct'] for c in cases),'repetitions':len(cases),
            'outcomes':[{'correct':c['correct'],'termination':c.get('termination'),'error':c.get('error'),
                'fact_hits':c['fact_hits'],'fact_total':c['fact_total'],'evidence':c['evidence']} for c in cases]})
    dev_runs={k:read(ROOT/'evidence'/v) for k,v in dev['runs'].items()}
    ablations={}
    for label,run,cat in [('final-C','dev-final','C'),('minus-RAG','dev-minus-rag','C'),
        ('final-E','dev-final','E'),('minus-Memory','dev-minus-memory','E'),
        ('final-D','dev-final','D'),('minus-gate','dev-minus-gate','D'),('multi-gate','dev-multi-gate','D'),
        ('pressure-mask','dev-pressure-mask','D'),('pressure-minus-compression','dev-pressure-none','D')]:
        ablations[label]={'metrics':group([dev_runs[run]],cat),'source':dev['runs'][run],
            'configuration':{k:dev_runs[run].get('judge_mode' if k=='judge' else k) for k in BASE if k not in {'question_ids','user_group','categories'}}}
    logger,path=start_log('eval_'+args.tag)
    summary={'source_log':path.name,'sources':sources,'holdout_protocol':args.final_report.name,
        'dev_protocol':dev_paths[0].name,'embedding':holdout[0]['embedding'],'groups':groups,'questions':questions,
        'all_repetitions_correct':sum(q['correct']==q['repetitions'] for q in questions),
        'any_repetition_correct':sum(q['correct']>0 for q in questions),'ablations':ablations,
        'metric_notes':'Arithmetic mean and min/max of complete passes; pooled denominator 66 repeated attempts on 22 questions. Agent tokens/latency include preference setup/extraction, exclude eval judge. Missing usage stays null.'}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    def fmt(value,pct=False):
        if value is None:return ''
        scale=100 if pct else 1; suffix='%' if pct else ''
        return f"{value['mean']*scale:.2f}{suffix} [{value['min']*scale:.2f}, {value['max']*scale:.2f}]{suffix}"
    def link(name):return f'[{name}](../evidence/{name})'
    lines=['# 最终评测与单项消融','',f'统计由 `eval/run.py --final-report` 读取真实收据生成。汇总日志 `{path.name}`；{link(receipt.name)}。','',
        '最终配置：single + 数字门禁 + RAG inject + vector + Memory + none；长任务可切换 mask，多智能体为可选。',
        '固定预算 100000 token、上下文上限 16000、on_demand schema、temperature=0；独立模型评分开启。每轮每题新用户；E 的偏好设置与后续问题跨独立任务。',
        '下表为完整轮次指标的算术均值 [最小值, 最大值]。Agent 用量与耗时包含偏好设置/抽取，排除独立评测评分。费用未配置，留空。','',
        '## Holdout：一次协议、三轮完整运行','',
        '| 类别 | 各轮正确 / 总题数 | 准确率 | D 事实命中率 | 无证据结论比例 | D 无证据数字比例 | 平均 Agent token | 平均 Agent ms |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for cat,g in groups.items():
        v=g['intervals'];counts='；'.join(f'{a} / {b}' for a,b in zip(g['correct_per_run'],g['total_per_run']))
        lines.append('| '+' | '.join([cat,counts,*[fmt(v[f],True) for f in ['accuracy','fact_hit_rate','unsupported_claim_ratio','d_unsupported_number_ratio']],fmt(v['average_agent_tokens']),fmt(v['average_agent_latency_ms'])])+' |')
    a=groups['all']
    lines+=['',f"共 {a['pooled_correct']} / {a['pooled_total']} 次作答正确，题目仍是 {len(questions)} 道；其中 {summary['all_repetitions_correct']} / {len(questions)} 道三轮均正确，{summary['any_repetition_correct']} / {len(questions)} 道至少一次正确。不是独立的 66 道题。",'',
        'D 整题判定、事实命中和数字核查是不同指标；独立核查器也检查 claim 文本，门禁只改报告正文。模型归因评分尚未经过人工校准。', '',
        '| 题号 | 正确次数 / 重复次数 |', '| --- | --- |']
    lines += [f"| {q['question_id']} | {q['correct']} / {q['repetitions']} |" for q in questions]
    lines+=['','## Dev：严格单项消融','',
        '每组一次，不做稳定性推断。C/E/D 分别使用同一次最终配置运行的对应子集。压力测试单列：在相同 6000 上限下比较 mask 与 none；默认 none 本身没有压缩可关闭。','',
        '| 配置 / 题集 | 正确 / 总题数 | 准确率 | D 事实命中率 | 无证据结论比例 | D 无证据数字比例 | 完成率 | 平均 Agent token | 平均 Agent ms | 来源 |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for label,entry in ablations.items():
        g=entry['metrics'];v=g['intervals']
        lines.append('| '+' | '.join([label,f"{g['correct_per_run'][0]} / {g['total_per_run'][0]}",
            *[fmt(v[f],True) for f in ['accuracy','fact_hit_rate','unsupported_claim_ratio','d_unsupported_number_ratio','completion_rate']],
            fmt(v['average_agent_tokens']),fmt(v['average_agent_latency_ms']),link(entry['source'])])+' |')
    lines+=['','旧 Step 6 重复实验与检索、偏好审计继续复用为历史设计依据，见 [重复对比](REVIEW_COMPARISON.md)。旧组 Memory 关闭，且源码版本不同，不能替代这里从最终配置出发的单项对照。','',
        '## 每个数字的运行来源','',f"冻结协议：{link('step9_holdout_protocol.json')}；完成协议：{link(args.final_report.name)}；dev 协议：{link(dev_paths[0].name)}。",'',
        '| 组别 | 原始运行日志文件名 | Git 汇总证据 |','| --- | --- | --- |']
    for label,name in [*suite['runs'].items(),*dev['runs'].items()]:
        lines.append(f"| {label} | `{sources[name]['source_log']}` | {link(name)} |")
    (ROOT/'docs/FINAL_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Final evidence:',receipt.name)
    return summary
