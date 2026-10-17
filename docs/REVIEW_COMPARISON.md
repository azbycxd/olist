# Step 6 审查补充对比

由 `eval/run.py --review-suite` 真实运行生成；区间是各次结果的最小值到最大值。未知用量留空。

汇总日志：`eval_review6-fixed_20261017T092756Z_ed1d9efd.jsonl`；[汇总证据](../evidence/eval_review6-fixed_20261017T092756Z_ed1d9efd.summary.json)。

| 组别 | 准确率 均值 [范围] | D 事实命中 均值 [范围] | 无证据结论比例 均值 [范围] | D 无证据数字比例 均值 [范围] | Agent 耗时 ms 均值 [范围] | 完成率 均值 [范围] |
| --- | --- | --- | --- | --- | --- | --- |
| C/single/gate=false | 100.00% [100.00, 100.00] |  | 0.00% [0.00, 0.00] |  | 4495.36 [4495.36, 4495.36] | 100.00% [100.00, 100.00] |
| C/single/gate=true | 100.00% [100.00, 100.00] |  | 0.00% [0.00, 0.00] |  | 4417.51 [4417.51, 4417.51] | 100.00% [100.00, 100.00] |
| C/multi/gate=false | 100.00% [100.00, 100.00] |  | 0.00% [0.00, 0.00] |  | 5547.41 [5547.41, 5547.41] | 100.00% [100.00, 100.00] |
| C/multi/gate=true | 100.00% [100.00, 100.00] |  | 0.00% [0.00, 0.00] |  | 5264.57 [5264.57, 5264.57] | 100.00% [100.00, 100.00] |
| D/single/gate=false | 25.00% [25.00, 25.00] | 93.33% [88.00, 96.00] | 2.26% [0.00, 4.00] | 21.67% [16.85, 25.60] | 9620.01 [9288.42, 10095.50] | 95.83% [87.50, 100.00] |
| D/single/gate=true | 62.50% [62.50, 62.50] | 93.33% [88.00, 96.00] | 1.19% [0.00, 3.57] | 2.43% [1.60, 3.45] | 10202.94 [9790.57, 10853.90] | 100.00% [100.00, 100.00] |
| D/multi/gate=false | 41.67% [37.50, 50.00] | 86.67% [80.00, 92.00] | 0.00% [0.00, 0.00] | 14.59% [10.39, 20.95] | 16534.58 [14896.29, 17408.59] | 91.67% [87.50, 100.00] |
| D/multi/gate=true | 66.67% [50.00, 75.00] | 93.33% [88.00, 96.00] | 0.00% [0.00, 0.00] | 3.99% [2.99, 5.56] | 16016.72 [14570.41, 17496.19] | 95.83% [87.50, 100.00] |

复杂题集合：D01, D02, D03, D06, D08。按实际 multi 拆分题目的并集取同题比较；规划路由存在波动，不作因果速度结论。

| 复杂题同题组别 | D 事实命中 均值 [范围] | Agent 耗时 ms 均值 [范围] |
| --- | --- | --- |
| D/single/gate=false | 89.58% [81.25, 93.75] | 11673.89 [10890.05, 12749.66] |
| D/single/gate=true | 93.75% [93.75, 93.75] | 12090.98 [11413.30, 13158.97] |
| D/multi/gate=false | 83.33% [68.75, 100.00] | 22244.80 [19568.96, 23823.36] |
| D/multi/gate=true | 89.58% [81.25, 93.75] | 20497.67 [18734.83, 22315.71] |

压力测试单独标注在 RESULTS 的 pressure 行；不混入普通模式均值。

逐次日志：

