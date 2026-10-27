# Step 12 工程化加固

执行范围以对话里的批次指令为准。第 1 批为 12.1（A1–A4）和 12.2（B1–B2），按顺序完成。冻结 Step 9 holdout，不重跑、不重新计分；题库、gold、核查器、知识库及既有迁移保持不变。

## 起始基线

- 起始提交：`22cb974`；默认配置仍为 single + NUMBER_GATE + RAG inject + vector + Memory + context none，DIMENSION_PRECHECK=true、BOUNDARY_GUARDS=false。
- 本地 Linux Compose 完整测试：[241 项通过](../evidence/step12_baseline_full.xml)。CI 同构离线测试：[200 项通过](../evidence/step12_baseline_linux_offline.xml)。
- 额外尝试的 Windows 离线测试失败：[原始 XML](../evidence/step12_baseline_offline.xml)。其网络禁止夹具拦截 Windows asyncio 自管道，沙箱也限制 pytest 临时目录；因此本批统一在与 CI 一致的 Linux 容器验证，不为此修改产品代码。
- [起始文件哈希](../evidence/step12_start_reference.json)用于结束时核对冻结文件；`agent/loop.py`允许工程改动，但其中系统提示必须保持原文。
- [12.1 归档校验清单](../evidence/step12_1_archive_checksums.json)记录远程 Git 文件的确切 SHA-256 和本机采集字节 SHA-256。少数 Windows 产物由 `.gitattributes` 将 CRLF 规范化为 LF；原收据保留采集时哈希，校验仓库副本使用清单中的 git_blob_sha256，不修改或重算实验数据。

## 12.1 / A1 模型重试与熔断

### 旧问题

所有异常均请求四次并等待 1/2/4 秒；忽略 Retry-After、任务剩余时长，没有跨任务熔断。

### 改法与进度

失败测试提交：`cd24c60`；修复提交：`44c6f14`。新增失败测试：[离线 XML](../evidence/step12_a1_red.xml)（10 项失败），[数据库 XML](../evidence/step12_a1_circuit_red.xml)（5 项失败）。

按 HTTP 状态和网络异常分类；上下文长度错误终止为 `context_limit`，其他指定 4xx 终止为 `model_fatal`。未知异常不盲目重试，以 `model_error` 结束。可重试错误使用全抖动，优先解析 Retry-After 秒数/HTTP 日期，受 cap 与 worker 返回的剩余任务时长约束。

迁移 `010_provider_health.sql` 按 provider+model 保存熔断状态。reserve 在同一事务中锁行检查、取得单个半开探针；settle 根据每个预扣的唯一 call_id 记录事件，重复事件不重复计数。generation 拒绝旧在途结果关闭新一代熔断；探针失联后在模型超时或任务截止时间允许接管。后台拒绝经父子进程协议传回子进程，明确结束为 `provider_unavailable`。

事件新增 `model_call.error_class`（成功为 null）和 `retry_wait_ms`（实测休眠毫秒）；模型请求耗时不包含休眠。A1 没有新增工具返回字段，没有修改系统提示、知识库或数字闸门。

验收：[完整测试 264 项通过](../evidence/step12_a1_full.xml)，[CI 同构离线 218 项通过](../evidence/step12_a1_offline.xml)。包括真实约 2 秒等待的假客户端测试、5 次错误后低于 100ms 的预扣拒绝、并发只放行一个探针及成功/失败转换。原重试测试的假异常改为可重试连接错误，断言改为抖动范围；没有修改核查器。

### 前后对比

HTTP 模型替身持续返回 503，经后台 API 入队并由一个 worker 顺序处理 10 个任务；为隔离模型调用，实验显式关闭 RAG 和 Memory。不是实际模型性能或质量数据。

| 指标 | 改前 | 改后 |
| --- | ---: | ---: |
| 10 个任务总耗时（ms） | 84130.051 | 14421.562 |
| HTTP 替身请求数 | 40 | 5 |

[改前收据](../evidence/step12_a1_before_20261027T143800Z_9303e8a3.summary.json)包含源码哈希、日志文件名和 SHA-256；[原始实验日志](../evidence/step12_a1_before_20261027T143800Z_9303e8a3.jsonl)保留任务事件。

[改后收据](../evidence/step12_a1_after_20261027T144045Z_fe574aca.summary.json)；[改后原始日志](../evidence/step12_a1_after_20261027T144045Z_fe574aca.jsonl)。单次工程实验，不将耗时变化外推为真实模型生产性能；抖动导致不同运行的等待时间变化。

