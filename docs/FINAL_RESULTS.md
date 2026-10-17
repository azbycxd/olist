# 最终评测与单项消融

统计由 `eval/run.py --final-report` 读取真实收据生成。汇总日志 `eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.jsonl`；[eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.summary.json](../evidence/eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.summary.json)。

最终配置：single + 数字门禁 + RAG inject + vector + Memory + none；长任务可切换 mask，多智能体为可选。
固定预算 100000 token、上下文上限 16000、on_demand schema、temperature=0；独立模型评分开启。每轮每题新用户；E 的偏好设置与后续问题跨独立任务。
下表为完整轮次指标的算术均值 [最小值, 最大值]。Agent 用量与耗时包含偏好设置/抽取，排除独立评测评分。费用未配置，留空。

## Holdout：一次协议、三轮完整运行

| 类别 | 各轮正确 / 总题数 | 准确率 | D 事实命中率 | 无证据结论比例 | D 无证据数字比例 | 平均 Agent token | 平均 Agent ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all | 20 / 22；21 / 22；21 / 22 | 93.94% [90.91, 95.45]% | 69.23% [69.23, 69.23]% | 0.98% [0.00, 2.94]% | 0.71% [0.00, 2.13]% | 9769.39 [9570.05, 9946.00] | 5959.68 [5861.83, 6053.02] |
| A | 3 / 3；3 / 3；3 / 3 | 100.00% [100.00, 100.00]% |  | 0.00% [0.00, 0.00]% |  | 5580.11 [4967.00, 5890.00] | 4570.71 [4453.69, 4765.94] |
| B | 3 / 3；3 / 3；3 / 3 | 100.00% [100.00, 100.00]% |  | 0.00% [0.00, 0.00]% |  | 8384.00 [8381.67, 8388.33] | 5027.76 [4903.20, 5228.63] |
| C | 8 / 8；8 / 8；8 / 8 | 100.00% [100.00, 100.00]% |  | 0.00% [0.00, 0.00]% |  | 10343.79 [9887.62, 10594.38] | 5106.87 [4897.06, 5254.53] |
| D | 2 / 4；3 / 4；3 / 4 | 66.67% [50.00, 75.00]% | 69.23% [69.23, 69.23]% | 2.22% [0.00, 6.67]% | 0.71% [0.00, 2.13]% | 15456.67 [15269.75, 15730.50] | 9004.81 [8855.09, 9133.86] |
| E | 4 / 4；4 / 4；4 / 4 | 100.00% [100.00, 100.00]% |  | 0.00% [0.00, 0.00]% |  | 7114.33 [6784.50, 7767.25] | 6360.83 [6094.94, 6565.73] |

共 62 / 66 次作答正确，题目仍是 22 道；其中 20 / 22 道三轮均正确，21 / 22 道至少一次正确。不是独立的 66 道题。

D 整题判定、事实命中和数字核查是不同指标；独立核查器也检查 claim 文本，门禁只改报告正文。模型归因评分尚未经过人工校准。

| 题号 | 正确次数 / 重复次数 |
| --- | --- |
| A08 | 3 / 3 |
| A09 | 3 / 3 |
| A10 | 3 / 3 |
| B08 | 3 / 3 |
| B09 | 3 / 3 |
| B10 | 3 / 3 |
| C04 | 3 / 3 |
| C07 | 3 / 3 |
| C10 | 3 / 3 |
| C13 | 3 / 3 |
| C16 | 3 / 3 |
| C19 | 3 / 3 |
| C22 | 3 / 3 |
| C25 | 3 / 3 |
| D09 | 2 / 3 |
| D10 | 3 / 3 |
| D11 | 0 / 3 |
| D12 | 3 / 3 |
| E02 | 3 / 3 |
| E04 | 3 / 3 |
| E06 | 3 / 3 |
| E08 | 3 / 3 |

## Dev：严格单项消融

每组一次，不做稳定性推断。C/E/D 分别使用同一次最终配置运行的对应子集。压力测试单列：在相同 6000 上限下比较 mask 与 none；默认 none 本身没有压缩可关闭。

