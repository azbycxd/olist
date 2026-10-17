# 最终设计决策

当前交付按 Step 9 固定配置。旧默认值、失败尝试和迭代过程完整保留在 [决策历史](DECISIONS_HISTORY.md)，不以最新成绩覆盖旧证据。性能与质量数字只引用真实运行；最终逐次来源见 [FINAL_RESULTS](FINAL_RESULTS.md)，所有原始实验行见 [RESULTS](RESULTS.md)。

## 最终默认值与多智能体取舍

**问题**：复杂问题需要隔离上下文和审核，但更多角色也增加调用、成本与失败机会。

**方案对比**：single、multi_no_review、multi；数字门禁独立开关，避免把门禁收益归因于多智能体。

**选择**：默认 single + 门禁 + RAG inject + vector + Memory + none；多智能体保留可选。默认单 Agent 直接执行，多智能体才进入计划确认和子问题恢复流程。single 的数字值匹配是确定性检查，不能称为语义 Reviewer；single Memory 是用户偏好，不包含 finding 复用。

**数据**：Step 6 在实际拆分题集上的同轮配对中，multi 均更慢，事实命中有升有降，不能宣传并行加速。三次重复的 single+门禁平均 Agent 耗时 10202.94 ms，multi+门禁 16016.72 ms；该历史协议 Memory 关闭，不与最终开启 Memory 的组混算。[统计证据](../evidence/eval_review6-statistics_20261017T100149Z_ea5440cc.summary.json)，日志 `eval_review6-statistics_20261017T100149Z_ea5440cc.jsonl`；逐次来源和范围见 [重复对比](REVIEW_COMPARISON.md)。最终配置 dev 的新对照见 [最终表](FINAL_RESULTS.md)。

## 固定评测与一次性 holdout

**问题**：在开发题上反复调试后报最好成绩会高估能力，gold SQL 自洽也不证明正确。

**方案对比**：示例题演示、无固定划分的重跑，或冻结分层题库、独立计算 gold、一次预声明留出评测。

**选择**：冻结题目和 gold；C 自然问法不暴露口径，保留 naive SQL 证明陷阱。pandas 只读原始 CSV 独立重算；评测运行器可查 oracle，模型进程不能获得 gold、模板或私有评分 rubric；D 类公开提供所需事实字段名，不提供标准值。holdout 启动前保存源码快照及逐文件哈希，固定最终配置并完整执行三轮；每轮每题独立用户，E 仅在本题的设置/提问会话间共享用户。失败计入分母，不选择性补跑。协议启动标记阻止再次执行；汇总读取收据，不产生新模型调用。

**数据**：原始 CSV 交叉验证全部 67 道题一致，见 [交叉验证](../evidence/cross_check_20261017T070428Z_accb136c.summary.json)，日志 `cross_check_20261017T070428Z_accb136c.jsonl`。最终 holdout 的每轮正确数、均值、范围和每题稳定性见 [FINAL_RESULTS](FINAL_RESULTS.md)。题库为自编业务题，不是独立抽样的生产流量；三轮是对同一题集重复，不是三倍独立题量。模型归因评分尚未人工校准。

## 业务口径检索与固定向量模型

**问题**：自然问题省略客户去重、GMV 运费、状态排除等口径，模型容易产生数值正确但业务定义错误的 SQL。

**方案对比**：无知识库、工具式检索、预先 inject；检索采用 BM25、纯向量、等权 RRF 或 BM25 降权 RRF。

**选择**：默认 inject + 纯向量，保留其他开关。bge-m3 独立容器提供 OpenAI 兼容 `/v1/embeddings`，通过镜像源下载固定 revision `5617a9f61b028005a4858fdac845db406aefb181`，模型缓存到 Docker 数据卷。服务加载完成才通过健康检查；每次评测记录模型名/revision，使用检索时核对服务与权重哈希。

**数据**：C dev recall@3，vector 17/17，等权混合 15/17，BM25:vector=0.25:1 的加权混合 16/17，BM25 14/17。[证据](../evidence/eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.summary.json)，日志 `eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.jsonl`。权重预先固定，未反复搜索；只有 17 道同源陷阱题，不能外推通用检索优势。最终 −RAG 的严格对照见 [消融表](FINAL_RESULTS.md)。

## 报告数字门禁与独立核查

**问题**：报告会自行补出差值、比例或计数；模型互相审核也可能共同漏错。

**方案对比**：提示约束、标红提示、无限重写，或确定性扫描后有限退回。