### 已知局限

CLI / 评测路径没有 worker 预扣回调，不经过共享熔断。总任务耗时包含子进程启动和 MCP 初始化；100ms 验收针对预扣熔断拒绝，不等于整个后台任务的端到端耗时。

## 12.1 / A2 无进展检测

### 旧问题

原循环仅识别同一 JSON 参数连续三次调用；A-B 交替、SQL 空格/大小写变化和不同参数的连续空结果无法提前终止。

### 改法

`agent/sql_normalize.py` 使用 sqlglot PostgreSQL 解析与标识符标准化，保留字符串和双引号标识符大小写，解析失败保留原文。`agent/progress.py` 被运行循环和只读回放共用：保留连续三次规则，增加六轮窗口和四轮全错/空且无新 result_id 规则。停止事件记录 rule、step、role，旧规则仍用 `repeated_tool_calls`，新规则用 `no_progress`。

### 前后对比与收据

失败测试提交：`d4be752`；修复提交：`f292108`。[旧实现三项失败](../evidence/step12_a2_red.xml)。修复后三种轨迹分别在第6轮调用前、第3轮调用前、第4轮结果后终止，[针对性通过 XML](../evidence/step12_a2_green.xml)，[完整269项通过](../evidence/step12_a2_full.xml)。没有模型质量或延迟估算。

运行 `python -m scripts.replay_progress` 只读原始日志及收据，校验四份源日志 SHA-256，再以相同检测器回放全部97次最终配置运行。结果：运行97次、误判0次、新模型调用0次，不计算任何答案评分。[回放收据](../evidence/step12_a2_replay_20261027T144321Z_09661f40.summary.json)与[原始回放记录](../evidence/step12_a2_replay_20261027T144321Z_09661f40.jsonl)保留每次运行结论和源日志哈希。

### 已知局限

历史日志有70条工具结果摘要因长度截断不能完整解析；回放仍使用独立记录的 result_id/error，无法恢复的内容视为未知，不当作空结果。返回新 result_id 的空查询按本批规定属于有进展；因此四轮空结果规则不承诺捕获所有业务上无进展的查询。A2 无新增工具返回字段，无提示词修改。

## 12.1 / A3 工具调用幂等

### 旧问题

同一 SQL 的并发请求、结果已落库但调用方丢失响应后的重跑，都会再次执行业务查询并插入结果；客户端没有连接失败重试。

### 改法

迁移 `011_tool_idempotency.sql` 新增 tool_calls 和 query_results 的 SQL 哈希、原始工具响应、内容唯一索引。每个 MCP 工具调用通过独立请求的 `_meta` 生成 `Idempotency-Key=task_id:tool_call_id` HTTP 头，不使用并发共享的可变请求头。所有工具都有传输幂等；SQL 额外按 task_id+标准化后执行 SQL 哈希+data_version 去重，事务级 advisory lock 避免并发重复执行，唯一索引兜底。

tool_calls 持久记录 running/done、完整响应和所有者 token。running 未超时返回可重试的 `tool_in_progress`；超过两倍 SQL 超时允许接管，旧所有者不能覆盖新结果。同 key 不同参数拒绝。重放 SQL/黑板写入仍先检查任务和租约，SQL 写结果前也保留原有 fencing。

HTTP 传输只对带 key 的请求增加一次连接/超时重试，复用同一 body/key；JSON 响应体超时同样覆盖。工具描述和系统提示未修改。新增工具错误返回字段：`error=tool_in_progress`、`retryable=true`、中文 `notice`；成功 SQL 返回字段未增加。

### 前后对比与收据

失败测试提交：`5998c43`；修复提交：`4dd9dab`。[旧实现失败 XML](../evidence/step12_a3_red.xml)。[针对性9项通过](../evidence/step12_a3_green.xml)，[同源码私有 MCP 完整277项通过](../evidence/step12_a3_full.xml)，包括真实 HTTP key 重放及所有工具的持久记录。

恢复实验是控制流程替身：真实 SQL 已提交后模拟丢失响应，令旧租约过期，再由生产 claim 领取并执行同一 SQL。没有调用真实模型，也不冒充实际 kill worker 演示。

| 指标 | 改前 | 改后 |
| --- | ---: | ---: |
| 实际业务 SQL 执行次数 | 2 | 1 |
| 保存结果行数 | 2 | 1 |
| 是否复用 result_id | 否 | 是 |

