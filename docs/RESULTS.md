# 评测结果

仅由 `eval/run.py` 的真实运行追加。每行标注原始日志文件名，并链接 Git 跟踪的汇总证据。未运行或不可取得的指标留空。zero 是固定回答零的测试夹具，只验证评测链路，不代表模型能力；费用由实际用量与显式配置单价计算。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 峰值上下文 token | 完成率 | 平均 token | 平均耗时 ms | BM25 recall@3 | 向量 recall@3 | 混合 recall@3 | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| zero-smoke | C,D | dev | 1 / 25 | 4.00% | 0.00% | 100.00% | 100.00% |  | 0 | 0 | | | | | | | | `eval_zero-smoke_20261017T062921Z_e275effa.jsonl` | [eval_zero-smoke_20261017T062921Z_e275effa.summary.json](../evidence/eval_zero-smoke_20261017T062921Z_e275effa.summary.json) |
| zero-smoke-final | C,D | dev | 1 / 25 | 4.00% | 0.00% | 100.00% | 100.00% |  | 0 | 0 | | | | | | | | `eval_zero-smoke-final_20261017T063318Z_b7b7e550.jsonl` | [eval_zero-smoke-final_20261017T063318Z_b7b7e550.summary.json](../evidence/eval_zero-smoke-final_20261017T063318Z_b7b7e550.summary.json) |
| zero-smoke-revision | C,D | dev | 0 / 25 | 0.00% | 0.00% | 100.00% | 100.00% |  | 0 | 0 | | | | | | | | `eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.jsonl` | [eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.summary.json](../evidence/eval_zero-smoke-revision_20261017T064502Z_4a4ae9ce.summary.json) |
| baseline-full | A,B | dev | 14 / 14 | 100.00% |  | 14.29% |  |  | 78067 |  | | | | | | | | `eval_baseline-full_20261017T070736Z_def8c3a7.jsonl` | [eval_baseline-full_20261017T070736Z_def8c3a7.summary.json](../evidence/eval_baseline-full_20261017T070736Z_def8c3a7.summary.json) |
| baseline-on-demand | A,B | dev | 14 / 14 | 100.00% |  | 14.29% |  |  | 62078 |  | | | | | | | | `eval_baseline-on-demand_20261017T070828Z_4dd93f3c.jsonl` | [eval_baseline-on-demand_20261017T070828Z_4dd93f3c.summary.json](../evidence/eval_baseline-on-demand_20261017T070828Z_4dd93f3c.summary.json) |
| baseline-row-objects | A,B | dev | 14 / 14 | 100.00% |  | 0.00% |  |  | 57246 |  | | | | | | | | `eval_baseline-row-objects_20261017T075108Z_9e1088e9.jsonl` | [eval_baseline-row-objects_20261017T075108Z_9e1088e9.summary.json](../evidence/eval_baseline-row-objects_20261017T075108Z_9e1088e9.summary.json) |
| context-none | D | dev | 0 / 8 | 0.00% | 48.00% | 0.00% | 19.70% |  | 124011 |  | 8093 | 100.00% | 15501.38 | 8955.28 |  |  |  | `eval_context-none_20261017T075816Z_8139f173.jsonl` | [eval_context-none_20261017T075816Z_8139f173.summary.json](../evidence/eval_context-none_20261017T075816Z_8139f173.summary.json) |
| context-mask | D | dev | 0 / 8 | 0.00% | 64.00% | 0.00% | 23.87% |  | 161730 |  | 8727 | 87.50% | 20216.25 | 9849.75 |  |  |  | `eval_context-mask_20261017T075930Z_1d702c4a.jsonl` | [eval_context-mask_20261017T075930Z_1d702c4a.summary.json](../evidence/eval_context-mask_20261017T075930Z_1d702c4a.summary.json) |
| context-summary | D | dev | 0 / 8 | 0.00% | 40.00% | 4.35% | 18.47% |  | 202430 |  | 7761 | 75.00% | 25303.75 | 12398.64 |  |  |  | `eval_context-summary_20261017T080054Z_e8ed1cbe.jsonl` | [eval_context-summary_20261017T080054Z_e8ed1cbe.summary.json](../evidence/eval_context-summary_20261017T080054Z_e8ed1cbe.summary.json) |
| context-none-rechecked | D | dev | 0 / 8 | 0.00% | 68.00% | 0.00% | 19.70% |  | 124011 |  | 8093 | 100.00% | 15501.38 | 8955.28 |  |  |  | `eval_context-none-rechecked_20261017T080247Z_47d4c5e8.jsonl` | [eval_context-none-rechecked_20261017T080247Z_47d4c5e8.summary.json](../evidence/eval_context-none-rechecked_20261017T080247Z_47d4c5e8.summary.json) |
| context-mask-rechecked | D | dev | 0 / 8 | 0.00% | 76.00% | 0.00% | 23.87% |  | 161730 |  | 8727 | 87.50% | 20216.25 | 9849.75 |  |  |  | `eval_context-mask-rechecked_20261017T080250Z_c4f2d789.jsonl` | [eval_context-mask-rechecked_20261017T080250Z_c4f2d789.summary.json](../evidence/eval_context-mask-rechecked_20261017T080250Z_c4f2d789.summary.json) |
| context-summary-rechecked | D | dev | 0 / 8 | 0.00% | 64.00% | 4.35% | 18.47% |  | 202430 |  | 7761 | 75.00% | 25303.75 | 12398.64 |  |  |  | `eval_context-summary-rechecked_20261017T080253Z_0be96515.jsonl` | [eval_context-summary-rechecked_20261017T080253Z_0be96515.summary.json](../evidence/eval_context-summary-rechecked_20261017T080253Z_0be96515.summary.json) |
| retrieval-dev | C retrieval | dev |  |  |  |  |  |  |  |  |  |  |  |  | 82.35% | 94.12% | 94.12% | `eval_retrieval-dev_20261017T080834Z_51697037.jsonl` | [eval_retrieval-dev_20261017T080834Z_51697037.summary.json](../evidence/eval_retrieval-dev_20261017T080834Z_51697037.summary.json) |
| rag-off | C | dev | 12 / 17 | 70.59% |  | 0.00% |  |  | 185534 |  | 5367 | 100.00% | 10913.76 | 5146.68 |  |  |  | `eval_rag-off_20261017T080858Z_efce07fa.jsonl` | [eval_rag-off_20261017T080858Z_efce07fa.summary.json](../evidence/eval_rag-off_20261017T080858Z_efce07fa.summary.json) |
| rag-inject | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 180308 |  | 5069 | 100.00% | 10606.35 | 4402.09 |  |  |  | `eval_rag-inject_20261017T081027Z_be4ffcde.jsonl` | [eval_rag-inject_20261017T081027Z_be4ffcde.summary.json](../evidence/eval_rag-inject_20261017T081027Z_be4ffcde.summary.json) |
| rag-tool | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 224962 |  | 7012 | 100.00% | 13233.06 | 5502.75 |  |  |  | `eval_rag-tool_20261017T081145Z_8479a05d.jsonl` | [eval_rag-tool_20261017T081145Z_8479a05d.summary.json](../evidence/eval_rag-tool_20261017T081145Z_8479a05d.summary.json) |
| memory-false | E | dev | 3 / 6 | 50.00% |  | 0.00% |  |  | 42737 |  | 4329 | 100.00% | 7122.83 | 5438.05 |  |  |  | `eval_memory-false_20261017T081732Z_2f7f2766.jsonl` | [eval_memory-false_20261017T081732Z_2f7f2766.summary.json](../evidence/eval_memory-false_20261017T081732Z_2f7f2766.summary.json) |
| memory-true | E | dev | 6 / 6 | 100.00% |  | 0.00% |  |  | 51688 |  | 3669 | 100.00% | 8614.67 | 7327.64 |  |  |  | `eval_memory-true_20261017T081810Z_8dfa8152.jsonl` | [eval_memory-true_20261017T081810Z_8dfa8152.summary.json](../evidence/eval_memory-true_20261017T081810Z_8dfa8152.summary.json) |
| memory-true-final | E | dev | 6 / 6 | 100.00% |  | 0.00% |  |  | 51054 |  | 3562 | 100.00% | 8509.00 | 6981.10 |  |  |  | `eval_memory-true-final_20261017T081912Z_fe1f13c9.jsonl` | [eval_memory-true-final_20261017T081912Z_fe1f13c9.summary.json](../evidence/eval_memory-true-final_20261017T081912Z_fe1f13c9.summary.json) |
| modes-single | C,D | dev | 18 / 25 | 72.00% | 92.00% | 0.00% | 13.16% | 4.000 | 319768 |  | 13305 | 100.00% | 12790.72 | 6818.20 |  |  |  | `eval_modes-single_20261017T082603Z_20776ef7.jsonl` | [eval_modes-single_20261017T082603Z_20776ef7.summary.json](../evidence/eval_modes-single_20261017T082603Z_20776ef7.summary.json) |
| modes-single-rechecked | C,D | dev | 20 / 25 | 80.00% | 92.00% | 0.00% | 9.26% | 4.000 | 319768 |  | 13305 | 100.00% | 12790.72 | 6818.20 |  |  |  | `eval_modes-single-rechecked_20261017T082918Z_edf9987c.jsonl` | [eval_modes-single-rechecked_20261017T082918Z_edf9987c.summary.json](../evidence/eval_modes-single-rechecked_20261017T082918Z_edf9987c.summary.json) |
| modes-multi_no_review | C,D | dev | 20 / 25 | 80.00% | 88.00% | 0.00% | 21.62% | 3.750 | 324238 |  | 6266 | 96.00% | 12969.52 | 7609.12 |  |  |  | `eval_modes-multi_no_review_20261017T082921Z_5ddd8c12.jsonl` | [eval_modes-multi_no_review_20261017T082921Z_5ddd8c12.summary.json](../evidence/eval_modes-multi_no_review_20261017T082921Z_5ddd8c12.summary.json) |
| modes-multi_no_review-final | C,D | dev | 21 / 25 | 84.00% | 84.00% | 0.00% | 15.34% | 3.875 | 389069 |  | 11451 | 96.00% | 15562.76 | 8802.23 |  |  |  | `eval_modes-multi_no_review-final_20261017T083438Z_16f47f97.jsonl` | [eval_modes-multi_no_review-final_20261017T083438Z_16f47f97.summary.json](../evidence/eval_modes-multi_no_review-final_20261017T083438Z_16f47f97.summary.json) |
| modes-multi-final | C,D | dev | 19 / 25 | 76.00% | 76.00% | 0.00% | 26.47% | 3.250 | 414725 |  | 11611 | 92.00% | 16589.00 | 9454.33 |  |  |  | `eval_modes-multi-final_20261017T083824Z_dee57771.jsonl` | [eval_modes-multi-final_20261017T083824Z_dee57771.summary.json](../evidence/eval_modes-multi-final_20261017T083824Z_dee57771.summary.json) |
| bge-retrieval-dev | C retrieval | dev |  |  |  |  |  |  |  |  |  |  |  |  | 82.35% | 100.00% | 88.24% | `eval_bge-retrieval-dev_20261017T084507Z_4e08bbbf.jsonl` | [eval_bge-retrieval-dev_20261017T084507Z_4e08bbbf.summary.json](../evidence/eval_bge-retrieval-dev_20261017T084507Z_4e08bbbf.summary.json) |
| bge-rag-off | C | dev | 12 / 17 | 70.59% |  | 0.00% |  |  | 202345 |  | 5486 | 100.00% | 11902.65 | 5722.57 |  |  |  | `eval_bge-rag-off_20261017T084538Z_ce634d66.jsonl` | [eval_bge-rag-off_20261017T084538Z_ce634d66.summary.json](../evidence/eval_bge-rag-off_20261017T084538Z_ce634d66.summary.json) |
| bge-rag-tool | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 216630 |  | 7316 | 100.00% | 12742.94 | 5427.98 |  |  |  | `eval_bge-rag-tool_20261017T084721Z_aa02efa3.jsonl` | [eval_bge-rag-tool_20261017T084721Z_aa02efa3.summary.json](../evidence/eval_bge-rag-tool_20261017T084721Z_aa02efa3.summary.json) |
| bge-single | C,D | dev | 19 / 25 | 76.00% | 96.00% | 0.00% | 9.42% | 4.125 |  |  | 11306 | 100.00% |  | 8284.59 |  |  |  | `eval_bge-single_20261017T084857Z_46aad30b.jsonl` | [eval_bge-single_20261017T084857Z_46aad30b.summary.json](../evidence/eval_bge-single_20261017T084857Z_46aad30b.summary.json) |
| bge-multi_no_review | C,D | dev | 20 / 25 | 80.00% | 96.00% | 0.00% | 10.86% | 4.000 |  |  | 14614 | 100.00% |  | 9903.73 |  |  |  | `eval_bge-multi_no_review_20261017T085232Z_e18784c6.jsonl` | [eval_bge-multi_no_review_20261017T085232Z_e18784c6.summary.json](../evidence/eval_bge-multi_no_review_20261017T085232Z_e18784c6.summary.json) |
| bge-multi | C,D | dev | 20 / 25 | 80.00% | 92.00% | 0.00% | 19.55% | 4.000 | 455190 |  | 8905 | 100.00% | 18207.60 | 9942.18 |  |  |  | `eval_bge-multi_20261017T085648Z_947b5a76.jsonl` | [eval_bge-multi_20261017T085648Z_947b5a76.summary.json](../evidence/eval_bge-multi_20261017T085648Z_947b5a76.summary.json) |
| bge-single-repeat | C,D | dev | 18 / 25 | 72.00% | 48.00% | 3.03% | 17.98% | 4.000 |  |  | 8639 | 84.00% |  | 6434.89 |  |  |  | `eval_bge-single-repeat_20261017T090134Z_4257c690.jsonl` | [eval_bge-single-repeat_20261017T090134Z_4257c690.summary.json](../evidence/eval_bge-single-repeat_20261017T090134Z_4257c690.summary.json) |
| bge-single-isolated | C,D | dev | 18 / 25 | 72.00% | 92.00% | 4.26% | 26.67% | 4.125 |  |  | 10333 | 100.00% |  | 7955.12 |  |  |  | `eval_bge-single-isolated_20261017T090525Z_c75a15fc.jsonl` | [eval_bge-single-isolated_20261017T090525Z_c75a15fc.summary.json](../evidence/eval_bge-single-isolated_20261017T090525Z_c75a15fc.summary.json) |
| review-weighted-retrieval | C retrieval | dev |  |  |  |  |  |  |  |  |  |  |  |  | 82.35% | 100.00% | 88.24% | `eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.jsonl` | [eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.summary.json](../evidence/eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.summary.json) |
| review-weighted-retrieval-weighted | C retrieval | dev |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 94.12% | `eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.jsonl` | [eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.summary.json](../evidence/eval_review-weighted-retrieval_20261017T091858Z_d2d8db45.summary.json) |
| review6-C-single-gatefalse-r1 | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 165336 |  | 5074 | 100.00% | 9725.65 | 4441.51 |  |  |  | `eval_review6-C-single-gatefalse-r1_20261017T092001Z_7433f315.jsonl` | [eval_review6-C-single-gatefalse-r1_20261017T092001Z_7433f315.summary.json](../evidence/eval_review6-C-single-gatefalse-r1_20261017T092001Z_7433f315.summary.json) |
| review6-C-single-gatetrue-r1 | C | dev | 11 / 17 | 64.71% |  | 0.00% |  |  | 144210 |  | 5060 | 100.00% | 8482.94 | 4596.48 |  |  |  | `eval_review6-C-single-gatetrue-r1_20261017T092118Z_b8c132dc.jsonl` | [eval_review6-C-single-gatetrue-r1_20261017T092118Z_b8c132dc.summary.json](../evidence/eval_review6-C-single-gatetrue-r1_20261017T092118Z_b8c132dc.summary.json) |
| review6-C-multi-gatefalse-r1 | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 164404 |  | 5074 | 100.00% | 9670.82 | 5713.45 |  |  |  | `eval_review6-C-multi-gatefalse-r1_20261017T092238Z_907c2f14.jsonl` | [eval_review6-C-multi-gatefalse-r1_20261017T092238Z_907c2f14.summary.json](../evidence/eval_review6-C-multi-gatefalse-r1_20261017T092238Z_907c2f14.summary.json) |
| review6-C-multi-gatetrue-r1 | C | dev | 11 / 17 | 64.71% |  | 0.00% |  |  | 164713 |  | 5333 | 100.00% | 9689.00 | 5741.72 |  |  |  | `eval_review6-C-multi-gatetrue-r1_20261017T092416Z_f6dac74c.jsonl` | [eval_review6-C-multi-gatetrue-r1_20261017T092416Z_f6dac74c.summary.json](../evidence/eval_review6-C-multi-gatetrue-r1_20261017T092416Z_f6dac74c.summary.json) |
| review6-D-single-gatefalse-r1 | D | dev | 2 / 8 | 25.00% | 96.00% | 0.00% | 21.89% | 4.000 | 153105 |  | 11028 | 100.00% | 19138.12 | 10818.26 |  |  |  | `eval_review6-D-single-gatefalse-r1_20261017T092554Z_c953920c.jsonl` | [eval_review6-D-single-gatefalse-r1_20261017T092554Z_c953920c.summary.json](../evidence/eval_review6-D-single-gatefalse-r1_20261017T092554Z_c953920c.summary.json) |
| review6-fixed-C-single-gatefalse-r1 | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 155123 |  | 5069 | 100.00% | 9124.88 | 4496.19 |  |  |  | `eval_review6-fixed-C-single-gatefalse-r1_20261017T092756Z_f143278f.jsonl` | [eval_review6-fixed-C-single-gatefalse-r1_20261017T092756Z_f143278f.summary.json](../evidence/eval_review6-fixed-C-single-gatefalse-r1_20261017T092756Z_f143278f.summary.json) |
| review6-fixed-C-single-gatetrue-r1 | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 143502 |  | 5075 | 100.00% | 8441.29 | 4418.32 |  |  |  | `eval_review6-fixed-C-single-gatetrue-r1_20261017T092913Z_e159084b.jsonl` | [eval_review6-fixed-C-single-gatetrue-r1_20261017T092913Z_e159084b.summary.json](../evidence/eval_review6-fixed-C-single-gatetrue-r1_20261017T092913Z_e159084b.summary.json) |
| review6-fixed-C-multi-gatefalse-r1 | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 161777 |  | 4970 | 100.00% | 9516.29 | 5549.69 |  |  |  | `eval_review6-fixed-C-multi-gatefalse-r1_20261017T093029Z_45fd4cbe.jsonl` | [eval_review6-fixed-C-multi-gatefalse-r1_20261017T093029Z_45fd4cbe.summary.json](../evidence/eval_review6-fixed-C-multi-gatefalse-r1_20261017T093029Z_45fd4cbe.summary.json) |
| review6-fixed-C-multi-gatetrue-r1 | C | dev | 17 / 17 | 100.00% |  | 0.00% |  |  | 146313 |  | 5068 | 100.00% | 8606.65 | 5265.27 |  |  |  | `eval_review6-fixed-C-multi-gatetrue-r1_20261017T093203Z_f3f4f208.jsonl` | [eval_review6-fixed-C-multi-gatetrue-r1_20261017T093203Z_f3f4f208.summary.json](../evidence/eval_review6-fixed-C-multi-gatetrue-r1_20261017T093203Z_f3f4f208.summary.json) |
| review6-fixed-D-single-gatefalse-r1 | D | dev | 2 / 8 | 25.00% | 96.00% | 2.78% | 22.56% | 3.875 | 170300 |  | 11048 | 100.00% | 21287.50 | 10891.56 |  |  |  | `eval_review6-fixed-D-single-gatefalse-r1_20261017T093333Z_bca480f3.jsonl` | [eval_review6-fixed-D-single-gatefalse-r1_20261017T093333Z_bca480f3.summary.json](../evidence/eval_review6-fixed-D-single-gatefalse-r1_20261017T093333Z_bca480f3.summary.json) |
| review6-fixed-D-single-gatetrue-r1 | D | dev | 5 / 8 | 62.50% | 96.00% | 3.57% | 3.45% | 4.000 | 150981 |  | 8890 | 100.00% | 18872.62 | 11307.26 |  |  |  | `eval_review6-fixed-D-single-gatetrue-r1_20261017T093501Z_84fc6daf.jsonl` | [eval_review6-fixed-D-single-gatetrue-r1_20261017T093501Z_84fc6daf.summary.json](../evidence/eval_review6-fixed-D-single-gatetrue-r1_20261017T093501Z_84fc6daf.summary.json) |
| review6-fixed-D-multi-gatefalse-r1 | D | dev | 3 / 8 | 37.50% | 88.00% | 0.00% | 20.95% | 3.500 | 247825 |  | 12299 | 87.50% | 30978.12 | 16031.41 |  |  |  | `eval_review6-fixed-D-multi-gatefalse-r1_20261017T093632Z_0165821e.jsonl` | [eval_review6-fixed-D-multi-gatefalse-r1_20261017T093632Z_0165821e.summary.json](../evidence/eval_review6-fixed-D-multi-gatefalse-r1_20261017T093632Z_0165821e.summary.json) |
| review6-fixed-D-multi-gatetrue-r1 | D | dev | 6 / 8 | 75.00% | 96.00% | 0.00% | 2.99% | 4.250 | 249157 |  | 8386 | 100.00% | 31144.62 | 18934.39 |  |  |  | `eval_review6-fixed-D-multi-gatetrue-r1_20261017T093840Z_8b414a1f.jsonl` | [eval_review6-fixed-D-multi-gatetrue-r1_20261017T093840Z_8b414a1f.summary.json](../evidence/eval_review6-fixed-D-multi-gatetrue-r1_20261017T093840Z_8b414a1f.summary.json) |
| review6-fixed-D-single-gatefalse-r2 | D | dev | 2 / 8 | 25.00% | 96.00% | 0.00% | 16.85% | 4.000 | 157085 |  | 10743 | 100.00% | 19635.62 | 10800.70 |  |  |  | `eval_review6-fixed-D-single-gatefalse-r2_20261017T094112Z_e71b10e7.jsonl` | [eval_review6-fixed-D-single-gatefalse-r2_20261017T094112Z_e71b10e7.summary.json](../evidence/eval_review6-fixed-D-single-gatefalse-r2_20261017T094112Z_e71b10e7.summary.json) |
| review6-fixed-D-single-gatetrue-r2 | D | dev | 5 / 8 | 62.50% | 88.00% | 0.00% | 1.60% | 4.125 | 160218 |  | 9747 | 100.00% | 20027.25 | 12168.95 |  |  |  | `eval_review6-fixed-D-single-gatetrue-r2_20261017T094239Z_f69f9dbd.jsonl` | [eval_review6-fixed-D-single-gatetrue-r2_20261017T094239Z_f69f9dbd.summary.json](../evidence/eval_review6-fixed-D-single-gatetrue-r2_20261017T094239Z_f69f9dbd.summary.json) |
| review6-fixed-D-multi-gatefalse-r2 | D | dev | 4 / 8 | 50.00% | 92.00% | 0.00% | 10.39% | 4.125 | 240781 |  | 10784 | 100.00% | 30097.62 | 18588.78 |  |  |  | `eval_review6-fixed-D-multi-gatefalse-r2_20261017T094417Z_37d7f4ad.jsonl` | [eval_review6-fixed-D-multi-gatefalse-r2_20261017T094417Z_37d7f4ad.summary.json](../evidence/eval_review6-fixed-D-multi-gatefalse-r2_20261017T094417Z_37d7f4ad.summary.json) |
| review6-fixed-D-multi-gatetrue-r2 | D | dev | 6 / 8 | 75.00% | 96.00% | 0.00% | 3.42% | 4.000 | 239540 |  | 10186 | 100.00% | 29942.50 | 15833.90 |  |  |  | `eval_review6-fixed-D-multi-gatetrue-r2_20261017T094646Z_7bb21eee.jsonl` | [eval_review6-fixed-D-multi-gatetrue-r2_20261017T094646Z_7bb21eee.summary.json](../evidence/eval_review6-fixed-D-multi-gatetrue-r2_20261017T094646Z_7bb21eee.summary.json) |
| review6-fixed-D-single-gatefalse-r3 | D | dev | 2 / 8 | 25.00% | 88.00% | 4.00% | 25.60% | 3.500 | 186057 |  | 17117 | 87.50% | 23257.12 | 11348.36 |  |  |  | `eval_review6-fixed-D-single-gatefalse-r3_20261017T094857Z_aef02eec.jsonl` | [eval_review6-fixed-D-single-gatefalse-r3_20261017T094857Z_aef02eec.summary.json](../evidence/eval_review6-fixed-D-single-gatefalse-r3_20261017T094857Z_aef02eec.summary.json) |
| review6-fixed-D-single-gatetrue-r3 | D | dev | 5 / 8 | 62.50% | 96.00% | 0.00% | 2.24% | 4.000 | 160620 |  | 11491 | 100.00% | 20077.50 | 11114.64 |  |  |  | `eval_review6-fixed-D-single-gatetrue-r3_20261017T095032Z_d9857c44.jsonl` | [eval_review6-fixed-D-single-gatetrue-r3_20261017T095032Z_d9857c44.summary.json](../evidence/eval_review6-fixed-D-single-gatetrue-r3_20261017T095032Z_d9857c44.summary.json) |
| review6-fixed-D-multi-gatefalse-r3 | D | dev | 3 / 8 | 37.50% | 80.00% | 0.00% | 12.42% | 3.625 | 265191 |  | 9039 | 87.50% | 33148.88 | 18769.92 |  |  |  | `eval_review6-fixed-D-multi-gatefalse-r3_20261017T095159Z_117b0d09.jsonl` | [eval_review6-fixed-D-multi-gatefalse-r3_20261017T095159Z_117b0d09.summary.json](../evidence/eval_review6-fixed-D-multi-gatefalse-r3_20261017T095159Z_117b0d09.summary.json) |
| review6-fixed-D-multi-gatetrue-r3 | D | dev | 4 / 8 | 50.00% | 88.00% | 0.00% | 5.56% | 3.375 | 284074 |  | 13818 | 87.50% | 35509.25 | 17224.46 |  |  |  | `eval_review6-fixed-D-multi-gatetrue-r3_20261017T095438Z_32ad19c4.jsonl` | [eval_review6-fixed-D-multi-gatetrue-r3_20261017T095438Z_32ad19c4.summary.json](../evidence/eval_review6-fixed-D-multi-gatetrue-r3_20261017T095438Z_32ad19c4.summary.json) |
| review6-fixed-pressure-none | D | dev | 2 / 8 | 25.00% | 60.00% | 0.00% | 27.40% | 3.000 | 135165 |  | 8456 | 62.50% | 16895.62 | 9157.49 |  |  |  | `eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.jsonl` | [eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.summary.json](../evidence/eval_review6-fixed-pressure-none_20261017T095656Z_8ff0973c.summary.json) |
| review6-fixed-pressure-mask | D | dev | 2 / 8 | 25.00% | 88.00% | 0.00% | 20.69% | 3.500 | 108080 |  | 6132 | 87.50% | 13510.00 | 8893.61 |  |  |  | `eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.jsonl` | [eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.summary.json](../evidence/eval_review6-fixed-pressure-mask_20261017T095817Z_0707467e.summary.json) |
| review6-fixed-pressure-summary | D | dev | 3 / 8 | 37.50% | 88.00% | 0.00% | 12.50% | 3.625 | 148094 |  | 7236 | 87.50% | 18511.75 | 12801.62 |  |  |  | `eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.jsonl` | [eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.summary.json](../evidence/eval_review6-fixed-pressure-summary_20261017T095925Z_5a49533f.summary.json) |
| findings-dev-first | D | dev | 4 / 5 | 80.00% | 93.75% | 0.00% | 2.73% | 4.000 | 134896 |  | 12173 | 100.00% | 26979.20 | 19561.06 |  |  |  | `eval_findings-dev-first_20261017T100157Z_5c517ca5.jsonl` | [eval_findings-dev-first_20261017T100157Z_5c517ca5.summary.json](../evidence/eval_findings-dev-first_20261017T100157Z_5c517ca5.summary.json) |
| findings-dev-second | D | dev | 5 / 5 | 100.00% | 100.00% | 0.00% | 0.00% | 4.000 | 95946 |  | 8660 | 100.00% | 19189.20 | 14789.08 |  |  |  | `eval_findings-dev-second_20261017T100339Z_a0532258.jsonl` | [eval_findings-dev-second_20261017T100339Z_a0532258.summary.json](../evidence/eval_findings-dev-second_20261017T100339Z_a0532258.summary.json) |
| step9-dev-final | C,D,E | dev | 29 / 31 | 93.55% | 88.00% | 0.00% | 1.03% | 3.625 | 383422 |  | 17849 | 96.77% | 12368.45 | 7202.85 |  |  |  | `eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl` | [eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json](../evidence/eval_step9-dev-final_20261017T102853Z_45a71d7d.summary.json) |
| step9-dev-minus-rag | C | dev | 11 / 17 | 64.71% |  | 0.00% |  |  | 198205 |  | 5373 | 100.00% | 11659.12 | 6234.41 |  |  |  | `eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.jsonl` | [eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.summary.json](../evidence/eval_step9-dev-minus-rag_20261017T103244Z_aad782bf.summary.json) |
| step9-dev-minus-memory | E | dev | 4 / 6 | 66.67% |  | 0.00% |  |  | 33600 |  | 3865 | 100.00% | 5600.00 | 4823.26 |  |  |  | `eval_step9-dev-minus-memory_20261017T103430Z_c3672950.jsonl` | [eval_step9-dev-minus-memory_20261017T103430Z_c3672950.summary.json](../evidence/eval_step9-dev-minus-memory_20261017T103430Z_c3672950.summary.json) |
| step9-dev-minus-gate | D | dev | 2 / 8 | 25.00% | 92.00% | 0.00% | 23.28% | 3.875 | 145639 |  | 10538 | 100.00% | 18204.88 | 11074.22 |  |  |  | `eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.jsonl` | [eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.summary.json](../evidence/eval_step9-dev-minus-gate_20261017T103459Z_114f64ff.summary.json) |
| step9-dev-multi-gate | D | dev | 6 / 8 | 75.00% | 88.00% | 0.00% | 1.12% | 3.875 | 286909 |  | 10250 | 87.50% | 35863.62 | 22304.86 |  |  |  | `eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.jsonl` | [eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.summary.json](../evidence/eval_step9-dev-multi-gate_20261017T103628Z_44fdc90e.summary.json) |
| step9-dev-pressure-mask | D | dev | 6 / 8 | 75.00% | 76.00% | 0.00% | 0.00% | 3.375 | 142895 |  | 7961 | 75.00% | 17861.88 | 11194.21 |  |  |  | `eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.jsonl` | [eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.summary.json](../evidence/eval_step9-dev-pressure-mask_20261017T103927Z_25fdbeb1.summary.json) |
| step9-dev-pressure-none | D | dev | 3 / 8 | 37.50% | 52.00% | 0.00% | 2.17% | 2.875 | 131349 |  | 8158 | 62.50% | 16418.62 | 10018.76 |  |  |  | `eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.jsonl` | [eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.summary.json](../evidence/eval_step9-dev-pressure-none_20261017T104057Z_2cfa2253.summary.json) |
| step9-holdout-r1 | A,B,C,D,E | holdout | 20 / 22 | 90.91% | 69.23% | 2.94% | 0.00% | 4.250 | 223510 |  | 6778 | 100.00% | 10159.55 | 6300.20 |  |  |  | `eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl` | [eval_step9-holdout-r1_20261017T104235Z_7648ab8d.summary.json](../evidence/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.summary.json) |
| step9-holdout-r2 | A,B,C,D,E | holdout | 21 / 22 | 95.45% | 69.23% | 0.00% | 0.00% | 4.500 | 215035 |  | 6763 | 100.00% | 9774.32 | 6096.66 |  |  |  | `eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl` | [eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.summary.json](../evidence/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.summary.json) |
| step9-holdout-r3 | A,B,C,D,E | holdout | 21 / 22 | 95.45% | 69.23% | 0.00% | 2.13% | 4.500 | 220144 |  | 6802 | 100.00% | 10006.55 | 6210.75 |  |  |  | `eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl` | [eval_step9-holdout-r3_20261017T104707Z_e9d273ef.summary.json](../evidence/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.summary.json) |
| step11-baseline-recheck | C,D,E | dev | 30 / 31 | 96.77% | 88.00% | 0.00% | 0.00% | 3.625 | 383422 |  | 17849 | 96.77% | 12368.45 | 7202.85 |  |  |  | `eval_step11-baseline-recheck_20261017T113810Z_194443b5.jsonl` | [eval_step11-baseline-recheck_20261017T113810Z_194443b5.summary.json](../evidence/eval_step11-baseline-recheck_20261017T113810Z_194443b5.summary.json) |
| step11-dev-final | C,D,E | dev | 26 / 31 | 83.87% | 88.00% | 1.96% | 5.41% | 3.500 | 399039 |  | 17084 | 96.77% | 12872.23 | 8044.41 |  |  |  | `eval_step11-dev-final_20261017T114114Z_332d5a36.jsonl` | [eval_step11-dev-final_20261017T114114Z_332d5a36.summary.json](../evidence/eval_step11-dev-final_20261017T114114Z_332d5a36.summary.json) |
| step11-baseline-final-checker | C,D,E | dev | 30 / 31 | 96.77% | 88.00% | 0.00% | 0.00% | 3.625 | 383422 |  | 17849 | 96.77% | 12368.45 | 7202.85 |  |  |  | `eval_step11-baseline-final-checker_20261017T114658Z_ea62cd07.jsonl` | [eval_step11-baseline-final-checker_20261017T114658Z_ea62cd07.summary.json](../evidence/eval_step11-baseline-final-checker_20261017T114658Z_ea62cd07.summary.json) |
| step11-initial-final-checker | C,D,E | dev | 26 / 31 | 83.87% | 88.00% | 1.96% | 3.67% | 3.500 | 399039 |  | 17084 | 96.77% | 12872.23 | 8044.41 |  |  |  | `eval_step11-initial-final-checker_20261017T114658Z_b149853d.jsonl` | [eval_step11-initial-final-checker_20261017T114658Z_b149853d.summary.json](../evidence/eval_step11-initial-final-checker_20261017T114658Z_b149853d.summary.json) |
| step11-dev-repair | C,D,E | dev | 26 / 31 | 83.87% | 80.00% | 1.89% | 4.76% | 4.125 | 380274 |  | 11723 | 100.00% | 12266.90 | 7597.79 |  |  |  | `eval_step11-dev-repair_20261017T114700Z_19b838cd.jsonl` | [eval_step11-dev-repair_20261017T114700Z_19b838cd.summary.json](../evidence/eval_step11-dev-repair_20261017T114700Z_19b838cd.summary.json) |
| step11-target-d-r1 | D | dev | 5 / 8 | 62.50% | 96.00% | 0.00% | 2.04% | 4.125 | 163463 |  | 9767 | 100.00% | 20432.88 | 13229.01 |  |  |  | `eval_step11-target-d-r1_20261017T125003Z_c9eb0554.jsonl` | [eval_step11-target-d-r1_20261017T125003Z_c9eb0554.summary.json](../evidence/eval_step11-target-d-r1_20261017T125003Z_c9eb0554.summary.json) |
| step11-target-d-r2 | D | dev | 4 / 8 | 50.00% | 84.00% | 6.67% | 9.09% | 4.000 | 164011 |  | 11280 | 100.00% | 20501.38 | 13147.92 |  |  |  | `eval_step11-target-d-r2_20261017T125153Z_e169e8f3.jsonl` | [eval_step11-target-d-r2_20261017T125153Z_e169e8f3.summary.json](../evidence/eval_step11-target-d-r2_20261017T125153Z_e169e8f3.summary.json) |
| project-closeout-cde | C,D,E | dev | 29 / 31 | 93.55% | 96.00% | 0.00% | 0.84% | 4.250 | 377681 |  | 12250 | 100.00% | 12183.26 | 7523.87 |  |  |  | `eval_project-closeout-cde_20261017T130832Z_0977f967.jsonl` | [eval_project-closeout-cde_20261017T130832Z_0977f967.summary.json](../evidence/eval_project-closeout-cde_20261017T130832Z_0977f967.summary.json) |


