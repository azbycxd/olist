# Step 12 工程化加固定稿

截至2026-10-28，12.1–12.6已完成。默认仍为 single + NUMBER_GATE + RAG inject + vector + Memory + context none，DIMENSION_PRECHECK=true、BOUNDARY_GUARDS=false、CONTEXT_PREFLIGHT=false、SLOT_RESOLUTION=false。槽位实验未达到采用标准，不启用。未配置备用模型，只实现了切换逻辑和替身测试。

Step9的holdout **93.94%**属于Step9源码；Step12没有运行或重新评分holdout。Step12默认配置dev v2一次运行 **C17/17、D7/8、E6/6，共30/31**，每题约0.011元、缓存命中率73.85%。槽位开启的另一份一次性实验为C17/17、D4/8、E6/6、边界7/10，不能替代默认成绩。v1因19题全部事件序号冲突、没有最终答案，经批准作废；失败测试17165f0/修复1d97b1e，原记录保留。

原分批过程、每条复核的红/绿提交、旧策略收据和中间失败XML原样保存在[历史记录](STEP12_HARDENING_HISTORY.md)，其“下一步/当前未完成”描述仅代表当时状态。完整提交索引见[STEP12_COMMITS](STEP12_COMMITS.md)，设计未做项见[STEP12_DESIGN_NOT_DONE](STEP12_DESIGN_NOT_DONE.md)。本文件按最终行为归并，不以旧策略实测冒充最终代码的性能。

## A1 模型重试与熔断

**改之前**：任意异常都尝试4次，固定等待1/2/4秒，没有跨worker故障状态。

**改了什么**：408/429/500/502/503/504及超时/连接错误可重试；400/401/403/404/422直接失败，上下文超限400单独终止。全抖动退避及Retry-After秒/日期均受cap与剩余任务时间约束。失败立即发model_call并结算，等待另发model_retry_wait。provider_health按provider+model共享，行锁维护5次连续可重试失败、30秒冷却与唯一半开探测；只有成功清零，fatal/unknown不清零，过时成功不能关闭新一代熔断。worker领取前等待冷却，每次最多MAX_SLEEP；运行中的任务快速退出后原子重排，供应商/基础设施故障共享3次上限，超限终止。

**证据路径**：初始红/绿cd24c60/44c6f14及复核提交见历史记录。持续503与40秒恢复替身收据分别为[持续故障](../evidence/step12_review3_503_after_20261027T153551Z_ae4867a3.summary.json)、[恢复](../evidence/step12_review3_recovery_after_20261027T153215Z_fc1cba00.summary.json)：当时持续故障14请求、10截止失败、0 provider_unavailable终态；恢复16请求、10/10成功、3次重排、82.079秒。故障重排上限后来追加，[上限测试](../evidence/step12_r2_2_receipt.json)验证3次后停止；未再次运行这两份故障实验，不把旧无限重排收据当作当前上限行为。初次503请求40→5的历史数字对应已被替换的直接失败策略。

**局限**：按“连续失败”计数，检测不出成功和失败交替出现（比如一半请求失败）的部分故障。毒请求在到达重排上限前仍可影响共享熔断。重排是整个任务从头再跑，已完成步骤会重新消耗token；SQL结果可经内容去重复用。CLI/评测路径没有预扣回调，不经过共享熔断。

## A2 无进展检测

**改之前**：仅同工具、同原始参数连续3轮终止，SQL空白变化和交替空查询可绕过。

**改了什么**：run_sql先sqlglot标准化，失败回退原文；保留连续3次，新增最近6轮≤2种签名，以及连续4轮全错误/空结果且无新有效证据。row_count=0即便生成新result_id也不算进展，只有正行数新ID算证据；事件记录命中规则。

**证据路径**：初始d4be752/f292108；空行复核76e5461/df92eea。使用全部既有最终配置轨迹只读回放，[回放收据](../evidence/step12_a2_replay_20261027T150757Z_76c794b1.summary.json)：97运行、0误判、0模型调用。70条历史被截短工具输出按未知处理，不误当空结果。

