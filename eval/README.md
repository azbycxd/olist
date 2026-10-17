# 评测协议

## 题目与划分

`questions.jsonl` 由 `generate_questions.py` 确定性生成。A/B/D 为手写 SQL，C/E 使用可逐条核对的 `templates.py`。分组为 A/B/C/D/E 各 10/10/25/12/10 题，共 67 题；dev 45 题，holdout 22 题。C 的每个模板都有 holdout，使用不同的业务自然问法；两个划分都不得在题干提示去重、运费或状态口径。模板 ID、参数、画像来源及私有 `naive_sql` 保留在题库中。

```powershell
docker compose run --rm init-data python eval/validate_gold.py
docker compose run --rm init-data python eval/run.py --tag zero-smoke --categories C,D --split dev
```

更改模板后运行 `python eval/generate_questions.py`，并重新执行全部 gold SQL 验证。验证器检查 SQL 可执行、结果形状与非空事实；对每道 C 题在同一个只读快照内执行 gold 和 naive SQL，要求标准答案非零，且 `abs(naive-gold)/abs(gold) >= 1%`。不合格时记录拒绝原因并返回非零退出码，必须替换参数或剔除后重新生成、验证，不能带着失败题进入评测。每道题的两条 SQL、两个答案、绝对／相对差异、参数与判定写入 `evidence/validate_gold_*.summary.json`，并注明原始日志名与哈希。

陷阱验证是题库质量检查，不代表人工已经确认业务正确，也不是模型评测或 RAG 效果证明。holdout 的 SQL 验证只用于数据集构建与审查，不用于调模型；Step 1 不运行 holdout 模型评测。选择差异足够大的时间和地区会让题库偏向容易观察的陷阱，不能据此推断自然业务流量中的错误率。Agent 可读取的 C 类口径只在后续 Step 4 知识库中提供；不得提前写入题干或系统提示。时间参数在 SQL 中左闭右开，题干将结束日换成前一天以便业务人员阅读。

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

归因 rubric 在 `judge.py`，范围为 1–5，要求区分观测、假设和因果。当前没有模型调用，因此未获得归因分数；[人工检查清单](HUMAN_REVIEW.md)尚待用户完成，不宣称模型评分已校准。

输入／输出 token 使用响应 usage，缺失时总 token 与费用都留空。费用只按用户确认的 `EVAL_INPUT_PRICE_PER_MILLION`、`EVAL_OUTPUT_PRICE_PER_MILLION` 计算，不抓取或猜测单价；服务端缓存和阶梯价格需要相应更精确的计价器，当前记录为按配置单价计算的费用。没有模型调用的 zero 运行 token 与模型费用都为零。判分、gold SQL 验证和数据库查询的 CPU／托管费用不计入模型费用。

## 留存与重复运行

每次运行创建唯一日志名、用户和任务，保存数据版本、题库哈希、代码哈希、依赖版本、逐题判定与汇总。完整日志在 `logs/`；每次实跑都把汇总 JSON 写到 `evidence/`，包含原始日志文件名和 SHA-256，再由同一脚本追加 `docs/RESULTS.md`。全局数据库锁串行化评测，避免同时追加同一文件。相同 tag 可以重复使用，每次都有独立 run_id 和文件名，不覆盖旧结果。

未运行指标使用 JSON null、Markdown 空白。SQL 验证和单元测试不写入 RESULTS；合成测试数据也不会成为模型评测成绩。下一步接入真实 Agent 时只替换适配器，保持标准答案、独立核查器及分母一致。
