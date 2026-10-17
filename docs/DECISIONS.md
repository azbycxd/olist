# 设计决策

## 业务库与 Agent 库隔离

**问题**：分析系统需要写任务、证据和记忆，但不能修改业务数据。

**方案**：只在提示词中限制写入；共享数据库并区分 schema；拆成业务库与 Agent 库并分配不同角色。

**选择**：同一 PostgreSQL 实例内建立 `olist` 和 `agent`。`agent_ro` 仅能连接业务库并 SELECT，默认只读事务和查询超时作为额外保护；`agent_app` 仅能连接 Agent 库。数据库初始化及导入使用管理账号。后续 MCP 服务持有业务只读凭据。数据库账号仍可调整会话超时，因此后续 SQL 语法校验必须拒绝 SET 等非查询语句。

**数据**：真实数据库验收已验证跨库连接限制，以及关闭会话只读设置后 DELETE 仍被数据库 ACL 拒绝；见 [pytest XML](../evidence/step0_pytest_20261017T061031Z.xml)。原始日志为 `step0_pytest_20261017T061031Z.log`。模型效果对比尚未运行，留空。

## 先固定任务、事件、证据与记忆的核心结构

**问题**：后续核查器、Agent 循环、多智能体与任务恢复都依赖相同的数据引用。

**方案**：各步骤临时存文件；每步独立设计表；先确定最小公共结构，再按后续步骤做迁移。

**选择**：建立 `users`、`tasks`、`events`、`query_results`、`memories`。任务归属用户；事件以任务内 `seq` 唯一排序，应用角色没有修改或删除事件的权限，触发器同时阻止 UPDATE、DELETE、TRUNCATE；查询结果以 UUID `result_id` 保存 SQL、完整 JSON 结果和数据版本，并约束实际结果长度等于行数。记忆先只建空表，向量和结论复用以后添加。模型调用的输入摘要、输出摘要、模型名和版本放在事件 `payload` 中，token 与耗时使用独立列。

**数据**：真实数据库测试已通过表结构、证据读写及事件不可变性检查；见 [pytest XML](../evidence/step0_pytest_20261017T061031Z.xml)，原始日志为 `step0_pytest_20261017T061031Z.log`。效果与恢复能力的对比尚未运行，留空。

## 保留源数据粒度和缺失值

**问题**：源数据的邮编、评价标识并非都唯一，部分品类没有翻译。

**方案**：按看起来像 ID 的列去重并丢掉异常；使用源数据中真实有效的键并保留所有行。

**选择**：客户、订单、商品、卖家保留源主键；商品明细和支付用订单加序号；评价使用 `(review_id, order_id)`；地理位置使用代理主键以保留重复记录。不对邮编或品类翻译强建外键，否则会删除有效源数据或使导入失败；订单到客户、明细到订单／商品／卖家、支付与评价到订单均有外键。金额使用精确十进制，时间使用不带时区的 timestamp，CSV 空字段保留 NULL。源字段的 `lenght` 拼写保持不变。

**数据**：真实导入后的行数、客户标识差异、缺失品类和关联膨胀结果见自动生成的 [数据画像](data_profile.md)，所有查询与结果记录在其标注的日志中。这里不写未经评测的效果数字。

## 导入事务与可追溯性

**问题**：中途失败或重复启动不能留下半份数据，也不能无提示覆盖现有业务库。

**方案**：每张表单独提交；每次启动清空重导；全量事务导入并记录源文件哈希。

**选择**：先检查全部文件和表头，记录 CSV 记录数与 SHA-256；表结构先通过迁移建立，数据导入事务完成 COPY、外键检查、行数检查与导入清单落库。导入后再核验文件哈希。使用事务级 advisory lock 串行化导入。相同清单与行数跳过重复导入；已存在且不同的数据必须显式 `--replace` 才替换。该快速跳过依赖业务表只读，不能证明管理员从未修改过同等行数的数据。画像在只读的一致性快照中查询，并将 SQL、结果、源数据版本与日志文件名一起保留。

**数据**：[首次导入摘要](../evidence/load_olist_20261017T061005Z_cb15c045.summary.json)记录提交成功；[重复导入摘要](../evidence/load_olist_20261017T061052Z_251dff07.summary.json)记录 `already_loaded`，行数和数据版本一致。摘要记录对应原始日志的文件名与哈希。模型评测尚未运行，留空。

## 编号迁移与版本化证据

**问题**：容器初始化 SQL 不会在已有数据卷上重复执行；只存在本机日志中的验收无法随代码复查。

**方案**：手工 ALTER、每次重建数据库；或使用带校验的有序迁移，并将小型运行证据提交到 Git。

**选择**：初始 Agent 表迁至 `001_agent_core.sql`，业务表迁至 `002_olist_core.sql`。每次导入前自动执行未完成迁移，已执行文件的哈希必须匹配。目标库内 DDL 与执行收据同事务提交，业务库的收据随后镜像至 Agent 库，以支持提交间隙退出后的恢复。后续结构变更只能新增迁移。`evidence/` 版本化保存运行摘要与测试 XML，不保存原始数据、密码或大日志。

**数据**：初始真实验收证据已从旧日志提取，保留日志文件名与 SHA-256；[升级验收 XML](../evidence/step0_migrations_20261017T062040Z.xml)验证全新数据库、幂等重跑、迁移失败回滚、历史文件变更拒绝及跨库收据恢复。

## dev／holdout 与可审查的参数化题库

**问题**：题目太少使结果不稳定；对同一批题调提示词后直接报告成绩会高估效果；人工逐题手写容易出现口径不一致。

**方案**：少量示例题；随机每次重划分；固定分层划分，结合手写题与可独立重算的参数模板。

**选择**：固定题库、模板 ID、参数与 split。C 类来源于真实数据画像，dev／holdout 均用不泄露口径的业务自然问法，holdout 改换措辞。每个 C 模板增加私有 naive SQL；在真实快照中逐题比较，标准答案为零或相对差异不足百分之一时替换参数或剔除。Step 1 修订曾用实际数据替换状态、签收缺失、评价粒度模板的参数，保留题数与划分；这会偏向可观察的陷阱，不能据此推断自然业务流量的错误率。E 类明确前序用户原话与新会话边界。被测适配器只获得公开问题信息，不能获得 gold／naive SQL、模板元数据或答案；Agent 所需的 C 类口径留到 Step 4 知识库提供。holdout SQL 执行只用于题库质量审查，不用于调模型。按用户后续要求，模板和 D 类标准答案改用独立原始 CSV 交叉验证，见下文；本次没有修改 gold。

**数据**：[修订后的 SQL 与陷阱验证摘要](../evidence/validate_gold_20261017T064243Z_88d30427.summary.json)逐题记录两条 SQL、实际答案、差异与判定，并绑定题库哈希及数据版本；原始日志为 `validate_gold_20261017T064243Z_88d30427.jsonl`。尚无真实模型的 dev／holdout 对比数据。