**选择**：`NUMBER_GATE=true` 时扫描正文，将无批准证据的数字反馈给模型重写一次，仍有则替换“未验证”。所有报告数字，包括差值和比例，必须由 SQL 计算；模型不得自行运算。跨行 value 必须是行对象数组，同一对象的键来自 SQL 列名，值来自同一结果行。匹配按绝对值容差处理“下降/减少/环比为负”，但匹配幅度不等于验证方向语义。评测核查器独立实现，并同时检查正文与 claim.text；门禁不篡改结构化值或 gold。日期、证据 UUID、列表编号不是业务数值。

**数据**：Step 6 三次重复中，single 的 D 无证据数字比例均值从 21.67% 降至 2.43%；multi 从 14.59% 降至 3.99%。[完整协议证据](../evidence/eval_review6-fixed_20261017T092756Z_ed1d9efd.summary.json)，日志 `eval_review6-fixed_20261017T092756Z_ed1d9efd.jsonl`；范围与分母见 [重复对比](REVIEW_COMPARISON.md)。初版列表序号误截行首小数的 bug、修复前全部运行与修复后完整重跑仍在历史中。门禁不证明口径正确；元数据残留数字与语义问题见 [FAILURES](FAILURES.md)。

## 正常上下文与压力测试

**问题**：长任务工具结果挤占窗口，但摘要本身也消耗模型调用并可能丢信息。

**方案对比**：none 保留上下文；mask 保留结果引用并压缩旧工具内容；summary 通过模型生成摘要。

**选择**：正常窗口默认 none，mask 作为长任务开关。最终消融中的“−压缩”专指相同紧窗口下由 mask 切回 none；不能从默认 none 再关一次不存在的压缩。各策略用同一题集、预算、门禁和 Memory 设置，不与普通窗口混算。

**数据**：历史压力测试在 6000 上限下，none 完成 5/8、事实 15/25，mask 与 summary 完成 7/8、事实 22/25；mask 与 summary 的实际总 token 分别 108080、148094（含评分）。来源为 [重复对比中的压力组](REVIEW_COMPARISON.md)，日志 `eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.jsonl`、`eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.jsonl`、`eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.jsonl`。最终门禁/Memory 均开启的压力对照另列于 [最终表](FINAL_RESULTS.md)，旧组不冒充完全匹配的消融。峰值为应用侧估计，包含被拦截请求，不能等同供应商接受窗口。

## 用户偏好与可审核的分析记忆

**问题**：跨会话偏好容易丢失，自动记忆又可能把模型猜测和过期答案放大。

**方案对比**：拼接历史聊天、自由摘要所有内容，或只保存可归属的明确用户偏好与 Reviewer 批准 finding。

**选择**：偏好由用户原话抽取，可查看/删除，当前问题条件优先；数据按用户隔离。multi 的 finding 只从持久化黑板读取已批准且进入最终报告的结论；按相似度阈值取候选并重新审核。同版本复制证据保留来源 ID，版本变化仅给历史问题线索。single 不保存或复用 finding。评测各题独立用户，避免历史答案泄漏。

**数据**：独立新说法偏好审计 20/20 精确匹配，提示未改，见 [审计收据](../evidence/memory_holdout_audit_20261017T092012Z_ab705f05.summary.json)，日志 `memory_holdout_audit_20261017T092012Z_ab705f05.jsonl`。这是偏好表达留出，不是题库 holdout。五道 D 题的两会话实验中，四道第二次无需 SQL，D02 仍需补查、步骤反而增加，见 [复用实验](FINDING_REUSE.md)与[证据](../evidence/eval_findings-dev_20261017T100156Z_399f6c31.summary.json)，日志 `eval_findings-dev_20261017T100156Z_399f6c31.jsonl`。不宣称所有重复问题都能节省调用。

## 数据边界、迁移与运行证据

**问题**：仅靠提示词不能阻止写库，修改历史迁移或只保留本机日志也无法复查。

**方案对比**：共享管理员连接、关键词拦截和手工改表；或最小数据库权限、SQL AST 白名单、编号迁移、不可变收据。

**选择**：业务库与 Agent 库隔离，只读账号、只读事务、AST 校验和超时共同约束；模型通过 MCP 查询，进程拿不到数据库和 JWT 凭据。查询结果完整保存并绑定任务/数据版本，模型仅看预览与 result_id。后续 DDL 只新增迁移，已执行哈希不可变。关键小型证据提交到 evidence，完整日志本机保留且在收据中记录哈希；缺 usage 不当作零，未配置单价不估费用。

**数据**：最终 [181 项单元/数据库/MCP 验证](../evidence/step9_release_tests.xml)，日志 `step9_release_tests.log`；真实模型注入测试为 8/8 暴露、0 次诱导，见 [注入收据](../evidence/injection_20261017T075418Z_5df33c1a.summary.json)，日志 `injection_20261017T075418Z_5df33c1a.jsonl`；首次分类口径有误的结果也在 [历史决策](DECISIONS_HISTORY.md) 中保留。有限测试不是安全证明；真实模型可能被文本影响，数据库权限仍是独立边界。