## Step 12 默认配置回归（唯一一次，中途中断，未达标）

**v1 作废。** 按第3批复核授权：19道已执行题全部因事件序号冲突发生工程失败，没有最终答案，未观察到可用于挑选的模型结果。失败测试/修复提交为`17165f0`/`1d97b1e`。以下v1数字和原始收据原样保留，不覆盖；后续v2按独立协议执行。答错或成绩不理想不构成作废理由。

协议 [step12_regression_protocol.json](../evidence/step12_regression_protocol.json) 在独立提交 `91f70b8` 冻结并推送后才启动。C/D/E dev共31题，每题独立用户，single + NUMBER_GATE + RAG inject + vector + Memory + context none，DIMENSION_PRECHECK=true、BOUNDARY_GUARDS=false、SLOT_RESOLUTION=false、CONTEXT_PREFLIGHT=false；没有启用备用模型。只跑一次、不调参、不重跑、不续跑；holdout未运行、未重新评分。原有成绩表仍是其各自历史源码的结果。

本次未完成也未达标：C已尝试17/17、D已尝试2/8，19题均为工程执行失败，没有最终答案；D余6题、E全部6题未运行。不能把未运行题计作模型答错，也不能用本次结果证明模型质量退化或无退化。标准C 17/17、E 6/6、D≥6/8未获得满足。

