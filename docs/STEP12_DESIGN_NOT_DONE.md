# Step 12 P2：尚未实施的设计

本文件只描述方案与未来验收，不改变索引、模型路由、SQL白名单或MCP协议。查阅日期：**2026-10-28**。性能、token和费用收益尚未测量，数字留空。任何后续行为变更均须先冻结新的回归协议，不能借用Step9 holdout或Step12默认dev成绩证明。

## 1. RAG 增量更新与索引切换

**问题**：知识重新导入时重复计算全部embedding；在原索引上逐条更新，会让一次检索混用不同文档或embedding版本，失败回滚也困难。

**方案**：对规范化后的文档内容记录哈希，对分块策略、embedding模型与revision也记录版本。相同内容与版本复用向量；新增和变化的块进入新generation，删除块只在新generation中移除。新索引完成后校验块数、维度、来源与检索样例，在短事务中原子更新active_generation指针。每次检索固定一个generation，正在执行的请求继续使用旧版本。旧索引按回滚窗口保留，通过同一指针原子回滚；构建失败不修改指针。切换后使知识缓存失效，不能把知识版本与业务数据C5计数混作同一含义。

**为什么现在不做**：当前知识库小且固定；增量索引增加双份存储、孤儿generation清理和并发切换复杂度，尚无真实增量吞吐需求。现在改切块或索引版本会改变检索结果，超出工程收尾范围。

**做的话怎么验收**：固定新增/修改/删除/未修改文档负载，记录实际embedding次数与耗时，未改块不得重复计算；在构建和切换边界注入崩溃，查询只见完整旧版或完整新版；并发请求证明单次检索版本一致，回滚后结果恢复。使用已有recall@3数据集对照旧索引，再执行单独预声明的C/D/E dev回归；不得重计现有holdout。

## 2. 检索元数据过滤与重排

**问题**：当前向量相似度不能区分指标定义、表结构和风险提示，同义问题可能召回不适用表的段落；仅靠前三个向量邻居没有单独的相关性重排。

**方案**：导入时增加document_type、applicable_tables、指标名和来源版本；先保留可解释的候选集合，再按问题确定的表/文档类型过滤。未知表或多指标问题不能过早过滤掉通用风险段落。增加独立重排模型处理候选，输出相关性分数和排序原因元数据，不让重排器执行文档中的指令。保留无过滤、过滤、过滤+重排三个固定配置，以相同候选预算比较；模型与revision提前固定。

**为什么现在不做**：增加推理依赖与延迟；适用表标注错误会直接降低召回。现有数据集仅17个C dev检索问题，不能据此宣称通用收益。当前不调整默认vector、top-k或权重。

**做的话怎么验收**：使用现有recall@3标注，按题记录相关块是否被过滤及重排位置，统计recall@3、候选覆盖、延迟和新增成本；补充元数据错误/缺失与重排服务不可用的替身测试。检索指标通过后再冻结一次下游C/D/E dev与边界回归，分别归因检索正确但SQL错误和检索漏召回，不挑最好的一组。

## 3. 模型路由

**问题**：所有正常请求都使用主模型，简单聚合也支付相同调用单价；备用模型C6只处理供应商故障，不是成本路由。

**方案**：先使用公开问题特征定义可解释路由：指标数、时间窗口数、是否需要比较/归因、所需工具能力与上下文长度。简单单指标走便宜模型，多指标报告和高复杂度问题走强模型；未知类型使用强模型。路由不能读取gold、题号或历史正确性。路由版本、实际模型、usage、费用和是否升级都记录在事件；升级次数、条件和预算在协议前固定，不能因当前答案看起来不好无限升级。每家模型单独配置上下文、价格、RPM/TPM和能力，不复用C6的同价假设。

**为什么现在不做**：当前没有可比较的第二家真实模型配置与冻结成本/质量基线。路由会改变模型行为，增加供应商可用性组合及成本结算分支，不能把替身测试当作模型质量证明。

**做的话怎么验收**：先用替身验证分流、超时、升级和预算不超支；冻结规则后按每题独立用户比较统一主模型与路由，统计C/E正确率、D事实命中、边界通过率、p50/p95耗时及逐题真实费用。报告路由误分题和缓存差异，分别保留两模型结果，不混入原主模型成绩；holdout仍不重跑。

## 4. MCP 2026-07-28 版本迁移

**问题**：本项目固定`mcp==1.30.0`，客户端仍调用`ClientSession.initialize()`。服务虽配置`stateless_http=True`，这只是旧SDK的HTTP会话选项，不等于支持新协议。实际构建镜像的`LATEST_PROTOCOL_VERSION`是`2025-11-25`，支持列表截止该版本；SDK源码中没有`server/discover`、`2026-07-28`、`InputRequiredResult`、`requestState`或`io.modelcontextprotocol/tasks`。检查未安装新包，证据见[SDK能力收据](../evidence/step12_mcp_sdk_capability.json)，原始日志`logs/step12_mcp_sdk_capability.txt`。

**方案**：以正式规范而非发布候选博客为准，逐层迁移：