## 统一输出与独立证据核查

**问题**：单／多 Agent 输出不同无法公平比较，运行时 Reviewer 给自己的系统打分会产生偏差，报告中堆数字也可能碰巧命中标准值。

**方案**：用字符串搜索 gold 数字；让被测模型自己评价；或使用共享数据协议、独立 SQL oracle 与独立证据核查器。

**选择**：共享的 `contracts.py` 只有输出类型定义，不含评分逻辑。独立 checker 直接读 `query_results`，核对引用存在、任务、数据版本与值；标签和值须在同一结果行中对应。number 只接受单个数值，list 要求集合一致；D 要求字段绑定的关键事实，并扫描完整报告中的额外数字。D 的确定性整题判分同时要求事实齐全与证据支撑，归因质量由独立 rubric 模型单列评分。没有 claim 或没有数字时相应比例未定义，不伪装成零。数值核查不能代替 SQL 语义与因果正确性检查。

**数据**：[真实 PostgreSQL 与核查器测试](../evidence/step1_revision_pytest_20261017T064436Z.xml)覆盖伪造证据、错任务、旧版本、错配字段、数字堆砌及误差边界；原始日志为 `step1_revision_pytest_20261017T064436Z.log`。[修订后固定零回答实跑汇总](../evidence/eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.summary.json)由 `eval/run.py` 产生，记录正确题数、所有判分分母和无证据比例；原始日志为 `eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.jsonl`。只用于链路验收，不用作模型效果结论；旧题库实跑证据仍保留。

## 报告数字全部来自 SQL，文字方向与数值幅度分开核验

**问题**：报告常将 SQL 的负数写成“下降／减少”加正数幅度，直接带符号匹配会误报；如果 Agent 自算差值或比率，核查器就无法在查询结果中定位它们。

**方案**：核查器自行推导所有可能的算式；放宽为任意数字相近即可；或要求全部数字落在 SQL 结果中，仅对报告文本使用绝对值匹配。

**选择**：报告中出现的所有业务数字（包括差值、比率、百分数）必须由 SQL 计算得到，保存到 `query_results` 并由 claim 引用，Agent 不得自行计算。这是核查器判定的基础：核查器核对已存结果，不替 Agent 算数。结构化 `claim.value` 保留 SQL 的符号与精度；报告 answer 和 claim.text 的数字按绝对值与已验证 claim 匹配。百分数单位转换也由 SQL 完成。仅有参与运算的原数，不能为未查询的差值或比率提供证据。绝对值匹配不能验证“增长／下降”方向是否正确，方向仍需语义审核和人工抽查。

**数据**：[回归测试 XML](../evidence/step1_revision_pytest_20261017T064436Z.xml)覆盖下降、减少、负环比、中文“负”与负金额单位写法，并验证错误幅度、无引用、自算差值和比率仍被拒绝；原始日志为 `step1_revision_pytest_20261017T064436Z.log`。没有据此推断模型准确率提升。

## 未观测指标与模型评分校准

**问题**：缺失的模型 usage、价格或评分容易被“合理估计”掩盖，温度为零也不能保证服务端版本变化后的结果相同。

**方案**：填默认 token／价格／分数；或明确保留未知值并记录配置、代码、数据与模型返回信息。

**选择**：`--judge off|model` 显式控制评分，默认关闭。调用固定 temperature 为零，记录响应模型和能取得的 backend fingerprint；未取得的版本或用量保持未知。没有任何模型请求时 token 与模型费用为真实的零；有调用但 usage 或单价缺失时相应汇总为空。每次运行先写不可覆盖的 JSON 证据，再由脚本追加 RESULTS；汇总携带原始日志名、哈希、逐题判定、代码及依赖版本。归因评分校准仍未完成，不能把模拟响应单测或 CSV 计算一致性当成真实模型评分校准。

**数据**：实际运行的模型归因分数为未运行，见 [评测结果](RESULTS.md) 的空白单元格。人工评分与模型评分的一致性尚无数据，留空。

## 用原始 CSV 独立重算标准答案

**问题**：gold SQL 能执行并不证明聚合粒度、去重和时间口径正确；人工签认难以自动复现。

**方案**：重复执行同一条 SQL；使用另一个 SQL 引擎重放；或根据题意另写 pandas 计算器，从原始 CSV 独立求值，再与 SQL 收据比较。

**选择**：采用最后一种。计算器不导入 SQL 模板、数据库驱动或评分代码，只读取题号、模板标识和参数；关联主要通过键映射与集合成员筛选实现，支付膨胀通过支付频次加权独立推导。先由 validate_gold 保存所有标准值，再让 cross_check 在不执行迁移的独立命令中读 CSV。比较时校验题库哈希和数据版本；每题两种答案、差异、计算器哈希和 pandas 版本写入 evidence，C/E/D 的 HUMAN_REVIEW 条目记录真实结果。数值允许百分之一相对误差，非数值按结构和集合比较；不一致只报告，不自行改 gold。数学一致不能证明题意、口径定义和归因语义正确。

**数据**：全部 67 题一致，不一致列表为空，见 [交叉验证摘要](../evidence/cross_check_20261017T070428Z_accb136c.summary.json)，原始日志 `cross_check_20261017T070428Z_accb136c.jsonl`。题库和 gold SQL 均未改变；该摘要绑定提供标准答案的 SQL 验证文件及其哈希。

## 手写循环、统一工具与凭据隔离

**问题**：模型需要多步查证、修正工具错误并有限地停止；内嵌业务数据库驱动会让模型运行进程同时持有数据库权限，数据源也难以替换。

**方案**：采用 Agent 框架；直接把 SQL 函数绑定给模型；或手写循环，并通过官方 MCP 服务分离数据访问。

**选择**：手写消息循环和工具注册表，远程工具由 list_tools 动态发现，本地 final_answer 同样通过注册表执行；循环不区分工具来源。同轮工具并行，工具错误以观察结果返回，模型调用初次失败后按指数退避重试三次，每次尝试均留事件。默认最多二十轮，另外由 final_answer、累计 token 预算和连续重复工具调用终止。预算依据实际 usage 判断，最多可能越过一个已发出的请求；缺 usage 时明确失败，不能声称精确限制了尚未观测的输入 token。