**局限**：离线轨迹不覆盖所有生产探索；历史结果缺字段时保守处理。阈值固定，不按回放结果调参。

## A3 工具调用幂等

**改之前**：MCP不重试，重复SQL会执行并插入两份结果。

**改了什么**：迁移011增加tool_calls；task_id+tool_call_id作传输key，done返回原结果、running返回可重试执行中，超过两倍SQL超时可接管，owner防旧请求提交。客户端有key的连接/超时最多额外重试一次。内容键包含任务、标准化公开SQL、capped、data_version及权限上下文，事务锁和唯一约束确保相同请求并发只执行一次。租约仍逐次校验。

**证据路径**：5998c43/4dd9dab。[恢复前](../evidence/step12_a3_before_20261027T144654Z_11d5ebb3.summary.json)与[恢复后](../evidence/step12_a3_after_20261027T154303Z_682ab6a7.summary.json)均为替身场景，重复SQL实际执行次数2→1、结果行数2→1，复用原result_id。

**局限**：传输层幂等键使用供应商返回的tool_call_id；如果供应商在同一任务重复使用同一个id，同key参数不一致会返回冲突，不返回错误结果（test_running_expiry_takeover_conflict覆盖）。当前连接重试覆盖现有HTTP JSON传输；未来SSE传输需另验收。

## A4 结果截断显式化

**改之前**：自动LIMIT 1000，但无法区分恰好1000行和确有更多结果。

**改了什么**：guard_sql同时返回公开SQL和内部capped。仅护栏补上或压低LIMIT时实际取1001探测、保存至多1000；模型、query_results.sql和证据页一律显示公开LIMIT 1000，hash也使用公开SQL并加入capped。模型自带LIMIT≤1000原样执行，不额外探测，不标截断；避免与护栏截断结果互相去重。迁移012保存truncated，证据页显示标记；无ORDER BY截断的notice提示“无序截断，不代表前N名，汇总请在SQL中完成”。

**证据路径**：4bd76cf/d214e80、公开SQL复核fa976f0/b1ab325、LIMIT来源复核d1bb2d2/914e315；[来源与去重验收](../evidence/step12_r2_1_receipt.json)。覆盖恰好1000、超过1000、LIMIT500、显式LIMIT1000及同任务两种语义不共用ID。

**局限**：旧结果truncated为NULL，未篡改历史证据。显式LIMIT1000的false表示没有护栏额外截断，并不承诺这是完整业务结果。

## B1 连接池、优雅退出与健康检查

**改之前**：每次新建数据库连接；SIGTERM等待租约过期后才接管，额外消耗领取次数。

**改了什么**：API一个agent池；MCP的agent与agent_ro业务池分开；每个worker使用agent小池和按findings需要懒加载的agent_ro只读池。checkout检查坏连接，所有查询设置用SET LOCAL/只读事务。SIGTERM/SIGINT停止新领取，等待20秒后杀子进程，同事务释放租约和重新排队，released不计领取上限；两池均关闭，多智能体从黑板恢复。healthz检查进程，API/worker ready只检查agent，MCP ready同时检查两库；每池ready取连接超时1秒，正常5秒，Compose宽限35秒。worker写心跳；必填配置缺失拒绝启动。

**证据路径**：[SIGTERM前](../evidence/step12_b1_signal_before_20261027T145755Z_c28e6ca2.summary.json)、[后](../evidence/step12_b1_signal_after_20261027T151113Z_bfe476ea.summary.json)：模型替身接管30803.701→20736.954ms，实际领取均2次，计费领取2→1，主动释放0→1。[连接峰值](../evidence/step12_b1_pool_after_20261027T151155Z_9983089c.summary.json)；池上限公式为 **API池 + MCP两个池 + worker数×每个worker两个池**，4worker默认8+8+8+4×(2+1)=36，实测应用连接峰值24。查询归还后statement_timeout恢复默认的数据库测试通过。

