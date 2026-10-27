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

当前事件新增 `model_call.error_class`（成功为 null）；失败立即上报，实测等待毫秒在独立 `model_retry_wait.retry_wait_ms` 中（复核2修正）。模型请求耗时不包含休眠。A1 没有新增工具返回字段，没有修改系统提示、知识库或数字闸门。

验收：[完整测试 264 项通过](../evidence/step12_a1_full.xml)，[CI 同构离线 218 项通过](../evidence/step12_a1_offline.xml)。包括真实约 2 秒等待的假客户端测试、5 次错误后低于 100ms 的预扣拒绝、并发只放行一个探针及成功/失败转换。原重试测试的假异常改为可重试连接错误，断言改为抖动范围；没有修改核查器。

### 初次验收前后对比（复核3之前的失败策略）

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

`agent/sql_normalize.py` 使用 sqlglot PostgreSQL 解析与标识符标准化，保留字符串和双引号标识符大小写，解析失败保留原文。`agent/progress.py` 被运行循环和只读回放共用：保留连续三次规则，增加六轮窗口和四轮全错/空且无行数大于0的新 result_id 规则。停止事件记录 rule、step、role，旧规则仍用 `repeated_tool_calls`，新规则用 `no_progress`。

### 前后对比与收据

失败测试提交：`d4be752`；修复提交：`f292108`。[旧实现三项失败](../evidence/step12_a2_red.xml)。修复后三种轨迹分别在第6轮调用前、第3轮调用前、第4轮结果后终止，[针对性通过 XML](../evidence/step12_a2_green.xml)，[完整269项通过](../evidence/step12_a2_full.xml)。没有模型质量或延迟估算。

运行 `python -m scripts.replay_progress` 只读原始日志及收据，校验四份源日志 SHA-256，再以相同检测器回放全部97次最终配置运行。结果：运行97次、误判0次、新模型调用0次，不计算任何答案评分。[回放收据](../evidence/step12_a2_replay_20261027T144321Z_09661f40.summary.json)与[原始回放记录](../evidence/step12_a2_replay_20261027T144321Z_09661f40.jsonl)保留每次运行结论和源日志哈希。

### 已知局限

历史日志有70条工具结果摘要因长度截断不能完整解析；回放仍使用独立记录的 result_id/error，无法恢复的内容视为未知，不当作空结果。复核1后，row_count=0 即使返回新的 result_id 也不算进展；更新后的97条只读重放仍为0误判。A2 无新增工具返回字段，无提示词修改。

## 12.1 / A3 工具调用幂等

### 旧问题

同一 SQL 的并发请求、结果已落库但调用方丢失响应后的重跑，都会再次执行业务查询并插入结果；客户端没有连接失败重试。

### 改法

迁移 `011_tool_idempotency.sql` 新增 tool_calls 和 query_results 的 SQL 哈希、原始工具响应、内容唯一索引。每个 MCP 工具调用通过独立请求的 `_meta` 生成 `Idempotency-Key=task_id:tool_call_id` HTTP 头，不使用并发共享的可变请求头。所有工具都有传输幂等；SQL 额外按 task_id+标准化后对外 SQL 哈希+data_version 去重，事务级 advisory lock 避免并发重复执行，唯一索引兜底。

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

原自动 LIMIT 1000 无法区分正好1000行和被截断。现在无 LIMIT 或超过1000的 LIMIT 实际最多取1001行，仅保存1000行；显式 LIMIT<1000 保留原样，外层上限1000的查询用内部1001探测；公开SQL仍为1000。新增迁移 `012_result_truncation.sql` 保存 `truncated`，历史结果为 null（未知），不伪造历史截断结论。无顶层 ORDER BY 且截断时，notice 追加“无序截断,不代表前 N 名,汇总请在 SQL 中完成”。历史结论复制证据时携带原截断状态，网页证据弹层显示已截断/未截断/历史未知。

### 测试与收据

