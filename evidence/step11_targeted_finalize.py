"""Offline derivation from four immutable real runs; no model calls."""
import hashlib,json
import xml.etree.ElementTree as ET
from config import ROOT,FINAL_CONFIG
from eval.step11_targeted import acceptance,frozen_files
from eval.final_suite import source_hashes
from scripts.common import start_log,record
from scripts.evidence import write_evidence

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name):return json.loads((ROOT/'evidence'/name).read_text(encoding='utf-8'))
names=list((ROOT/'evidence').glob('eval_step11-targeted-protocol_*.summary.json'))
assert len(names)==1
protocol=load(names[0].name)
assert protocol['complete'] and source_hashes()==protocol['source_sha256']
frozen_files()
review_name='step11_targeted_boundary_review.json'
review=load(review_name)
ds=[];bs=[];all_ids=set()
for label,name in protocol['receipts'].items():
    run=load(name)
    assert digest(ROOT/'logs'/run['source_log'])==run['source_log_sha256']
    ids={c.get('task_id') for c in run['cases']}
    assert len(ids)==len(run['cases']) and not ids&all_ids
    all_ids|=ids
    item={'label':label,'receipt':name,'source_log':run['source_log'],
          'receipt_sha256':digest(ROOT/'evidence'/name),'embedding':run['embedding']}
    if label.startswith('step11-target-d-'):
        assert run['split']=='dev' and run['categories']==['D']
        assert run['boundary_guards']=='true'
        assert run['code_sha256']['eval/checker.py']==protocol['checker_sha256']
        ds.append({**item,'correct':run['metrics']['correct'],'total':run['metrics']['total'],
            'fact_hits':sum(c['fact_hits'] for c in run['cases']),
            'fact_total':sum(c['fact_total'] for c in run['cases']),
            'cases':[{k:c[k] for k in ['question_id','correct','fact_hits','fact_total','termination','evidence']} for c in run['cases']]})
    else:
        assert run['before']==run['after'] and run['configuration']['BOUNDARY_GUARDS']=='true'
        cases=[{'id':c['id'],'question':c['question'],'expected':c['expected'],
                **review['cases'][c['id']],'evidence_audit':c['evidence_audit'],
                'termination':c.get('termination')} for c in run['cases']]
        bs.append({**item,'correct':sum(c['passed'] for c in cases),'total':len(cases),'cases':cases,
                   'business_snapshot_unchanged':True})
    contexts=[]
    for line in (ROOT/'logs'/run['source_log']).read_text(encoding='utf-8').splitlines():
        e=json.loads(line)
        if e['event']=='data_boundary_context':contexts.append({'question_id':e['question_id'],**e['payload']})
    item=(ds if label.startswith('step11-target-d-') else bs)[-1]
    item['injected_contexts']=contexts
    assert all(len(c['injected_lines'])==(2 if c['coverage_warning'] else 1) for c in contexts)
    if label.startswith('step11-target-d-'):assert not any(c['coverage_warning'] for c in contexts)
assert len(ds)==len(bs)==2 and len(all_ids)==36
adopted=acceptance([(r['correct'],r['total']) for r in ds],[(r['correct'],r['total']) for r in bs])
assert not adopted and FINAL_CONFIG['BOUNDARY_GUARDS']=='false'
tests={}
for name in ['step11_targeted_full_tests.xml','step11_targeted_offline_tests.xml']:
    s=ET.parse(ROOT/'evidence'/name).getroot().find('testsuite')
    tests[name]={key:int(s.get(key,0)) for key in ['tests','failures','errors','skipped']}
    assert tests[name]['failures']==tests[name]['errors']==0
logger,path=start_log('step11_targeted_selection')
summary={'source_log':path.name,'protocol_receipt':names[0].name,'new_model_calls':0,
    'candidate_adopted':adopted,'default_config':FINAL_CONFIG,'dimension_precheck':True,
    'boundary_review_method':review['method'],'boundary_review_file':review_name,
    'boundary_review_sha256':digest(ROOT/'evidence'/review_name),
    'checker_sha256':protocol['checker_sha256'],'scoring_sha256':protocol['scoring_sha256'],
    'D':ds,'boundaries':bs,'tests':tests,
    'frozen_holdout_unchanged':True,'further_tuning_or_model_runs':False,
    'tradeoff':'Restore Step 9 analytical prompts and numeric scanner; keep code dimension precheck and task controls. Boundary profile remains optional; historical holdout is not a new deployment score.',
    'finalizer_sha256':digest(ROOT/'logs/step11_targeted_finalize.py')}
record(logger,'selection',**summary)
summary['source_log_sha256']=digest(path)
receipt=write_evidence(path.stem+'.summary.json',summary)
lines=['\n## 本轮实测与选择\n',f'**未达到采用条件；默认回退 `BOUNDARY_GUARDS=false`，不再调参。** [选择与复核收据](../evidence/{receipt.name})，汇总日志 `{path.name}`。',
       '\n| 运行 | 通过 / 总数 | D 事实命中 | 日志及证据 |','| --- | --- | --- | --- |']
for item in ds+bs:
    facts=f"{item['fact_hits']}/{item['fact_total']}" if 'fact_hits' in item else '—'
    lines.append(f"| {item['label']} | {item['correct']}/{item['total']} | {facts} | [`{item['source_log']}`](../evidence/{item['receipt']}) |")
