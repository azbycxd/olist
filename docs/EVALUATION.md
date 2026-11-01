# Step 13 评测体系加固

本批范围为13.1、13.2及补充题A段，不调用真实模型。新增模块独立运行，Agent、旧评测入口、系统提示、知识库、数字闸门、旧题库/gold、eval/checker.py和eval/scoring.py均冻结。新增参考解与变异是评分器的人工构造输入，不是重新运行或重计历史Agent/holdout成绩。

## 13.1 历史失败分析

先保存无类别的[开放观察](../evidence/step13_error_open_notes.json)，再归并为8类；每个失败试验只计一个主要类别，其他问题保留在备注。分类由 **Codex完成，待人工抽查**，不是独立人工盲审。公平性判断不改原得分。

纳入明确列出的8份模型运行：Step9 dev-final、holdout r1/r2/r3、Step12 v2、槽位dev及边界、原始Step10边界，共179次题目试验，原发布判断下18次失败。原始边界取Step10首次10题运行；Step11原/新边界及target是最终未采用的BOUNDARY_GUARDS候选，不混入最终配置分母；消融、替身和已作废v1也排除。Step9 dev-final本身为31题，不把其他配置的A/B运行拼进来。源文件名、SHA256、每条原始case/审核、完整事件轨迹及保存SQL见[逐条分析](../evidence/step13_error_analysis.json)。

事件先后只帮助定位错误出现的位置，不用于判分。first_observed记最早可见问题，failure_origin另记最终失败的直接表现；例如D02较早SQL语法错误已经恢复，不能仅因发生在前就断言它单独造成上下文超限。已从Agent库只读导出47份历史query_results补足日志截短内容，没有重跑这些SQL；X08/X09直接澄清本来没有SQL结果。日志和SHA见[保存结果导出](../evidence/step13_saved_query_results.json)。

| 类别 | 条数 | 占18条失败 | 代表试验 | 公平性分布 |
| --- | ---: | ---: | --- | --- |
| 上下文超限 | 2 | 11.11% | step9-dev-final:D02, slot-dev:D02 | agent_error:2 |
| 日期或定义阈值被当作业务数值 | 3 | 16.67% | step9-dev-final:D07, slot-dev:D01 | grader_issue:3 |
| 跨结果拼接单个证据行 | 1 | 5.56% | holdout-r1:D09 | agent_error:1 |
| 公开事实字段契约不符 | 4 | 22.22% | holdout-r1:D11, holdout-r2:D11 | agent_error:4 |
| 下降幅度与带符号变化混用 | 1 | 5.56% | step12-v2:D02 | task_ambiguity:1 |
| 无数据或不完整范围被作业务断言 | 4 | 22.22% | slot-boundary:X06, original-boundary:X02 | agent_error:4 |
| 过度澄清阻断任务 | 2 | 11.11% | slot-boundary:X08, slot-boundary:X09 | agent_error:2 |
| 缺时间未澄清 | 1 | 5.56% | original-boundary:X05 | agent_error:1 |

公平性分布：agent_error 14/18（77.78%）；environment 0/18（0.00%）；grader_issue 3/18（16.67%）；task_ambiguity 1/18（5.56%）。

事实字段问题按公开契约归agent_error：D11三轮和槽位D03数值可与gold对应，但eval/adapters.py确实把required_facts字段名发给Agent，并非私有要求；长表不等价的评分局限仍另记。v2 D02归task_ambiguity是审计判断：正文给正下降幅度、SQL/claim给带符号变化，原gold要求正数，而公开字段没有明确符号定义；不把这一判断变成改分。日期/阈值扫描的3条grader_issue均保存了事实命中、SQL结果ID、claim文字与原audit作为证据。

### 每条原始失败

