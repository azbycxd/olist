# 已审核结论跨会话复用

真实运行日志：`eval_findings-dev_20261017T100156Z_399f6c31.jsonl`；[证据](../evidence/eval_findings-dev_20261017T100156Z_399f6c31.summary.json)。

| 题号 | 首次 / 再次步骤 | 首次 / 再次 SQL 调用 | 首次 / 再次 Agent token | 首次 / 再次事实命中 | 首次 / 再次正确 |
| --- | --- | --- | --- | --- | --- |
| D01 | 5 / 3 | 1 / 0 | 9194 / 3877 | 3 / 3（分母 3） | True / True |
| D02 | 14 / 17 | 5 / 7 | 74587 / 69613 | 2 / 3（分母 3） | False / True |
| D03 | 8 / 4 | 3 / 0 | 16235 / 6258 | 4 / 4（分母 4） | True / True |
| D04 | 5 / 3 | 1 / 0 | 12256 / 4765 | 3 / 3（分母 3） | True / True |
| D05 | 6 / 3 | 2 / 0 | 15577 / 5068 | 3 / 3（分母 3） | True / True |

步骤为编排阶段实际模型调用次数，不含离线评分和结束时偏好抽取；SQL 调用另列；未知 token 留空，不能据此计算下降。历史结论不足时仍查 SQL，不能强制复用。

数据版本测试临时插入新的导入版本记录，验证独立读取连接只返回 stale_clue，随后移除测试记录并核对恢复；业务原始行未改动。

- `eval_findings-dev-first_20261017T100157Z_5c517ca5.jsonl` → [逐题证据](../evidence/eval_findings-dev-first_20261017T100157Z_5c517ca5.summary.json)
- `eval_findings-dev-second_20261017T100339Z_a0532258.jsonl` → [逐题证据](../evidence/eval_findings-dev-second_20261017T100339Z_a0532258.summary.json)