lines+=['\nD 采用同一个未修改的独立核查器。边界列是按预先 expected 的行为通过数，不等同于整篇答案所有语义均正确；独立数字核查结果逐题保留。',
        f'\n[运行前协议](../evidence/step11_targeted_protocol.json)和 [源码快照](../evidence/step11_targeted_source.zip)已固定；实际完成的 [协议收据](../evidence/{names[0].name})记录全部四次运行，日志 `{protocol["source_log"]}`。各轮新建独立用户与任务，没有重跑失败题。',
        '\n### 边界逐题复核\n','| 题目 | 行为判定 | 说明 |','| --- | --- | --- |']
for group in bs:
    for c in group['cases']:lines.append(f"| {c['id']} | {'通过' if c['passed'] else '未通过'} | {c['reason']} |")
lines+=['\n### D 仍失败的原因\n',
    '- 两轮 D02：下降金额符号/字段契约不一致；第二轮还有把跨 SQL 的值拼成单行对象、重复同一事实字段导致矛盾的问题。',
    '- 第二轮 D04：按季度行对象返回 avg_days，未使用公开要求的 q1_days/q2_days，实际查询数值正确仍未满足事实字段契约；短日期和换算常量也有门禁误替换。',
    '- 两轮 D06：核心金额在判分容差内，但额外阈值/跨查询结论未获直接证据支持；两轮还误把问题要求的全部订单换成知识库的排除状态口径，不能把数值命中等同口径正确。',
    '- 两轮 D07：核心事实正确；claim.text 中复购次数阈值没有作为 SQL 结果列，独立核查不豁免。',
    '\n回退只恢复已冻结的分析提示、工具接口和数字门禁路径，保留默认开启的维度预检及后台控制。没有另跑回退后的模型评测，也不宣称当前部署已经重新测得 Step 9 的成绩。可选增强有条件覆盖提示、澄清兜底和格式识别，但本轮数据显示不足以作为默认。',
    '\n### 工程验证\n',
    f"[完整测试 XML](../evidence/step11_targeted_full_tests.xml)：{tests['step11_targeted_full_tests.xml']['tests']} 项通过；[离线 XML](../evidence/step11_targeted_offline_tests.xml)：{tests['step11_targeted_offline_tests.xml']['tests']} 项通过。回退分支对照冻结 ZIP 核验系统提示、final_answer 契约与旧数字扫描结果；MCP 实连核验预检开启、未知值无业务结果、有效结果不增加字段。",
    '\n原始 holdout 收据、源码 ZIP、题库、既有迁移未改；没有 holdout 新运行或重新计分。费用未配置，未填写费用估算。']
with (ROOT/'docs/STEP11_TARGETED.md').open('a',encoding='utf-8',newline='\n') as f:f.write('\n'.join(lines)+'\n')
dtext='、'.join(f"{r['correct']}/{r['total']}" for r in ds)
btext='、'.join(f"{r['correct']}/{r['total']}" for r in bs)
decision=f'''\n## Step 11 审查：唯一一次定向修复与默认回退\n
**选择**：默认开启代码层维度预检，但不增加模型提示/工具定义/有效结果字段；撤销常驻全量覆盖 profile，仅在代码判定日期越界时注入一行说明，澄清规则只保留一句。运行前固定 D dev 两次、原/新边界各一次，同一核查器；所有失败照计，不再次调参。\n
**两组数据**：D 两轮分别 {dtext}；原/新边界行为复核分别 {btext}。行为评分沿用运行前 expected，Codex 检查保存回答，未增加评审模型、不是独立盲评；原始数值核查与逐题局限同时保留。全部运行日志及直接收据见 [完整定向验收](STEP11_TARGETED.md)，[选择汇总](../evidence/{receipt.name}) 的日志为 `{path.name}`。\n
**权衡与执行**：采用条件是两次 D 各至少 6/8、两个边界组各至少 8/10；本轮未达标，因此 `BOUNDARY_GUARDS=false` 恢复 Step 9 分析提示及旧门禁路径。缩短上下文仍未恢复多步任务表现，不能用原边界组的表现掩盖 D 或新边界组失败。增强作为可选开关保留；`DIMENSION_PRECHECK=true` 独立默认开启，任务取消/超时/额度、领取上限与迁移均不撤销。LIKE 模糊路径仍可能绕过等值预检，强制澄清也可能吞掉合法空结果，数字核查通过仍可能错误声称分页可取回截断后的全量数据。上述问题只记录，不继续修改。\n
**冻结边界**：无追加模型调用、无回退后的补测、无 holdout 重跑或重新计分。冻结成绩属于原 Step 9 运行，不能把恢复行为路径称为本次重新测得相同成绩。全部原始运行、核查器哈希和候选源码已归档；停止调参并交审。\n'''
with (ROOT/'docs/DECISIONS.md').open('a',encoding='utf-8',newline='\n') as f:f.write(decision)
with (ROOT/'README.md').open('a',encoding='utf-8',newline='\n') as f:
    f.write(f'\n唯一一次定向验收：D 两轮 {dtext}，原/新边界 {btext}，未达到采用条件，默认回退并停止调参。[选择证据](evidence/{receipt.name})，日志 `{path.name}`；逐题原因见 [定向验收](docs/STEP11_TARGETED.md)。\n')
print('Evidence:',receipt.name,flush=True)