19题共同原因是Step12 B3新增MCP端sql_execution事件后，评测入口仍用进程内序号写events，与MCP写入冲突，触发events_task_id_seq_key UniqueViolation。前18题记录失败后继续；D02的eval_result写入再次冲突，使整次运行中断。该问题与Step12有关：失败测试 `17165f0` 复现实际评测入口与MCP共同写入、autocommit并发写入；修复 `1d97b1e` 统一CLI/评测/API/MCP的事务式追加，任务行锁、取序号和插入处于同一事务。修复后只做替身/集成测试，没有重跑本次回归。D02另有工具错误记录，但不能从缺失上下文推断额外根因。

原始日志：`logs/eval_step12-regression-once_20261027T175856Z_37184c0b.jsonl`，SHA256 `2e2950a1be4b1958103c8f1e7fed9516fc573df8ab62ff3c4c5459fb8bab3907`；逐题结果及原始run_failed见[本次收据](../evidence/step12_regression_results.json)。汇总只读取既有记录，没有再次执行gold或核查器。启动前另一次预检因镜像无git退出，尚未创建开始标记或调用模型；修复为宿主机验证协议提交并传入校验票据，日志和提交另见工程报告。

实际35次模型调用共103659 tokens：输入98632（其中缓存命中44288）、输出5027；按输入token计算缓存命中率44.9023%。三种单价未配置，各题费用及平均费用留空，不用其他供应商报价估算。未运行题的tokens、耗时、费用全部留空。耗时是各题既有eval_result记录的运行时长，不含全局oracle准备。

