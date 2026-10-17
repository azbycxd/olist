"""Render Step 10 documents exclusively from saved receipts (no model calls)."""
import json
import hashlib
import re
from pathlib import Path
from config import ROOT
from eval.parameters import stats
from scripts.common import start_log, record
from scripts.evidence import write_evidence


def read_latest(pattern):
    path=sorted((ROOT/'evidence').glob(pattern))[-1]
    return path,json.loads(path.read_text(encoding='utf-8'))


def fmt(value):
    if value is None:return ''
    return str(value) if isinstance(value,int) else f'{value:.3f}'


def triple(d):return ' / '.join(fmt(d[k]) for k in ('p50','p95','max'))


def parameters():
    path,s=read_latest('step10_parameters_*.summary.json')
    final=s['final_config_cohort'];history=s['historical_mixed_config']
    lines=['# 参数依据与观测分布','',
        f'数据来源：[离线统计证据](../evidence/{path.name})，统计日志 `{s["source_log"]}`。收据包含逐题原始观测、每次运行配置、源日志文件名和 SHA-256；本次没有聊天模型或向量模型调用。',
        '',f'历史样本来自 {len(s["sources"])} 次真实评测、{len(s["cases"])} 次答题；排除 zero、重评分收据和 Step 10 新实验，按 task_id 去重。历史组混合了不同版本、参数与失败运行，仅用于观察负载边界，不能作效果对比。主表使用 Step 9 最终配置 dev 加三轮 holdout 的 {final["steps"]["n"]} 次原有记录，读取冻结结果不会产生新 holdout 运行。',
        '', '分位数用 nearest-rank：排序后取 ceil(n×p) 对应的观测。每次重复答题作为一个样本，不按题目先平均；缺失值排除并单列，不以零补齐。',
        '', '| 指标 | 最终配置 n / 缺失 | 最终配置 p50 / p95 / 最大 | 历史混合 n / 缺失 | 历史混合 p50 / p95 / 最大 |',
        '| --- | --- | --- | --- | --- |']
    names={'steps':'每题步数','tokens':'每题实际 token','peak_context_tokens':'每题上下文峰值 token',
           'sql_total_ms':'每题 SQL 调用耗时之和 ms','max_result_rows':'每题可见结果行数最大值',
           'sql_call_latency_ms':'每次 SQL 调用耗时 ms','sql_result_rows':'每次 SQL 返回行数'}
    for key,name in names.items():
        a,b=final[key],history[key]
        lines.append(f'| {name} | {a["n"]} / {a["missing"]} | {triple(a)} | {b["n"]} / {b["missing"]} | {triple(b)} |')
    lines+=['','口径：步数使用任务级 termination.steps，multi 是编排汇总步数，不能等同单角色上限。token 含本题偏好设置/抽取、摘要、门禁等 Agent 调用，不含 eval_judge；任一模型调用缺 usage 时整题 token 留空。上下文峰值来自模型实际返回的 prompt_tokens，超应用上限的那次调用也计入；应用是在调用后检查，不能保证请求发送前不超限。',
        '', 'SQL 耗时是 tool_result 的端到端调用时间，包含 MCP、网络、SQL 执行及结果保存，不是数据库执行计划的纯执行时间。并发 SQL 的每题求和不是墙钟耗时；无 SQL 调用时和为零。结果行数从历史工具返回元数据提取；错误或被日志截断的返回没有行数时留空。每题行数最大值只取可见返回，可能低估缺失返回。SQL LIMIT 后的行数不能表示原始全量规模。',
        '', '## 参数取值与依据类型','',
        '| 参数 / 当前取值 | 依据类型 | 依据与限制 |','| --- | --- | --- |',
        f'| MAX_STEPS=20 / 单角色 | 安全护栏、预先固定 | 最终组 p95={final["steps"]["p95"]}、max={final["steps"]["max"]}；历史 multi 汇总 max={history["steps"]["max"]}。不是根据 p95 搜索出的最优上限。 |',
        f'| TOKEN_BUDGET=100000 / 产品任务累计 | 安全护栏、预先固定 | 最终组 p95={final["tokens"]["p95"]}、max={final["tokens"]["max"]}。历史混合 max={history["tokens"]["max"]}，来自不同预算/版本；调用后才获 usage，不能解释为严格逐 token 费用封顶。config.py 通用回退为 50000，产品 FINAL_CONFIG/Compose 显式覆盖。 |',
        f'| CONTEXT_LIMIT=16000；压力测试=6000 | 安全护栏、预先固定 | 最终组 p95={final["peak_context_tokens"]["p95"]}、max={final["peak_context_tokens"]["max"]}，保留超限失败。它是应用停止阈值，不是模型窗口规格。 |',
        '| CONTEXT_STRATEGY=none；长任务选 mask | 观测数据 | [最终消融](FINAL_RESULTS.md)在同一压力窗口比较，正常窗口不默认压缩。 |',
        '| CONTEXT_KEEP_TURNS=2；CONTEXT_SUMMARY_THRESHOLD=6000 | 预先固定 | 历史压力组比较整个策略，没有单独搜索保留轮数或摘要阈值；summary 不是默认配置。 |',
        f'| SQL MAX_ROWS=1000；默认 preview=20；get_result limit≤1000 | 安全护栏、预先固定 | 最终 SQL 行数 p95={final["sql_result_rows"]["p95"]}、max={final["sql_result_rows"]["max"]}；历史 max={history["sql_result_rows"]["max"]}。完整聚合应在 SQL 内完成，不能将截断明细当作全量。 |',
        f'| statement_timeout=10s；lock_timeout=2s | 安全护栏、预先固定 | 最终端到端 SQL p95={fmt(final["sql_call_latency_ms"]["p95"])} ms、max={fmt(final["sql_call_latency_ms"]["max"])} ms；不是纯引擎耗时，不能据此声称最优 SQL 超时。 |',
        '| SQL 文本≤30000字符；结果≤2000000字节 | 安全护栏、预先固定 | 控制解析/序列化及上下文负载；未保存完整字节分布，不能宣称按观测推导。 |',
        '| MCP 超时=30s；DB connect_timeout=10s | 安全护栏、预先固定 | 覆盖连接/协议故障的等待边界；故障验证见 [工程边界](ROBUSTNESS.md)。 |',
        '| MODEL_TIMEOUT=60s；MODEL_MAX_OUTPUT_TOKENS=4096；temperature=0 | 安全护栏 / 预先固定 | 防止长等待、约束输出并减少随机性；未比较其他取值，不宣称调参最优。 |',
        '| 模型最多4次请求；退避1、2、4秒；SDK重试=0 | 安全护栏、预先固定 | 初次加三次重试；429故障测试分别验证恢复与耗尽。偏好抽取是另一组有界调用。 |',
        '| Embedding timeout=300s；SDK max_retries=2 | 安全护栏、预先固定 | 冷启动/CPU服务等待设置；连接拒绝与超时不同，宕机实验不证明最坏超时长度。 |',
        '| RAG=inject；RETRIEVAL_METHOD=vector；top_k=3 | 观测数据 / 预先固定 | 方法依据 [检索对比](REVIEW_COMPARISON.md)；top_k 预先固定，未做 k 搜索。 |',
        '| RRF k=60；BM25:vector 权重=0.25:1 | 预先固定 | 非默认候选；仅比较这些固定组合，样本为 C dev，未调到最优。 |',
        '| BAAI/bge-m3；revision 5617a9f61b028005a4858fdac845db406aefb181 | 预先固定、观测数据 | 用户指定独立容器、HF 镜像与 Docker 卷；固定修订的检索表现有证据，未切换小模型。 |',
        '| FINDING_MIN_SIMILARITY=0.78；最多3条 | 预先固定 | 下表有同题实际命中与已有 finding 向量对分布；异题检索误命中率缺数据，不能把阈值宣传为已校准。仅 multi 使用。 |',
        '| NUMBER_GATE=true；反馈重写1次 | 安全护栏、观测数据 | 重写次数预先固定，开启依据 [最终消融](FINAL_RESULTS.md)；仍有未验证数字替换和日期误报问题。 |',
        '| 数字核查相对误差1%、绝对值匹配 | 预先固定 | 容忍 SQL/报告精度差与“下降”表述；不验证因果、未知指标或真实零值的语义。 |',
        '| 相同工具调用连续3次停止 | 安全护栏、预先固定 | 防止循环调用，MCP中途宕机实验覆盖有界失败；不是模型正确率参数。 |',
        '| WORKER_LEASE_SECONDS=30；心跳=max(1,lease/4)秒 | 安全护栏、预先固定 | 原恢复演示验证过期租约接管；未优化心跳间隔，数据库不可达时不能保证即时持久化状态。 |',
        '| 最多3次实际领取；第四次尝试失败 | 安全护栏、预先固定 | Step 10 新增，含 planning/execute/recovery 全部租约；失败原因和拒绝次数进入事件，claim_count 只计实际发出租约。 |',
        '| 默认单 Agent + Memory偏好开启；multi 可选 | 观测数据 | [最终消融](FINAL_RESULTS.md)；single 不启用 finding 复用，不能将 multi 复用收益归于默认模式。 |',
        '', '## 结论复用相似度','',
        '| 对象 | 同题 n；p50 / p95 / 最大 | 异题 n；p50 / p95 / 最大 |','| --- | --- | --- |']
    for name,key in [('实际 query→finding 过阈值命中','accepted_match_distributions'),('已有 finding→finding 向量对（补充诊断）','stored_finding_similarity')]:
        ds=s[key] if key=='accepted_match_distributions' else s[key]['distributions'];a,b=ds['same_question'],ds['different_question']
        lines.append(f'| {name} | {a["n"]}；{triple(a)} | {b["n"]}；{triple(b)} |')
    lines+=['','历史读取日志只有通过阈值的候选，同题实际分布有选择偏差；异题候选及阈值以下分数从未记录，真实异题检索分布留空。补充诊断只读取 Step 7 首轮持久化的 question+claim 向量，两两算余弦，按原题相同/不同分组，不生成新向量；跨用户配对仅由离线评测器计算，不改变运行时用户隔离。该诊断不是 query→finding 分布，也不能估计线上误命中率。',
        '', '## 每题历史分布','', '下表覆盖所有历史题目，混合配置仅用于查负载，不用于比较成绩。单元格依次为 p50 / p95 / 最大；缺失计数、每次观测与源日志详见首部收据的 cases、sources 和 by_run。SQL 时间列为每题调用耗时之和，结果行数列为每题可见最大值。',
        '', '| 题目 | 答题次数 | 步数 | token | 上下文峰值 | SQL ms | 结果行数 |','| --- | --- | --- | --- | --- | --- | --- |']
    for q in sorted({c['question_id'] for c in s['cases']}):
        cases=[c for c in s['cases'] if c['question_id']==q];d=stats(cases)
        lines.append('| '+q+' | '+str(len(cases))+' | '+' | '.join(triple(d[k]) for k in ('steps','tokens','peak_context_tokens','sql_total_ms','max_result_rows'))+' |')
    lines+=['','## 最终配置主表的原始运行','']
    for src in s['sources']:
        tag=src['configuration']['tag']
        if tag=='step9-dev-final' or tag.startswith('step9-holdout-r'):
            lines.append(f'- [{tag}](../evidence/{src["receipt"]})：`{src["source_log"]}`。')
    (ROOT/'docs/PARAMETERS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def boundary():
    path,s=read_latest('eval_step10-boundary_*.summary.json')
    review=json.loads((ROOT/'eval/boundary_review.json').read_text(encoding='utf-8'))
    lookup={r['id']:r for r in review['cases']}
    assert set(lookup)=={c['id'] for c in s['cases']}
    rows=[]
    for c in s['cases']:
        row={**lookup[c['id']],'question':c['question'],'expected':c['expected'],'task_id':c['task_id'],
             'termination':c.get('termination'),'evidence_audit':c['evidence_audit'],'response_excerpt':str(c['response']['answer'])[:1200]}
        rows.append(row)
    write_calls=[]
    for c in s['cases']:
        for e in c['events']:
            if e['type']=='tool_call' and e['payload']['name']=='run_sql':
                args=e['payload']['input_summary']
                if isinstance(args,str):
                    try:args=json.loads(args)
                    except ValueError:continue
                if re.search(r'\b(DELETE|DROP|UPDATE|INSERT|ALTER|TRUNCATE)\b',args.get('sql',''),re.I):write_calls.append({'id':c['id'],'arguments':args})
    receipt_name='step10_boundary_review.summary.json'
    summary={'source_receipt':path.name,'source_receipt_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
             'model_run_log':s['source_log'],'reviewer':review['reviewer'],'standard':review['standard'],
             'cases':rows,'passed':sum(r['passed'] for r in rows),'total':len(rows),'new_model_calls':0,
             'write_attempts':write_calls,'business_row_counts_unchanged':s['before']==s['after'],
             'before':s['before'],'after':s['after']}
    target=ROOT/'evidence'/receipt_name
    if not target.exists():
        logger,log=start_log('step10_boundary_review');record(logger,'saved_response_review',**summary)
        summary.update(source_log=log.name,source_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        write_evidence(receipt_name,summary)
    else:
        old=json.loads(target.read_text(encoding='utf-8'))
        assert all(old[k]==v for k,v in summary.items()),'Saved review changed; preserve both versions explicitly'
        summary=old
    lines=['# 数据边界评测（独立于 holdout）','',
           f'使用最终配置，在运行前固定的 [边界题与期望行为](../eval/boundary_cases.json) 上各跑一次。按保存回答保守复核通过 **{summary["passed"]} / {summary["total"]}**；这是行为边界检查，不并入原业务题或 holdout 成绩。没有为改善本次结果重跑或修改 Agent 提示。',
           '',f'[运行前协议](../evidence/step10_boundary_protocol.json)；[真实运行收据](../evidence/{path.name})，日志 `{s["source_log"]}`；[逐项复核](../evidence/{receipt_name})，日志 `{summary["source_log"]}`。',
           '',review['reviewer']+'。'+review['standard'],
           '',f'配置：single、NUMBER_GATE=true、RAG inject、vector、Memory=true、context none。聊天模型 `{s["requested_model"]}`，向量模型 BAAI/bge-m3 固定 revision `5617a9f61b028005a4858fdac845db406aefb181`；完整运行身份见收据。实际模型调用 {s["usage"]["model_calls"]} 次，总 token {s["usage"]["total_tokens"]}；未配置单价，费用留空。一次题目运行包含其工具循环、一次可选门禁重写和偏好抽取。',
           '', '| 题目 | 预期行为 | 结果 | 观察 |','| --- | --- | --- | --- |']
    for r in rows:lines.append(f'| {r["id"]}：{r["question"]} | {r["expected"]} | {"通过" if r["passed"] else "未通过"} | {r["reason"]} |')
    lines+=['','## 数值与语义的边界','',
        'X03/X05 的 SQL 和数字证据成立，但业务问题仍未被合理回答。数值可溯源不能证明“不存在”就是“零”，也不能替代时间范围澄清。X02 的完整年度说法与数据终点直接矛盾，不能因为先承认数据不覆盖目标年份就算整题通过。',
        '', '数字门禁还会把时间戳、字符串分桶阈值、工具行数上限替换为“未验证”。独立核查器同时扫描 claim.text，告警不能一概解释成编造，也不能隐去。下表保留原始核查结果；边界通过不是整份报告无瑕疵的声明。',
        '', '| 题目 | 不支持的 claim / claim数 | 未匹配数字 / 扫描数字 | 其他局限 |','| --- | --- | --- | --- |']
    for r in rows:
        a=r['evidence_audit'];lines.append(f'| {r["id"]} | {a["unsupported_claims"]} / {a["claim_count"]} | {a["unsupported_numbers"]} / {a["report_number_count"]} | {r["caveat"]} |')
    facts=s['evaluator_boundary_facts']
    lines+=['',f'评测器独立确认：订单时间为 {facts["min_purchase"]} 至 {facts["max_purchase"]}；负 price 明细 {facts["negative_price_rows"]} 行；目标年份订单 {facts["orders_2017"]} 行。X09 明细返回为空，X10 明细只保存到接口上限；这几项校验值没有传给 Agent。',
        '',f'只读验证：运行前后订单均为 {s["before"]["orders"]} 行，取消订单均为 {s["before"]["canceled_orders"]} 行；记录到写 SQL 尝试 {len(write_calls)} 次。均来自上述真实运行收据。',
        '', '一次小样本检查不能估计生产环境失败率。仍保留不存在指标、未知维度、缺少时间范围、未来预测、因果和大结果集的产品边界，不把这些新结果回填到已冻结 holdout。']
    (ROOT/'docs/BOUNDARY_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def engineering():
    cp,c=read_latest('step10_concurrency_*.summary.json')
    faults=[read_latest('step10_fault_'+scenario+'_*.summary.json') for scenario in ('vector_down','mcp_midway','429_recovered','429_exhausted')]
    lines=['# 工程边界与故障实验','',
           '这些实验验证队列、资源和终止语义，独立于模型业务正确率及冻结 holdout。常驻 worker 在测试前停止，受控进程只竞争本批任务，结束后恢复常驻 worker。测试数据和用户有独立 ID，业务表不写入。',
           '', '## 两个 worker、六个真实模型任务','',
           f'[正式并发证据](../evidence/{cp.name})，日志 `{c["source_log"]}`。两个独立 Python worker 进程使用生产 claim/process；都尝试同一批任务 ID，领取 SQL 仍为 FOR UPDATE SKIP LOCKED。为了隔离实验，不领取不属于本批的用户任务。使用最终配置、真实配置模型与 bge-m3 固定 revision。',
           '',f'六个任务全部 completed，每个 claim_count=1，worker_claimed 事件不重复，观察到执行时间重叠；两个 worker 均有实际领取，所有租约清除。总墙钟耗时 **{c["wall_ms"]/1000:.3f} 秒**。本次未评估横向扩展吞吐上限。',
           '', '| 数据库观测 | 值 |','| --- | --- |',
           f'| max_connections / superuser_reserved_connections | {c["database"]["max_connections"]} / {c["database"]["superuser_reserved"]} |',
           f'| 采样间隔 / 样本数 | {c["database"]["sample_period_s"]} 秒 / {c["database"]["sample_count"]} |',
           f'| 初始连接 / 采样峰值 | {c["database"]["baseline"]["total_including_sampler"]} / {c["database"]["sampled_peak_client_connections_including_sampler"]} |',
           f'| 各角色独立峰值 | {json.dumps(c["database"]["peak_by_role"],ensure_ascii=False)} |',
           '', '计数包含采样连接和实验互斥锁连接；各角色峰值不一定同时出现。采样可能漏过短连接，不是瞬时精确上界。本规模未观察到逼近连接限制，因此未引入连接池；这个结论不适用于更多 worker 或慢查询场景。当前 MCP 在向量等待时仍可能持有数据库连接，扩容前需重新压测。',
           '', '首次并发试运行与边界评测重叠，保留 [试运行证据](../evidence/step10_concurrency_20261017T111018Z_f9155c08.summary.json)，日志 `step10_concurrency_20261017T111018Z_f9155c08.jsonl`，不用于正式耗时结论。随后工程脚本加入与 eval/run.py 共用的互斥锁，并在边界评测结束后独立运行上述正式实验。',
           '', '## 服务故障与 HTTP 429','',
           '向量实验实际停止 embeddings 容器，在 finally 中恢复并等待健康检查；[停止/恢复控制记录](../evidence/step10_vector_service_control.summary.json)，日志 `step10_vector_control.log`。MCP 实验启动独立的真实服务进程，首条 SQL 已持久化后杀掉该进程，避免破坏其他会话。',
           '', '429 用本地 HTTP 服务真实返回状态码，生产 OpenAI SDK、退避、runtime 子进程和 worker 均未替换。MCP 故障也用同一模型替身准确控制故障时点。替身返回的 usage 为合成零，仅用于状态机实验，绝不是模型性能、token 或费用证据。向量宕机路径未调用聊天模型。',
           '', '| 场景 | 任务终态 | 墙钟秒 | 已验证行为 | 证据 / 原始日志 |','| --- | --- | --- | --- | --- |']
    notes={'vector_down':'检索失败即终止，无聊天调用；真实容器已恢复。','mcp_midway':'保留第一条 SQL，随后传输异常，干净失败；私有 MCP 进程被杀。',
           '429_recovered':'连续两次 429，退避后第三次主调用成功；偏好抽取另成功一次。',
           '429_exhausted':'主调用最多四次；后续偏好抽取也有独立四次上限，最终 model_error。'}
    for p,s in faults:
        lines.append(f'| {s["scenario"]} | {s["task"]["status"]} | {s["wall_ms"]/1000:.3f} | {notes[s["scenario"]]}租约清除，再次领取为空。 | [收据](../evidence/{p.name})；`{s["source_log"]}` |')
    lines+=['','这里的干净终止指数据库进入终态、租约字段清除、子进程退出且不能重复领取；服务恢复不会自动重试已经 failed 的任务。连接拒绝和传输中断不等于超慢服务，未声称覆盖最长网络超时、数据库宕机或所有组合故障。',
           '', '## 毒任务上限与回归','',
           '任务最多发出三次租约，规划和执行都计入。若第三次后又出现 pending 或租约过期，下一次领取尝试原子地置 failed，清除租约，并写入 claim_limit_exceeded、attempted_claim=4 和上限。第四次不会执行模型，claim_count 保持实际发出的租约数。全队列领取继续寻找下一条，毒任务不会永远挡住队列。该逻辑复用已有字段，不修改已执行迁移。',
           '', '[领取/API 测试](../evidence/step10_queue_tests.xml)，日志 `step10_queue_tests.log`：包括 single/multi 三次领取、并发第四次拒绝、旧租约失效及 pending 耗尽场景。',
           '', '[主测试集](../evidence/step10_full_tests.xml)，日志 `step10_full_tests.log`；[MCP 实连测试](../evidence/step10_mcp_tests.xml)，日志 `step10_mcp_tests.log`。主测试中未启用的 MCP 项在后一收据中单独执行。首次实连命令使用错误文件名、没有执行测试的 [原始 XML](../evidence/step10_live_mcp_tests.xml) 和 `step10_live_mcp_tests.log` 保留，不计为通过。',
           '', '生产行为只新增了领取次数上限，以及领取事件中的 worker 标识/计数。提示、模型循环、知识口径、检索、数字门禁和 gold 未为边界题改动；新队列上限可能使连续崩溃任务更早失败，但不改变已保存的 Step 9 非后台评测结果，未重跑 holdout。']
    (ROOT/'docs/ROBUSTNESS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


if __name__=='__main__':
    import argparse
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--all',action='store_true');args=parser.parse_args()
    parameters()
    if args.all:boundary();engineering()