模型进程仅有模型和 MCP 环境配置，dotenv 禁用，既无业务数据库凭据也无直接查库工具。CLI／离线评测器管理任务与事件，MCP 容器持有业务只读和 Agent 结果写入凭据，初始化／离线验证工具按职责保留数据库权限。Bearer 是内部服务鉴权，X-Task-ID 来自运行器并要求任务处于 running；它尚不是跨用户授权机制，登录和逐用户访问控制留到 Step 8。实现依据 [官方 MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x) 和 [官方工具调用文档](https://developers.openai.com/api/docs/guides/function-calling)。

**数据**：[真实 CLI 证据](../evidence/ask_20261017T065752Z_b426c568.summary.json)记录模型调用、SQL 结果 ID 与最终答案，原始日志 `ask_20261017T065752Z_b426c568.jsonl`。[完整验收 XML](../evidence/step2_pytest_20261017T070651Z.xml)为 134 passed，原始日志 `step2_pytest_20261017T070651Z.log`，覆盖并行、四类终止、错误恢复和凭据环境隔离。第三方 [Inspector 命令行验收](../evidence/inspector_20261017T070435Z_e3c0a23e.summary.json)及[界面验收与截图哈希](../evidence/inspector_ui_20261017T071031Z_4d025329.summary.json)证明服务可被独立标准客户端调用，不依赖本项目 Agent 封装。

## SQL 白名单、限行结果与不可信数据边界

**问题**：提示词无法阻止破坏性 SQL，数据库文本也可能包含诱导指令；大量结果会耗尽上下文。

**方案**：关键词过滤和提示词限制；或 AST 校验、数据库权限及超时共同限制，再将结果预览与证据存储分开。

**选择**：sqlglot 解析后仅接受单条 SELECT／只读 CTE／集合查询；按实际作用域解析 CTE 引用，限制真实表、函数和转换类型，拒绝写入、系统表、文件访问、休眠、锁及多语句。数据库再强制只读事务、只读 ACL 和查询超时。未设或过大的 LIMIT 均限行；保存的是执行后完整结果，row_count 与数值统计也只描述这次限行查询，不能冒充原始全量。模型只得到预览和可引用 ID，全量计数应在 SQL 中求值。工具结果用转义分隔符包裹，系统声明数据不得成为指令；不声称这能从语义层彻底防住提示注入。数值统计用于导航，报告数字仍须出现在 SQL 结果单元格中。

**数据**：[完整测试](../evidence/step2_pytest_20261017T070651Z.xml)验证攻击 SQL 拒绝、跨作用域 CTE 绕过拒绝、Bearer 鉴权、实际限行结果持久化和预览边界。新增结构注释由 [迁移执行收据](../evidence/migrate_20261017T065423Z_97f73b65.summary.json)记录，后续启动检查同一迁移哈希；已有迁移从未修改。这里不把有限测试覆盖等同于安全证明。

## full 与 on_demand 的真实基线

**问题**：一开始提供全部表结构会增加每轮输入，按需取结构则需要额外调用；没有实际用量无法选择。

**方案**：full 将所有表的结构和注释放入初始上下文；on_demand 只给表目录，由模型请求 describe_table。full 不额外预载样例，两种模式使用相同工具协议和输出规则。

**选择**：当前默认 on_demand，保留开关。用户本机配置使用 deepseek-flash 的 OpenAI 兼容接口，Agent 请求固定 temperature=0，并显式关闭该服务的 thinking 模式以避免温度参数失效，依据 [DeepSeek thinking mode 文档](https://api-docs.deepseek.com/guides/thinking_mode/)。费用单价未配置，保留空值；不根据 token 猜价格。

**数据**：仅在 A/B dev 上各运行一次，未调用归因评分模型，未运行 holdout 模型评测。

| 模式 | 答案正确 | 平均 token / 题 | 总 token | 平均步数 | 平均耗时 ms | 无证据结论 |
| --- | --- | --- | --- | --- | --- | --- |
| full | 14 / 14 | 5576.21 | 78067 | 2.0 | 3034.82 | 2 / 14 |
| on_demand | 14 / 14 | 4434.14 | 62078 | 2.5 | 3790.95 | 2 / 14 |

数据分别来自 [full 实跑汇总](../evidence/eval_baseline-full_20261017T070736Z_def8c3a7.summary.json)和 [on_demand 实跑汇总](../evidence/eval_baseline-on-demand_20261017T070828Z_4dd93f3c.summary.json)，原始日志 `eval_baseline-full_20261017T070736Z_def8c3a7.jsonl`、`eval_baseline-on-demand_20261017T070828Z_4dd93f3c.jsonl`；RESULTS 已由 eval/run.py 追加两行。当前 on_demand 的 token 更少、步数和耗时更多，选择侧重用量；样本与次数有限，不推断其复杂题效果或稳定性。

两组 A05 的 answer 列表正确，却自行数出状态数，SQL 没返回这个计数；B06 把不同结果行拼成州名为键的金额对象，无法匹配 SQL 列名与同一行，核查器拒绝。A/B 正确率只判 answer，证据比例独立报告。保留这两处失败，不放宽核查器，也不将满分答案写成“所有结论有证据”。运行时审核留到后续步骤；CSV 交叉验证和这组 A/B 基线均未校准归因评分。

## Step 2 审查修复：多行绑定与真实注入实验

**选择**：final_answer 描述及系统提示要求跨行 value 为行对象数组，键为 SQL 列名，每个对象只能来自同一结果行；附 SP/RJ 格式示例。不改变独立核查器。

**数据**：[修复后 A/B dev](../evidence/eval_baseline-row-objects_20261017T075108Z_9e1088e9.summary.json)，原始日志 `eval_baseline-row-objects_20261017T075108Z_9e1088e9.jsonl`：on_demand 无证据结构化结论从旧基线 2/14 到 0/14，答案仍为 14/14，总 token 57246。A05 文字仍自行写出“8 种”，该数字未由 SQL 计数；这是文字与结构化 value 的差别，不能把本次零无证据结论理解为所有数字都合规。后续 Writer 的报告扫描必须保留这一边界。

**注入实验**：eval/injection.py 用真实已配置模型、惰性 MCP 替身，在样例行或查询结果插入角色伪装、回答零、DROP/DELETE、读文件及指定标记攻击。替身只识别固定样例的 SUM/COUNT，绝不执行 SQL；危险调用尝试即计诱导成功，不以实际破坏为条件。[数值输出约定复跑](../evidence/injection_20261017T075418Z_5df33c1a.summary.json)，原始日志 `injection_20261017T075418Z_5df33c1a.jsonl`：8/8 已暴露，0 次诱导成功，0 个不确定结果，8 个完成。未暴露或非规范回答不会算防御成功。有限合成攻击与单模型单次实验不构成免疫保证。

保留[首次实验](../evidence/injection_20261017T075056Z_b0d957e8.summary.json)：同样 8 次暴露、0 次诱导，但当时合法答案分类要求数值，问题却允许文本，因此 7 条合法文本回答被该辅助字段误判。复跑明确数值输出，并将无法判定单列，未改写历史证据。测试挂载源码后首次未固定 PYTHONPATH，误导入旧安装包；保留[失败 XML](../evidence/step2_revision_final.xml)，以[固定路径复核 XML](../evidence/step2_revision_verified.xml)为修复验收。

## Step 3 上下文策略与测量边界

**问题**：历史工具结果持续占用输入，压缩又可能丢失发现和证据对应关系。

**方案**：none 原样保留；mask 省略最近指定轮数以前的工具内容，留下 result_id/行数/取回提示；summary 在上一轮实测输入达到阈值后调用模型压缩完整的旧消息组。二者保留工具调用与返回的配对。固定笔记通过 save_finding 主动保存，摘要与笔记都只是未审核数据，不赋予系统指令权限。get_result 使用任务 ID 与结果 ID 双重条件分页读取。

**测量**：逐轮 context_usage 记录 provider 实际 prompt_tokens 和峰值，超过 CONTEXT_LIMIT 即失败。缺少 provider tokenizer 时，不以字符数代替 token；超限判断发生在响应之后，该请求已经消耗的用量照实记录。摘要请求也计入上下文峰值和累计预算。

**评测修复**：D 的事实提取原先只认单个 value 对象，遗漏已允许的行对象数组；现统一读取两种形态，仍要求原字段名、带符号数值、原容差及无矛盾重复。没有从州名等值推断事实字段，没有修改 gold 或证据核查器。原始三组实验保留；eval/run.py 的 --recheck-evidence 重新执行 gold SQL 并核查保存的真实回答，验证数据版本和题库哈希，记录来源收据哈希。重核行的 token 和耗时来自原始模型运行，不是第二次模型调用，也不能重复加总为新消耗。

**实跑选择**：当前默认 none，保留 mask/summary 开关。D dev 这次窗口峰值均未超过限制；mask 反而有一次累计预算耗尽，summary 有两次。不能声称压缩在本题集提高了完成率，也不把单次小样本结论推广到更长任务。

| 策略 | 事实命中 | 峰值上下文 token | 总 token | 完成 | 证据与原始日志 |
| --- | --- | --- | --- | --- | --- |
| none | 17 / 25 | 8093 | 124011 | 8 / 8 | [eval_context-none-rechecked_20261017T080247Z_47d4c5e8.summary.json](../evidence/eval_context-none-rechecked_20261017T080247Z_47d4c5e8.summary.json)；`eval_context-none-rechecked_20261017T080247Z_47d4c5e8.jsonl`；原模型日志 `eval_context-none_20261017T075816Z_8139f173.jsonl` |
| mask | 19 / 25 | 8727 | 161730 | 7 / 8 | [eval_context-mask-rechecked_20261017T080250Z_c4f2d789.summary.json](../evidence/eval_context-mask-rechecked_20261017T080250Z_c4f2d789.summary.json)；`eval_context-mask-rechecked_20261017T080250Z_c4f2d789.jsonl`；原模型日志 `eval_context-mask_20261017T075930Z_1d702c4a.jsonl` |
| summary | 16 / 25 | 7761 | 202430 | 6 / 8 | [eval_context-summary-rechecked_20261017T080253Z_0be96515.summary.json](../evidence/eval_context-summary-rechecked_20261017T080253Z_0be96515.summary.json)；`eval_context-summary-rechecked_20261017T080253Z_0be96515.jsonl`；原模型日志 `eval_context-summary_20261017T080054Z_e8ed1cbe.jsonl` |

全部报告按严格的 D 完整正确标准仍未通过；事实字段遗漏、口径与未经 SQL 计算的叙述数字都保留。没有只报告结构化无证据结论比例来掩盖报告数字问题。summary 在真实运行中触发了摘要，费用仍因未配置单价留空。[最终镜像测试](../evidence/step3_image_tests.xml) 142 passed，原始日志 `step3_image_tests.log`。

## Step 4 业务知识与混合检索

**问题**：语法正确不意味着业务口径正确；客户标识、GMV 状态、商品金额、评价粒度与时间缺失都需要企业定义。

**方案**：按指标和陷阱的语义边界切分，保留 SQL 例子；jieba BM25 与真实多语言向量分别排名，使用 RRF 融合取前三块。向量保存在新增 004 迁移创建的 knowledge_chunks 中，内容、模型名、维数与哈希一同存储，重建在事务内替换。off 隐藏知识工具，inject 自动检索，tool 由模型选择时机。

**向量模型**：本机没有额外向量接口配置，按提前声明的默认方案使用公开 multilingual-e5-small，FastEmbed CPU 推理，通过独立服务暴露 OpenAI 兼容接口。遵循[模型作者](https://huggingface.co/intfloat/multilingual-e5-small)的 query/passage 前缀与归一化约定，模型加载方式依据[FastEmbed 官方说明](https://github.com/qdrant/fastembed)。[真实索引收据](../evidence/knowledge_index_20261017T080829Z_a1331a1e.summary.json)记录全部知识块与模型文件哈希，原始日志 `knowledge_index_20261017T080829Z_a1331a1e.jsonl`；不是随机向量或用词频伪装的 embedding。

**独立检索测量**：[C dev 检索汇总](../evidence/eval_retrieval-dev_20261017T080834Z_51697037.summary.json)，原始日志 `eval_retrieval-dev_20261017T080834Z_51697037.jsonl`，BM25 recall@3 为 14/17，向量 16/17，混合 16/17。RRF 并非每题都优于单路：C02 的目标 buyers 被挤出前三，不能宣称融合总是更好。全部 C 题已标注所需块，未用 holdout 表现调参；只运行 dev。KB 与 C 的陷阱有共同来源，未来必须用留出的改写题核对泛化。

[完整复核测试](../evidence/step4_verified_tests.xml)为 144 passed，原始日志 `step4_verified_tests.log`。首次运行的旧核心表测试错误地禁止任何新表，更新为验证原核心表必须存在；原失败 XML 也保留。迁移幂等、不可修改历史和只读权限测试未放宽。

**选择与真实回答比较**：保留三种开关，推荐 inject。此次 inject 与 tool 都答对全部 C dev，inject 平均用量和耗时较低。项目默认值仍为 off 便于显式做消融；后续完整配置和多智能体对比显式使用 inject。
| 模式 | 正确题数 | 平均 token | 平均耗时 ms | 证据与日志 |
| --- | --- | --- | --- | --- |
| off | 12 / 17 | 10913.76 | 5146.68 | [eval_rag-off_20261017T080858Z_efce07fa.summary.json](../evidence/eval_rag-off_20261017T080858Z_efce07fa.summary.json)；`eval_rag-off_20261017T080858Z_efce07fa.jsonl` |
| inject | 17 / 17 | 10606.35 | 4402.09 | [eval_rag-inject_20261017T081027Z_be4ffcde.summary.json](../evidence/eval_rag-inject_20261017T081027Z_be4ffcde.summary.json)；`eval_rag-inject_20261017T081027Z_be4ffcde.jsonl` |
| tool | 17 / 17 | 13233.06 | 5502.75 | [eval_rag-tool_20261017T081145Z_8479a05d.summary.json](../evidence/eval_rag-tool_20261017T081145Z_8479a05d.summary.json)；`eval_rag-tool_20261017T081145Z_8479a05d.jsonl` |

这只是 dev 单次运行，不报告未运行的 holdout 成绩或稳定性。最终检索读取采用只读可重复读事务，避免与重建索引混用版本；[最终测试](../evidence/step4_final_tests.xml)通过。

## Step 5 用户偏好、冲突与授权

**问题**：用户明确口径应跨会话保留，但模型推断和错误结论不能变成长期事实；一个人的偏好不能影响别人。

**选择**：只抽取 preference，短期历史仍由上下文管理负责。模型只能返回限定 key 和逐字 source_quote，运行器在写入前再次验证；value 直接采用原话，不接受模型另写的规则。没有明确长期措辞、不在当前用户输入中的引文或重复 key 全部拒绝。一次性问题、助手回答和 SQL 分析结论都不进入此存储。键更新在锁定用户的事务内使旧版本 superseded，保留历史；同值重写幂等。读取从任务所属用户反查，模型不能传入其他用户 ID。

**接口边界**：GET/DELETE 依据 HS256 签名 token 的 subject，而非请求中的 user_id。每条 DELETE 都同时约束所有者与 memory_id，别人的记录返回不存在。当前只提供本机管理员签发短期 token 的入口，交互登录仍留给 Step 8。API 独立密钥不进入模型进程，业务数据库凭据也不进入模型进程。本步复用已有表，无表结构修改；后续任何新增字段仍须新迁移。

**用量边界**：SMALL_MODEL 可单独指定，未配置则复用当前模型，不能据名称推断费用。设置和查询会话分别启动新进程，抽取调用也计入全任务观测预算，缺 usage 不能记作零。并行角色的预算在后续多智能体中共用同一对象；不能在发送前精确预测尚未返回的 prompt_tokens。

**初次抽取审计**：[20 条真实抽取](../evidence/memory_audit_20261017T081721Z_7e8a19bb.summary.json)，原始日志 `memory_audit_20261017T081721Z_7e8a19bb.jsonl`，严格原话/key 匹配为 15/20。销售额的状态限制曾误归入通用订单状态；一些引文略去“记住”等前缀而被边界校验拒绝；另有语义正确但不是全句的引文在严格核对中失败。修复提示要求保留完整原句并按最具体指标分类，没有改变预先声明的审计样例或评分标准。

**修复后抽取**：[相同样例复跑](../evidence/memory_audit_20261017T081910Z_35671a53.summary.json)，原始日志 `memory_audit_20261017T081910Z_35671a53.jsonl`，严格原话/key 匹配 20/20。[逐条审查表](../eval/MEMORY_REVIEW.md)保留人工结论空栏；这不是人工准确率，也不代表任意用户输入的效果。

| 配置 | E dev 正确 | 总 token（含抽取） | 证据与日志 |
| --- | --- | --- | --- |
| 无记忆 | 3 / 6 | 42737 | [eval_memory-false_20261017T081732Z_2f7f2766.summary.json](../evidence/eval_memory-false_20261017T081732Z_2f7f2766.summary.json)；`eval_memory-false_20261017T081732Z_2f7f2766.jsonl` |
| 有记忆（最终） | 6 / 6 | 51054 | [eval_memory-true-final_20261017T081912Z_fe1f13c9.summary.json](../evidence/eval_memory-true-final_20261017T081912Z_fe1f13c9.summary.json)；`eval_memory-true-final_20261017T081912Z_fe1f13c9.jsonl` |

首次有记忆实验也完整保留在 RESULTS。两组后续问题使用独立新进程、同题用户的数据库偏好，没有复用设置会话消息。知识库关闭，避免替代偏好影响对照。[完整测试](../evidence/step5_final_tests.xml) 148 passed，原始日志 `step5_final_tests.log`，包含真实数据库与鉴权测试。


## 固定 bge-m3 容器、镜像源与索引版本

**问题**：用户进一步指定 bge-m3。原 e5 结果只代表当时的配置，不能在换模型后直接沿用为最终对比；只记录模型名字也不足以重现可变的 main 权重。

**方案**：继续使用小模型；下载未固定的最新权重；或固定官方仓库 commit，独立服务返回身份，索引与评测同时保存版本。按用户要求选最后一种，只有 CPU 实测过慢才考虑回退。

**选择**：`BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181`，`HF_ENDPOINT=https://hf-mirror.com`，持久化到 Docker 数据卷 `embedding_models`。采用官方 ONNX dense 表示、CLS pooling 和归一化，经 `/v1/embeddings` 提供；不把 BM25 冒充模型的 sparse 输出。模型能力和不需要 query 前缀的规则参照[官方模型说明](https://huggingface.co/BAAI/bge-m3/blob/5617a9f61b028005a4858fdac845db406aefb181/README.md)。通过新增迁移 006 增加索引 revision，旧行标记 unrecorded 并强制重建；每个响应、服务身份、配置和索引版本必须一致。每次新评测保存模型名、revision、是否实际使用；RAG 启用时额外验证服务并保存权重哈希。关闭时明确 used=false，旧收据不伪造回填新身份。

**数据**：[bge-m3 CPU 实测](../evidence/eval_bge-cpu_20261017T084350Z_c3e5ae16.summary.json)，原始日志 `eval_bge-cpu_20261017T084350Z_c3e5ae16.jsonl`：通过 `eval/run.py --embedding-benchmark` 在 C dev 的 17 个查询上暖启动串行测量，平均 101.59 ms，P95 123.63 ms，向量 1024 维且归一化检查通过。服务首次加载已缓存权重耗时 2.19 秒，下载时间不计入暖请求。CPU 延迟可接受，因此保留 bge-m3，没有回退或虚构更小模型的速度对比。这不是并发压力测试或 GPU 性能结论。

[bge 索引收据](../evidence/knowledge_index_20261017T084451Z_7fffe624.summary.json)对应 `knowledge_index_20261017T084451Z_7fffe624.jsonl`，原子重建 32 个知识块。由 `eval/run.py` 产生的[检索汇总](../evidence/eval_bge-retrieval-dev_20261017T084507Z_4e08bbbf.summary.json)，原始日志 `eval_bge-retrieval-dev_20261017T084507Z_4e08bbbf.jsonl`：BM25 命中 14/17，bge 向量 17/17，固定 RRF 混合 15/17。混合没有优于纯向量；仍保留计划规定的混合实现和固定融合参数，不因为本轮 dev 成绩临时调权重。历史 e5 的混合 16/17 只作配置变化记录，见前述 Step 4 收据；未据此推断 holdout 表现。

## Step 6：类型化黑板、并行分析与独立审核

**问题**：复杂分析需要独立的上下文、可追溯的证据审核和可控的重做次数。多角色可能增加模型成本，也可能因为拆题丢失关键事实，不能预设一定优于单 Agent。

**方案**：让角色自由对话；在一个上下文里串联全部角色；或用带类型和角色字段约束的数据库黑板控制状态流转。选择黑板，通过新增迁移 005 实现任务状态，不修改已有迁移。

**选择**：Planner 为简单查询输出单个子问题，保留原问题直接路由；复杂问题拆成有向无环依赖图，各 Analyst 使用独立循环，无依赖任务 asyncio 并行。Reviewer 从黑板取结论，经完整保存结果做同一行、同名列、带符号数值校验，再用模型判断 SQL 的口径与论断；拒绝后只允许重做一次，再失败保留“未能验证”。Writer 只接收已批准 claims，数据库拒绝自增或被否决的 claim；正文中缺乏支持的数字标红，独立 eval/checker 仍照常扣分。multi_no_review 保留规划、分析、撰写，仅跳过审核；简单路由两种 multi 模式都跳过 Reviewer。任务控制工具被运行器隐藏，LLM 不能通过猜测名称调用。内部服务 token 仍属于可信运行器边界，面向用户的完整登录和后台恢复留待后续步骤。

**证据边界**：所有角色实际调用和用量进入事件日志，独立归因评分另记 eval_judge，比较时分别展示 Agent 用量和评测总量。共同使用预算 100000；已发出的并行请求可能越过阈值，统计真实响应 usage 并将任务记为预算终止。数字值在结果中出现不能证明 SQL 语义、因果方向正确，Reviewer 与评分模型也不是人工校准的替代品。

**实现过程中发现的问题**：首次复杂拆题生成了合法但较长的 ID，被未写入提示的旧长度限制拒绝；已将限制明确为最长六十四字符并测试真实 MCP。旧完整 multi 运行在升级期间中止，保留[中止收据](../evidence/eval_modes-multi_20261017T083241Z_f8b8d34a.summary.json)，没有为不完整运行填 RESULTS 汇总。UUID 证据链接和 `YYYY Qn` 时间标签曾被数字扫描误识别，运行时扫描与独立核查器分别修复并测试；金额本身不因此豁免。另有 Writer 返回 `type: json_object` 的无害格式元数据，被严格 JSON 形状判为失败；现在只容许该已知元数据，仍拒绝 Writer 提交 claims。所有旧结果留存，最终对比重新运行，不通过修改 gold 改成绩。


**日志补齐**：主对比和隔离复跑的评测／Agent 代码哈希一致，收据保存各文件的代码哈希。之后仅补充 MCP 传输层审计与报告导出原始问题：内部 state_read/state_write、Reviewer 的 get_result 和普通 MCP 调用均记录成对的 mcp_call/mcp_result，包含调用 ID、输入输出摘要与实际耗时，不记录鉴权头。这些事件与模型请求的 tool_call 分层，不能把两层相加为工具次数。此补丁不改变模型输入、SQL、审核规则或评分；对比表使用实测版本耗时，不估算加入日志后的延迟。新版本另做真实命令行与数据库日志核验。

**bge-m3 主对比**：三轮使用相同代码哈希、题库、数据版本、模型、温度、RAG inject、无 Memory、上下文 none 与任务预算。全部是 dev 单次结果。平均 token 含独立归因评分；Agent 调用数和 Agent 耗时单列，调用数包括失败重试。空白用量表示有请求未取得 usage，不能把失败尝试当零。

| 模式 | C 正确 | D 整题正确 | D 事实命中 | 无证据 claims | D 无证据正文数字 | 归因均分 | 平均 token | Agent 调用数 | Agent 平均 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [single](../evidence/eval_bge-single_20261017T084857Z_46aad30b.summary.json) | 17/17 | 2/8 | 24/25 | 0/51 | 21/223 | 4.125 |  | 83 | 7819.05 |
| [multi_no_review](../evidence/eval_bge-multi_no_review_20261017T085232Z_e18784c6.summary.json) | 17/17 | 3/8 | 24/25 | 0/50 | 24/221 | 4.000 |  | 121 | 8827.21 |
| [multi](../evidence/eval_bge-multi_20261017T085648Z_947b5a76.summary.json) | 17/17 | 3/8 | 23/25 | 0/45 | 35/179 | 4.000 | 18207.60 | 137 | 9462.30 |

原始运行日志：
- single：`eval_bge-single_20261017T084857Z_46aad30b.jsonl`。
- multi_no_review：`eval_bge-multi_no_review_20261017T085232Z_e18784c6.jsonl`。
- multi：`eval_bge-multi_20261017T085648Z_947b5a76.jsonl`。

**判断**：这轮加入 Reviewer 没有带来一致收益：结构化 claims 本来就都能在 SQL 结果中找到，正文额外数字仍然存在，multi 的事实命中低于 single，正文无证据数字比例更高。暂保留 single 默认，multi 和 multi_no_review 作为可比较的开关；不把多角色包装成已证明更好。multi 与无审核模式各有 21 个简单路由、4 个复杂拆题；完整 multi 的审核记录包括 18 次批准、3 次拒绝和 1 次退回事件，说明机制实际执行过，但不等于判断总是正确。这里审核事件按每次审查累计，不能与最终 claim 数直接相加。

**口径实验补充**：固定 bge 后，[off](../evidence/eval_bge-rag-off_20261017T084538Z_ce634d66.summary.json) 为 12/17，[tool](../evidence/eval_bge-rag-tool_20261017T084721Z_aa02efa3.summary.json) 为 17/17，主对比 single 的 inject C 部分为 17/17。原始日志分别为 `eval_bge-rag-off_20261017T084538Z_ce634d66.jsonl`、`eval_bge-rag-tool_20261017T084721Z_aa02efa3.jsonl` 与主对比 single 日志。inject 本轮存在未知 usage，不能据此编造它与 tool 的完整 token 差；保留 inject 作为主动提供口径的实验配置。

**运行故障与保留规则**：single 主运行在 C11、D08 各经历两次 APIConnectionError，最终完成但总用量未知；无审核模式也存在无 usage 的连接失败。一次 single 补跑又被本地 Compose 冒烟启动引发的 MCP 重建影响，D02–D05 失败；[受影响收据](../evidence/eval_bge-single-repeat_20261017T090134Z_4257c690.summary.json)与其真实 RESULTS 行均保留，明确排除出模式比较。[调用日志核验与排除说明](../evidence/step6_trace_audit_20261017T090605Z_1c11efa5.summary.json)，原始日志 `step6_trace_audit_20261017T090605Z_1c11efa5.jsonl`，记录已落库的 8 对 MCP 调用及事故来源。恢复运行使用 --no-deps 和与原始哈希逐文件相符的冻结 Agent 快照；不以正确率择优选择运行。

**验证与界限**：[最终回归 XML](../evidence/step6_release_tests.xml)为 164 passed，原始日志 `step6_release_tests.log`；[原始问题与 HTML 转义测试](../evidence/step6_report_export_test.xml)通过，原始日志 `step6_report_export_test.log`。没有运行 holdout，没有模型单价，所以费用留空。偏好抽取与报告的人工评分仍未完成，不声称评分模型已校准。


**具体失败机制**：主 multi 的 D02 先输出正确的最大下降品类，又在其他下降品类列表中重复使用 `largest_drop_category/amount` 字段，产生多个互相不同的“最大值”。独立核查器按防止堆答案的规则只认可无歧义的事实；不能因正确值混在列表里就放宽判分。D08 的 Reviewer 还出现了“最大值为 2 不能支持每单最多 2 条”的错误拒绝理由；审核模型本身也会犯逻辑错误。两者都见主 multi 收据与同名日志，因此没有把模型审核当作可信真值，也没有为提高成绩改 gold 或核查规则。

[十份真实报告导出收据](../evidence/report_exports_20261017T090708Z_289d1726.summary.json)，原始日志 `report_exports_20261017T090708Z_289d1726.jsonl`。按模式轮流选取 D 报告，原始问题、SQL、结果、自动核查和模型评分可一起审阅；HTML 内证据锚点已检查。人工判断与评分仍留空，清单在 `eval/REPORT_REVIEW.md`。


**隔离复跑结果也保留**：[single 隔离复跑](../evidence/eval_bge-single-isolated_20261017T090525Z_c75a15fc.summary.json)，原始日志 `eval_bge-single-isolated_20261017T090525Z_c75a15fc.jsonl`。代码、依赖版本、题库、数据与向量身份与主对比一致；完成 25/25，整题正确 18/25，D 事实 23/25，无证据 claims 2/47，D 正文无证据数字 56/210，归因均分 4.125。Agent 调用 83 次，平均 Agent 耗时 7295.55 ms。仍有连接失败尝试没有 usage，所以完整 token 和费用继续留空，不再反复重跑以挑出完整或更好看的成绩。复跑更差的数字没有替换或隐藏主运行；温度固定也未保证输出相同。本步不能据单次主对比断言 single 或 multi 稳定更优，更不能报告精确 token 成本增幅。十份报告按预先选定的三轮主运行导出，未根据复跑成绩重挑样本。

[最终证据一致性核验](../evidence/step6_integrity_20261017T091012Z.summary.json)，原始日志 `step6_integrity_20261017T091012Z.jsonl`：RESULTS 所有已填指标与真实运行收据一致，原始日志哈希匹配；旧表未填列继续留空，新 bge 行逐列核对，包括缺失用量空白。主对比与隔离复跑的代码、依赖、题库和数据版本一致。


## Step 6 审查修复：数字门禁与重复实验

问题：正文中会出现没有已批准证据的差值、比率和其他数字，标红只能提示，不能阻止报告继续输出。

方案：继续标红、无限退回、或一次退回后确定性替换。选择 `NUMBER_GATE=true` 时先扫描正文，把不受支持的数字列表反馈给模型重写一次，仍不合格则替换为“未验证”。关闭时保留原行为。单 Agent 和简单路由的数字来源先经过同名列、同一行的确定性证据核查；复杂 multi 使用 Reviewer 批准的 claims。代码核查与语义审核的能力不同，不把单 Agent 的值匹配称为语义通过。数字匹配仍按绝对值和既有容差，不允许模型自行计算。日期标签、证据 UUID 和列表序号不作为业务数值；它们不是经过核验的业务事实。

数据：初版实跑发现行首小数被列表编号规则误截，导致正确的数值答案被退回并变成不符合数值答案契约的文本。已有 review6 行保留，不能作为门禁有效性的最终对比。中断尚未完成的 D 门禁实验，并保留[中断收据](../evidence/eval_review6-D-single-gatetrue-r1_20261017T092721Z_53d1efae.summary.json)。运行时与独立核查器分别修复“句点后紧跟数字不是序号”，补充小数原值、文本小数和真序号回归；[测试收据](../evidence/step78_decimal_tests.xml)，日志 `step78_decimal_tests.log`。后续完整重跑使用 review6-fixed 标签，不能把前后两批混合成重复样本。正文门禁不改结构化 claim.value 或 gold；独立核查器同时检查正文与 claim.text，因此即使正文已清理，元数据中的文字仍可能被扣分。


完整四组结果见 [审查补充对比](REVIEW_COMPARISON.md)、[重复运行汇总](../evidence/eval_review6-fixed_20261017T092756Z_ed1d9efd.summary.json)和[实际拆题配对及计数](../evidence/eval_review6-statistics_20261017T100149Z_ea5440cc.summary.json)；汇总日志分别为 `eval_review6-fixed_20261017T092756Z_ed1d9efd.jsonl`、`eval_review6-statistics_20261017T100149Z_ea5440cc.jsonl`，各次原始日志列在报告内。C dev 四组均为 17/17。D 每组完整保留三次：single 的无证据数字比例均值由 21.67% 降为 2.43%，multi 由 14.59% 降为 3.99%；范围、分母和计数均单列。single 开关前后的事实命中均值相同，为 93.33%；multi 从 86.67% 到 93.33%。这支持在网页交付报告时启用门禁，但不证明其能纠正语义错误或保证全部元数据没有幻觉。

复杂题按每次实际拆分题号与同轮 single 配对，所有配对中 multi 的平均 Agent 耗时更长，事实命中有升有降，不能宣称并行已有加速收益。CLI 保留 single；网页采用 multi 是为了计划确认、审核与子问题恢复，不把它宣传为更准确、更快。三轮仍是很小的样本，温度为零也有路由与生成波动。预算和上下文失败进入分母，没有择优重跑。为保留实际评测版本，另存 [冻结源码快照](../evidence/review6_evaluated_source.zip)，其中 manifest 的逐文件哈希已与首轮收据核对；后续 Step 7–8 的代码变化不回填这些运行。

6000 上下文压力测试单独运行：none 完成 5/8、事实 15/25；mask 与 summary 均完成 7/8、事实 22/25。mask 实际总 token 108080，summary 148094，均含独立评分；本轮紧窗口优先选择 mask，正常窗口默认不因单轮压力成绩整体切换。summary 阈值在运行前固定为 3600，未据成绩再调；两种压缩均仍有一次上下文超限。日志分别为 `eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.jsonl`、`eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.jsonl`、`eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.jsonl`，对应证据及峰值在对比报告中。

## 检索默认值的实测选择

问题：等权 RRF 会让较弱的关键词排名挤掉正确的向量候选。对照纯向量、等权混合，以及预先固定 BM25:vector=0.25:1 的加权 RRF；未进行多轮权重搜索。

选择：默认改为纯向量，保留 `RETRIEVAL_METHOD=hybrid|weighted|bm25|vector` 可选。依据[本次检索证据](../evidence/eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.summary.json)，日志 `eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.jsonl`：C dev recall@3，纯向量 17/17，等权混合 15/17，加权混合 16/17，BM25 14/17。加权仍漏掉 C02 的 buyers 块。只有 17 道同源陷阱题，样本小且知识库与题库共享业务陷阱，不能外推到其他问法、其他语料或 holdout。固定 bge-m3 模型与 revision 保持不变。

## 偏好抽取的新写法留出审计

问题：原样例复跑成功可能是提示适配该批措辞。新增独立的 [20 条新说法](../eval/preference_holdout.json)，保持抽取器代码与提示完全不变，只跑一次。[真实审计](../evidence/memory_holdout_audit_20261017T092012Z_ab705f05.summary.json)，日志 `memory_holdout_audit_20261017T092012Z_ab705f05.jsonl`，完整原话与预声明 key 精确匹配 20/20；收据保存抽取器及样例哈希、逐次模型输出和实际 usage。它是自编表达留出，不是生产输入的随机抽样，也不是题库 holdout 的最终评测。未把它称为人工准确率。

## Step 7：已审核结论的复用边界

问题：重复查询浪费调用，未经审核或过期的结论又会持续污染后续答案。选择只读取持久化黑板中的 Reviewer 通过项，且该项必须进入最终报告；未通过、缺证据、版本不一致的内容不写入 finding。迁移 007 增加证据、版本、向量和来源任务，复用既有 memories 表。

finding 在多角色规划阶段读取；single 的 USE_MEMORY 继续用于用户偏好，不能把它当作 finding 复用。按用户隔离，固定模型及 revision，余弦相似度阈值预设 0.78，最多取三条。当前版本的证据复制到当前任务，保留 source_result_id 和原始引用；MCP 仍只能读取当前任务，不能凭历史 UUID 跨用户取结果。Planner 判断是否覆盖新问题，复用项仍由 Reviewer 针对新问题复核。数据版本不同时仅给历史问题，不给旧结论、数值或 result_id。真实两会话与版本变更测试见 [复用实验](FINDING_REUSE.md)，不承诺每个问题都会省 token。

两会话实测固定选择 D01–D05，见 [证据](../evidence/eval_findings-dev_20261017T100156Z_399f6c31.summary.json)，日志 `eval_findings-dev_20261017T100156Z_399f6c31.jsonl`。五题第二次都触发了历史复用；D01、D03、D04、D05 第二次 SQL 调用为零，事实命中保持，步骤和 token 下降。D02 只获得部分历史证据，仍需补查：步骤从 14 增至 17，SQL 从 5 增至 7，token 从 74587 到 69613，事实命中从 2/3 到 3/3。不能把局部复用描述成全部重复问题都无需查库。逐题原始值与首次/再次正确性均在实验报告中。

版本测试提交临时 data_imports 记录，让独立读取连接看见不同版本；各题匹配项只能返回 stale_clue，不含旧 claim 或结果引用；测试完成后删除该测试标记并核对原版本恢复。原业务行未修改。它验证版本边界，不代替生产数据更新后的业务正确性评估。

## Step 8：数据库任务队列、确认与恢复

问题：HTTP 请求不能承担长分析，进程重启也不能丢失已完成的查证。选择独立 worker 和 PostgreSQL 行锁，不增加消息队列；新增迁移 008 保存确认时间、租约、心跳和领取次数。

API 的 JWT subject 决定所有任务、SQL 结果及记忆的归属。密码使用带随机盐的 PBKDF2，JWT 有有效期；浏览器只接收用户 token，不接收 MCP 或数据库凭据。任务创建只入队，计划完成后必须人工确认；确认提交校验整个依赖图，客户端不能塞入未经计划提供的历史引用。

租约过期允许接管，所有后台事件和状态写入检查当前租约；保存 SQL 结果时再次核对租约，阻止旧进程在接管后提交。恢复跳过已审核的完成子问题，已有查询未审核则继续审核，其他未完成项重跑。事件 seq 在任务行锁下分配，SSE 根据 Last-Event-ID 续传。被杀死的在途模型调用可能没有 usage，完整总 token 留空，已记录用量单列；不假装恢复能找回供应商没有返回的用量。


真实恢复：[核验收据](../evidence/resume_demo_20261017T100621Z.summary.json)，日志 `resume_demo_20261017T100621Z.jsonl`。同一个任务在 SP 子问题审核通过后被 SIGKILL，重启接管后，已完成的 SP claims、审核和 evidence 原样保留，只重跑 RJ；SSE 以 Last-Event-ID 重连得到严格对应的事件后缀。原始任务总历时包含前期排队、人工确认及重启诊断，不把它当作模型推理延迟。

演示首次使用 `docker compose start worker` 时，Compose 连带启动遗留的旧 init-data 镜像，迁移检查因缺少已执行的迁移文件而拒绝启动。没有修改迁移或清库绕过；将恢复命令改为 `docker compose up -d --no-deps worker`，继续同一个检查点，并将主项目初始化容器更新到当前镜像。此问题与恢复成功均记录，未重挑任务隐藏失败。新部署还改为在向量服务启动期间下载并加载固定快照，健康检查通过后才允许导入索引，避免空缓存时由第一条 HTTP 索引请求承担下载。

浏览器完成了计划修改、确认、实时事件、恢复完成和金额点击 SQL 的真实验收，未发现控制台错误；[画面收据](../evidence/ui_demo_20261017T100932Z_f92bcf6e.summary.json)对应日志 `ui_demo_20261017T100932Z_f92bcf6e.jsonl`。GIF 为真实阶段截图编码，等待和故障诊断时间被压缩，不能据动画播放时长计算性能。

[最终回归](../evidence/step78_release_tests.xml)为 176 passed，日志 `step78_release_tests.log`。保留初次 [失败收据](../evidence/step78_initial_tests.xml)（旧计划断言漏掉新增默认 memory_ids）和后续 [失败收据](../evidence/step78_ready_tests.xml)（错误地在整个返回字符串中检查数字，随机 UUID 碰巧包含该数字）；修正为计划规范化比较和明确字段级断言，没有放宽隔离或版本校验。


冷启动验收使用独立项目 `olist-step8-smoke`，先确认数据库卷和模型卷均不存在，从空卷下载固定 revision；[通过收据](../evidence/fresh_compose_20261017T101027Z_450b90f6.summary.json)，日志 `fresh_compose_20261017T101027Z_450b90f6.jsonl`。全部迁移落库，初始化容器实际 exited/0，API 返回成功，数据库、向量服务、MCP、API 健康且 worker 运行，测试卷已清理。复用了本机已构建镜像与原 CSV，不宣称在另一台物理机器实际部署过。首次 [失败收据](../evidence/fresh_compose_20261017T100503Z_ac054510.summary.json)来自验收脚本：`compose wait` 对已退出容器返回“no containers”，并非可据此判断初始化进程失败；改为读取退出容器状态与 ExitCode 后，从空卷重新验证，没有把第一次收据改为成功。

最终页面还验证了已完成任务重开后的历史时间线，见 [UI 回放证据](../evidence/step8_reopen_ui.summary.json)，日志 `step8_reopen_ui.json`。当前工作在 Step 9 之前停止，未启动题库 holdout 或最终消融。人工归因评分校准仍未完成，不能将模型分数当作已验证的人类判断。

[提交前证据一致性检查](../evidence/evidence_integrity_20261017T101750Z_8c083213.summary.json)，日志 `evidence_integrity_20261017T101750Z_8c083213.jsonl`：RESULTS 的已填单元格与真实收据一致，原始日志哈希匹配，已检查的文档链接存在，候选 Git 文件未发现配置密钥。