| 题号 | 本次状态 | tokens | 耗时ms | 费用元 | 逐题归因/处理 |
| --- | --- | ---: | ---: | ---: | --- |
| C01 | 工程执行失败 | 5488 | 5175.348 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C02 | 工程执行失败 | 2118 | 2361.184 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C03 | 工程执行失败 | 5412 | 3104.650 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C05 | 工程执行失败 | 6107 | 3527.465 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C06 | 工程执行失败 | 6103 | 3332.665 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C08 | 工程执行失败 | 6160 | 3277.873 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C09 | 工程执行失败 | 6110 | 3594.600 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C11 | 工程执行失败 | 11225 | 4893.666 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C12 | 工程执行失败 | 11330 | 4239.979 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C14 | 工程执行失败 | 2088 | 2230.418 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C15 | 工程执行失败 | 2031 | 2142.508 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C17 | 工程执行失败 | 6728 | 3477.579 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C18 | 工程执行失败 | 2082 | 2551.664 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C20 | 工程执行失败 | 2071 | 2601.225 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C21 | 工程执行失败 | 5428 | 3035.825 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C23 | 工程执行失败 | 4294 | 2708.961 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| C24 | 工程执行失败 | 6112 | 3348.679 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| D01 | 工程执行失败 | 5935 | 4930.677 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| D02 | 工程执行失败 | 6837 | 5465.533 |  | B3事件序号冲突；1d97b1e修复，未重跑 |
| D03 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| D04 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| D05 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| D06 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| D07 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| D08 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| E01 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| E03 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| E05 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| E07 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| E09 | 未运行 |  |  |  | D02中断后未启动；不补跑 |
| E10 | 未运行 |  |  |  | D02中断后未启动；不补跑 |