失败测试提交：`4bd76cf`；修复提交：`d214e80`。[改前4项失败 XML](../evidence/step12_a4_red.xml)。改后本地完整测试：[281项通过](../evidence/step12_1_full.xml)；CI 同构离线：[226项通过](../evidence/step12_1_offline.xml)。1000行、1001行、LIMIT500及有序截断均由真实数据库查询验证。A4 未做延迟对比，不填写估算。

### 工具返回变化与局限

`run_sql` 新增 `truncated`，截断且无序时扩展现有 notice；`get_result` 新增 `truncated` 和 notice。证据 API 新增 truncated。显式小 LIMIT 的“不截断”指调用者指定的查询结果，不代表原表只有这么多行。历史工具重放仍可能保留原始旧响应；历史查询分页和证据页显示未知。

## 12.1 验收检查点

新增迁移010–012；没有重跑/重新计分 holdout，没有真实模型调用。现有模型提示、知识库、数字闸门和核查器保持不变；所有数据库/MCP 集成测试通过后进入12.2。完整测试使用 `python -m scripts.local_tests` 启动同源码私有 MCP，避免与旧部署版本混淆。

## 12.2 / B1 服务加固

### 旧问题与已完成的准备

旧实现按请求新建连接；SIGTERM 不主动释放租约；无 /healthz、/readyz 和统一启动配置校验。[失败测试 XML](../evidence/step12_b1_red.xml)实际复现4项缺失，先单独提交测试与改前收据，修复见下文。

### 改前实测

使用长响应 HTTP 模型替身，向生产 worker 进程发送 SIGTERM，另一 worker 经原 claim 路径接管。模型第一次请求阻塞90秒，后续请求立即返回；RAG/Memory 显式关闭以隔离退出流程。

| 指标 | 改前 | 改后 |
| --- | ---: | ---: |
| 从 SIGTERM 到第二次领取（ms） | 30803.701 | 20736.954 |
| 实际领取次数 | 2 | 2 |
| 主动释放次数 | 0 | 1 |
| 计入上限的领取次数 | 2 | 1 |

[改前收据](../evidence/step12_b1_signal_before_20261027T145755Z_c28e6ca2.summary.json)和[原始日志](../evidence/step12_b1_signal_before_20261027T145755Z_c28e6ca2.jsonl)保存实际时间、事件和源码哈希；不属于真实模型性能数据。

### 已获批准的设计调整

本批要求“worker 一个小池”，但已有多智能体历史结论路径在可信 worker 内访问两个数据库/角色：`scripts/runtime.py` 调用 `scripts.findings.retrieve/save_reviewed`；后者通过 `current_version()` 以 agent_ro 连接 olist 库读取 data_imports，同时以 agent_app 访问 agent 库。标准 psycopg_pool.ConnectionPool 不能将两个不同数据库/角色的连接当作一个可互换池。

用户明确批准 worker 两个独立小池，默认 agent=2、olist=1，olist 使用 agent_ro、只读事务、懒加载。现已实现；两个池在退出时均关闭。API/MCP readyz 和 worker 心跳只检查 agent 库，olist 不因健康探测创建连接。

## 12.1 复核1：空行不是新证据

旧实现把任何新的 result_id 视为进展，实际 run_sql 空结果也分配 ID。现仅 row_count>0 的新 ID 算证据；空结果替身已与线上一致。失败测试提交 `76e5461`，修复提交见 Git 历史。

[失败收据](../evidence/step12_review1_red.json)2失败/4通过；[修复收据](../evidence/step12_review1_green.json)6通过。[只读重放收据](../evidence/step12_a2_replay_20261027T150757Z_76c794b1.summary.json)：97运行、0误判、70条结果内容不完整；未调用模型、未重新计分。结果内容不完整的历史轨迹不能证明完整结果下的所有边界情况。阈值未修改。

## 12.1 复核2、5、6：失败先结算，等待单独观测