| 试验（运行:题号） | 首次问题日志行 / 模型步 | 主要模式 | 公平性 | 原始日志 |
| --- | --- | --- | --- | --- |
| step9-dev-final:D02 | 738 / 2 | 上下文超限 | agent_error | `eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl` |
| step9-dev-final:D07 | 995 / 3 | 日期或定义阈值被当作业务数值 | grader_issue | `eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl` |
| holdout-r1:D09 | 587 / 4 | 跨结果拼接单个证据行 | agent_error | `eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl` |
| holdout-r1:D11 | 674 / 2 | 公开事实字段契约不符 | agent_error | `eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl` |
| holdout-r2:D11 | 661 / 2 | 公开事实字段契约不符 | agent_error | `eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl` |
| holdout-r3:D11 | 669 / 2 | 公开事实字段契约不符 | agent_error | `eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl` |
| step12-v2:D02 | 689 / 2 | 下降幅度与带符号变化混用 | task_ambiguity | `eval_step12-regression-v2-once_20261028T011034Z_c949fe88.jsonl` |
| slot-dev:D01 | 666 / 3 | 日期或定义阈值被当作业务数值 | grader_issue | `eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl` |
| slot-dev:D02 | 708 / 2 | 上下文超限 | agent_error | `eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl` |
| slot-dev:D03 | 774 / 4 | 公开事实字段契约不符 | agent_error | `eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl` |
| slot-dev:D08 | 978 / 2 | 日期或定义阈值被当作业务数值 | grader_issue | `eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl` |
| slot-boundary:X06 | 205 / 4 | 无数据或不完整范围被作业务断言 | agent_error | `eval_step12-slot-once-boundary_20261028T045332Z_f52ef925.jsonl` |
| slot-boundary:X08 | 282 / 模型前 | 过度澄清阻断任务 | agent_error | `eval_step12-slot-once-boundary_20261028T045332Z_f52ef925.jsonl` |
| slot-boundary:X09 | 286 / 模型前 | 过度澄清阻断任务 | agent_error | `eval_step12-slot-once-boundary_20261028T045332Z_f52ef925.jsonl` |
| original-boundary:X02 | 111 / 4 | 无数据或不完整范围被作业务断言 | agent_error | `eval_step10-boundary_20261017T110935Z_62bc557e.jsonl` |
| original-boundary:X03 | 164 / 4 | 无数据或不完整范围被作业务断言 | agent_error | `eval_step10-boundary_20261017T110935Z_62bc557e.jsonl` |
| original-boundary:X04 | 244 / 7 | 无数据或不完整范围被作业务断言 | agent_error | `eval_step10-boundary_20261017T110935Z_62bc557e.jsonl` |
| original-boundary:X05 | 291 / 3 | 缺时间未澄清 | agent_error | `eval_step10-boundary_20261017T110935Z_62bc557e.jsonl` |

### 准确率、证据支持与新增“严格通过”

准确率与无证据比例分开发布是有意的设计，答案正确不自动等于证据合规。本步按用户澄清分别检查对应评分器：改值/符号/标签看score；删证据/错任务引用/新增无出处数字看证据audit。补充实现细节：number/list的score只看答案；key_facts分支目前还要求事实键全部命中且证据无问题，故D并非完全独立的纯答案分数。本步不改这个既有行为。

**严格通过 = 保存的correct为true，且保存的unsupported_claims、unsupported_numbers都为0。** 缺audit标未知，不擅自补0。本表仅聚合旧收据，不调用check/score重新评判答案，不替代或改写任何发布成绩。这也不是业务错误率：历史日期误报会降低严格率，不能因此宣称对应业务数值错误。

| 原运行 | 总试验 | 原正确数 / 原准确率 | 严格通过数 / 诊断率 | 答案对但证据有问题 | 缺audit |
| --- | ---: | --- | --- | ---: | ---: |
| step9-dev-final | 31 | 29 / 93.55% | 26 / 83.87% | 3 | 0 |
| holdout-r1 | 22 | 20 / 90.91% | 14 / 63.64% | 6 | 0 |
| holdout-r2 | 22 | 21 / 95.45% | 16 / 72.73% | 5 | 0 |
| holdout-r3 | 22 | 21 / 95.45% | 15 / 68.18% | 6 | 0 |
| step12-v2 | 31 | 30 / 96.77% | 29 / 93.55% | 1 | 0 |
| holdout三轮合计（按试验） | 66 | 62 / 93.94% | 45 / 68.18% | 17 | 0 |

### 答案对但证据有问题的21条试验

