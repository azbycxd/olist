# 评测协议

## 题目与划分

`questions.jsonl` 由 `generate_questions.py` 确定性生成。A/B/D 为手写 SQL，C/E 使用可逐条核对的 `templates.py`。分组为 A/B/C/D/E 各 10/10/25/12/10 题，共 67 题；dev 45 题，holdout 22 题。C 的每个模板都有 holdout，使用不同的业务自然问法；两个划分都不得在题干提示去重、运费或状态口径。模板 ID、参数、画像来源及私有 `naive_sql` 保留在题库中。

```powershell
docker compose run --rm init-data python eval/validate_gold.py
docker compose run --rm init-data python eval/run.py --tag zero-smoke --categories C,D --split dev
```

更改模板后运行 `python eval/generate_questions.py`，并重新执行全部 gold SQL 验证。验证器检查 SQL 可执行、结果形状与非空事实；对每道 C 题在同一个只读快照内执行 gold 和 naive SQL，要求标准答案非零，且 `abs(naive-gold)/abs(gold) >= 1%`。不合格时记录拒绝原因并返回非零退出码，必须替换参数或剔除后重新生成、验证，不能带着失败题进入评测。每道题的两条 SQL、两个答案、绝对／相对差异、参数与判定写入 `evidence/validate_gold_*.summary.json`，并注明原始日志名与哈希。

陷阱验证是题库质量检查，不代表人工已经确认业务正确，也不是模型评测或 RAG 效果证明。holdout 的 SQL 验证只用于数据集构建与审查，不用于调模型；Step 1 不运行 holdout 模型评测。选择差异足够大的时间和地区会让题库偏向容易观察的陷阱，不能据此推断自然业务流量中的错误率。Agent 可读取的 C 类口径只在后续 Step 4 知识库中提供；不得提前写入题干或系统提示。时间参数在 SQL 中左闭右开，题干将结束日换成前一天以便业务人员阅读。

按用户要求，C、E 模板和 D 标准答案的人工核对改为独立 CSV 交叉验证，同时覆盖 A、B 全部题目。`cross_check.py` 用 pandas 从原始文件独立计算，不连接数据库、不执行或导入 gold SQL，只使用题号、模板 ID 和参数。SQL 答案从上一步 `validate_gold.py` 保存的 `gold_value` 读取；两边必须具有相同题库哈希和源数据版本，CSV 计算结束后再核验文件未改变。每题比较结果（含两边原值和差异）写入 evidence，并更新 [HUMAN_REVIEW.md](HUMAN_REVIEW.md)。发现不一致只列题号和差异并返回非零，不自动修改 gold。

```powershell
$gold = (Get-ChildItem evidence/validate_gold_*.summary.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
docker compose run --rm --entrypoint python -v "${PWD}/eval:/app/eval" init-data eval/cross_check.py --gold-evidence "evidence/$gold"
```

覆盖 entrypoint 是为了不执行初始化迁移；绑定 eval 目录用于保留自动生成的 HUMAN_REVIEW.md。数值相对误差不超过 1% 判一致，零值绝对容差为一亿分之一，列表按集合比较，复合事实逐字段比较。真实运行 [67 / 67 一致](../evidence/cross_check_20261017T070428Z_accb136c.summary.json)，原始日志 `cross_check_20261017T070428Z_accb136c.jsonl`；这是标准答案计算核验，不是模型评分校准。

## 统一输出与防止答案泄漏

`contracts.FinalAnswer` 只有 `answer` 和 `claims`；每条 claim 必须有 `text`、JSON 类型的 `value`、`evidence`（真实 UUID result_id 列表）。number 的 answer 是单个数值或严格数值字符串；list 的 answer 是 JSON 数组；key_facts 的 answer 是报告文本，claim.value 用对象将事实名绑定到值。`required_facts` 告诉适配器所需字段名，不包含标准值。

`PublicCase` 仅传问题、输出类型、事实字段名、用户与任务标识，以及 E 类前序用户原话和新会话标记。适配器看不到 gold SQL、naive SQL、标准答案、模板／参数元数据、split 或评分 rubric。标准查询由评测器独立执行，只写入评测日志和汇总，不写到 Agent 的 `query_results`，避免伪造 Agent 查证。