旧实现先退避再发 model_call，延迟跨任务的熔断计数。现失败立即发 model_call（含 error_class），随后等待；实际等待毫秒移至 model_retry_wait.retry_wait_ms（带 control_call_id/role/step/attempt），不再放在 model_call。五个并发任务都在退避未结束时，第五个失败已使真实数据库熔断 open。fatal/unknown 保持原失败数，仅成功清零（半开探测失败仍重新打开）。

失败测试 `881e18e`，[失败收据](../evidence/step12_review2_red.json)6失败/20通过；[通过收据](../evidence/step12_review2_green.json)26通过。测试客户端是替身，不是真实模型。

局限：按“连续失败”计数，检测不出成功和失败交替出现（比如一半请求失败）的部分故障。传输层幂等键使用供应商返回的 tool_call_id；供应商在同一任务中重复使用同一 ID、但参数不同，会返回冲突错误，不会返回错误结果；test_running_expiry_takeover_conflict 覆盖冲突。

### B1 改法、验收与局限

API 单池，MCP 两池，worker 两个独立小池，checkout 检查失效连接并替换。查询只用 SET LOCAL 或事务级 SET TRANSACTION；statement_timeout 归还后恢复默认。池耗尽 HTTP 503。SIGTERM/SIGINT 停止领取，20s grace 后杀子进程、事务内释放租约和重排任务，released_count 抵消主动释放的领取次数；保留黑板。新增迁移013同时记录 worker_heartbeats。启动校验必填配置并只报变量名。Compose 停止宽限35s；健康检查读取 DB 提交后才写入的本地心跳，避免健康检查进程占额外连接。

[改后 SIGTERM 收据](../evidence/step12_b1_signal_after_20261027T151113Z_bfe476ea.summary.json)：接管20736.954ms、实际领取2次、主动释放1次、计费领取1次。[连接峰值收据](../evidence/step12_b1_pool_after_20261027T151155Z_9983089c.summary.json)：20任务全部完成、20 SSE、4 workers、40次 HTTP 替身调用。上限公式：API池 + MCP agent池 + MCP olist池 + worker数×(worker agent池 + worker olist池)=8+8+8+4×(2+1)=36；20ms采样实测峰值24。采样排除管理/采样连接，包含该验收的所有服务池连接；olist worker池在这些 single/Memory=false 任务中为0。

失败测试提交 `a8cf2ce`；本地全量293通过（含数据库与私有 MCP），离线231通过；XML及日志哈希见 [B1 验收清单](../evidence/step12_b1_checkpoint.json)。以上数字均为替身验收，不是真实模型性能。局限：连接峰值为离散采样；checkout 坏连接替换通过终止 PostgreSQL backend 验证，本项未重启整个数据库服务；SIGKILL 无法优雅释放，仍依赖原租约恢复。

## 12.1 复核3：故障队列等待及恢复

用户已确认允许运行中因供应商故障失败的任务重新排队。旧行为会启动子进程并立即将冷却期中的任务置为失败。现 claim 先检查 provider_health，冷却或正在半开探测时不领取；主循环每次最多等待 MAX_SLEEP=5s，仍执行原截止回收。运行中 provider_unavailable 或重试耗尽的 retryable model_error 原子重排，保留截止时间、黑板和未知用量预扣；unknown/fatal 不重排。迁移014新增 provider_requeues，与 released_count 分开，不计入恢复次数上限。

失败测试 `684874d`：[失败收据](../evidence/step12_review3_red.json)3失败/1通过，[通过收据](../evidence/step12_review3_green.json)4通过。

| HTTP 替身场景 | 请求次数 | 成功 | provider_unavailable 最终失败 | 截止失败 | 重排 | 总耗时ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 持续503，原300s截止 | 14 | 0 | 0 | 10 | 11 | 298220.891 |
| 第40秒恢复 | 16 | 10 | 0 | 0 | 3 | 82079.118 |

