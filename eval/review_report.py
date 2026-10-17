"""Render all repeated-run metrics from immutable eval/run.py receipts."""
import hashlib
import json
from config import ROOT
from eval.review_suite import interval
from scripts.common import start_log,record
from scripts.evidence import write_evidence


def execute(args):
    source=args.review_report
    suite=json.loads(source.read_text(encoding='utf-8'))
    logger,path=start_log('eval_'+args.tag)
    groups={}
    fields=['correct','fact_hits','fact_total','unsupported_claims','claim_count','d_unsupported_numbers','d_number_count','judge_mean','average_tokens']
    for key,group in suite['groups'].items():
        runs=[json.loads((ROOT/'evidence'/name.replace('.jsonl','.summary.json')).read_text(encoding='utf-8')) for name in group['sources']]
        groups[key]={f:(None if key.startswith('C/') and f in {'fact_hits','fact_total','d_unsupported_numbers','d_number_count','judge_mean'}
            else interval([r['metrics'].get(f) for r in runs])) for f in fields}
    from eval.run import summarize
    all_runs={}
    for name in suite['sources']:
        run=json.loads((ROOT/'evidence'/name.replace('.jsonl','.summary.json')).read_text(encoding='utf-8'))
        all_runs[run['tag']]=run
    pairs=[]
    for tag,multi in all_runs.items():
        if multi['categories']!=['D'] or multi['agent_mode']!='multi':continue
        single=all_runs[tag.replace('-multi-','-single-')]
        ids=sorted(c['question_id'] for c in multi['cases'] if c.get('complex_route'))
        pairs.append({'tag':tag,'question_ids':ids,'single':summarize([c for c in single['cases'] if c['question_id'] in ids]),
            'multi':summarize([c for c in multi['cases'] if c['question_id'] in ids]),
            'sources':[single['source_log'],multi['source_log']]})
    summary={'source_log':path.name,'source_evidence':source.name,'source_evidence_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'sources':suite['sources'],'groups':groups,'actual_split_pairs':pairs,'embedding':suite['embedding']}
    record(logger,'run_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    def fmt(v):
        return '' if v is None else f"{v['mean']:.2f} [{v['min']:.2f}, {v['max']:.2f}]"
    lines=['','## 补充计数、归因与用量均值及范围','',f"由已有真实运行收据计算；日志 `{path.name}`，[证据](../evidence/{receipt.name})。",'',
        '| 组别 | 整题正确数 | 事实命中数 | 事实分母 | 无证据 claim 数 | claim 分母 | D 无证据数字数 | D 数字分母 | D 归因评分 | 平均总 token |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for key,values in groups.items():lines.append('| '+' | '.join([key]+[fmt(values[f]) for f in fields])+' |')
    lines+=['','平均总 token 含独立评测评分；任一重复的 usage 不完整则该组总量均值留空。事实和数字分母单列，比例均值是各次比例的算术平均，不能与平均计数的比值混淆。']
    lines+=['','## 按当次实际拆分配对','',
        '上表的固定并集便于跨轮比较；下表额外只取每次 multi 实际拆开的题，在同轮、同门禁设置的 single 中取相同题目。路由会波动，不能将不同题集的差别归因于并行。','',
        '| multi 运行标签 | 当次实际拆分题号 | single 平均 Agent ms | multi 平均 Agent ms | single 事实命中 | multi 事实命中 |',
        '| --- | --- | --- | --- | --- | --- |']
    for pair in pairs:
        a,b=pair['single'],pair['multi']
        latency=lambda m:'' if m['average_agent_latency_ms'] is None else f"{m['average_agent_latency_ms']:.2f}"
        lines.append(f"| {pair['tag']} | {', '.join(pair['question_ids'])} | {latency(a)} | {latency(b)} | {a['fact_hits']} / {a['fact_total']} | {b['fact_hits']} / {b['fact_total']} |")
    lines+=['','## 上下文压力测试','',
        '各策略只运行一次，限制为 6000；summary 的预设压缩阈值为 3600。峰值包含触发超限时的输入估计，不能当作供应商实际接受的窗口大小。失败保留，不混入普通模式均值。','',
        '| 策略 | 完成数 | 事实命中 | 峰值上下文估计 token | 实际总 token（含评分） | 终止原因 |',
        '| --- | --- | --- | --- | --- | --- |']
    for run in all_runs.values():
        if '-pressure-' not in run['tag']:continue
        m=run['metrics'];reasons={}
        for case in run['cases']:
            reason=case.get('termination','unknown');reasons[reason]=reasons.get(reason,0)+1
        total=run['usage']['total_tokens']
        lines.append(f"| {run['context_strategy']} | {reasons.get('final_answer',0)} / {m['total']} | {m['fact_hits']} / {m['fact_total']} | {m['peak_context_tokens']} | {'' if total is None else total} | {json.dumps(reasons,ensure_ascii=False)} |")
    target=ROOT/'docs/REVIEW_COMPARISON.md'
    original=target.read_text(encoding='utf-8').split('\n## 补充计数、归因与用量均值及范围')[0]
    target.write_text(original+'\n'.join(lines)+'\n',encoding='utf-8')
    print('Evidence:',receipt.name)
