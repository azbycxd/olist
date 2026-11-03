# 数字闸门 as-built 规格

> **as-built 规格，补写于 2026-11-03，非开发前规格。**
> 业务代码基线：`27062194c67b3cb78d8aac6ff9d2de3192733e3e`。本文只记录可核对的现状，不是开发计划或修复声明。

## 1. 目标、范围、不做的事

目标：说明数字如何与给定 claims 的值匹配、证据如何被批准、答案如何经一次改写及确定性替换，并标出测试边界。
范围：[agent/number_gate.py](../../../agent/number_gate.py)、[tests/test_number_gate.py](../../../tests/test_number_gate.py)，以及 [EVALUATION.md 的已知产品缺陷记录](../../EVALUATION.md#已知产品缺陷数字闸门损坏日期和时间)。
为避免把已有覆盖记成缺失，仅补充引用两个边界测试文件中的相关断言，不扩展其他模块规格。
不做：不改业务代码、测试、开关、提示词、评分器或成绩；不补测试、不修缺陷，不走 brainstorming 或实现流程，不运行模型或评测。

## 2. 已实现的行为

- `approve_values()` 按唯一证据 ID 获取 `get_result`（offset=0、limit=1000）；要求无错误、返回 ID 匹配、版本非空且同一 claim 的证据版本一致，并用 `value_in_rows()` 检查值。它不是语义审查。
- `scan()` 递归扫描字典值和列表元素，不扫描 JSON 键；跳过 None / bool。数字与给定 claims 的数值叶子按绝对值匹配，容差为 `max(批准值×1%, 0.00000001)`，支持千/万/亿换算。
- `nonbusiness_view()` 按 `BOUNDARY_GUARDS` 选择旧屏蔽规则或扩展规则；屏蔽仅作用于扫描视图。`scan(..., replace=True)` 把未匹配片段替换为“未验证”；替换数字型值时可将其变成字符串。
- `enforce()` 无未支持数字时直接返回；否则最多发起一次改写 `request()`，仅接受键集合恰为 `{'answer'}` 且可按 `allow_nan=False` 序列化的 JSON 对象，之后再次扫描并确定性替换。
- 改写异常记录 `number_gate_rewrite_failed`（异常类型）；`number_gate` 记录 `before`、`after_rewrite`、`replaced`、`rewrites`。本模块约束的是改写调用次数，不证明底层 HTTP 请求次数。

## 3. Given / When / Then：有测试断言的关键场景

G / W / T 分别为 Given / When / Then；同类输入合并。下表只描述实际断言，本次未运行这些测试。

| 编号 | Given | When | Then | 对应测试名 |
| --- | --- | --- | --- | --- |
| S01 | claims 含 -5、10000；正文含年份、下降 5%、-5、1 万及无支持的 66，列表内也含 66 | `scan(..., True)` | 两处 66 被报告，结构化 66 变“未验证”，下降 5% 和 1 万保留 | `test_scan_sign_units_identifiers_and_structured_values` |
| S02 | 原答案含 99；替身改写又生成无支持的 88 和有支持的下降 5% | `enforce()` | 改写调用一次，88 被替换，5% 保留，末事件 `replaced=['88']` | `test_only_one_rewrite_then_replace_even_new_hallucinations` |
| S03 | 无 claims，答案为 999，改写调用抛 RuntimeError | `enforce()` | 返回“未验证” | `test_failed_rewrite_fails_closed` |
| S04 | 同一有效结果含 SP/5 和 RJ/9 两行；claim 分别为 SP/5 与 SP/9 | `approve_values()` | 只批准 SP/5，拒绝跨行拼成的 SP/9 | `test_single_approval_rejects_cross_row_and_bad_references`（实际没有构造错误引用） |
| S05 | claim 支持 181968.09；答案为数字、数字字符串或带 `1.` 列表序号的正文 | `scan()` | 数字及字符串保持原值，均无未支持数字；序号不误吞小数 | `test_leading_decimal_is_not_a_list_ordinal` |
| S06 | `BOUNDARY_GUARDS=true`；给定日期时间、年月范围、季度、标题序号及工具行数说明 | `scan(..., True)` | 参数中的文本不变、未支持数字为空 | `test_boundaries.py::test_gate_and_independent_checker_preserve_dates_and_tool_metadata` |
| S07 | `BOUNDARY_GUARDS=true`；业务量 1000/20、比率 12:30、非约定上限 2000，或日期后带利润 55 | 扫描 | 未支持数字的个数符合参数；不会因工具常数豁免而放过这些业务数字 | `test_boundaries.py::test_metadata_exemption_does_not_allow_business_numbers`（gate 只断言个数） |
| S08 | `BOUNDARY_GUARDS=false`；给定业务数字、时间戳、元数据和年份等样例 | 与冻结 Step 9 的 `scan()` 比较 | 返回结果一致；这不证明日期被完整保留 | `test_targeted_boundaries.py::test_fallback_matches_frozen_step9_prompt_contract_and_gate` |

S01–S05 位于主要测试文件；S06–S07 见 [test_boundaries.py](../../../tests/test_boundaries.py)，S08 见 [test_targeted_boundaries.py](../../../tests/test_targeted_boundaries.py)。

## 4. 未覆盖场景

“未覆盖”指未找到针对所列条件与结果的专项断言，不表示相关代码从未被间接执行；以下只记录现状，不批准新增测试或实现。

| 编号 | Given / When / Then | 对应测试名 / 状态 |
| --- | --- | --- |
| U01 | G：证据为空、获取异常、返回错误、ID 不匹配、版本缺失或混用版本；W：`approve_values()`；T：相关 claim 不获批准 | **未覆盖**；S04 只有有效引用下的跨行值检查，测试名称中的 bad_references 不等于已验证这些分支 |
| U02 | G：答案扫描无未支持数字；W：`enforce()`；T：原样返回、不调用改写，发出空数组且 `rewrites=0` 的事件 | **未覆盖**；S05 只调用 scan，不验证 enforce 的快速返回 |
| U03 | G：改写返回 None、非法 JSON、非对象、多余键或含非有限数值的答案；W：`enforce()`；T：不采纳候选，继续清理原答案，解析或序列化异常另记失败事件 | **未覆盖**；S03 只覆盖请求抛 RuntimeError 后的返回值，未验证完整事件字段 |
| U04 | G：字典键含数字、值含 None / bool；W：递归 `scan()`；T：键不扫描，None / bool 保持原值且不报数字 | **未覆盖**；S01 的字典、列表用例没有这些输入 |
| U05 | G：数值位于 1% / 1e-8 容差边界，或使用千、亿、科学计数法及 UUID；W：扫描；T：分别按容差、单位换算及标识符屏蔽规则处理 | **未覆盖**（这些边界及格式的独立断言）；S01 直接覆盖的是符号、万和年份，没有因测试名含 identifiers 就覆盖 UUID |
| U06 | G：默认关闭扩展屏蔽，输入历史受损日期/月份样例；W：完整改写及替换；T：现有记录出现日期组件被改成“未验证” | **未覆盖**（历史损坏样例的专项 enforce 测试）；S08 只锁定旧扫描结果一致性，不能当成产品缺陷已修复的证明 |

## 5. 已知限制（未修复）

- 既有离线记录：207 份 Step 13 真实回答中 44 份含“未验证”，共 169 处；其中 24 份涉及日期、时间或年份损坏。219 份 HTTP 替身回答无命中；本次没有重新扫描或计分。
- 保存的受损例子包括 `2016-09-04 未验证:未验证:未验证`、`2018 年 未验证-未验证 月`。默认 `BOUNDARY_GUARDS=false` 仍保留旧规则，不能用 S06 的开启模式断言宣称默认问题已解决。
- 与评分器日期误报的根因相同：未充分区分上下文时间数字与业务度量；二者是独立实现，当前 checker 已修复部分形式不代表运行时同步修复。改写模型和最终确定性替换都可能破坏呈现。
- 44 份命中不等于 44 份误伤：还包含正确撤回的未存证派生业务数。详情及源日志 SHA-256 见[原扫描收据](../../../evidence/step13_number_gate_text_scan.json)，不改变已发布成绩。
- 扫描按绝对值和数值叶子匹配，不证明正负方向、指标含义或正文语义正确；`scan()` / `enforce()` 本身不获取证据，证据批准由独立的 `approve_values()` 完成。

## 6. 本次核对

只静态核对代码、测试断言及既有文档；未运行单元测试、数据库查询、模型或评测。仅新增本文，提交推送后等待确认；U01–U06 不在本次处理。