[持续503收据](../evidence/step12_review3_503_after_20261027T153551Z_ae4867a3.summary.json)、[40秒恢复收据](../evidence/step12_review3_recovery_after_20261027T153215Z_fc1cba00.summary.json)。均为真实运行的HTTP替身，不是真实模型性能。原A1改后“9个 provider_unavailable 最终失败”的收据是历史版本，已被当前排队策略取代；持续故障现在等待原截止时间，不能把总耗时增加解释为性能退化。

局限：恢复发现受30s冷却和最多5s轮询影响；未知token用量继续保守占用额度，不将网络失败猜成0消耗；用户取消、任务截止和额度上限仍优先。

## 12.1 复核4：内部探测 SQL 与证据 SQL

旧代码把内部 LIMIT 1001 存入 query_results.sql 并返回给模型/证据页。现 guard_sql 输出对外 LIMIT 1000，以此计算 sql_hash；仅实际执行时 probe_sql 转成 LIMIT 1001。小于1000的显式 LIMIT 保持原样。工具 run_sql/get_result、证据API以及新保存的SQL都使用对外版本。已有历史行不原地重写，读取展示时会将旧外层1001规范为1000；历史内部子查询的显式LIMIT不改变。

失败测试 `fa976f0`，修改 tests/test_sql_guard.py 和 tests/test_mcp.py 的对外断言为 LIMIT 1000；新增真实SQL执行、数据库哈希和证据API联合测试，确认执行1001但公开SQL重跑为1000行。

[失败收据](../evidence/step12_review4_red.json)11失败/39通过；[通过收据](../evidence/step12_review4_green.json)50通过。[复核后全量](../evidence/step12_reviews_full.json)298通过，含本地数据库与私有MCP。局限：历史存储行保持原样，公开读取兼容转换；历史内部探测版哈希不会原地改写，因此已有任务首次改用公开版哈希时可能新增一份结果。

## 12.2 / B2 全局限流

### 旧问题与改法

只有每用户并发和每日额度，跨worker供应商流量要遇到429才反应。新增迁移015：rate_buckets 保存每供应商 RPM/TPM 剩余量、补充时间和在途数；rate_leases 保存 call_id 的在途过期时间；model_reservations.rate_held 将桶预扣与结算关联。单条 UPDATE ... RETURNING 按 clock_timestamp() 补充并扣减 RPM=1、TPM=预扣tokens，行锁保证多个用户/worker共享。

容量不足会回滚整个预扣事务，归还池连接和所有锁后等待，最多 RATE_WAIT_MAX_SECONDS；超时以 rate_limited 结束。实际模型用量返回后，TPM返还预扣与实际差额（超额则补扣）；重复事件不重复返还。未知用量仅释放在途席位，保留TPM预扣；取消/重排释放席位，硬崩溃经在途租约过期回收。租约截止受 MODEL_TIMEOUT 和任务截止限制。配置默认不限制 RPM/TPM/在途；同供应商所有worker应使用一致配置。

### 真实前后对比

固定验收配置：20并发后台任务、20 worker、20 SSE；HTTP模型替身供应商桶10 RPM/16000 TPM，每个成功响应实际usage=1000 tokens，响应约1s。worker配置10 RPM/16000 TPM、最多3在途、等待上限180s；RAG/Memory关闭。该配置是预先固定的故障验收，不是供应商推荐值或参数搜索。

| 指标 | 改前 | 改后 |
| --- | ---: | ---: |
| 成功任务 | 20 | 20 |
| HTTP请求 | 35 | 20 |
| HTTP 429 | 15 | 0 |
| 实际tokens总数 | 20000 | 20000 |
| 实际tokens / 总耗时 × 60（TPM） | 14160.612 | 11463.439 |
| 滚动60s实际tokens峰值 | 16000 | 12000 |
| 总耗时ms | 84742.102 | 104680.633 |

