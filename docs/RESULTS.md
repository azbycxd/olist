# 评测结果

仅由 `eval/run.py` 的真实运行追加。每行标注原始日志文件名，并链接 Git 跟踪的汇总证据。未运行或不可取得的指标留空。zero 是固定回答零的测试夹具，只验证评测链路，不代表模型能力；费用由实际用量与显式配置单价计算。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| zero-smoke | C,D | dev | 1 / 25 | 4.00% | 0.00% | 100.00% | 100.00% |  | 0 | 0 | `eval_zero-smoke_20261017T062921Z_e275effa.jsonl` | [eval_zero-smoke_20261017T062921Z_e275effa.summary.json](../evidence/eval_zero-smoke_20261017T062921Z_e275effa.summary.json) |
| zero-smoke-final | C,D | dev | 1 / 25 | 4.00% | 0.00% | 100.00% | 100.00% |  | 0 | 0 | `eval_zero-smoke-final_20261017T063318Z_b7b7e550.jsonl` | [eval_zero-smoke-final_20261017T063318Z_b7b7e550.summary.json](../evidence/eval_zero-smoke-final_20261017T063318Z_b7b7e550.summary.json) |
| zero-smoke-revision | C,D | dev | 0 / 25 | 0.00% | 0.00% | 100.00% | 100.00% |  | 0 | 0 | `eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.jsonl` | [eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.summary.json](../evidence/eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.summary.json) |