- `eval_review6-fixed-C-single-gatefalse-r1_20261017T092756Z_f143278f.jsonl` → [证据](../evidence/eval_review6-fixed-C-single-gatefalse-r1_20261017T092756Z_f143278f.summary.json)
- `eval_review6-fixed-C-single-gatetrue-r1_20261017T092913Z_e159084b.jsonl` → [证据](../evidence/eval_review6-fixed-C-single-gatetrue-r1_20261017T092913Z_e159084b.summary.json)
- `eval_review6-fixed-C-multi-gatefalse-r1_20261017T093029Z_45fd4cbe.jsonl` → [证据](../evidence/eval_review6-fixed-C-multi-gatefalse-r1_20261017T093029Z_45fd4cbe.summary.json)
- `eval_review6-fixed-C-multi-gatetrue-r1_20261017T093203Z_f3f4f208.jsonl` → [证据](../evidence/eval_review6-fixed-C-multi-gatetrue-r1_20261017T093203Z_f3f4f208.summary.json)
- `eval_review6-fixed-D-single-gatefalse-r1_20261017T093333Z_bca480f3.jsonl` → [证据](../evidence/eval_review6-fixed-D-single-gatefalse-r1_20261017T093333Z_bca480f3.summary.json)
- `eval_review6-fixed-D-single-gatetrue-r1_20261017T093501Z_84fc6daf.jsonl` → [证据](../evidence/eval_review6-fixed-D-single-gatetrue-r1_20261017T093501Z_84fc6daf.summary.json)
- `eval_review6-fixed-D-multi-gatefalse-r1_20261017T093632Z_0165821e.jsonl` → [证据](../evidence/eval_review6-fixed-D-multi-gatefalse-r1_20261017T093632Z_0165821e.summary.json)
- `eval_review6-fixed-D-multi-gatetrue-r1_20261017T093840Z_8b414a1f.jsonl` → [证据](../evidence/eval_review6-fixed-D-multi-gatetrue-r1_20261017T093840Z_8b414a1f.summary.json)
- `eval_review6-fixed-D-single-gatefalse-r2_20261017T094112Z_e71b10e7.jsonl` → [证据](../evidence/eval_review6-fixed-D-single-gatefalse-r2_20261017T094112Z_e71b10e7.summary.json)
- `eval_review6-fixed-D-single-gatetrue-r2_20261017T094239Z_f69f9dbd.jsonl` → [证据](../evidence/eval_review6-fixed-D-single-gatetrue-r2_20261017T094239Z_f69f9dbd.summary.json)
- `eval_review6-fixed-D-multi-gatefalse-r2_20261017T094417Z_37d7f4ad.jsonl` → [证据](../evidence/eval_review6-fixed-D-multi-gatefalse-r2_20261017T094417Z_37d7f4ad.summary.json)
- `eval_review6-fixed-D-multi-gatetrue-r2_20261017T094646Z_7bb21eee.jsonl` → [证据](../evidence/eval_review6-fixed-D-multi-gatetrue-r2_20261017T094646Z_7bb21eee.summary.json)
- `eval_review6-fixed-D-single-gatefalse-r3_20261017T094857Z_aef02eec.jsonl` → [证据](../evidence/eval_review6-fixed-D-single-gatefalse-r3_20261017T094857Z_aef02eec.summary.json)
- `eval_review6-fixed-D-single-gatetrue-r3_20261017T095032Z_d9857c44.jsonl` → [证据](../evidence/eval_review6-fixed-D-single-gatetrue-r3_20261017T095032Z_d9857c44.summary.json)
- `eval_review6-fixed-D-multi-gatefalse-r3_20261017T095159Z_117b0d09.jsonl` → [证据](../evidence/eval_review6-fixed-D-multi-gatefalse-r3_20261017T095159Z_117b0d09.summary.json)
- `eval_review6-fixed-D-multi-gatetrue-r3_20261017T095438Z_32ad19c4.jsonl` → [证据](../evidence/eval_review6-fixed-D-multi-gatetrue-r3_20261017T095438Z_32ad19c4.summary.json)
- `eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.jsonl` → [证据](../evidence/eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.summary.json)
- `eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.jsonl` → [证据](../evidence/eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.summary.json)
- `eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.jsonl` → [证据](../evidence/eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.summary.json)

## 补充计数、归因与用量均值及范围

由已有真实运行收据计算；日志 `eval_review6-statistics_20261017T100149Z_ea5440cc.jsonl`，[证据](../evidence/eval_review6-statistics_20261017T100149Z_ea5440cc.summary.json)。