**局限**：SIGKILL仍靠租约；数据库完全不可达时主动释放可能无法提交。worker业务池懒加载，所以ready不探测olist；MCP主要服务查询，必须探测olist。连接峰值是采样观测，非任意瞬间严格证明。

## B2 PostgreSQL共享限流

**改之前**：只有用户并发与每日额度，供应商限流遇429才退避。

**改了什么**：迁移015建立RPM/TPM桶与在途租约，在同一UPDATE RETURNING中按clock_timestamp补充并扣预留额度。等待发生在锁和事务之外，有总时限；预扣超过TPM总容量立即rate_limited并记录request_exceeds_tpm。结算按实际token退差额且只结算一次；未知usage保守保留预扣。未配置RPM/TPM则不限，inflight默认0不限。

**证据路径**：失败测试1f84c33/2109e73，修复0c05250；[20任务替身前](../evidence/step12_b2_rate_before_20261027T153652Z_a191b84e.summary.json)、[后](../evidence/step12_b2_rate_after_20261027T154011Z_fdd7de9d.summary.json)：请求35→20、429次数15→0、实际token均20000，平均TPM14160.612→11463.439、60秒滚动峰值16000→12000、总耗时84.742→104.681秒。

**局限**：令牌桶允许突发，不等价于所有供应商滚动窗口；多worker须一致配置。CLI/评测无准入回调，不覆盖共享限流。真实供应商性能不能从替身数字推断。

## B3 端到端追踪、指标与成本

**改之前**：只有任务events，没有跨进程trace；初版metrics全扫events，清理事件会让counter下降。

