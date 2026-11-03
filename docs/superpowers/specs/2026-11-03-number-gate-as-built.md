# 数字闸门 as-built 规格

> **as-built 规格，补写于 2026-11-03，非开发前规格。**
> 业务代码核对基线：`e873b9e961309c701256356080408d8a658d4bf1`。本文只记录可核对的现状；本次为现有行为补保护测试，不属于 TDD，不是业务修复。

## 1. 目标、范围、不做的事

目标：说明数字如何与给定 claims 的值匹配、证据如何被批准、答案如何经一次改写及确定性替换，并标出测试边界。
范围：[agent/number_gate.py](../../../agent/number_gate.py)、[tests/test_number_gate.py](../../../tests/test_number_gate.py)，以及 [EVALUATION.md 的已知产品缺陷记录](../../EVALUATION.md#已知产品缺陷数字闸门损坏日期和时间)。
仅补充引用边界测试、配置及调用入口以说明覆盖与适用范围；本次只改 `tests/test_number_gate.py` 和本文。
不做：不改业务代码、开关、提示词、评分器或成绩，不修已知限制，不走 brainstorming 或业务实现流程，不运行真实模型或评测。

## 2. 已实现的行为

- 开关：`NUMBER_GATE` 控制调用方是否进入 `enforce()`；模块自身不检查此开关。部署默认开启：[.env.example](../../../.env.example) 为 `true`，[docker-compose.yml](../../../docker-compose.yml) 使用 `${NUMBER_GATE:-true}`；[config.py](../../../config.py) 的 `FINAL_CONFIG['NUMBER_GATE']='true'` 用于任务默认配置。需区分：`NUMBER_GATE` 缺失时的 `false` 回退实际写在三个调用入口，不在 config.py 中；config.py 的 `boundary_guards_enabled()` 则对独立的 `BOUNDARY_GUARDS` 回退 `false`。
- 入口一：[agent/worker.py](../../../agent/worker.py) 的单智能体 `final_answer` 路径，先 `approve_values()` 再 `enforce()`。
- 入口二：[agent/multi.py](../../../agent/multi.py) 的单子任务且未启用 memory 的直达路径，在 `final_answer` 时同样先批准再执行闸门。
- 入口三：[agent/writer.py](../../../agent/writer.py) 的 `write()` 直接把传入 claims 交给 `enforce()`，不调用 `approve_values()`；上游 `multi.approved()` 在 multi 模式按 Reviewer 决定筛选，在 multi_no_review 模式取已完成子任务的 claims。开关关闭时 writer 仍用 `mark_numbers()` 标红；历史来源附注后的额外 `scan()` 不是第四个 enforce 入口。
- `approve_values()` 按唯一证据 ID 获取 `get_result`（offset=0、limit=1000）；要求无错误、返回 ID 匹配、版本非空且同一 claim 的证据版本一致，并用 `value_in_rows()` 检查值。它不是语义审查。
- `scan()` 递归扫描字典值和列表元素，不扫描 JSON 键；跳过 None / bool。数字与给定 claims 的数值叶子按绝对值匹配，容差为 `max(批准值×1%, 0.00000001)`，支持千/万/亿换算。
- `nonbusiness_view()` 按 `BOUNDARY_GUARDS` 选择旧屏蔽规则或扩展规则；屏蔽仅作用于扫描视图。`scan(..., replace=True)` 把未匹配片段替换为“未验证”；替换数字型值时可将其变成字符串。
- `enforce()` 无未支持数字时直接返回；否则最多发起一次改写 `request()`，仅接受键集合恰为 `{'answer'}` 且可按 `allow_nan=False` 序列化的 JSON 对象，之后再次扫描并确定性替换。
- 改写异常记录 `number_gate_rewrite_failed`（异常类型）；`number_gate` 记录 `before`、`after_rewrite`、`replaced`、`rewrites`。本模块约束的是改写调用次数，不证明底层 HTTP 请求次数。

## 3. Given / When / Then：有测试断言的关键场景

G / W / T 分别为 Given / When / Then；同类输入合并。下表描述实际断言；本次只运行主要测试文件，结果见第 6 节，补充引用的边界测试未重跑。

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

## 4. U 场景覆盖状态

“已覆盖”限于列明的输入与断言；“未覆盖”指没有专项断言，不表示从未间接执行。U04、U06 不补测试；U07 只记录未修复限制，按要求不加测试。

| 编号 | Given / When / Then | 对应测试名 / 状态 |
| --- | --- | --- |
| U01 | G：证据为空、获取异常、返回 error、ID 不匹配、版本为空字符串或两份证据版本不同；W：`approve_values()`；T：均不批准；两份证据版本相同且值匹配时批准 | **已覆盖（7 个参数）**：`test_approval_requires_valid_consistent_evidence`；正向对照防止“一律拒绝”也通过 |
| U02 | G：答案扫描无未支持数字；W：`enforce()`；T：返回原对象、不调用 request，唯一事件三个数组均为空且 `rewrites=0` | **已覆盖**：`test_supported_answer_skips_rewrite_and_emits_empty_event` |
| U03 | G：原文“虚构 99”，request 返回 None、非法 JSON、`[1]`、`{"answer":"x","k":1}`、`{"answer":NaN}`；W：`enforce()`；T：均返回“虚构 未验证”；仅非法 JSON / NaN 记录失败事件，error 分别为 JSONDecodeError / ValueError，末事件替换 99、rewrites=1 | **已覆盖（5 个参数）**：`test_invalid_rewrite_preserves_original_for_replacement`；每个参数断言 request 一次及完整事件列表 |
| U04 | G：字典键含数字、值含 None / bool；W：递归 `scan()`；T：键不扫描，None / bool 保持原值且不报数字 | **未覆盖**；S01 的字典、列表用例没有这些输入 |
| U05 | G：claim=5 时的 5.04/5.06、claim=0 时的 1e-8/2e-8；30.5万/1.2亿/3千/1e3 对应 305000/120000000/3000/1000，及无 claims 的 UUID；W：scan；T：各容差对前者保留、后者替换，单位及科学计数法匹配，UUID 保留 | **已覆盖（9 个用例）**：`test_scan_relative_and_absolute_tolerance`、`test_scan_units_and_scientific_notation`、`test_scan_preserves_uuid_without_claims` |
| U06 | G：默认关闭扩展屏蔽，输入历史受损日期/月份样例；W：完整改写及替换；T：现有记录出现日期组件被改成“未验证” | **未覆盖**（历史损坏样例的专项 enforce 测试）；S08 只锁定旧扫描结果一致性，不能当成产品缺陷已修复的证明 |
| U07 | G：已进入改写分支，响应为 `{"answer":null}` 或 `{"answer":""}`；W：enforce 接纳该 JSON；T：答案变为 None 或空字符串，末事件 `replaced=[]`，也没有验证新答案与旧答案结构一致 | **已知限制，未修复；不加测试**。按现有候选接受条件、scan 对 None/空文本的处理记录 |

## 5. 已知限制（未修复）

- 既有离线记录：207 份 Step 13 真实回答中 44 份含“未验证”，共 169 处；其中 24 份涉及日期、时间或年份损坏。219 份 HTTP 替身回答无命中；本次没有重新扫描或计分。
- 保存的受损例子包括 `2016-09-04 未验证:未验证:未验证`、`2018 年 未验证-未验证 月`。默认 `BOUNDARY_GUARDS=false` 仍保留旧规则，不能用 S06 的开启模式断言宣称默认问题已解决。
- EVALUATION.md 另记录 **13 份回答**的筛选阈值或公式/换算常数被替换，如 30 天、50 单、2 件、86400、100、0.01；模式可重叠，不能与其他类直接相加。按当前 scan 规则，无匹配批准值时 `30 天`、`第 3 名`、`Top 10` 分别变为 `未验证 天`、`第 未验证 名`、`Top 未验证`；`12%` 只取数值 12，不会换算为比例 0.12，只有 claim=0.12 时变为 `未验证%`。这些上下文数没有专门豁免，未修复。
- **U07 未修复**：改写只校验外层键集合和有限 JSON，不要求 answer 非空，也不保持原答案类型或结构；因此 null / 空字符串可清空答案，合法 JSON 还可能把结构化答案改成另一种结构。`replaced=[]` 只表示扫描没有待替换数字，不表示内容完整或正确；本次不为 U07 加测试。
- 与评分器日期误报的根因相同：未充分区分上下文时间数字与业务度量；二者是独立实现，当前 checker 已修复部分形式不代表运行时同步修复。改写模型和最终确定性替换都可能破坏呈现。
- 44 份命中不等于 44 份误伤：还包含正确撤回的未存证派生业务数。详情及源日志 SHA-256 见[原扫描收据](../../../evidence/step13_number_gate_text_scan.json)，不改变已发布成绩。
- 扫描按绝对值和数值叶子匹配，不证明正负方向、指标含义或正文语义正确；`scan()` / `enforce()` 不获取证据。`approve_values()` 只用于上述入口一、二；writer 路径依赖上游 claims 的筛选，不能笼统称所有路径都由 approve_values 批准证据。

## 6. 本次验证

本次仅修改测试和本文，为现有行为补保护，不属于 TDD。2026-11-03 在项目 `.venv` 执行 `python -m pytest tests/test_number_gate.py -q`，实际结果 **`27 passed in 5.13s`**，退出码 0（原有 5 个、新增 22 个用例）。新增 request / remote 均为替身，未调用真实模型或数据库，未运行其他测试或评测；业务代码未改动，U04 / U06 仍未覆盖，U07 未修复且未加测试。