| 运行 | 题号 | 原unsupported_claims / numbers | 具体问题（诊断，不改分） |
| --- | --- | --- | --- |
| step9-dev-final | C18 | 0 / 4 | 原核查报4个未支持数字；claim.text包含含1月1日、不含7月1日的中文边界日期；claim.value只含unknown_items=65。日期是范围说明，诊断疑似词法误报，保留原audit。 |
| step9-dev-final | C23 | 0 / 1 | 原核查报1个未支持数字；claim.text包含含2月整月，value只含reviewed_orders=796。月份为范围说明，疑似词法误报。 |
| step9-dev-final | E10 | 0 / 1 | 原核查报1个未支持数字；claim.text写秒数/86400换算，value包含delivery_days及样本数，没有换算常数86400。常量不是新增业务测量值。 |
| holdout-r1 | A08 | 0 / 1 | 原核查报1个未支持数字；claim.text说共5种，但SQL/claim.value仅返回支付方式列表，未返回COUNT列。列表正确不等于已显式绑定数量证据。 |
| holdout-r1 | A09 | 0 / 1 | 原核查报1个未支持数字；claim.text写review_score=1这个筛选条件，value只含记录数11424。定义阈值不是额外测量值，疑似词法误报。 |
| holdout-r1 | A10 | 0 / 1 | 原核查报1个未支持数字；claim.text写2018年5月，value只含订单数6873。此处按原收据标问题，不用当前修订过的日期规则重新计分。 |
| holdout-r1 | B10 | 0 / 1 | 原核查报1个未支持数字；claim.text写2018年1月，value只含264。原收据日期扫描问题保持可见，不用当前规则覆盖。 |
| holdout-r1 | C13 | 0 / 2 | 原核查报2个未支持数字；claim.text含6月30日全天，而value是paid_sales和paid_orders。疑似中文范围端点词法误报。 |
| holdout-r1 | C22 | 0 / 2 | 原核查报2个未支持数字；claim.text含7月31日全天，value只有missing_signature=6。疑似范围日期词法误报。 |
| holdout-r2 | A08 | 0 / 1 | 原核查报1个未支持数字；claim.text说共5种，但SQL/claim.value仅返回支付方式列表，未返回COUNT列。列表正确不等于已显式绑定数量证据。 |
| holdout-r2 | A09 | 0 / 1 | 原核查报1个未支持数字；claim.text写review_score=1这个筛选条件，value只含记录数11424。定义阈值不是额外测量值，疑似词法误报。 |
| holdout-r2 | A10 | 0 / 1 | 原核查报1个未支持数字；claim.text写2018年5月，value只含订单数6873。此处按原收据标问题，不用当前修订过的日期规则重新计分。 |
| holdout-r2 | B10 | 0 / 1 | 原核查报1个未支持数字；claim.text写2018年1月，value只含264。原收据日期扫描问题保持可见，不用当前规则覆盖。 |
| holdout-r2 | C22 | 0 / 2 | 原核查报2个未支持数字；claim.text含7月31日全天，value只有missing_signature=6。疑似范围日期词法误报。 |
| holdout-r3 | A08 | 0 / 1 | 原核查报1个未支持数字；claim.text说共5种，但SQL/claim.value仅返回支付方式列表，未返回COUNT列。列表正确不等于已显式绑定数量证据。 |
| holdout-r3 | A09 | 0 / 1 | 原核查报1个未支持数字；claim.text写review_score=1这个筛选条件，value只含记录数11424。定义阈值不是额外测量值，疑似词法误报。 |
| holdout-r3 | A10 | 0 / 1 | 原核查报1个未支持数字；claim.text写2018年5月，value只含订单数6873。此处按原收据标问题，不用当前修订过的日期规则重新计分。 |
| holdout-r3 | B10 | 0 / 1 | 原核查报1个未支持数字；claim.text写2018年1月，value只含264。原收据日期扫描问题保持可见，不用当前规则覆盖。 |
| holdout-r3 | C13 | 0 / 2 | 原核查报2个未支持数字；claim.text含6月30日全天，而value是paid_sales和paid_orders。疑似中文范围端点词法误报。 |
| holdout-r3 | C22 | 0 / 2 | 原核查报2个未支持数字；claim.text含7月31日全天，value只有missing_signature=6。疑似范围日期词法误报。 |
| step12-v2 | E10 | 0 / 1 | 原核查报1个未支持数字；claim.text写秒数/86400换算，value包含delivery_days及样本数，没有换算常数86400。常量不是新增业务测量值。 |

这些试验的原始日志名和SHA与上方逐条JSON的strict_diagnostics.source绑定，原完整回答和audit同时保存。尤其Step9中文日期规则和当前评分器不同；只读诊断保留当时的告警，不用现行规则重新打holdout分。