**改了什么**：016/017保存traceparent，API→worker→Agent步骤→模型/工具→MCP SQL保持一条trace，环境白名单及HTTP头传递。OpenTelemetry Python/OTLP HTTP 1.45.1，GenAI属性固定参考[官方fc13eed7](https://github.com/open-telemetry/semantic-conventions-genai/blob/fc13eed7a8019acfda2643ef4d1c4c729d3601c9/docs/gen-ai/client-inference.md)，2026-10-28查阅，Development约定。记录gen_ai.operation.name、provider.name、request.model、response.model、usage.input_tokens/output_tokens/cache_read.input_tokens及error_class/retry_count/retry_wait_ms；工具记名字/结果ID/行数/截断，SQL仅哈希与耗时，不写SQL或结果内容。OTLP空则不导出。018创建metrics_rollup并一条SQL回填，写事件同事务原子累加counter及直方图；/metrics仅读汇总和tasks/provider_health当前状态，标签无用户/任务/SQL。**counter只增不减，保留期及用户删除不影响累计指标。** 三单价只从配置读取，缺价或缺缓存usage则费用未知。

**证据路径**：f6a7e8e/4d8d7c8；汇总复核2e77d1d/95e1529。[真实trace](../evidence/step12_b3_real_trace.json)、[Jaeger图](../evidence/step12_b3_jaeger.png)、[metrics样例](../evidence/step12_b3_metrics.prom)、[汇总事务测试](../evidence/step12_r3_metrics_receipt.json)。首次README真实示例9879 tokens因退出flush缺SQL span；修复后获批再跑一次4939 tokens，22 spans/4服务，合计14818 tokens。无第三次模型任务，当时单价空，历史费用继续留空。metrics样例包含共享库历史替身事件，不当单任务用量。

**局限**：Jaeger本地内存存储不持久；SIGKILL/导出网络错误仍可能丢span；数据库不可用时SQL事件可能缺失。GenAI约定仍在开发；告警仅写文档未接系统，费用不是供应商账单。

## B4 故障演练与压测

**改之前**：缺少完整依赖故障、100任务/SSE压力的可复核收据。

**改了什么**：全部用HTTP模型替身，在真实PostgreSQL/MCP/API/worker路径演练。Toxiproxy在MCP与两库之间；启动MCP连接/超时和调用连接/超时归infra_retryable，共享故障重排3次上限，耗尽infra_unavailable。原RuntimeError经日志定位为瞬时MCP连接故障；SQL语义、权限、unknown_dimension、fatal不重排。

**证据路径**：每份报告首行/首字段标“模型替身”，不是模型质量或性能数据。

| 演练 | 实测 | 收据 |
| --- | --- | --- |
| PostgreSQL重启 | 任务1/1成功；API ready恢复1.475s；池恢复API/MCP1.450s、worker2.579s | [db_restart](../evidence/step12_chaos_db_restart.json) |
| 网络基线 | 5/5成功，12.729s，SQL均值4.652ms | [baseline](../evidence/step12_chaos_network_baseline.json) |
| 500ms延迟 | 5/5成功，74.454s，SQL均值508.917ms | [latency](../evidence/step12_chaos_latency.json) |
| 10%丢失改前 | 1/5成功，69.870s；3个bootstrap_error、1个连接RuntimeError | [before](../evidence/step12_chaos_packet_loss.json) |
| 相同配置唯一改后 | 3/5成功，67.055s；另2个启动失败 | [after](../evidence/step12_chaos_packet_loss_after.json) |
| 4worker/100任务/100同时SSE | 100/100成功，0错误，97.160s，61.754任务/分钟；队列p50/p95=48.156/89.463s，应用连接24/36、全部客户端26 | [load](../evidence/step12_chaos_load.json) |
| SIGTERM与503 | 直接引用A1/B1，不重跑 | [reused](../evidence/step12_chaos_reused.json) |

**局限**：改后另外2个失败来自实际SDK把超时编码为408，而原替身为-32001；已先红f33be49再修79d9c08，未再跑丢失场景，不能宣称最终代码5/5。Toxiproxy这里丢的是TCP数据块，不等同内核IP丢包。health轮询可能漏掉短暂MCP失联。100任务4worker串行处理时，排队p95约等于“任务数÷worker数×单任务耗时”，这是容量问题，不是故障，告警按worker数解读。

## C1 任务短期令牌

**改之前**：子进程共用静态MCP token，任务身份由调用者请求头声明。

**改了什么**：worker每次领取签HS256 JWT，含sub/task_id/lease_token/roles/aud=mcp-olist/exp/iat/jti，独立MCP_TOKEN_SECRET，30秒时钟偏差。MCP固定HS256并校验aud/exp，从令牌取身份，忽略伪造X-Task-ID等头；越权工具403且租约仍数据库校验。子进程没有静态token、签名secret或数据库凭据。静态token仅留健康检查/本地CLI评测兼容，不能代表后台任务。

**证据路径**：1516bb0/8af577d，[C1收据](../evidence/step12_c1_receipt.json)。跨任务、过期、错误aud、alg=none、角色越权及伪造身份头测试通过。

**局限**：多智能体角色在同一子进程，角色令牌防误用与越权调用，不能隔离同进程恶意代码；健康存活探针不意味着持有业务权限。

## C2 行级权限及RLS优化

**改之前**：agent_ro能读全部业务数据；初版RLS的嵌套EXISTS造成明显计划开销。

**改了什么**：019用户data_scope，020对customers/orders及关联子表启用默认拒绝RLS；缺失/空SET LOCAL app.allowed_states返回0行，ALL放行。agent_ro不是属主且无BYPASSRLS，SQL白名单禁set_config/current_setting。州/全国范围预检越权返回forbidden_dimension并boundary_stop说明无权限；评测用户ALL。025增加order_scope单层映射，agent_ro仅SELECT、模型白名单不放行该表；导入/后续写触发维护并纳入数据版本。

**证据路径**：[EXPLAIN诊断](../evidence/step12_c2_explain.md)对最慢D03/D02/D01/D06/D08比较前后ANALYZE/BUFFERS。根因为嵌套策略抬高计划成本，引发207–334ms JIT及错误基数/约99k循环；ALL运行时嵌套子计划实际loops=0，不能说每行都真的执行嵌套EXISTS。日期索引仍可用，没有证据支持security barrier阻止过滤下推是主要原因。按结论做单层映射和ALL InitPlan，红81c0f5e/绿2707572；31条固定SQL只读重测一次，无重复调参。

| 31条固定SQL | p50 ms | p95 ms |
| --- | ---: | ---: |
| 无RLS | 28.530 | 100.356 |
| 初版RLS | 74.416 | 500.678 |
| 优化后RLS | 29.114 | 73.780 |

原始收据：[before](../evidence/step12_c2_rls_before.json)、[after](../evidence/step12_c2_rls_after.json)、[optimized](../evidence/step12_c2_rls_optimized.json)。全部现有RLS安全测试保持通过，没有绕过RLS账号。

**局限**：范围预检是保守静态检查，复杂表达可能误拒；维度表不全受州RLS覆盖；order_scope增加写入维护成本，未压测写吞吐；单次SQL测量不代表所有硬件或线上负载。

## C3 脱敏、保留与用户删除

**改之前**：events文本可能保存敏感串，没有审计化保留和彻底用户删除路径。

**改了什么**：写events前递归脱敏文本，邮箱→[EMAIL]、手机号→[PHONE]、身份证→[ID]、CPF→[CPF]。样例alice@example.com、13800138000、11010519491231002X、529.982.247-25；32位十六进制订单号和金额不伤及。evidence/query_results业务结果不动。021审计与保留、022限制用户删除入口；终态过期30天删除事件和详情，保留最终答案、被引用result_id及最小任务归属；用户删除级联任务/事件/偏好/findings并审计。累计metrics不删除。

**证据路径**：3c10e94/733dbb0，[12.4检查点](../evidence/step12_4_checkpoint.json)，含脱敏样例及独立测试库保留/删除集成测试。管理员维护入口python -m scripts.maintenance retain或delete-user；用户入口DELETE /me。

**局限**：正则/CPF校验不是通用PII识别，可能漏报或误报；引用识别对UUID保守保留。维护任务需运维调度，本仓库未自动启动清理；独立文件日志/evidence不在数据库保留任务范围。

## C4 调用前上下文估算

**改之前**：模型请求后才知道上下文超限。

**改了什么**：CONTEXT_PREFLIGHT默认false；开启时按消息字符数×系数加预留输出估算，超限先按已有遮蔽策略压缩一次，再超限以context_limit_preflight终止，不发HTTP。系数使用历史dev日志比值p95=0.7288973384030418，不用平均、不搜索。

**证据路径**：39a303f/ccf447a，[拟合](../evidence/step12_context_fit.json)、[测试](../evidence/step12_c4_receipt.json)。3741样本覆盖95.2419%，绝对误差p50/p95=1293/5867 tokens，最大低估486，绝对相对误差p50/p95=66.466%/98.050%；不调用模型、不重新评测holdout。

**局限**：保守系数不是严格上界，对新模型/新文本分布不保证覆盖；默认关闭，所以本次槽位D02仍可触发既有context_limit。

## C5 数据与黑板版本

**改之前**：data_version只有导入哈希，后续写入不改变版本；旧黑板结构可能被新程序误读。

**改了什么**：023关键业务表语句级写触发器递增计数，版本=导入哈希:计数器；事务回滚不推进，025派生映射也纳入。旧finding版本不一致降级需复核，不注入旧事实值；024黑板schema_version=1，不认识的版本重建计划，保留任务预算与截止限制。

**证据路径**：10f3064/d91f713，[C5收据](../evidence/step12_c5_receipt.json)。改行、旧finding及旧黑板测试均在独立测试库，不修改正式数据。state_read/write返回新增schema_version，data_version格式增加计数器。

**局限**：全局计数会粗粒度失效且写入串行更新；无行变更的写语句也会推进；DDL变化仍需迁移管理。

## C6 备用模型

**改之前**：主供应商熔断无可选替代。

**改了什么**：三个FALLBACK配置共同提供时，在worker准入/排队检测主熔断后选择备用；去除reasoning_content等专有字段，事件记录实际provider/model。两者不可用则provider_unavailable；全空时不启用。

**证据路径**：b1105f2/544e41c，[C6收据](../evidence/step12_c6_receipt.json)。替身覆盖切换及双故障。**未配置备用模型，只实现了切换逻辑和替身测试**；没有备用模型dev成绩。

**局限**：现有费用/限流/上下文系数配置并非完整的逐模型配置体系；CLI无worker回调不切换。不同供应商语义与价格须独立验收。

## C7 槽位解析及一次性采用判定

**改之前**：口径依赖模型理解提示，没有代码化的来源和冲突解析。

**改了什么**：新增SLOT_RESOLUTION，默认false；开启时在第一次模型调用前解析金额定义/运费、逐指标订单状态、客户标识及时间。问题>保存偏好>知识默认，各值记录来源；冲突时问题优先并在答案说明。时间必需且无可解析值时直接澄清，不调用模型/MCP。关闭路径不增加消息/提示；time_range偏好提取也仅开启时扩展。

**证据路径**：失败测试274ed0c、实现c39d3be；评估保护红f46a05b/绿6d656a6。41题[HTTP替身演练](../evidence/step12_slot_rehearsal.json)零工程错误，0真实调用，120替身HTTP请求；[协议](../evidence/step12_slot_protocol.json)2b8dcf1单独提交推送后真实一次运行。结果 **C17/17、D4/8、E6/6、边界7/10，不采用，默认false**；[结果](../evidence/step12_slot_results.json)、[边界原答复核](../evidence/step12_slot_boundary_review.json)、[只读分析](../evidence/step12_slot_analysis.json)。dev 360617 tokens/0.43221048元/缓存66.93%，41题合计453295 tokens/0.56364920元/缓存65.81%。D01/D03/D08通过→失败，无失败→通过，dev费用比v2多0.09048360元。逐题对照同时记录在[RESULTS](RESULTS.md)与[DECISIONS](DECISIONS.md)。

**局限**：规则仅支持声明的日期/指标表达，不是通用语言解析；KB默认代码映射需随KB同步。缺时间先澄清挡住X08写拒绝和X09空结果任务；X06答案仍混淆无数据与零。D01/D08暴露既有文字数字核查局限、D03事实键不合契约、D02上下文超限；按协议不因答错改代码重跑。冲突说明可将数字型answer转成文本。边界评分为Codex对保存答案复核，不是独立人工；单次差异不证明完整因果。

## 最终验收与接口变化

实际构建镜像中全量单元+PostgreSQL+MCP测试 **414通过**，离线CI **320通过、94集成项排除**，两条第三方弃用警告；[全量XML](../evidence/step12_slot_image_full.xml)、[离线XML](../evidence/step12_slot_ci.xml)。此后只增加文档、收据和分析，没有修改运行源码、开关默认或测试。各项red XML保留，不把预期失败算入最终通过数量。

Step12新增迁移010–025，未改已执行001–009。工具返回新增truncated（历史可能NULL）、notice的截断说明、黑板schema_version；data_version增加计数器。guard_sql的capped是内部字段，不暴露为新工具字段；C7无工具返回变化，仅slot_resolution事件。其他新增观测字段为model_call.error_class/会计usage、独立model_retry_wait、sql_execution、provider/infra重排和trace相关事件。所有新增配置及来源见[41项参数总表](PARAMETERS.md#step-12-新增参数总表最终索引)。

[最终检查点](../evidence/step12_final_checkpoint.json)记录文件哈希、冻结核验与测试数量；[秘密扫描](../evidence/step12_secret_scan.json)覆盖已跟踪工作树、evidence和logs，不输出凭据内容。文件日志未作为业务保留任务删除；后续工程工作应新立协议，不能继续本批一次性评估。