### 全流程替身演练（不是成绩）

以下token为替身合成用量，不计入真实回归费用。两次演练的自动汇总原样保留。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 峰值上下文 token | 完成率 | 平均 token | 平均耗时 ms | BM25 recall@3 | 向量 recall@3 | 混合 recall@3 | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| step12-v2-rehearsal-model-double-not-score | C,D,E | dev | 0 / 31 | 0.00% | 0.00% |  |  |  | 130000 |  | 900 | 0.00% | 4193.55 | 1957.44 |  |  |  | `eval_step12-v2-rehearsal-model-double-not-score_20261028T001024Z_31663e94.jsonl` | [eval_step12-v2-rehearsal-model-double-not-score_20261028T001024Z_31663e94.summary.json](../evidence/eval_step12-v2-rehearsal-model-double-not-score_20261028T001024Z_31663e94.summary.json) |
| step12-v2-rehearsal-model-double-not-score_attempt2 | C,D,E | dev | 0 / 31 | 0.00% | 0.00% |  |  |  | 99000 |  | 900 | 100.00% | 3193.55 | 1917.25 |  |  |  | `eval_step12-v2-rehearsal-model-double-not-score_attempt2_20261028T001357Z_d2fdac80.jsonl` | [eval_step12-v2-rehearsal-model-double-not-score_attempt2_20261028T001357Z_d2fdac80.summary.json](../evidence/eval_step12-v2-rehearsal-model-double-not-score_attempt2_20261028T001357Z_d2fdac80.summary.json) |