13.1测试先行：失败提交bf6593a，8个缺失诊断模块测试失败（首次Windows临时目录权限错误另存原XML，换工作区新临时目录后确认8个目标失败）。实现后的单元和全量XML为step13_1_unit.xml、step13_1_full.xml。旧评分器没有修改。

## 13.2 任务与评分器审计

新入口为`python -m eval.step13_grader --capture`，使用agent_ro在一个REPEATABLE READ READ ONLY事务中执行全部67条既有gold SQL（只设SET LOCAL），保存当前data_version、实际结果、耗时、SQL/题库哈希。构造带本题专属task_id/result_id的FinalAnswer，并用原check/score验证。证据存在审计内存映射和提交的fixture里，不插入正式query_results。**67/67参考解同时通过答案与证据评分器**。这不是运行Agent、holdout重答或历史重新评分。

[SQL与参考答案](../evidence/step13_gold_reference.json)、[逐条评分器审计](../evidence/step13_grader_audit.json)均记录源日志文件名及SHA-256。读取已保存fixture可用`python -m eval.step13_grader`纯离线重现；capture拒绝覆盖已有原始收据。现有eval/run.py、checker.py、scoring.py和题库均未改。

### 固定变异及对应评分器

| 变异 | 对应评分器 | 原67题：杀死/适用 | 不适用 | 补充12题：杀死/适用 | 不适用 | 漏掉题号 |
|---|---|---:|---:|---:|---:|---|
| 非零数值偏移5% | score | 63/63（100%） | 4 | 11/11（100%） | 1 | 无 |
| 非零数值符号取反 | score | 63/63（100%） | 4 | 11/11（100%） | 1 | 无 |
| 删除全部evidence | evidence | 67/67（100%） | 0 | 12/12（100%） | 0 | 无 |
| evidence换成另一题结果 | evidence | 67/67（100%） | 0 | 12/12（100%） | 0 | 无 |
| 改品类或州名 | score | 2/2（100%） | 65 | 2/2（100%） | 10 | 无 |
| 无出处业务数字 | evidence | 67/67（100%） | 0 | 12/12（100%） | 0 | 无 |

数值变异固定改遍历顺序中第一个非零数值叶子；保留原始SQL证据。原题A05/A08/B06/B09是纯文字列表，不存在可偏移/取反的数值；补充N09同理。代码还显式拒绝把0的乘法/取反当有效变异。标签变异仅适用于原题B06/D02、补充N06/N09：数字答案没有携带题干品类或州名，不能通过只改题干、制造字段来假装测试了答案标签。

key_facts把无出处数字加入answer正文；number/list必须保持其公开输出类型，所以加在公开claim.text说明里（同样由证据评分器扫描），不把原数值answer强行改成字符串。异题证据保留真实的不同task_id，即使两题值相同也必须拒绝；有专门测试。每个变异保存修改后完整答案、对应grader、audit、score、适用原因；分母从不把无效或不适用变异算成杀死。仅这组固定变异全杀死，不代表评分器对所有错误完备。

### 合理等价表达诊断

| 变体 | 原题误拒/适用 | 补充题误拒/适用 | 被拒题 |
|---|---:|---:|---|
| 宽表转fact/value长表，值不变 | 12/12（100%） | 9/9（100%） | D01–D12；N01/N03/N04/N05/N06/N07/N08/N10/N12 |
| 日期说明：2018 年 Q2；1 月到 3 月 | 0/67（0%） | 0/12（0%） | 无 |
| 下降加正幅度，claim保留原SQL符号 | 0/2（0%） | 不适用 | 原题D02/D04均通过 |

长表变体把保存结果和claim一起无损转换，证据检查全部通过，但score找不到规定键，所以全部被拒。它在信息层面等价，却不满足当前已公开的exact-key契约；这是**表示限制诊断**，不能直接归为评分器实现bug，也不能据此翻改D11历史成绩。日期文本是词法说明样例，不改变原查询时间；number/list仍放在claim.text。下降表达不改claim符号，因此不会重复v2 D02的有符号事实不一致问题。当前日期样例通过，不说明历史旧版本告警可以删掉。

### 逐题要求、歧义及盲区

JSON的67条ambiguity逐题列出原题、公开answer_type/required_facts/setup、期望数值、符号、容差、形状、完整gold SQL与WHERE/HAVING范围、未写入题干的检查。字段来自eval/adapters.py公开透传；C的业务定义来自KB，E的偏好来自setup，不能把这些伪称隐藏条件。