E 类每题使用不同用户；偏好设置和后续提问使用不同任务，同一用户贯穿两个任务。后续适配器应先处理 setup_turns，再清空会话历史，只通过该用户的长期记忆影响新会话。当前 zero 夹具只记录会话阶段并始终返回零，不写记忆，也不代表 Memory 已实现。

## 独立核查与正确率

`checker.py` 不导入任何 Agent、MCP 服务或运行时 Reviewer。它直接查询 `query_results`，核对引用存在、任务归属、数据版本和 value 支撑关系。对象中的标签和值必须在同一结果行里匹配，避免把一个州的数字移到另一个州。标量数字必须真实出现在结果单元格；数字匹配仅保留浮点表示误差容限（相对百万分之一，绝对一亿分之一）。证据比例按所有 claim 的数量计算；没有 claim 时为未定义，不能当作零幻觉。

number 正确率允许相对误差不超过 1%；标准值为零时只允许绝对一亿分之一的表示误差。list 比较规范化后的集合，不能靠返回包含标准答案的大集合得分。D 类分别记录关键事实命中率、报告中无证据数字比例及独立模型归因评分。事实必须用要求的字段名绑定，矛盾重复 claim 不得分；D 类的“整题正确”要求全部事实命中、非空 claims、所有 claims 有证据、没有未落地的报告数字。模型归因分数单列，不混入这一确定性正确率。

报告扫描覆盖 answer 与 claim.text，包括未声明为 claim 的数字。排除标准日期、带“年”的年份、Q 季度标签和列表序号；支持千分位、科学记数法及千／万／亿单位。报告显示数字按绝对值匹配，相对误差允许 1%，使 SQL 中的负数可以写成“下降／减少”加正数幅度；结构化 claim.value 仍必须保留 SQL 的符号与查询精度。所有报告业务数字（包括差值、比率、百分数）必须由 SQL 计算并引用，Agent 不得自行计算。百分数应由 SQL 转为百分数单位，不能把比例小数直接当百分数匹配。报告中的业务数量统一使用阿拉伯数字。按绝对值匹配只核验幅度，方向语义仍需审核者或人工检查。

限制：数值存在并不能证明 SQL 的业务口径或文字归因正确，中文数字写法和隐含单位也无法靠当前词法扫描完全核实。运行时 Reviewer 后续另行实现；评测必须保留人工抽查，不把数值核查称为语义证明。没有数字的空泛回答不会获得 D 类事实信用。

## 模型归因评分与费用