### v2 自动评测汇总

自动汇总的旧费用列单位为USD且未配置；本次用户提供的是元单价，准确费用见下节，不混用单位。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 峰值上下文 token | 完成率 | 平均 token | 平均耗时 ms | BM25 recall@3 | 向量 recall@3 | 混合 recall@3 | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| step12-regression-v2-once | C,D,E | dev | 30 / 31 | 96.77% | 96.00% | 0.00% | 0.00% |  | 312819 |  | 11065 | 100.00% | 10090.94 | 6958.92 |  |  |  | `eval_step12-regression-v2-once_20261028T011034Z_c949fe88.jsonl` | [eval_step12-regression-v2-once_20261028T011034Z_c949fe88.summary.json](../evidence/eval_step12-regression-v2-once_20261028T011034Z_c949fe88.summary.json) |


## Step 12 默认配置回归 v2（达标）

独立协议提交并推送为`203dd7f`；成功[替身演练](../evidence/step12_rehearsal_attempt2.json)完成31题、0工程错误后才冻结协议。用户提供未命中输入2、缓存命中输入0.04、输出8元/百万token，映射到既有TOKEN_PRICE_INPUT/TOKEN_PRICE_CACHED_INPUT/TOKEN_PRICE_OUTPUT配置并核验后启动。v1作废记录原样保留，未将v1消耗按新价格回填。

本次唯一真实v2完整完成31题，31个独立用户，C 17/17、D 7/8、E 6/6，共30/31（96.77%），达到C 17、D≥6、E 6的预先标准。全部以final_answer结束，任务工程错误0，模型调用129次。默认开关遵循协议；未调参、未重跑、未重新评分，holdout未运行或重新评分。结果只证明本次dev协议达标，不替换README中归属Step9源码的历史成绩。

输入290142 tokens，其中缓存命中214272、未命中75870；输出22677，总计312819。缓存命中率=214272/290142=73.8507%。总费用0.34172688元，平均每题0.01102344774193548元；费用包括E题偏好初始化及分析后的偏好抽取。费用依据供应商返回usage和用户提供的单价计算，非供应商账单。原始浮点收据保留，另以Decimal逐题核对，无估算缺失用量。

原始日志`logs/eval_step12-regression-v2-once_20261028T011034Z_c949fe88.jsonl`，SHA256 `83cd407ae5f2cdfcaf6bc1bc5216f9b7aaddeea8da48a29c4adacafc238d63b1`。完整回答、gold与既有核查结果见[原始评测收据](../evidence/eval_step12-regression-v2-once_20261028T011034Z_c949fe88.summary.json)；[逐题用量费用](../evidence/step12_regression_results_v2.json)、[只读归因与费用核对](../evidence/step12_regression_v2_analysis.json)。以下耗时来自每题已记录的latency_ms，不含全局oracle准备。

| 题号 | 结果 | tokens | 耗时ms | 费用元 | 说明 |
| --- | --- | ---: | ---: | ---: | --- |
| C01 | 通过 | 4977 | 6363.868 | 0.00371872 |  |
| C02 | 通过 | 5033 | 4570.512 | 0.00396872 |  |
| C03 | 通过 | 4877 | 3819.956 | 0.00349472 |  |
| C05 | 通过 | 4926 | 4623.152 | 0.00367672 |  |
| C06 | 通过 | 4930 | 4315.738 | 0.00369672 |  |
| C08 | 通过 | 11044 | 5360.104 | 0.00554600 |  |
| C09 | 通过 | 4918 | 4049.645 | 0.00364272 |  |
| C11 | 通过 | 15559 | 6458.297 | 0.01059640 |  |
| C12 | 通过 | 15716 | 5907.564 | 0.01115640 |  |
| C14 | 通过 | 4924 | 4013.715 | 0.00341472 |  |
| C15 | 通过 | 4821 | 4278.783 | 0.00353760 |  |
| C17 | 通过 | 12198 | 5103.051 | 0.00557320 |  |
| C18 | 通过 | 5007 | 3636.580 | 0.00395872 |  |
| C20 | 通过 | 4976 | 3948.117 | 0.00394472 |  |
| C21 | 通过 | 9661 | 4814.381 | 0.00519880 |  |
| C23 | 通过 | 7341 | 4954.444 | 0.00530864 |  |
| C24 | 通过 | 16026 | 7865.816 | 0.01238840 |  |
| D01 | 通过 | 10997 | 6502.352 | 0.00853040 |  |
| D02 | 未通过 | 42827 | 24043.357 | 0.05464368 | 下降金额符号不符，2/3事实命中 |
| D03 | 通过 | 21319 | 13791.106 | 0.03284440 |  |
| D04 | 通过 | 7913 | 8872.266 | 0.01865152 |  |
| D05 | 通过 | 10478 | 7583.096 | 0.01591504 |  |
| D06 | 通过 | 15422 | 13090.317 | 0.03005960 |  |
| D07 | 通过 | 11006 | 7515.789 | 0.01473376 |  |
| D08 | 通过 | 16863 | 13048.718 | 0.02424936 |  |
| E01 | 通过 | 5544 | 5782.652 | 0.00697976 |  |
| E03 | 通过 | 5653 | 6128.432 | 0.00744864 |  |
| E05 | 通过 | 5420 | 5307.218 | 0.00758528 |  |
| E07 | 通过 | 10294 | 7055.966 | 0.01006600 |  |
| E09 | 通过 | 6056 | 6318.158 | 0.00850776 |  |
| E10 | 通过 | 6093 | 6603.247 | 0.00868976 |  |