[改前收据](../evidence/step12_b2_rate_before_20261027T153652Z_a191b84e.summary.json)、[改后收据](../evidence/step12_b2_rate_after_20261027T154011Z_fdd7de9d.summary.json)，各有同名jsonl、日志哈希和核心源码哈希。减少429以主动等待为代价，不能宣称延迟改善或真实模型吞吐。

### 测试、返回变化与局限

失败测试 `1f84c33`，5失败/1通过；修复后验证跨用户并发不超发、数据库时钟补充、差额仅返还一次、过期席位、等待期间可获取任务/桶锁、rate_limited终止、未知用量不虚构退款。全量308通过，CI离线234通过；XML和哈希见第1批最终清单。B2无工具返回字段变化；新增 rate_wait 事件（control_call_id、wait_ms、outcome）和终止原因 rate_limited。

局限：令牌桶允许初始突发，不等于供应商的严格固定/滚动窗口；未知实际用量保守保留扣额；预扣大于TPM桶容量时立即以rate_limited拒绝（第二轮复核4）；本机替身压测不能外推到真实供应商。修改同一供应商配置应同时重启所有worker，避免新旧配置交替更新容量。CLI/评测没有可信预扣回调，不走共享桶。

## 第1批最终验收

[最终校验清单](../evidence/step12_batch1_checkpoint.json)：全量308通过（本地数据库和同源码MCP集成）、CI离线234通过；保留各次XML和日志SHA-256。冻结题库、gold、核查器、知识库、数字闸门、旧迁移以及系统提示/工具定义均核对未变；未调用真实模型、未重跑或重计分holdout。README仍注明成绩属于Step9源码。

B2额外失败测试 `2109e73` 复现 rate_limited 后继续提取Memory；现终止后不再发起额外模型请求。MCP健康/池耗尽补充验收9项通过，确认SDK封装后HTTP仍返回503。最终恢复演示[新收据](../evidence/step12_a3_after_20261027T154303Z_682ab6a7.summary.json)再次实测重复SQL仅执行1次、保存1份、复用result_id；脚本已适配连接池和内部探测SQL。

新增迁移：010 provider_health；011 tool_calls/SQL内容去重；012 truncated；013 released_count/worker_heartbeats；014 provider_requeues；015 rate_buckets/rate_leases/model_reservations.rate_held。所有均为新增编号迁移，无旧迁移改写。

工具返回最终新增字段：run_sql.truncated；get_result.truncated/notice；幂等正在执行错误的 error=tool_in_progress、retryable=true、notice。截断时扩展现有notice；外层公开SQL和sql_hash恢复1000版本。证据API另加truncated。其余B1/B2不新增模型工具字段。事件新增/调整：model_call.error_class、独立model_retry_wait.retry_wait_ms、no_progress.rule、released、provider_requeued、rate_wait；终止原因增加model_fatal/provider_unavailable/rate_limited。

## 第1批提交对照

| 项目 | 失败测试提交 | 修复提交 |
| --- | --- | --- |
| A1 重试与熔断 | cd24c60 | 44c6f14 |
| A2 无进展检测 | d4be752 | f292108 |
| A3 幂等 | 5998c43 | 4dd9dab |
| A4 截断 | 4bd76cf | d214e80 |
| B1 服务加固 | a8cf2ce | 48feb95 |
| B2 全局限流 | 1f84c33；Memory边界补充2109e73 | 0c05250 |
| 复核1 空结果ID | 76e5461 | df92eea |
| 复核2 事件时序（含复核5计数） | 881e18e | 94bd518 |
| 复核3 供应商故障重排 | 684874d | 88746f1 |
| 复核4 对外SQL | fa976f0 | b1ab325 |

复核6的幂等ID冲突局限随94bd518记录。新增参数名称、默认值及来源类型均在 [PARAMETERS.md](PARAMETERS.md) 和 `.env.example`；供应商RPM/TPM保持空值，等待用户按供应商文档填写，未填不会开启全局限流。