[改前收据](../evidence/step12_a3_before_20261027T144654Z_11d5ebb3.summary.json)、[改后收据](../evidence/step12_a3_after_20261027T144946Z_57320f70.summary.json)均附源码和原始日志 SHA-256；原始日志同名 `.jsonl` 保存在 evidence。

### 已知局限

迁移前结果没有 sql_hash，不回填或修改旧证据，内容去重覆盖迁移后写入的结果。HTTP 自动重试覆盖当前服务使用的 JSON 响应；未来启用 SSE 响应体时需另行处理流中断。running 返回可重试标记，由后续调用/恢复再次提交；不会无限轮询。data_version 的外部写入检测仍是后续 C5 范围。

## 12.1 / A4 结果截断显式化

### 旧问题与改法

原自动 LIMIT 1000 无法区分正好1000行和被截断。现在无 LIMIT 或超过1000的 LIMIT 实际最多取1001行，仅保存1000行；显式 LIMIT≤1000 保留原样。新增迁移 `012_result_truncation.sql` 保存 `truncated`，历史结果为 null（未知），不伪造历史截断结论。无顶层 ORDER BY 且截断时，notice 追加“无序截断,不代表前 N 名,汇总请在 SQL 中完成”。历史结论复制证据时携带原截断状态，网页证据弹层显示已截断/未截断/历史未知。

### 测试与收据

失败测试提交：`4bd76cf`；修复提交：`d214e80`。[改前4项失败 XML](../evidence/step12_a4_red.xml)。改后本地完整测试：[281项通过](../evidence/step12_1_full.xml)；CI 同构离线：[226项通过](../evidence/step12_1_offline.xml)。1000行、1001行、LIMIT500及有序截断均由真实数据库查询验证。A4 未做延迟对比，不填写估算。

### 工具返回变化与局限

`run_sql` 新增 `truncated`，截断且无序时扩展现有 notice；`get_result` 新增 `truncated` 和 notice。证据 API 新增 truncated。显式小 LIMIT 的“不截断”指调用者指定的查询结果，不代表原表只有这么多行。历史工具重放仍可能保留原始旧响应；历史查询分页和证据页显示未知。

## 12.1 验收检查点

新增迁移010–012；没有重跑/重新计分 holdout，没有真实模型调用。现有模型提示、知识库、数字闸门和核查器保持不变；所有数据库/MCP 集成测试通过后进入12.2。完整测试使用 `python -m scripts.local_tests` 启动同源码私有 MCP，避免与旧部署版本混淆。

## 12.2 / B1 服务加固（按规则11暂停，尚未修复）

### 旧问题与已完成的准备

连接仍按请求新建；SIGTERM 不主动释放租约；无 /healthz、/readyz 和统一启动配置校验。[失败测试 XML](../evidence/step12_b1_red.xml)实际复现4项缺失，仅提交测试和改前收据，没有实施连接池或退出逻辑。

### 改前实测

使用长响应 HTTP 模型替身，向生产 worker 进程发送 SIGTERM，另一 worker 经原 claim 路径接管。模型第一次请求阻塞90秒，后续请求立即返回；RAG/Memory 显式关闭以隔离退出流程。

| 指标 | 改前 | 改后 |
| --- | ---: | ---: |
| 从 SIGTERM 到第二次领取（ms） | 30803.701 | |
| 实际领取次数 | 2 | |
| 主动释放次数 | 0 | |
| 计入上限的领取次数 | 2 | |

[改前收据](../evidence/step12_b1_signal_before_20261027T145755Z_c28e6ca2.summary.json)和[原始日志](../evidence/step12_b1_signal_before_20261027T145755Z_c28e6ca2.jsonl)保存实际时间、事件和源码哈希；不属于真实模型性能数据。

### 需要确认的约束冲突

本批要求“worker 一个小池”，但已有多智能体历史结论路径在可信 worker 内访问两个数据库/角色：`scripts/runtime.py` 调用 `scripts.findings.retrieve/save_reviewed`；后者通过 `current_version()` 以 agent_ro 连接 olist 库读取 data_imports，同时以 agent_app 访问 agent 库。标准 psycopg_pool.ConnectionPool 不能将两个不同数据库/角色的连接当作一个可互换池。

保留现有路径需要 worker 两个独立小池；保持一个池则需把版本查询转到 MCP 等其他路径。按全局规则11停止，不自行新增第二个池、不保留未池化例外、不改数据版本读取路径。B2 尚未开始，12.2 未完成；待用户明确选择后续实现。