| 组别 | 整题正确数 | 事实命中数 | 事实分母 | 无证据 claim 数 | claim 分母 | D 无证据数字数 | D 数字分母 | D 归因评分 | 平均总 token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C/single/gate=false | 17.00 [17.00, 17.00] |  |  | 0.00 [0.00, 0.00] | 17.00 [17.00, 17.00] |  |  |  | 9124.88 [9124.88, 9124.88] |
| C/single/gate=true | 17.00 [17.00, 17.00] |  |  | 0.00 [0.00, 0.00] | 18.00 [18.00, 18.00] |  |  |  | 8441.29 [8441.29, 8441.29] |
| C/multi/gate=false | 17.00 [17.00, 17.00] |  |  | 0.00 [0.00, 0.00] | 17.00 [17.00, 17.00] |  |  |  | 9516.29 [9516.29, 9516.29] |
| C/multi/gate=true | 17.00 [17.00, 17.00] |  |  | 0.00 [0.00, 0.00] | 18.00 [18.00, 18.00] |  |  |  | 8606.65 [8606.65, 8606.65] |
| D/single/gate=false | 2.00 [2.00, 2.00] | 23.33 [22.00, 24.00] | 25.00 [25.00, 25.00] | 0.67 [0.00, 1.00] | 31.33 [25.00, 36.00] | 35.67 [31.00, 44.00] | 168.00 [125.00, 195.00] | 3.79 [3.50, 4.00] | 21393.42 [19635.62, 23257.12] |
| D/single/gate=true | 5.00 [5.00, 5.00] | 23.33 [22.00, 24.00] | 25.00 [25.00, 25.00] | 0.33 [0.00, 1.00] | 28.33 [28.00, 29.00] | 3.67 [3.00, 5.00] | 155.67 [134.00, 188.00] | 4.04 [4.00, 4.12] | 19659.12 [18872.62, 20077.50] |
| D/multi/gate=false | 3.33 [3.00, 4.00] | 21.67 [20.00, 23.00] | 25.00 [25.00, 25.00] | 0.00 [0.00, 0.00] | 26.67 [25.00, 28.00] | 19.00 [16.00, 22.00] | 137.33 [105.00, 154.00] | 3.75 [3.50, 4.12] | 31408.21 [30097.62, 33148.88] |
| D/multi/gate=true | 5.33 [4.00, 6.00] | 23.33 [22.00, 24.00] | 25.00 [25.00, 25.00] | 0.00 [0.00, 0.00] | 28.00 [25.00, 31.00] | 4.33 [4.00, 5.00] | 113.67 [90.00, 134.00] | 3.88 [3.38, 4.25] | 32198.79 [29942.50, 35509.25] |

平均总 token 含独立评测评分；任一重复的 usage 不完整则该组总量均值留空。事实和数字分母单列，比例均值是各次比例的算术平均，不能与平均计数的比值混淆。

## 按当次实际拆分配对

上表的固定并集便于跨轮比较；下表额外只取每次 multi 实际拆开的题，在同轮、同门禁设置的 single 中取相同题目。路由会波动，不能将不同题集的差别归因于并行。

| multi 运行标签 | 当次实际拆分题号 | single 平均 Agent ms | multi 平均 Agent ms | single 事实命中 | multi 事实命中 |
| --- | --- | --- | --- | --- | --- |
| review6-fixed-D-multi-gatefalse-r1 | D02, D03, D06, D08 | 12809.39 | 22339.35 | 12 / 13 | 10 / 13 |
| review6-fixed-D-multi-gatetrue-r1 | D01, D02, D03, D06, D08 | 11700.67 | 22315.71 | 15 / 16 | 15 / 16 |
| review6-fixed-D-multi-gatefalse-r2 | D01, D02, D03, D06, D08 | 10890.05 | 23823.36 | 15 / 16 | 16 / 16 |
| review6-fixed-D-multi-gatetrue-r2 | D02, D03, D06, D08 | 15073.94 | 21871.84 | 12 / 13 | 12 / 13 |
| review6-fixed-D-multi-gatefalse-r3 | D01, D02, D03, D06, D08 | 12749.66 | 23342.08 | 13 / 16 | 11 / 16 |
| review6-fixed-D-multi-gatetrue-r3 | D01, D02, D03, D06, D08 | 11413.30 | 20442.46 | 15 / 16 | 13 / 16 |

## 上下文压力测试

各策略只运行一次，限制为 6000；summary 的预设压缩阈值为 3600。峰值包含触发超限时的输入估计，不能当作供应商实际接受的窗口大小。失败保留，不混入普通模式均值。

| 策略 | 完成数 | 事实命中 | 峰值上下文估计 token | 实际总 token（含评分） | 终止原因 |
| --- | --- | --- | --- | --- | --- |
| none | 5 / 8 | 15 / 25 | 8456 | 135165 | {"final_answer": 5, "context_limit": 3} |
| mask | 7 / 8 | 22 / 25 | 6132 | 108080 | {"final_answer": 7, "context_limit": 1} |
| summary | 7 / 8 | 22 / 25 | 7236 | 148094 | {"final_answer": 7, "context_limit": 1} |