`--judge off|model` 控制独立归因评分，默认 off。启用前在 `.env` 配置 OpenAI 兼容服务的 `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`EVAL_JUDGE_MODEL`（或 `OPENAI_MODEL`）。调用固定 `temperature=0`，记录请求模型、响应模型、可取得的 backend fingerprint、用量、耗时、输入／输出摘要与错误；未提供模型版本或用量时保持未知，不能填估算值。SDK 自动重试关闭，避免未记录的隐式调用。参数与用量字段依据 [官方 Chat Completions 文档](https://developers.openai.com/api/reference/resources/chat)。零温度不能保证不同服务端版本完全可复现。

归因 rubric 在 `judge.py`，范围为 1–5，要求区分观测、假设和因果。Step 2 已运行真实 Agent A/B 基线，但未运行 D 类归因评分；[交叉验证与校准状态](HUMAN_REVIEW.md)明确区分计算核验和待做的模型评分校准。

输入／输出 token 使用响应 usage，缺失时总 token 与费用都留空。费用只按用户确认的 `EVAL_INPUT_PRICE_PER_MILLION`、`EVAL_OUTPUT_PRICE_PER_MILLION` 计算，不抓取或猜测单价；服务端缓存和阶梯价格需要相应更精确的计价器，当前记录为按配置单价计算的费用。没有模型调用的 zero 运行 token 与模型费用都为零。判分、gold SQL 验证和数据库查询的 CPU／托管费用不计入模型费用。

## 留存与重复运行

每次运行创建唯一日志名、用户和任务，保存数据版本、题库哈希、代码哈希、依赖版本、逐题判定与汇总。完整日志在 `logs/`；每次实跑都把汇总 JSON 写到 `evidence/`，包含原始日志文件名和 SHA-256，再由同一脚本追加 `docs/RESULTS.md`。全局数据库锁串行化评测，避免同时追加同一文件。相同 tag 可以重复使用，每次都有独立 run_id 和文件名，不覆盖旧结果。

未运行指标使用 JSON null、Markdown 空白。SQL 验证、CSV 交叉验证和单元测试不写入 RESULTS；合成测试数据也不会成为模型评测成绩。single 适配器复用已有标准答案、独立核查器及分母，不根据真实模型表现放宽判分。

## Step 2 真实模型与第三方客户端

`--adapter single --schema-mode full|on_demand` 调用 `agent/loop.py`。评测器只将公开问题和输出约定送入独立子进程；该进程环境按白名单构造，去除所有数据库凭据并禁止 dotenv 加载。MCP 服务负责业务查询和结果持久化；评测器仍独立执行 gold 和核查证据。`--judge off` 只关闭评分模型，不能关闭 single 的 Agent 调用。E 的前置偏好尚待 Step 5，single 暂时明确拒绝 E，不伪装成已经支持记忆。

```powershell
docker compose run --rm init-data python eval/run.py --adapter single --schema-mode full --tag baseline-full --categories A,B --split dev --judge off
docker compose run --rm init-data python eval/run.py --adapter single --schema-mode on_demand --tag baseline-on-demand --categories A,B --split dev --judge off
```

两组真实记录分别为 [full](../evidence/eval_baseline-full_20261017T070736Z_def8c3a7.summary.json)、[on_demand](../evidence/eval_baseline-on-demand_20261017T070828Z_4dd93f3c.summary.json)，对应同名 `.jsonl` 原始日志。A/B 正确率比较 answer，证据支持率独立报告；本次两组均答对全部题，但都有被拒绝的 claim，详见 README 和 DECISIONS。

官方 MCP Inspector CLI 可独立验证本服务（先安装 Node.js；本次固定 Inspector 1.0.2）：

```powershell
docker compose run --rm init-data python -m scripts.inspector_demo prepare
$cfg = Get-Content logs/inspector.private.json -Raw | ConvertFrom-Json
$inspectorLog = 'inspector_call_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json'
npx.cmd --yes @modelcontextprotocol/inspector@1.0.2 --cli http://localhost:8001/mcp --transport http --method tools/call --tool-name run_sql --tool-arg 'sql=SELECT COUNT(*) AS orders FROM orders' --header ('Authorization: ' + $cfg.mcpServers.olist.headers.Authorization) --header ('X-Task-ID: ' + $cfg.mcpServers.olist.headers.'X-Task-ID') > "logs/$inspectorLog"
docker compose run --rm init-data python -m scripts.inspector_demo verify --response "logs/$inspectorLog"
```

`prepare` 创建运行中任务并将鉴权配置仅写入忽略的 logs。`verify` 对照实际持久化结果，完成任务并生成不含 token 的 evidence 摘要。UI 连接时使用相同两个请求头；来源、传输类型、SQL、结果 ID 和截图见 [真实界面证据](../evidence/inspector_ui_20261017T071031Z_4d025329.summary.json)。

## 上下文实验与重核

`--context-strategy none|mask|summary --context-limit 16000` 在 D dev 上比较原始历史、省略、模型摘要。每个 model_call 的真实 usage 和每轮 context_usage 保存在日志与汇总；摘要调用包含在总用量中。工具结果取回和笔记区不授予数据指令权限。

`--recheck-evidence evidence/<原始汇总>.summary.json --tag <新标签>` 不调用模型：验证题库哈希和数据版本，重新执行 gold SQL，用原始响应及原任务的持久化结果重新评分。新收据保留原收据哈希和评分代码哈希；记录的模型用量、模型调用和题目耗时均来自原始运行，不是新增消耗。此入口用于修复行对象数组的事实读取，不能更改 gold，也不能将重核行与原行的 token 相加。
