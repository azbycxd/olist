import asyncio
import hashlib
import json
import zipfile
from pathlib import Path
import psycopg
from config import ROOT,db_kwargs
from contracts import FinalAnswer
from agent.number_gate import scan,approve_values
from scripts.common import start_log,record
from scripts.evidence import write_evidence
from mcp_olist.service import get_saved_result


def load_one(pattern):
    paths=list((ROOT/'evidence').glob(pattern))
    if len(paths)!=1:raise ValueError((pattern,len(paths)))
    return paths[0],json.loads(paths[0].read_text(encoding='utf-8'))


def execute():
    logger,path=start_log('step11_verification')
    review=json.loads((ROOT/'eval/step11_review.json').read_text(encoding='utf-8'))
    archive=ROOT/'evidence/step11_pre_patch_source.zip'
    old={'__name__':'retained_number_gate'}
    with zipfile.ZipFile(archive) as z:exec(compile(z.read('agent/number_gate.py'),'retained_number_gate.py','exec'),old)
    groups={};replays=[]
    for group in ['original','new']:
        receipt,run=load_one('eval_step11-'+group+'-boundary_*.summary.json')
        events=[json.loads(x) for x in (ROOT/'logs'/run['source_log']).read_text(encoding='utf-8').splitlines() if x]
        cases=[]
        for case in run['cases']:
            response=FinalAnswer.model_validate(case['response']);candidate=None
            for e in events:
                if e.get('question_id')!=case['id'] or e['event']!='model_call':continue
                p=e['payload'];out=p.get('output_summary',{})
                for call in out.get('tool_calls',[]) or []:
                    if call['function']['name']=='final_answer':
                        candidate=json.loads(call['function']['arguments'])['answer']
                if p['role']=='number_gate' and out.get('content'):
                    try:
                        v=json.loads(out['content'])
                        if isinstance(v,dict) and set(v)=={'answer'}:candidate=v['answer']
                    except ValueError:pass
            class Stored:
                async def call(self,name,args):return get_saved_result(args['result_id'],case['task_id'],0,1000)
            approved=asyncio.run(approve_values(response.claims,Stored()))
            if candidate is not None:
                before,bad_before=old['scan'](candidate,approved,True)
                after,bad_after=scan(candidate,approved,True)
                replay={'id':case['id'],'source_receipt':receipt.name,'input':candidate,'before':before,'after':after,
                        'old_unmatched':bad_before,'new_unmatched':bad_after,
                        'method':'Same saved rewrite candidate and SQL-approved claim values; deterministic formatting only, not a new model answer'}
                replays.append(replay);record(logger,'gate_replay',**replay)
            cases.append({'id':case['id'],'question':case['question'],'expected':case['expected'],**review[case['id']],
                          'evidence_audit':case['evidence_audit']})
        groups[group]={'receipt':receipt.name,'source_log':run['source_log'],'passed':sum(c['passed'] for c in cases),'total':len(cases),
                       'cases':cases,'data_unchanged':run['before']==run['after'],'usage':run['usage'],'embedding':run['embedding']}
    comparisons=[]
    for label,pattern in [
        ('Step 9 原始','eval_step9-dev-final_*.summary.json'),
        ('Step 9 同一最终核查器离线复核','eval_step11-baseline-final-checker_*.summary.json'),
        ('Step 11 首轮真实运行','eval_step11-dev-final_*.summary.json'),
        ('Step 11 首轮同一最终核查器离线复核','eval_step11-initial-final-checker_*.summary.json'),
        ('Step 11 修复后真实运行','eval_step11-dev-repair_*.summary.json')]:
        receipt,run=load_one(pattern)
        comparisons.append({'label':label,'receipt':receipt.name,'source_log':run['source_log'],'metrics':run['metrics'],'by_category':run['by_category'],
                            'usage':run['usage'],'average_agent_tokens':sum(c['agent_usage']['total_tokens'] for c in run['cases'])/len(run['cases']),'failures':[{'id':c['question_id'],'termination':c.get('termination'),'facts':[c.get('fact_hits'),c.get('fact_total')],'audit':c['evidence']} for c in run['cases'] if not c['correct']]})
    frozen=json.loads((ROOT/'evidence/step11_frozen_reference.json').read_text())
    immutable=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in frozen['immutable_files'].items())
    if not immutable:raise AssertionError('Frozen reference changed')
    summary={'source_log':path.name,'kind':'Step11 saved-response review and deterministic replay','new_model_calls':0,
             'reviewer':'Codex inspection of saved answers against predeclared expectations; not blinded human labels or a model judge',
             'boundary':groups,'dev':comparisons,'gate_replays':replays,'frozen_reference_unchanged':immutable,
             'runtime_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['agent/boundaries.py','agent/number_gate.py','eval/checker.py','scripts/task_limits.py','mcp_olist/leases.py']},
             'limit':'Boundary cases were run once before the corrective format/contract patch. Replays are not post-patch model evaluations. Only CDE had a retained additional corrective real pass.'}
    record(logger,'verification_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    output=write_evidence(path.stem+'.summary.json',summary)
    lines=['# Step 11 验证记录','',
        '保留首轮失败，再做一次共性修复后的 C/D/E 真实回归；没有重复边界题，也没有触碰 holdout。所有阶段的代码哈希、源码快照和收据均保留。',
        f'汇总与离线回放：[证据](../evidence/{output.name})，日志 `{path.name}`。本汇总没有新增模型调用。','',
        f"**无退化验收{'通过' if all(comparisons[-1]['by_category'][c]['correct']>=comparisons[1]['by_category'][c]['correct'] for c in 'CDE') else '未通过'}。** 按同一最终核查器逐类比较；全部失败与额外修复运行保留，停止进一步调参和重跑，交由审查。",'',
        '## C/D/E dev 对照','',
        '同一最终核查器离线复核仅改变判分，不产生新回答。它用于排除日期/元数据扫描规则变化的影响；不能把复核行当成模型质量提升。',
        '', '| 阶段 | C | D | E | 全部 | D 事实命中 | D 无证据结论 | 平均 Agent token | 平均 Agent 耗时 ms |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in comparisons:
        cats=row['by_category'];m=row['metrics'];d=cats['D']
        counts=[f"{cats[c]['correct']}/{cats[c]['total']}" for c in 'CDE']
        lines.append('| '+ ' | '.join([row['label'],*counts,f"{m['correct']}/{m['total']}",f"{d['fact_hits']}/{d['fact_total']}",f"{d['unsupported_claims']}/{d['claim_count']}",str(round(row['average_agent_tokens'],2)),str(round(m['average_agent_latency_ms'],2))])+' |')
    lines.extend(['','每行均来自对应真实运行或离线复核；所列 Agent 平均值不含独立评分开销。'])
    for row in comparisons:lines.append(f"- {row['label']}：[收据](../evidence/{row['receipt']})；日志 `{row['source_log']}`。")
    base,final=comparisons[1],comparisons[-1]
    for row in [comparisons[2],final]:
        lines.extend(['',row['label']+'未通过题目：'+ '；'.join(f"{c['id']}（{c['termination']}，事实 {c['facts'][0]}/{c['facts'][1]}，无支持 claim {c['audit']['unsupported_claims']}，未匹配数字 {c['audit']['unsupported_numbers']}）" for c in row['failures'])+'。'])
    lines.extend(['','“无退化”按同核查器的严格通过题数逐类比较，不只看旧表面分数；单轮样本无法证明统计等价。新增上下文与核对动作的 token/延迟成本同样列出。','',
        '## 边界题（各一次）','',
        'Codex 按运行前 expected 复核保存回答，不是独立盲评，也没有额外调用评分模型。必要的拒绝/澄清与正确的边界说明必须存在；附加业务数字仍须有直接 SQL 结果支持，因此因果拒绝正确但附加数字不合规也记失败。',
        '', 'Step 10 历史对照为 6/10，见 [原复核](../evidence/step10_boundary_review.summary.json)；原日志 `eval_step10-boundary_20261017T110935Z_62bc557e.jsonl`。'])
    for name,g in groups.items():
        lines.extend(['',f"### {'原题对照' if name=='original' else '新实体与问法'}：{g['passed']}/{g['total']}",'',
            f"[真实运行](../evidence/{g['receipt']})，日志 `{g['source_log']}`。总 token {g['usage']['total_tokens']}，模型调用 {g['usage']['model_calls']}；费用未配置，留空。",
            '', '| 题目 | 行为判定 | 不支持 claim / 总数 | 未匹配数字 / 总数（首次核查器） | 说明 |','| --- | --- | --- | --- | --- |'])
        for c in g['cases']:
            a=c['evidence_audit']
            lines.append(f"| {c['id']}：{c['question']} | {'通过' if c['passed'] else '未通过'} | {a['unsupported_claims']}/{a['claim_count']} | {a['unsupported_numbers']}/{a['report_number_count']} | {c['reason']} |")
    lines.extend(['','两组运行前后订单数、取消订单数和评价分数分布均保持不变。题目来自 [新边界题](../eval/boundary_step11.json) 和 [原边界题](../eval/boundary_cases.json)，不并入 holdout。',
        '', '## 修复与证据边界','',
        '首轮补丁涉及的模块已保存修复前源码快照 [ZIP](../evidence/step11_pre_patch_source.zip)。之后补齐全年、月份、短日期、工具参数/分批行数等格式；转换比例和业务口径阈值仍要求 SQL 返回，不能随意豁免。范围元数据只作 answer 背景，不构造不在 SQL 结果中的 claims。缺时间且没有明确假设时，兜底请求澄清，不再盲目声称某条 SQL 使用全数据。',
        '', '数字门禁回放使用保存的同一重写候选、同一批已批准 SQL 值，保留 before/after 与未匹配列表。它只证明确定性格式识别变化，不能冒称模型重新生成了更好的边界回答。字符串分桶、否定句中的零和语义证据错引仍有局限。',
        '', '冻结 holdout 的原始收据、源码 ZIP、协议、全部题库及既有迁移哈希未变，见 [核对基准](../evidence/step11_frozen_reference.json)。其成绩属于 Step 11 修复前配置；没有重跑或重新计分 holdout。后台控制及 CI 验证见 [任务控制](TASK_CONTROLS.md)。'])
    (ROOT/'docs/STEP11_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Evidence:',output.name)


if __name__=='__main__':execute()