| 配置 / 题集 | 正确 / 总题数 | 准确率 | D 事实命中率 | 无证据结论比例 | D 无证据数字比例 | 完成率 | 平均 Agent token | 平均 Agent ms | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| final-C | 17 / 17 | 100.00% [100.00, 100.00]% |  | 0.00% [0.00, 0.00]% |  | 100.00% [100.00, 100.00]% | 9384.59 [9384.59, 9384.59] | 4913.79 [4913.79, 4913.79] | [eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json](../evidence/eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json) |
| minus-RAG | 11 / 17 | 64.71% [64.71, 64.71]% |  | 0.00% [0.00, 0.00]% |  | 100.00% [100.00, 100.00]% | 11659.12 [11659.12, 11659.12] | 6233.59 [6233.59, 6233.59] | [eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.summary.json](../evidence/eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.summary.json) |
| final-E | 6 / 6 | 100.00% [100.00, 100.00]% |  | 0.00% [0.00, 0.00]% |  | 100.00% [100.00, 100.00]% | 6508.83 [6508.83, 6508.83] | 6179.13 [6179.13, 6179.13] | [eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json](../evidence/eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json) |
| minus-Memory | 4 / 6 | 66.67% [66.67, 66.67]% |  | 0.00% [0.00, 0.00]% |  | 100.00% [100.00, 100.00]% | 5600.00 [5600.00, 5600.00] | 4822.42 [4822.42, 4822.42] | [eval_step9-dev-minus-memory_20261017T103430Z_c3672950.summary.json](../evidence/eval_step9-dev-minus-memory_20261017T103430Z_c3672950.summary.json) |
| final-D | 6 / 8 | 75.00% [75.00, 75.00]% | 88.00% [88.00, 88.00]% | 0.00% [0.00, 0.00]% | 1.03% [1.03, 1.03]% | 87.50% [87.50, 87.50]% | 22004.38 [22004.38, 22004.38] | 11461.79 [11461.79, 11461.79] | [eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json](../evidence/eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json) |
| minus-gate | 2 / 8 | 25.00% [25.00, 25.00]% | 92.00% [92.00, 92.00]% | 0.00% [0.00, 0.00]% | 23.28% [23.28, 23.28]% | 100.00% [100.00, 100.00]% | 16929.75 [16929.75, 16929.75] | 9679.15 [9679.15, 9679.15] | [eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.summary.json](../evidence/eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.summary.json) |
| multi-gate | 6 / 8 | 75.00% [75.00, 75.00]% | 88.00% [88.00, 88.00]% | 0.00% [0.00, 0.00]% | 1.12% [1.12, 1.12]% | 87.50% [87.50, 87.50]% | 34725.75 [34725.75, 34725.75] | 21218.78 [21218.78, 21218.78] | [eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.summary.json](../evidence/eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.summary.json) |
| pressure-mask | 6 / 8 | 75.00% [75.00, 75.00]% | 76.00% [76.00, 76.00]% | 0.00% [0.00, 0.00]% | 0.00% [0.00, 0.00]% | 75.00% [75.00, 75.00]% | 16991.62 [16991.62, 16991.62] | 9970.39 [9970.39, 9970.39] | [eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.summary.json](../evidence/eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.summary.json) |
| pressure-minus-compression | 3 / 8 | 37.50% [37.50, 37.50]% | 52.00% [52.00, 52.00]% | 0.00% [0.00, 0.00]% | 2.17% [2.17, 2.17]% | 62.50% [62.50, 62.50]% | 15703.38 [15703.38, 15703.38] | 8828.46 [8828.46, 8828.46] | [eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.summary.json](../evidence/eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.summary.json) |

旧 Step 6 重复实验与检索、偏好审计继续复用为历史设计依据，见 [重复对比](REVIEW_COMPARISON.md)。旧组 Memory 关闭，且源码版本不同，不能替代这里从最终配置出发的单项对照。

## 每个数字的运行来源

冻结协议：[step9_holdout_protocol.json](../evidence/step9_holdout_protocol.json)；完成协议：[eval_step9-holdout-protocol_20261017T104235Z_c86b4a05.summary.json](../evidence/eval_step9-holdout-protocol_20261017T104235Z_c86b4a05.summary.json)；dev 协议：[eval_step9-dev-protocol_20261017T102852Z_c3e6c931.summary.json](../evidence/eval_step9-dev-protocol_20261017T102852Z_c3e6c931.summary.json)。

| 组别 | 原始运行日志文件名 | Git 汇总证据 |
| --- | --- | --- |
| holdout-r1 | `eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl` | [eval_step9-holdout-r1_20261017T104235Z_7648ab8d.summary.json](../evidence/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.summary.json) |
| holdout-r2 | `eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl` | [eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.summary.json](../evidence/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.summary.json) |
| holdout-r3 | `eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl` | [eval_step9-holdout-r3_20261017T104707Z_e9d273ef.summary.json](../evidence/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.summary.json) |
| dev-final | `eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl` | [eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json](../evidence/eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json) |
| dev-minus-rag | `eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.jsonl` | [eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.summary.json](../evidence/eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.summary.json) |
| dev-minus-memory | `eval_step9-dev-minus-memory_20261017T103430Z_c3672950.jsonl` | [eval_step9-dev-minus-memory_20261017T103430Z_c3672950.summary.json](../evidence/eval_step9-dev-minus-memory_20261017T103430Z_c3672950.summary.json) |
| dev-minus-gate | `eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.jsonl` | [eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.summary.json](../evidence/eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.summary.json) |
| dev-multi-gate | `eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.jsonl` | [eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.summary.json](../evidence/eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.summary.json) |
| dev-pressure-mask | `eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.jsonl` | [eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.summary.json](../evidence/eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.summary.json) |
| dev-pressure-none | `eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.jsonl` | [eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.summary.json](../evidence/eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.summary.json) |

## 输出契约与汇总修复说明

D11 三轮均使用季度长表，而未按公开要求的 `q1_canceled` 等事实键输出，故该题事实字段命中为零；查询数值与 gold 一致。D09 首轮因一个对象跨查询行拼接而失败。按冻结规则保留判定，不以语义等价为由事后重评，详见 [FAILURES](FAILURES.md)。

上述数据由修正后的只读汇总器输出；唯一修正是将原始 `judge_mode` 映射到汇总 `configuration.judge`，与模型、gold、评分器无关。[修正前统计](../evidence/eval_step9-final-statistics_20261017T104954Z_640a2765.summary.json)与[一致性核验](../evidence/step9_metadata_repair.summary.json)均保留；日志分别为 `eval_step9-final-statistics_20261017T104954Z_640a2765.jsonl`、`step9_metadata_repair.json`。所有分数、原始证据与逐题结果完全相同，未再调用模型。