## 后台执行、确认与恢复

**问题**：长分析不能占住 HTTP 请求，worker 被杀后不应丢掉已持久化的查证结果。

**方案对比**：同步 HTTP、额外消息队列，或数据库任务队列与租约；恢复整个任务或恢复子问题。

**选择**：API 只入队，独立 worker 用 `FOR UPDATE SKIP LOCKED` 领取并续租。默认 single 直接执行，恢复时重跑该任务；可选 multi 先确认 DAG，再按已审核子问题恢复，查询完成但审核未完成时继续审核。租约 fencing 阻止旧 worker 继续提交。追加事件和 SSE Last-Event-ID 支持重连；报告按文本渲染，点击数字可查看 SQL。登录、任务、结果、Memory 都按 JWT subject 校验归属。

**数据**：同一真实多智能体任务中断后复用 SP 检查点并完成 RJ，首次重启命令失败也保留，见 [恢复证据](../evidence/resume_demo_20261017T100621Z.summary.json)，日志 `resume_demo_20261017T100621Z.jsonl`。空数据库与空模型缓存的 [启动证据](../evidence/fresh_compose_20261017T101027Z_450b90f6.summary.json)，日志 `fresh_compose_20261017T101027Z_450b90f6.jsonl`；测试复用本机镜像与 CSV，不声称另一台机器验收。恢复中丢失的在途 usage 无法补算，完整总量留空。

## Step 9 冻结后的结论

**问题**：最终报告必须反映真实剩余问题，不能根据 holdout 错题继续调参再报最好结果。

**方案对比**：修题调提示后覆盖旧成绩，或保留一次运行、逐题分析并明确不确定性。

**选择**：采用后者。开发消融在 holdout 前完成，holdout 后只做收据汇总、错误分析与文档整理。源码快照与当前逐文件哈希核对；若必须修复真实 bug，需另行说明并保留前后结果，不把修复后的分数冒充原始留出成绩。

**数据**：holdout 各轮 20/22、21/22、21/22，准确率均值 93.94%，范围 90.91%–95.45%；20/22 道三轮都通过。D 事实字段命中均值为 69.23%，不能只展示总准确率。逐题失败见 [FAILURES](FAILURES.md)；[统计收据](../evidence/eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.summary.json) 对应日志 `eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.jsonl`，全部原始来源见 [最终评测](FINAL_RESULTS.md)。没有改提示、模型运行时、gold 或评分器，也未重跑 holdout。

汇总完成后发现 `configuration.judge` 使用了错误字段名，原始收据实际为 `judge_mode=model`。仅修正只读汇总器的一处映射，不改变任何得分或模型执行路径。[修正前统计](../evidence/eval_step9-final-statistics_20261017T104954Z_640a2765.summary.json)（日志 `eval_step9-final-statistics_20261017T104954Z_640a2765.jsonl`）与上述修正后统计均保留；[修复核验](../evidence/step9_metadata_repair.summary.json)，日志 `step9_metadata_repair.json`，确认 holdout、逐题、dev 的指标和原始证据哈希完全一致，新增模型调用为零。冻结源码仍保留修正前版本，当前只有汇总器该行与冻结清单不同。

最终 dev 单项消融中，C 开启/关闭 RAG 为 17/17 与 11/17，E 开启/关闭 Memory 为 6/6 与 4/6；D 开启/关闭门禁为 6/8 与 2/8，但事实命中分别为 22/25 与 23/25。multi+门禁同为 6/8、22/25，平均 Agent token 34725.75、耗时 21218.78 ms，高于 single+门禁的 22004.38 token、11461.79 ms。压力 mask 完成 6/8、事实 19/25，none 完成 5/8、事实 13/25。这些单次观测支持保留默认选择，但不是稳定优势证明；每个数字与原始日志一一列在 [最终消融表](FINAL_RESULTS.md)。

[最终冻结与统计核验](../evidence/step9_release_integrity.summary.json)，日志 `step9_release_integrity.json`，独立复核源码归档、唯一一行汇总修正、原始题库/迁移、用户隔离及准确率/用量/耗时的汇总计算。[文档与日志核验](../evidence/evidence_integrity_20261017T105305Z_4bc116f8.summary.json)，日志 `evidence_integrity_20261017T105305Z_4bc116f8.jsonl`，已填 RESULTS 单元格和原始日志哈希一致，链接有效，候选提交文件未发现配置密钥。