| 范围/题号 | 评分器检查但题干未明说，或待澄清点 | 审计判断 |
|---|---|---|
| A01–A10、B01–B10、C01–C25、D01–D12、E01–E10（全部67题） | 数值/证据容差、列表集合比较等通用实现细节未逐题写出 | 属于统一评测约定，建议集中公开，不是67道业务歧义 |
| D01 | 变化率取(Q2-Q1)/Q1；题干未显式定义方向 | 建议明确基期/符号，不宣称当前理解错误 |
| D02 | 下降金额要求正幅度；最大降幅并列时gold按品类升序取一个 | 符号是v2失败的诊断点；并列规则未公开，未声称本数据确有并列 |
| D04 | “两期相差”gold固定Q2-Q1，负值不能写成无符号差额 | 方向存在合理解释空间，建议明确 |
| D01–D12 | 事实键重复且矛盾、证据告警都会使整题不通过 | public required_facts名称已公开；组合判定细节建议集中说明 |

未发现现有67份gold结果与其参考解不相容的问题。语义澄清重点清单为**D01、D02、D04**，其余通用约定如上逐题附在JSON，不把仅在题干中省略、但公开契约已有的字段名当歧义。

建议（本步只写、不改）：在题干/公共协议显式写差值方向、基期和并列约定；集中公开答案与证据双评分及key_facts的组合例外；如将来允许长表，先约定可验证的字段映射，避免丢失标签-值绑定；补足中文日期/定义常量的词法反例；对B06/B09排名是否要求顺序作明确选择（当前list集合比较不查顺序/重复）；如果需要考察原因解释或谨慎表述，另设可审查评分维度，当前参考解仅“事实见证据”也能过D，rubric_focus并未自动核查解释。任何实现变更留给后续授权。

## 补充题A段

[新题库](../eval/step13_supplement_cases.json)原样收录N01–N12，split=supplement，未修改原questions.jsonl。逐题gold SQL全文、gold结果、pandas结果、口径与城市行数见[审阅全文](STEP13_SUPPLEMENT_REVIEW.md)。

12/12独立pandas与SQL结果一致（上限1%，本次记录差值为0），12/12参考解通过；适用变异全杀死，见上表。[交叉核对](../evidence/step13_supplement_crosscheck.json)、[参考SQL](../evidence/step13_supplement_reference.json)、[评分器审计](../evidence/step13_supplement_grader_audit.json)。pandas直接读取6份原始CSV，不使用SQL或旧cross_check计算函数；源CSV、程序和日志哈希均留存。

城市实际写法为`sao paulo`和`rio de janeiro`，客户表分别15540、6882行。N02圣保罗Q1匹配3286单。N03 Q2两市GMV分别用3994、1394行商品明细，对应3415、1204笔符合GMV状态的订单；全部状态订单分别3442、1204笔。SQL和CSV独立核对一致。

并列/缺失预检未发现当前答案不唯一：N01/N05/N06/N08最高/最低均唯一，N09第三名不并列；N08合格卖家的8236个卖家-订单对实际/预计时间缺失均0。仍待用户逐题确认，**没有用这12题调用真实模型**。

## 测试、提交与局限

13.1：失败测试bf6593a → 实现557dab5，已推送。13.2和补充A：失败测试af44c2e（90个目标失败）→ 本实现提交。新增离线测试共98个（13.1为8个、13.2/补充为90个），已有CI自动发现`tests/test_eval_*.py`，CI_OFFLINE拦截数据库/网络调用，无xfail。最终执行计数与源日志SHA见step13_2_checkpoint.json。

本地Windows旧venv缺项目依赖导致一次全套离线收集错误，原XML留存；使用已有容器完整依赖后13.1全量422通过、离线328通过。不是通过删测试绕开错误。

限制：分类为Codex阅读后判断，需人工抽查；参考解证明gold/契约自洽，不证明gold本身业务定义唯一（补充题有独立CSV重算）；固定变异仅覆盖当前表示中的适用叶子，不能代表所有错误；长表是信息等价但违背现契约的诊断；SQL范围由数值间接约束，语义正确但巧合同值/原因分析质量未全面覆盖。历史成绩只读聚合，未重跑或重新评分holdout。