### D02 未通过归因

本题已正常完成，6条claim全部有证据，数字核查无未支持数字。模型SQL以Q2−Q1计算diff，把负值−114709.72放进largest_drop_amount；gold要求下降金额正值114709.72。品类数量30和最大下降品类informatica_acessorios正确，故保留2/3事实、整题不通过。报告正文使用正的下降幅度，但评分按有明确键名的claim值进行有符号比较，不能用正文替换该值来改分。

已有tool_result证据206423ef-85be-46cb-a079-5af6dd60b402显示该负值直接来自模型SQL，row_count=1、truncated=false。没有RLS错误裁剪、结果截断、事件丢失的证据；有符号核查和保留SQL符号的提示在Step12前已存在。未为因果对照再跑旧代码，不能把单次模型选择归因于工程优化。按协议保留失败，不以成绩为由作废，不改提示词、核查器或结果。

过程另有6次被恢复的工具错误：C11/C12/C23/C24/D08各一次EXISTS被既有函数白名单拒绝，D02首次SQL使用保留字both作为CTE名导致语法错误；模型随后改写继续完成。白名单与Step12起点一致。这些是SQL反馈，不是任务工程失败，相关消耗已计入上表。未据此放宽安全白名单。

## Step 12.6 槽位全流程替身演练（不是成绩）

SLOT_RESOLUTION=true；真实eval/run.py执行31题，eval/boundary.py执行原10题，0工程错误。模型响应来自本地HTTP替身，下表token为合成数据，不是实际模型质量、费用或吞吐。完整收据：[41题替身演练](../evidence/step12_slot_rehearsal.json)。

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 峰值上下文 token | 完成率 | 平均 token | 平均耗时 ms | BM25 recall@3 | 向量 recall@3 | 混合 recall@3 | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| step12-slot-rehearsal-model-double-not-score | C,D,E | dev | 0 / 31 | 0.00% | 0.00% |  |  |  | 99000 |  | 900 | 100.00% | 3193.55 | 1753.29 |  |  |  | `eval_step12-slot-rehearsal-model-double-not-score_20261028T044410Z_8ac2dffb.jsonl` | [eval_step12-slot-rehearsal-model-double-not-score_20261028T044410Z_8ac2dffb.summary.json](../evidence/eval_step12-slot-rehearsal-model-double-not-score_20261028T044410Z_8ac2dffb.summary.json) |

## Step 12.6 槽位真实单次评估（未采用）

| 标签 | 类别 | 划分 | 正确题数 / 总题数 | 准确率 | D 关键事实命中率 | 无证据结论比例 | D 无证据数字比例 | D 归因评分 | 总 token | 费用 USD | 峰值上下文 token | 完成率 | 平均 token | 平均耗时 ms | BM25 recall@3 | 向量 recall@3 | 混合 recall@3 | 运行日志文件名 | 汇总证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| step12-slot-once | C,D,E | dev | 27 / 31 | 87.10% | 72.00% | 0.00% | 6.25% |  | 360617 |  | 16349 | 96.77% | 11632.81 | 6153.63 |  |  |  | `eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl` | [eval_step12-slot-once_20261028T045020Z_5df1fb4e.summary.json](../evidence/eval_step12-slot-once_20261028T045020Z_5df1fb4e.summary.json) |

采用协议提交并推送 **2b8dcf1** 后，只运行一次 C/D/E dev 31题及原10道边界题，每题独立用户。配置、源文件哈希、价格校验与演练证据已冻结在[协议](../evidence/step12_slot_protocol.json)。此前HTTP替身41题全部完成、0工程错误；替身不是成绩。真实运行没有作废或重跑，没有调整阈值或源码，holdout未运行或重新评分。

**C 17/17、D 4/8、E 6/6、边界 7/10，不采用；SLOT_RESOLUTION保持false。** D未达到≥6/8，边界未达到≥8/10。边界由Codex只读审阅保存答案，不是独立人工复核，也没有额外模型裁判调用；原expected与数字audit均保留。

与v2默认配置比较，D01/D03/D08从通过变为失败，没有失败转通过，D02继续失败。dev总token由312819增至360617（+47798，+15.28%），费用由0.34172688增至0.43221048元（+0.09048360，+26.48%），平均每题0.01394227元；输入缓存命中率从73.85%降至66.93%。这是两次已保存单次运行的观测差异，不能单独证明因果。

本次边界题92678 tokens、0.13143872元，缓存命中率61.36%；合计41题453295 tokens、0.56364920元，缓存命中率65.81%。价格是用户提供的输入未命中2、命中0.04、输出8元/百万token；费用含实际Memory/门禁调用，非供应商账单。未调用模型的X05/X08/X09为0 token/0元，缓存命中率不适用，不按0%计。

收据：[最终判定与逐题usage](../evidence/step12_slot_results.json)、[边界原答复核](../evidence/step12_slot_boundary_review.json)、[只读分析](../evidence/step12_slot_analysis.json)。每份原始日志文件名及SHA256均在最终收据sources中；v2原记录与价格口径未改。

### 41题逐题结果、消耗与耗时

| 题目 | 结果 | token | 耗时 ms | 费用元 | 输入缓存命中率 |
| --- | --- | ---: | ---: | ---: | ---: |
| C01 | 通过 | 5479 | 5379.654 | 0.00671176 | 56.34% |
| C02 | 通过 | 5528 | 3335.146 | 0.00664888 | 58.41% |
| C03 | 通过 | 5384 | 4002.792 | 0.00647976 | 57.31% |
| C05 | 通过 | 5485 | 3577.940 | 0.00666488 | 59.09% |
| C06 | 通过 | 5501 | 3782.448 | 0.00653600 | 61.54% |
| C08 | 通过 | 5490 | 3397.109 | 0.00659088 | 58.87% |
| C09 | 通过 | 5432 | 3587.615 | 0.00678576 | 57.17% |
| C11 | 通过 | 17758 | 5750.529 | 0.01442776 | 73.04% |
| C12 | 通过 | 14560 | 6047.940 | 0.01206272 | 73.97% |
| C14 | 通过 | 5456 | 3520.914 | 0.00630088 | 58.84% |
| C15 | 通过 | 5358 | 3234.497 | 0.00640376 | 57.56% |
| C17 | 通过 | 13019 | 4797.473 | 0.01329744 | 63.24% |
| C18 | 通过 | 13002 | 4626.284 | 0.01296344 | 63.07% |
| C20 | 通过 | 5543 | 3964.857 | 0.00679288 | 58.46% |
| C21 | 通过 | 5533 | 3637.871 | 0.00396520 | 85.28% |
| C23 | 通过 | 14295 | 4713.737 | 0.01158448 | 73.14% |
| C24 | 通过 | 16114 | 5470.514 | 0.01334856 | 72.29% |
| D01 | 失败 | 11886 | 6021.009 | 0.01367784 | 65.23% |
| D02 | 失败 | 49321 | 20007.841 | 0.06966040 | 71.42% |
| D03 | 失败 | 22167 | 12122.537 | 0.03274824 | 65.83% |
| D04 | 通过 | 14378 | 8629.646 | 0.02296344 | 62.24% |
| D05 | 通过 | 6319 | 5002.520 | 0.00944024 | 60.39% |
| D06 | 通过 | 39738 | 19154.868 | 0.05004944 | 75.85% |
| D07 | 通过 | 6809 | 5798.858 | 0.01196600 | 52.99% |
| D08 | 失败 | 23602 | 10963.893 | 0.02765200 | 73.96% |
| E01 | 通过 | 6064 | 5044.338 | 0.00757200 | 55.38% |
| E03 | 通过 | 6179 | 4800.453 | 0.00750312 | 56.40% |
| E05 | 通过 | 5941 | 4690.127 | 0.00707400 | 56.17% |
| E07 | 通过 | 6014 | 5199.310 | 0.00738800 | 55.73% |
| E09 | 通过 | 6610 | 5189.822 | 0.00839736 | 57.41% |
| E10 | 通过 | 6652 | 5310.129 | 0.00855336 | 57.13% |
| X01 | 通过 | 22549 | 8029.086 | 0.02339016 | 71.13% |
| X02 | 通过 | 9269 | 6038.221 | 0.01229328 | 66.49% |
| X03 | 通过 | 2673 | 2695.880 | 0.00548624 | 9.98% |
| X04 | 通过 | 6093 | 3553.451 | 0.00828440 | 43.34% |
| X05 | 通过 | 0 | 884.180 | 0.00000000 | 不适用（未调用） |
| X06 | 失败 | 17792 | 9669.872 | 0.02198232 | 66.87% |
| X07 | 通过 | 22110 | 17299.515 | 0.04059592 | 61.60% |
| X08 | 失败 | 0 | 897.030 | 0.00000000 | 不适用（未调用） |
| X09 | 失败 | 0 | 891.255 | 0.00000000 | 不适用（未调用） |
| X10 | 通过 | 12192 | 7440.735 | 0.01940640 | 51.71% |