1. 每次请求自带协议版本、客户端身份和能力，现代路径移除`initialize`/`initialized`与`Mcp-Session-Id`依赖。需要兼容旧客户端时，显式保留双版本适配，按规范解析版本错误后降级，不能遇到任意业务400都退回旧协议。[版本与兼容规则](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
2. 服务实现`server/discover`，返回支持版本和能力；客户端可以先发现，也可以直接调用并处理版本不支持。发现结果里的自报身份不能替代JWT鉴权。[Discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
3. HTTP继续使用单一POST端点，增加并校验`MCP-Protocol-Version`、`Mcp-Method`与适用时的`Mcp-Name`，校验头与消息体一致。GET常驻流和协议会话不沿用；SSE仍可作为单次请求的响应，不能把“无状态”误写成“不支持SSE”。项目API自己的任务SSE不是MCP传输，保持独立。[Streamable HTTP](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
4. MRTR以`InputRequiredResult`携带`inputRequests`与不透明`requestState`，客户端获取输入后重发原调用并附`inputResponses`。当前只读工具不需要反向sampling/elicitation，先不声明未实现能力；如以后引入，客户端不得解析或篡改state，服务须验证其完整性、身份、请求绑定和有效期。恢复重发必须继续受幂等、租约、预算约束，不能当作新任务重复执行。[MRTR](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
5. Tasks是双方显式声明的扩展`io.modelcontextprotocol/tasks`。服务决定返回持久任务句柄，客户端通过`tasks/get`、`tasks/update`、`tasks/cancel`驱动完成或补充输入。现有PostgreSQL后台任务不是这个协议扩展：以后需建立句柄映射、所有权检查、过期与终态恢复，不直接公开数据库任务表；取消是协作语义，仍保留租约隔离。[Tasks扩展](https://modelcontextprotocol.io/extensions/tasks/overview)
6. `_meta.traceparent`、`tracestate`、`baggage`按W3C格式传播。本项目客户端已经同时放`_meta.traceparent`和HTTP头，服务目前从HTTP头恢复；迁移时统一校验与恢复优先级，并以完整跨进程trace验证。自定义幂等/角色元数据改为符合规范的项目命名空间；JWT身份和角色是授权依据，不能信任`_meta`自报角色。禁止把用户标识、SQL或密钥放进baggage。[元数据与追踪规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/index)

**为什么现在不做**：实际固定SDK不支持该版本，需要同时改客户端、服务、错误分类、元数据与测试；直接换版本字符串不会实现协议。协议升级与槽位行为评估分开，避免混淆故障和质量变化。本节没有升级依赖、去掉握手或启用Tasks。

**做的话怎么验收**：先锁定确实支持该协议的Python SDK版本并检查源码/能力，建立现代—现代与允许的现代—旧版兼容矩阵；使用官方conformance测试和本项目真实HTTP集成检查发现、头体不一致拒绝、无会话跨实例请求、MRTR恢复、取消、Tasks跨用户拒绝、幂等和过期租约。SDK替身回归覆盖超时/连接错误分类，再跑真实评测入口的全流程替身演练、trace关联和预声明的C/D/E dev及边界质量回归；旧端点/镜像保留回滚路径，不重算holdout。

## 5. SQL 白名单误拒 EXISTS

**问题**：v2中C11/C12/C23/C24/D08各遇到一次`Function is not allowed: EXISTS`，改写后完成，额外请求与SQL修正消耗已计入v2。`sqlglot==30.23.0`把`exp.Exists`纳入`exp.Func`遍历，而当前SAFE_FUNCTIONS没有EXISTS。它在SQL语义上是只读子查询谓词，不是可以执行任意代码的函数；现在仍保持拒绝。

**方案**：以后对`exp.Exists`做显式AST节点处理，要求其子节点为受支持的SELECT/集合查询，而非简单地允许任意同名`Anonymous`函数。整个子查询递归走既有表、函数、类型、CTE作用域白名单：拒绝写CTE、SELECT INTO、锁、命令、多语句、系统/跨schema表、限定函数以及set_config/current_setting；关联子查询的外部列只能解析到当前合法作用域，CTE别名遮蔽不能授权同名系统表。RLS、州权限预检、只读事务、SET LOCAL超时和外层截断规则继续生效；不能跳过EXISTS子树，也不能把外层LIMIT机械插入子查询改变语义。NOT EXISTS同样检查内部AST。

**为什么现在不做**：放开原先拒绝的SQL会改变工具行为，需要单独回归，不能混入已经冻结的v2或本次槽位实验。预计可能减少一次拒绝后的修正调用、输入上下文和输出SQL tokens，但模型也可能改变查询策略或增加相关子查询开销；未做干预对照，节省量、费用和SQL耗时均留空，不从五道题推算收益。

**做的话怎么验收**：先提交能复现误拒的失败测试，再测试EXISTS/NOT EXISTS、相关/非相关、多层嵌套、NULL语义、CTE遮蔽、恶意函数/表及写子查询拒绝，保持RLS安全测试。用固定只读SQL检查结果一致和实际耗时；随后走31+10题真实入口的HTTP替身演练，冻结单独的“SQL护栏变更”协议，执行一次C/D/E dev和原10道边界题，并按题对照采用后的正式默认配置，记录修正次数、token、费用与正确性。不得借此重跑本次槽位评估或holdout。
