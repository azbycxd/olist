"""Predeclared Step 6 review protocol, executed only by eval/run.py."""
import hashlib
from argparse import Namespace
from statistics import mean
from config import ROOT
from scripts.common import start_log, record
from scripts.evidence import write_evidence


def interval(values):
    if not values or any(v is None for v in values): return None
    return {'mean':mean(values),'min':min(values),'max':max(values)}


def execute_suite(args, execute, summarize):
    logger,path=start_log('eval_'+args.tag)
    protocol={'C_repetitions':1,'D_repetitions':3,'modes':['single','multi'],
        'number_gate':['false','true'],'rag_mode':'inject','retrieval_default':'vector',
        'token_budget':100000,'context_limit':16000,'judge':'model',
        'pressure':{'context_limit':6000,'summary_threshold':3600,'strategies':['none','mask','summary']},
        'complex_subset':'Union of question IDs actually split by multi across the three repeats and both gate settings; paired identical IDs in single, all repeats retained.'}
    record(logger,'protocol',**protocol)
    runs=[]
    # Interleave modes within repetitions. Never retry a bad score or discard an API failure.
    for category,repetitions in [('C',1),('D',3)]:
        for repeat in range(1,repetitions+1):
            for mode in protocol['modes']:
                for gate in protocol['number_gate']:
                    values={**vars(args),'categories':[category],'adapter':'single','agent_mode':mode,
                        'number_gate':gate,'rag_mode':'inject','use_memory':'false','judge':'model',
                        'context_strategy':'none','context_limit':16000,'context_summary_threshold':6000,
                        'token_budget':100000,'tag':f'{args.tag}-{category}-{mode}-gate{gate}-r{repeat}'}
                    result=execute(Namespace(**values));result['suite_repeat']=repeat
                    runs.append(result)
                    record(logger,'run_completed',tag=result['tag'],source_log=result['source_log'])
    complex_ids=sorted({c['question_id'] for r in runs if r['agent_mode']=='multi'
        for c in r['cases'] if c.get('complex_route')})
    groups={};complex_groups={}
    fields=['accuracy','fact_hit_rate','unsupported_claim_ratio','d_unsupported_number_ratio',
        'judge_mean','average_agent_latency_ms','completion_rate','average_tokens']
    for category in ['C','D']:
        for mode in protocol['modes']:
            for gate in protocol['number_gate']:
                selected=[r for r in runs if r['categories']==[category] and r['agent_mode']==mode and r['number_gate']==gate]
                key=f'{category}/{mode}/gate={gate}'
                groups[key]={'repetitions':len(selected), 'sources':[r['source_log'] for r in selected],
                    'metrics':{f:interval([r['metrics'].get(f) for r in selected]) for f in fields}}
                if category=='D':
                    paired=[summarize([c for c in r['cases'] if c['question_id'] in complex_ids]) for r in selected]
                    complex_groups[key]={'question_ids':[i for i in complex_ids if i.startswith('D')],
                        'sources':[r['source_log'] for r in selected],
                        'metrics':{f:interval([m.get(f) for m in paired]) for f in ['fact_hit_rate','average_agent_latency_ms','completion_rate']}}
    pressure=[]
    for strategy in protocol['pressure']['strategies']:
        values={**vars(args),'categories':['D'],'adapter':'single','agent_mode':'single','number_gate':'false',
            'rag_mode':'inject','use_memory':'false','judge':'model','context_strategy':strategy,
            'context_limit':6000,'context_summary_threshold':3600,'token_budget':100000,
            'tag':f'{args.tag}-pressure-{strategy}'}
        pressure.append(execute(Namespace(**values)))
    summary={'protocol':protocol,'groups':groups,'complex_groups':complex_groups,'complex_ids':complex_ids,
        'pressure':[{'tag':r['tag'],'metrics':r['metrics'],'usage':r['usage'],'source_log':r['source_log']} for r in pressure],
        'sources':[r['source_log'] for r in runs+pressure], 'source_log':path.name,
        'embedding':runs[0]['embedding'],'code_sha256':runs[0]['code_sha256']}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    lines=['# Step 6 审查补充对比','', '由 `eval/run.py --review-suite` 真实运行生成；区间是各次结果的最小值到最大值。未知用量留空。',
        '', f"汇总日志：`{path.name}`；[汇总证据](../evidence/{receipt.name})。",'',
        '| 组别 | 准确率 均值 [范围] | D 事实命中 均值 [范围] | 无证据结论比例 均值 [范围] | D 无证据数字比例 均值 [范围] | Agent 耗时 ms 均值 [范围] | 完成率 均值 [范围] |',
        '| --- | --- | --- | --- | --- | --- | --- |']
    def fmt(v,percent=False):
        if v is None:return ''
        scale=100 if percent else 1;suffix='%' if percent else ''
        return f"{v['mean']*scale:.2f}{suffix} [{v['min']*scale:.2f}, {v['max']*scale:.2f}]"
    for key,group in groups.items():
        m=group['metrics']; fs=['accuracy','fact_hit_rate','unsupported_claim_ratio','d_unsupported_number_ratio','average_agent_latency_ms','completion_rate']
        lines.append('| '+' | '.join([key]+[fmt(m[f],f!='average_agent_latency_ms') for f in fs])+' |')
    lines+=['','复杂题集合：'+', '.join(complex_ids)+'。按实际 multi 拆分题目的并集取同题比较；规划路由存在波动，不作因果速度结论。','',
        '| 复杂题同题组别 | D 事实命中 均值 [范围] | Agent 耗时 ms 均值 [范围] |','| --- | --- | --- |']
    for key,group in complex_groups.items():
        m=group['metrics'];lines.append(f"| {key} | {fmt(m['fact_hit_rate'],True)} | {fmt(m['average_agent_latency_ms'])} |")
    lines+=['','压力测试单独标注在 RESULTS 的 pressure 行；不混入普通模式均值。','', '逐次日志：','']
    for r in runs+pressure: lines.append(f"- `{r['source_log']}` → [证据](../evidence/{r['source_log'].removesuffix('.jsonl')}.summary.json)")
    (ROOT/'docs/REVIEW_COMPARISON.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Suite evidence:',receipt.name)