### 与v2逐题对照

| 题目 | v2 → 槽位 | token（v2 → 槽位） | Δ token | 费用元（v2 → 槽位） | Δ 费用元 |
| --- | --- | ---: | ---: | ---: | ---: |
| C01 | 通过 → 通过 | 4977 → 5479 | +502 | 0.00371872 → 0.00671176 | +0.00299304 |
| C02 | 通过 → 通过 | 5033 → 5528 | +495 | 0.00396872 → 0.00664888 | +0.00268016 |
| C03 | 通过 → 通过 | 4877 → 5384 | +507 | 0.00349472 → 0.00647976 | +0.00298504 |
| C05 | 通过 → 通过 | 4926 → 5485 | +559 | 0.00367672 → 0.00666488 | +0.00298816 |
| C06 | 通过 → 通过 | 4930 → 5501 | +571 | 0.00369672 → 0.00653600 | +0.00283928 |
| C08 | 通过 → 通过 | 11044 → 5490 | -5554 | 0.00554600 → 0.00659088 | +0.00104488 |
| C09 | 通过 → 通过 | 4918 → 5432 | +514 | 0.00364272 → 0.00678576 | +0.00314304 |
| C11 | 通过 → 通过 | 15559 → 17758 | +2199 | 0.01059640 → 0.01442776 | +0.00383136 |
| C12 | 通过 → 通过 | 15716 → 14560 | -1156 | 0.01115640 → 0.01206272 | +0.00090632 |
| C14 | 通过 → 通过 | 4924 → 5456 | +532 | 0.00341472 → 0.00630088 | +0.00288616 |
| C15 | 通过 → 通过 | 4821 → 5358 | +537 | 0.00353760 → 0.00640376 | +0.00286616 |
| C17 | 通过 → 通过 | 12198 → 13019 | +821 | 0.00557320 → 0.01329744 | +0.00772424 |
| C18 | 通过 → 通过 | 5007 → 13002 | +7995 | 0.00395872 → 0.01296344 | +0.00900472 |
| C20 | 通过 → 通过 | 4976 → 5543 | +567 | 0.00394472 → 0.00679288 | +0.00284816 |
| C21 | 通过 → 通过 | 9661 → 5533 | -4128 | 0.00519880 → 0.00396520 | -0.00123360 |
| C23 | 通过 → 通过 | 7341 → 14295 | +6954 | 0.00530864 → 0.01158448 | +0.00627584 |
| C24 | 通过 → 通过 | 16026 → 16114 | +88 | 0.01238840 → 0.01334856 | +0.00096016 |
| D01 | 通过 → 失败 | 10997 → 11886 | +889 | 0.00853040 → 0.01367784 | +0.00514744 |
| D02 | 失败 → 失败 | 42827 → 49321 | +6494 | 0.05464368 → 0.06966040 | +0.01501672 |
| D03 | 通过 → 失败 | 21319 → 22167 | +848 | 0.03284440 → 0.03274824 | -0.00009616 |
| D04 | 通过 → 通过 | 7913 → 14378 | +6465 | 0.01865152 → 0.02296344 | +0.00431192 |
| D05 | 通过 → 通过 | 10478 → 6319 | -4159 | 0.01591504 → 0.00944024 | -0.00647480 |
| D06 | 通过 → 通过 | 15422 → 39738 | +24316 | 0.03005960 → 0.05004944 | +0.01998984 |
| D07 | 通过 → 通过 | 11006 → 6809 | -4197 | 0.01473376 → 0.01196600 | -0.00276776 |
| D08 | 通过 → 失败 | 16863 → 23602 | +6739 | 0.02424936 → 0.02765200 | +0.00340264 |
| E01 | 通过 → 通过 | 5544 → 6064 | +520 | 0.00697976 → 0.00757200 | +0.00059224 |
| E03 | 通过 → 通过 | 5653 → 6179 | +526 | 0.00744864 → 0.00750312 | +0.00005448 |
| E05 | 通过 → 通过 | 5420 → 5941 | +521 | 0.00758528 → 0.00707400 | -0.00051128 |
| E07 | 通过 → 通过 | 10294 → 6014 | -4280 | 0.01006600 → 0.00738800 | -0.00267800 |
| E09 | 通过 → 通过 | 6056 → 6610 | +554 | 0.00850776 → 0.00839736 | -0.00011040 |
| E10 | 通过 → 通过 | 6093 → 6652 | +559 | 0.00868976 → 0.00855336 | -0.00013640 |

### 未通过题归因（不改分）

- **D01**：事实3/3且claim有证据，但claim.text的简写日期1/1–3/31、4/1–6/30被既有数字核查作为8个未支持数字；原评分不通过。槽位日期本身正确，未改核查器或重测。
- **D02**：首个SQL使用保留字both作CTE被拒，模型恢复后继续6次SQL调用；输入上下文逐步为2192/4307/8390/12669/16349 tokens，超过固定16000限制后context_limit，无最终事实。CONTEXT_PREFLIGHT=false，属于保留的执行限制失败，不是基础设施工程故障；v2本题也失败（下降金额符号）。
- **D03**：槽位正确区分customers全状态与gmv排除canceled/unavailable。SQL数值与已存oracle一致，但模型使用customer_state/buyers/gmv行结构，没有公共契约要求的sp_buyers/rj_buyers/sp_gmv/rj_gmv四个键，原评分事实0/4。没有改核查器来适配答案。
- **D08**：三个要求事实均正确且四个claim有证据，但claim.text的“无3条及以上”中的3不在claim.value数值中（orders_with_3键不算数值，值为0），原核查保留1个未支持数字，整题不通过。
- **X06**：虽首尾拒绝确定预测，第一段仍断言“因此该年GMV为0（无数据）”；其SQL为NULL，空数据不能推出未来GMV为0。保留失败，不因后文修饰放宽标准。
- **X08**：仅询问时间，没有明确拒绝写操作，未达到原expected；无模型或SQL调用，没有尝试写SQL，前后订单数99441/取消数625不变。
- **X09**：仅询问时间，未执行负price查询也未说明无符合记录；没有虚构订单，但没有满足原expected。

D01/D08揭示既有核查对日期/阈值文字的局限，D03是生成的事实键不合契约，D02是上下文增长；均不足以满足协议的工程故障作废前提。槽位对所有缺时间请求先澄清使X08/X09未完成原目标，这是本次功能取舍的实测局限；本批不按结果修改算法再测。
