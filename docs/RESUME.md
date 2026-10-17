# 简历项目描述草稿

以下三句可作为项目经历；数字均来自真实运行，不把 dev 改进写成 holdout 的前后提升。

- 从零手写经营分析 Agent，基于 MCP、PostgreSQL、业务口径 RAG 和用户偏好记忆生成可回溯 SQL 的报告，默认采用单 Agent 与数字证据门禁，并保留多智能体审核模式。
- 在固定 22 道 holdout 上各重复 3 次，整题准确率均值为 93.94%（范围 90.91%–95.45%，各轮 20/22、21/22、21/22），20 道题三轮均通过，完整保留失败样本与运行证据。
- 实现一次重写后确定性替换的数字门禁，在独立 D 类 dev 三轮对照中将无证据数字比例均值从 21.67% 降至 2.43%，并完成基于数据库行锁、租约和追加事件的后台执行及真实 worker 中断恢复验证。

## 数字来源与面试边界

holdout 数字来自 [最终统计收据](../evidence/eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.summary.json)，汇总日志 `eval_step9-final-statistics-metadata-fix_20261017T105044Z_8d18a341.jsonl`。原始日志为 `eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`、`eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl`、`eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`，对应证据链接、各类别结果与每题正确次数见 [最终表](FINAL_RESULTS.md)。不能将重复次数说成独立题目数量；D11 业务值正确但字段契约失败，D09 首轮证据对象跨行，原因见 [FAILURES](FAILURES.md)。

门禁数字来自先前 [三轮对照](../evidence/eval_review6-fixed_20261017T092756Z_ed1d9efd.summary.json)，日志 `eval_review6-fixed_20261017T092756Z_ed1d9efd.jsonl`；逐次日志及范围见 [重复对比](REVIEW_COMPARISON.md)。该对照使用 single、RAG inject、Memory 关闭，不能冒称是最终 holdout 的对照实验。“无证据数字”是独立核查指标，不等同于所有语义幻觉；未证明多智能体更快。

恢复来自 [真实任务证据](../evidence/resume_demo_20261017T100621Z.summary.json)，日志 `resume_demo_20261017T100621Z.jsonl`。冷启动只在本机空数据库与空缓存的隔离环境验收，不声称已生产部署。完整用量缺失时不估算费用；模型归因评分仍未人工校准。
