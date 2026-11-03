# SQL 护栏 as-built 规格

> **as-built 规格，补写于 2026-11-03，非开发前规格。**
>
> 本文记录已有实现及测试断言，不是新功能方案。业务代码基线：`942f4675ab23d38fca4ac53d3bc107e5baf13e20`。初稿只做静态阅读；确认后仅为现有行为补充保护测试并更新本文，**不属于 TDD**，没有修改业务实现。指定测试命令与结果见第 6 节；不运行数据库查询、模型调用或评测。

## 1. 目标、范围与不做的事

**目标**：把 SQL 护栏已经实现的输入检查、PostgreSQL AST 白名单、外层行数上限、探测 SQL 和内容指纹行为写成可追溯的规格，区分代码事实、测试已断言的行为和未覆盖的场景。

**范围**：

- 实现：[mcp_olist/sql_guard.py](../../../mcp_olist/sql_guard.py)，包括 `UnsafeSQL`、`GuardedSQL`、`guard_sql()`、`probe_sql()`、`sql_fingerprint()` 及本模块常量。
- 主要测试：[tests/test_sql_guard.py](../../../tests/test_sql_guard.py)。原有 3 个测试函数、44 个 pytest 用例；本次增加 5 个测试函数、6 个用例（U05 有两个参数），合计 8 个测试函数、50 个用例。运行结果单独记录在第 6 节。
- 已知限制依据：[STEP12_DESIGN_NOT_DONE.md 第 5 节](../../STEP12_DESIGN_NOT_DONE.md#5-sql-白名单误拒-exists)。其中的未来方案和未来验收不作为已实现行为。
- 为避免把已有覆盖误列为缺失，补充引用现有 `test_data_scope.py`、`test_rls_flat.py`、`test_truncation.py` 中直接涉及本模块行为的断言；不为这些模块补写完整规格。

**不做的事**：本次只修改 `tests/test_sql_guard.py` 和本文，不改业务代码、SQL 白名单、依赖、Agent、评分器或成绩；不实现 EXISTS 放行，不运行评测，也不启动 brainstorming 或业务实现流程。新增测试用于保护已存在的行为，不是先写失败测试再修改实现的 TDD。数据库权限、RLS、租约、查询执行、结果持久化及服务端截断标记不属于本模块的实现职责，本文只在已有集成测试能佐证本模块接口时引用它们。

## 2. 已实现的接口与处理顺序

以下是源码事实，不等于每一分支都有测试。

| 接口或规则 | 当前行为 | 源码位置 |
| --- | --- | --- |
| 输入 | 必须是非空白字符串，长度不超过 30,000 个 Python 字符；否则抛 `UnsafeSQL`，它继承 `ValueError` | `sql_guard.py:24–25,38–40` |
| 解析 | 以 `postgres` 方言、`ErrorLevel.RAISE` 解析，过滤 `None` 节点；捕获解析调用的 `ParseError` / `ValueError` 并转换为 `UnsafeSQL` | `sql_guard.py:41–44` |
| 顶层语句 | 过滤后必须恰好有一个语句，且根节点为 `exp.Select` 或 `exp.SetOperation` | `sql_guard.py:45–47` |
| AST 检查 | 遍历整棵树，拒绝 `DDL`、`DML`、`Command`、`Into`、`Lock`、`Dot`；CTE 内容必须是 SELECT 或集合查询 | `sql_guard.py:48–52` |
| 表来源 | `exp.Table.this` 必须为标识符；不允许 catalog；schema 仅允许未限定或 `public`。随后按 `traverse_scope()` 解析来源，物理表名须在导入的 `TABLES` 中 | `sql_guard.py:53–55,62–67` |
| 函数 | 遍历 `exp.Func`；匿名函数取大写名称，其余取 `sql_name()`，必须在 `SAFE_FUNCTIONS` 中。不是只看 SQL 文本关键字 | `sql_guard.py:13–19,56–59` |
| 类型 | 遍历 `exp.DataType`，其类型名称必须在 `SAFE_TYPES` 中 | `sql_guard.py:20–21,60–61` |
| 外层 LIMIT | 未写时加 `LIMIT 1000`；超过 1000 时压至 1000；这两种情况 `capped=True`。显式非负整数字面量不超过 1000 时保留其值，`capped=False`；其他外层 LIMIT 表达式拒绝 | `sql_guard.py:68–79` |
| 返回 | 返回 `GuardedSQL(sql, capped)`；`sql` 是 PostgreSQL 方言重新生成的公开 SQL，不承诺保留输入的空白、大小写或文本格式 | `sql_guard.py:28–30,80` |
| 探测 SQL | `probe_sql(public_sql, capped)` 重新解析公开 SQL；仅在 `capped` 为真时把外层 LIMIT 设为 1001，再生成 PostgreSQL SQL。返回的是内部探测字符串，不修改已经返回的公开字符串 | `sql_guard.py:83–88` |
| 指纹 | `sql_fingerprint(public_sql, capped)` 对 `normalize_sql(public_sql) + '\ncapped=' + str(bool(capped))` 编码后计算 SHA-256 十六进制摘要；本模块不自行实现规范化算法 | `sql_guard.py:33–35` |

`capped` 表示护栏是否补加或压低上限，不表示实际数据已经被截断。`guard_sql()` 和 `probe_sql()` 都不执行 SQL，也不读取结果行数。`probe_sql()` 的输入约定是公开 SQL 及其 `capped`，它没有再次调用完整的 `guard_sql()` 白名单检查。

## 3. Given / When / Then：已有测试断言

“有断言”表示测试源码包含相应断言，运行范围与结果见第 6 节。原有 `test_attacks_are_rejected` 只断言 `UnsafeSQL`，不验证错误消息；本次新增 U08 用 `match="business allowlist"` 锁定拒绝原因。原有 `test_read_only_queries_are_capped` 只检查公开 SQL 的 LIMIT 后缀，不验证数据库执行结果。

### 3.1 主要测试文件

下表测试名均位于 [tests/test_sql_guard.py](../../../tests/test_sql_guard.py)。同一个参数化测试可对应多个场景。

| 编号 | Given（前提） | When（动作） | Then（已有断言） | 对应测试名及参数 |
| --- | --- | --- | --- | --- |
| S01 | 输入 DROP、DELETE 或 UPDATE 语句 | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`DROP TABLE orders`、`DELETE FROM orders`、`UPDATE orders SET order_status='x'` |
| S02 | 输入两条 SELECT，或 SELECT 后接带注释的 DROP | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`SELECT 1; SELECT 2`、`SELECT 1; /* hidden */ DROP TABLE orders` |
| S03 | CTE 中包含 DELETE RETURNING，或包含 `pg_sleep` | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x`、`WITH x AS (SELECT pg_sleep(1)) SELECT * FROM x` |
| S04 | SELECT 带 INTO 或 FOR UPDATE | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`SELECT * INTO copy_of_orders FROM orders`、`SELECT * FROM orders FOR UPDATE` |
| S05 | 输入 COPY、EXPLAIN ANALYZE 或 SET | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`COPY orders TO STDOUT`、`EXPLAIN ANALYZE SELECT * FROM orders`、`SET statement_timeout=0` |
| S06 | 调用 `pg_sleep`，包括普通、schema 限定和双引号名称 | 调用 `guard_sql()` | 三个参数均抛 `UnsafeSQL` | `test_attacks_are_rejected`：`pg_sleep(1)`、`pg_catalog.pg_sleep(1)`、`"pg_sleep"(1)` 所在 SELECT |
| S07 | 调用文件、远程访问、会话设置、序列、锁或 XML 查询相关的非白名单函数 | 调用 `guard_sql()` | 各参数抛 `UnsafeSQL` | `test_attacks_are_rejected`：`pg_read_file`、`pg_ls_dir`、`dblink`、`set_config`、`nextval`、`pg_advisory_lock`、`lo_import`、`query_to_xml` 所在 SELECT；`pg_read_file` 用例含注释 |
| S08 | 查询系统 schema、其他 schema、跨 catalog 表，或 `data_imports` | 调用 `guard_sql()` | 各参数抛 `UnsafeSQL` | `test_attacks_are_rejected`：`pg_catalog.pg_authid`、`information_schema.tables`、`other.orders`、`agent.public.tasks`、`data_imports` |
| S09 | 用 CTE 同名别名尝试遮蔽物理表 | 调用 `guard_sql()` | 两个已有参数均抛 `UnsafeSQL`；第 22 行含 EXISTS 的参数当前先被 EXISTS 函数检查拦下，不能据此证明作用域检查生效 | `test_attacks_are_rejected`：嵌套 `pg_settings` 别名且含 EXISTS 的用例，以及 `WITH data_imports AS (SELECT 1) SELECT * FROM public.data_imports` |
| S10 | 输入 `regclass` 转换或 FROM `generate_series(...)` | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`SELECT 'pg_authid'::regclass`、`SELECT * FROM generate_series(1,100000000)` |
| S11 | 外层 LIMIT 为 ALL、子查询或 -1 | 调用 `guard_sql()` | 抛 `UnsafeSQL` | `test_attacks_are_rejected`：`LIMIT ALL`、`LIMIT (SELECT 10000)`、`LIMIT -1` |
| S12 | 无 LIMIT 的 COUNT，或针对 `public.order_items` 的 SUM / AVG | 调用 `guard_sql()` | 返回公开 SQL，以 `LIMIT 1000` 结尾 | `test_read_only_queries_are_capped`：前两个聚合参数 |
| S13 | 无 LIMIT 的只读 CTE 分组查询，或带 FILTER 的 COUNT | 调用 `guard_sql()` | 返回公开 SQL，以 `LIMIT 1000` 结尾 | `test_read_only_queries_are_capped`：`WITH x AS (SELECT customer_state,count(*) AS n FROM customers GROUP BY 1) SELECT * FROM x`、带 `FILTER (WHERE order_status='delivered')` 的参数 |
| S14 | 无 LIMIT 的 DATE_TRUNC，或 EXTRACT epoch / 86400.0 表达式 | 调用 `guard_sql()` | 返回公开 SQL，以 `LIMIT 1000` 结尾 | `test_read_only_queries_are_capped`：两个日期表达式参数 |
| S15 | 危险词和分号只存在于字符串字面量中 | 调用 `guard_sql()` | 不因该字面量拒绝；公开 SQL 以 `LIMIT 1000` 结尾 | `test_read_only_queries_are_capped`：`SELECT 'DROP TABLE orders; pg_sleep(2)' AS untrusted_text` |
| S16 | 输入无 LIMIT 的 `SELECT 1 AS n UNION ALL SELECT 2 AS n` | 调用 `guard_sql()` | 返回公开 SQL，以 `LIMIT 1000` 结尾 | `test_read_only_queries_are_capped`：UNION ALL 参数 |
| S17 | 输入 `SELECT * FROM orders LIMIT 2000` | 调用 `guard_sql()` | 公开 SQL 以 `LIMIT 1000` 结尾；本断言没有检查 `capped` | `test_explicit_limit_is_enforced`：第一条断言 |
| S18 | 输入 `SELECT * FROM orders LIMIT 7` | 调用 `guard_sql()` | 公开 SQL 以 `LIMIT 7` 结尾；本断言没有检查 `capped` | `test_explicit_limit_is_enforced`：第二条断言 |

### 3.2 已有补充测试对本模块的佐证

这些是现有测试，不是本次新增测试。涉及 `test_truncation.py` 的场景属于需数据库的集成测试，不能当作纯护栏单元测试。

| 编号 | Given（前提） | When（动作） | Then（已有断言） | 对应测试名 |
| --- | --- | --- | --- | --- |
| S19 | SQL 调用 `set_config('app.allowed_states',...)` 或 `current_setting('app.allowed_states')` | 调用 `guard_sql()` | 抛 `UnsafeSQL` | [test_data_scope.py](../../../tests/test_data_scope.py)：`test_model_cannot_change_or_inspect_scope` |
| S20 | SQL 查询 `order_scope` | 调用 `guard_sql()` | 抛 `UnsafeSQL` | [test_rls_flat.py](../../../tests/test_rls_flat.py)：`test_scope_mapping_is_not_a_model_table` |
| S21 | 同一任务先执行显式 `LIMIT 1000`，再执行未写 LIMIT 的同一查询 | 经 `run_query()` 使用护栏及探测 SQL | 观察到执行 SQL 分别为 LIMIT 1000 / 1001；返回行数均 1000，截断标记分别假 / 真，结果 ID 不同 | [test_truncation.py](../../../tests/test_truncation.py)：`test_explicit_limit_is_not_probed_or_reused_for_guard_cap` |
| S22 | 无 LIMIT 且有 ORDER BY 的订单查询 | 经 `run_query()` 执行并读取保存结果及 API 结果 | 执行 SQL 为 LIMIT 1001；工具、保存结果及 API 中的公开 SQL 为 LIMIT 1000；保存摘要等于 `sql_fingerprint(public_sql, True)` | [test_truncation.py](../../../tests/test_truncation.py)：`test_public_sql_matches_saved_rows_and_hash_but_execution_probes_one_more` |
| S23 | 输入显式 `LIMIT 500` 的查询 | 经 `run_query()` 调用护栏并执行 | 返回 500 行，截断标记为假；本参数没有直接断言探测 SQL 文本或 `capped` | [test_truncation.py](../../../tests/test_truncation.py)：`test_truncation_boundaries_are_explicit_and_persisted` 的 LIMIT 500 参数 |

## 4. Given / When / Then：初稿 U01–U10 的覆盖状态

保留初稿的 U 编号，记录确认后补充的保护测试。**已覆盖**指相应场景已有直接断言；**间接覆盖**指通过调用链中的行为断言提供保护；**未覆盖**指没有对应的专项断言，不等于该代码从未被其他测试执行。U09 保留为已知限制，不在本次补测试或修复。

| 编号 | Given（前提） | When（动作） | Then（代码所示行为） | 对应测试名 / 覆盖状态 |
| --- | --- | --- | --- | --- |
| U01 | 合法 SELECT 字符串字面量查询分别长 30,000 和 30,001 个字符 | 调用 `guard_sql()` | 30,000 字符通过并生成 LIMIT 1000；30,001 字符抛 `UnsafeSQL`，消息匹配 `at most 30000` | **已覆盖（长度边界）**：`test_sql_length_boundary`。依据 `sql_guard.py:39–40` |
| U02 | PostgreSQL 解析调用抛出 `ParseError` 或 `ValueError` | 调用 `guard_sql()` | 转换为 `UnsafeSQL("SQL could not be parsed as PostgreSQL")`，保留异常链 | **未覆盖**；无对应测试。现有攻击用例不单独验证解析异常转换。依据 `sql_guard.py:41–44` |
| U03 | 解析结果过滤 `None` 后没有有效语句 | 调用 `guard_sql()` | 按“必须恰好一条 SELECT / 集合查询”的条件拒绝 | **未覆盖**；无对应测试。已有 S02 验证多语句，不验证零语句分支。依据 `sql_guard.py:42,45–46` |
| U04 | 合法查询显式写 `LIMIT 0` | 调用 `guard_sql()`，再将其返回值交给 `probe_sql()` | 公开 SQL 保留 LIMIT 0、`capped=False`；探测 SQL 与公开 SQL 完全相同 | **已覆盖**：`test_zero_limit_is_preserved_without_probe`。依据 `sql_guard.py:68–88` |
| U05 | 外层 LIMIT 为 `1.5` 或 `1+1` | 调用 `guard_sql()` | 两个输入均抛 `UnsafeSQL`，消息匹配 `LIMIT must be a nonnegative integer literal` | **已覆盖（这两个参数）**：`test_noninteger_or_expression_limit_is_rejected`。依据 `sql_guard.py:70–73` |
| U06 | 合法查询显式写 `LIMIT 2000` | 调用 `guard_sql()`，再把 `sql` 和 `capped` 交给 `probe_sql()` | 公开 LIMIT 为 1000、`capped=True`，探测 SQL 以 LIMIT 1001 结尾 | **已覆盖**：`test_oversized_limit_is_capped_and_probed`，补齐原有 `test_explicit_limit_is_enforced` 没有检查的标记和探测结果。依据 `sql_guard.py:74–76,83–88` |
| U07 | 类型转换的 `exp.DataType` 名称属于 `SAFE_TYPES`，且其他检查均满足 | 调用 `guard_sql()` | 该类型节点不会触发类型拒绝分支 | **未覆盖**（类型白名单正向专项）；无对应测试。S10 的 regclass 只验证反向拒绝，不能证明白名单成员的正向解析与接受。依据 `sql_guard.py:20–21,60–61` |
| U08 | 输入 `SELECT * FROM (WITH pg_settings AS (SELECT 1) SELECT * FROM pg_settings) AS a, pg_settings`，不含 EXISTS | 调用 `guard_sql()` | 抛 `UnsafeSQL`，用 `match="business allowlist"` 确认内层 CTE 别名没有授权外层物理表 | **已覆盖**：`test_nested_cte_does_not_authorize_outer_system_table`。与第 22 行的旧用例分开验证。依据 `sql_guard.py:62–67` |
| U09 | 只引用允许业务表、内部为只读 SELECT 的 EXISTS 或 NOT EXISTS 查询 | 调用 `guard_sql()` | 当前仍因 EXISTS 不在函数白名单而拒绝；这是现状误拒，不是期望新增的允许行为 | **已知限制（无专项测试）**。已有含 EXISTS 的攻击同时引用系统表，没有专门断言合法查询的误拒。依据函数检查及设计文档第 5 节，详见第 5 节 |
| U10 | 相同公开 SQL 来自显式 LIMIT 1000 与自动上限两种路径；另有自动上限查询保存其摘要 | 经调用链使用 `sql_fingerprint()` 并保存、复用结果 | 显式上限与自动上限不复用同一结果；保存摘要等于 `sql_fingerprint(public_sql, True)` | **间接覆盖**：[test_truncation.py](../../../tests/test_truncation.py) 的 `test_explicit_limit_is_not_probed_or_reused_for_guard_cap`（S21）和 `test_public_sql_matches_saved_rows_and_hash_but_execution_probes_one_more`（S22）。已有断言保护结果隔离和摘要存储一致性，没有独立固定摘要断言；本次不新增指纹测试、不运行这些集成测试 |

本次补齐 **U01 的长度边界、U04、U05 的指定参数、U06、U08**；U10 改记间接覆盖；U02、U03、U07 继续标为未覆盖，U09 保留为已知限制。初稿 U01 中的非字符串、空字符串和全空白输入不在这次批准的新增测试范围内，仍未覆盖，不因长度测试通过而声称已覆盖。

## 5. 已知限制

### EXISTS 误拒，尚未实施放行

[既有设计文档第 5 节](../../STEP12_DESIGN_NOT_DONE.md#5-sql-白名单误拒-exists)记录：`sqlglot==30.23.0` 将 `exp.Exists` 纳入 `exp.Func`，本模块的 `SAFE_FUNCTIONS` 没有 EXISTS，因此只读子查询谓词也会被拒。该文档记录 v2 的 C11 / C12 / C23 / C24 / D08 各出现一次 `Function is not allowed: EXISTS` 后改写完成；本文只引用既有记录，没有重跑或重新计分。

`tests/test_sql_guard.py` **第 22 行**的现有攻击参数为 `SELECT * FROM pg_settings WHERE EXISTS (WITH pg_settings AS (SELECT 1) SELECT * FROM pg_settings)`。它当前先被 **EXISTS** 拦下，拒绝消息是 `Function is not allowed: EXISTS`，尚未进入后面的物理表业务白名单检查；旧测试本身只断言异常类型。该用例不能独立证明 CTE 作用域检查生效。本次 U08 去掉了 EXISTS，并以 `match="business allowlist"` 专门锁定作用域隔离的拒绝原因。合法 EXISTS / NOT EXISTS 的误拒仍列为 U09 已知限制。

未来显式处理 EXISTS AST、递归检查子查询、验证关联作用域、保留其他护栏及重新冻结回归协议，均是设计文档中的未实施方案。本文不把这些方案写成当前支持能力，也不对放行后的 token、费用或耗时收益作估计。

### AST 白名单不等于数据库语义或执行保证

- 接受的是特定 AST 形状、函数和类型的白名单，不是“所有只读 PostgreSQL SQL”。现有正向测试只覆盖列出的语法，不能由此推导其他语法均可用。
- 本模块检查表来源，但没有做数据库列存在性、结果正确性、执行计划或耗时验证；数据库是否可执行和是否有权限，不由 `GuardedSQL` 返回值保证。
- LIMIT 处理只针对根查询的 `tree.args['limit']`；它不是每个子查询的统一改写，也不是计算量或扫描行数上限。
- 公开 SQL 是重新生成的 SQL，不是输入文本的原样副本；`capped=True` 也不是 `truncated=True`。
- `probe_sql()` 注释要求探测 SQL 不对外返回、持久化或用于内容摘要，但函数本身只返回字符串。这一调用边界有 S21 / S22 的集成断言，不能由辅助函数单独保证所有调用者都遵守。
- 只有解析调用的 `ParseError` / `ValueError` 在此处被转换为 `UnsafeSQL`；不能把它扩大表述为“本模块的所有异常都会统一转换”。

## 6. 本次验证与改动边界

本次只为已有行为补保护测试并更新本文，不属于 TDD，不修改 `mcp_olist/sql_guard.py`。只运行以下指定单元测试命令，若失败则停止，不修改业务实现、不放宽断言：

```text
python -m pytest tests/test_sql_guard.py -q
```

运行记录（2026-11-03，项目 `.venv` 中的 Python）：**`50 passed in 0.51s`**，退出码 0；原有 44 个用例及本次新增 6 个用例全部通过。该结果来自上述命令的实际输出。本次未运行其他测试、数据库查询、模型或评测，不把现有成绩当作本规格的验证结果。后续补齐其他场景或改变护栏行为须另行确认。
