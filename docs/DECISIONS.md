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