[本批归档校验清单](../evidence/step12_batch1_archive_checksums.json)固定0c05250中新增/更新证据的Git字节SHA-256与本机采集SHA-256；结合早先12.1归档清单可校验全部本批证据。批次已完成，停止于12.2，等待审查，不进入12.3。


## 第1批第二轮复核1：LIMIT来源与内容去重

旧问题：显式LIMIT1000被内部探测误标截断，并与护栏补限额共享缓存。guard_sql现在返回公开SQL及capped；仅capped为真执行1001探测。哈希同时包含标准化公开SQL和capped，不增加工具返回字段。保存/证据页仍为1000。

真实数据库回归：改前新增测试1失败；改后全量309通过。超过1000行的orders表，显式1000与无LIMIT分别执行1000/1001、保存1000/1000，truncated分别false/true，result_id不同。收据：[日志、XML及哈希](../evidence/step12_r2_1_receipt.json)。旧哈希不会命中新格式，历史记录不改写；既有历史截断标记不追溯重算。


## 第1批第二轮复核2：供应商故障重排上限

旧问题：重排不占领取额度，只靠任务截止时间终止。现在行锁事务内检查PROVIDER_REQUEUE_MAX（预先固定3），三次重排之后再次供应商故障，以provider_unavailable终止；不影响优雅退出释放额度，也不重置原始截止时间。

改前新增测试1失败，改后队列/服务14测试通过；毒请求重排3次、第4次失败终止，另一任务经真实预扣/熔断结算完成。收据：[XML、日志及哈希](../evidence/step12_r2_2_receipt.json)。未重跑已有SIGTERM、持续503及40秒恢复演练，旧报告保留其代码版本与当时无限重排语义。

局限：重排是整个任务从头再跑，已完成的步骤会重新消耗token；SQL结果可以经内容去重复用。既有多智能体黑板恢复路径保留。上限限制单任务的影响持续时间；达到上限之前的可重试失败仍按原规则计入全局熔断，其他任务可能等待冷却，不能保证完全没有延迟影响。


## 第1批第二轮复核3：模块文档字符串

旧问题：四个模块的连接池import先于文档字符串。现移至文档字符串之后，无运行逻辑变化。改前4失败，改后4通过；[XML、日志及哈希](../evidence/step12_r2_3_receipt.json)。无新增局限。


## 第1批第二轮复核4：TPM永久容量不足

旧问题：预扣大于桶容量仍等满等待上限。现在在扣桶前抛出永久拒绝，外层事务回滚（包括可能的半开席位），记录rate_wait.reason=request_exceeds_tpm并以rate_limited结束。不预扣用户token、不产生模型请求。

改前1失败；改后限流10测试通过。测试容量100、预扣101、等待上限0.3秒，拒绝在0.15秒内完成；[XML、日志及哈希](../evidence/step12_r2_4_receipt.json)。这是本地替身时限断言，不是供应商性能数据。TPM未配置继续不限流。


## 第1批第二轮复核5：MCP业务库就绪

旧问题：MCP仅检查agent库。现readyz同时检查agent池和使用agent_ro的olist池，任一失败返回503；worker仍仅检查agent，保持olist懒加载。改前1失败，改后就绪/服务10通过；[XML、日志及哈希](../evidence/step12_r2_5_receipt.json)。健康检查只表示当前连通性，不保证后续业务查询一定成功。


## 第1批第二轮复核6：就绪取连接短超时

旧问题：readyz使用普通池5秒超时，超过compose检查3秒。现每个池的取连接使用READY_CONNECTION_TIMEOUT_SECONDS，默认1秒，失败返回503；普通业务取连接仍5秒。MCP两个池顺序检查，worker一个池且不建立olist连接。

改前3失败/1通过；六项改完后本地全量319通过；[XML、日志及哈希](../evidence/step12_r2_6_receipt.json)。该配置限制取连接时间，不把业务SQL的执行超时改为1秒。
