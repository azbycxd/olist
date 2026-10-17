# 工程边界与故障实验

这些实验验证队列、资源和终止语义，独立于模型业务正确率及冻结 holdout。常驻 worker 在测试前停止，受控进程只竞争本批任务，结束后恢复常驻 worker。测试数据和用户有独立 ID，业务表不写入。

## 两个 worker、六个真实模型任务

[正式并发证据](../evidence/step10_concurrency_20261017T111217Z_702ad536.summary.json)，日志 `step10_concurrency_20261017T111217Z_702ad536.jsonl`。两个独立 Python worker 进程使用生产 claim/process；都尝试同一批任务 ID，领取 SQL 仍为 FOR UPDATE SKIP LOCKED。为了隔离实验，不领取不属于本批的用户任务。使用最终配置、真实配置模型与 bge-m3 固定 revision。

六个任务全部 completed，每个 claim_count=1，worker_claimed 事件不重复，观察到执行时间重叠；两个 worker 均有实际领取，所有租约清除。总墙钟耗时 **14.824 秒**。本次未评估横向扩展吞吐上限。

| 数据库观测 | 值 |
| --- | --- |
| max_connections / superuser_reserved_connections | 100 / 3 |
| 采样间隔 / 样本数 | 0.05 秒 / 292 |
| 初始连接 / 采样峰值 | 2 / 5 |
| 各角色独立峰值 | {"agent_app": 3, "agent_ro": 1, "olist_admin": 1} |

计数包含采样连接和实验互斥锁连接；各角色峰值不一定同时出现。采样可能漏过短连接，不是瞬时精确上界。本规模未观察到逼近连接限制，因此未引入连接池；这个结论不适用于更多 worker 或慢查询场景。当前 MCP 在向量等待时仍可能持有数据库连接，扩容前需重新压测。

首次并发试运行与边界评测重叠，保留 [试运行证据](../evidence/step10_concurrency_20261017T111018Z_f9155c08.summary.json)，日志 `step10_concurrency_20261017T111018Z_f9155c08.jsonl`，不用于正式耗时结论。随后工程脚本加入与 eval/run.py 共用的互斥锁，并在边界评测结束后独立运行上述正式实验。

## 服务故障与 HTTP 429

向量实验实际停止 embeddings 容器，在 finally 中恢复并等待健康检查；[停止/恢复控制记录](../evidence/step10_vector_service_control.summary.json)，日志 `step10_vector_control.log`。MCP 实验启动独立的真实服务进程，首条 SQL 已持久化后杀掉该进程，避免破坏其他会话。

429 用本地 HTTP 服务真实返回状态码，生产 OpenAI SDK、退避、runtime 子进程和 worker 均未替换。MCP 故障也用同一模型替身准确控制故障时点。替身返回的 usage 为合成零，仅用于状态机实验，绝不是模型性能、token 或费用证据。向量宕机路径未调用聊天模型。

| 场景 | 任务终态 | 墙钟秒 | 已验证行为 | 证据 / 原始日志 |
| --- | --- | --- | --- | --- |
| vector_down | failed | 6.927 | 检索失败即终止，无聊天调用；真实容器已恢复。租约清除，再次领取为空。 | [收据](../evidence/step10_fault_vector_down_20261017T111323Z_24e12c63.summary.json)；`step10_fault_vector_down_20261017T111323Z_24e12c63.jsonl` |
| mcp_midway | failed | 3.533 | 保留第一条 SQL，随后传输异常，干净失败；私有 MCP 进程被杀。租约清除，再次领取为空。 | [收据](../evidence/step10_fault_mcp_midway_20261017T111225Z_c4ed7fa1.summary.json)；`step10_fault_mcp_midway_20261017T111225Z_c4ed7fa1.jsonl` |
| 429_recovered | completed | 4.946 | 连续两次 429，退避后第三次主调用成功；偏好抽取另成功一次。租约清除，再次领取为空。 | [收据](../evidence/step10_fault_429_recovered_20261017T111238Z_1fdd5884.summary.json)；`step10_fault_429_recovered_20261017T111238Z_1fdd5884.jsonl` |
| 429_exhausted | failed | 15.945 | 主调用最多四次；后续偏好抽取也有独立四次上限，最终 model_error。租约清除，再次领取为空。 | [收据](../evidence/step10_fault_429_exhausted_20261017T111258Z_14140ef0.summary.json)；`step10_fault_429_exhausted_20261017T111258Z_14140ef0.jsonl` |

这里的干净终止指数据库进入终态、租约字段清除、子进程退出且不能重复领取；服务恢复不会自动重试已经 failed 的任务。连接拒绝和传输中断不等于超慢服务，未声称覆盖最长网络超时、数据库宕机或所有组合故障。

## 毒任务上限与回归

任务最多发出三次租约，规划和执行都计入。若第三次后又出现 pending 或租约过期，下一次领取尝试原子地置 failed，清除租约，并写入 claim_limit_exceeded、attempted_claim=4 和上限。第四次不会执行模型，claim_count 保持实际发出的租约数。全队列领取继续寻找下一条，毒任务不会永远挡住队列。该逻辑复用已有字段，不修改已执行迁移。

[领取/API 测试](../evidence/step10_queue_tests.xml)，日志 `step10_queue_tests.log`：包括 single/multi 三次领取、并发第四次拒绝、旧租约失效及 pending 耗尽场景。

[主测试集](../evidence/step10_full_tests.xml)，日志 `step10_full_tests.log`；[MCP 实连测试](../evidence/step10_mcp_tests.xml)，日志 `step10_mcp_tests.log`。主测试中未启用的 MCP 项在后一收据中单独执行。首次实连命令使用错误文件名、没有执行测试的 [原始 XML](../evidence/step10_live_mcp_tests.xml) 和 `step10_live_mcp_tests.log` 保留，不计为通过。

生产行为只新增了领取次数上限，以及领取事件中的 worker 标识/计数。提示、模型循环、知识口径、检索、数字门禁和 gold 未为边界题改动；新队列上限可能使连续崩溃任务更早失败，但不改变已保存的 Step 9 非后台评测结果，未重跑 holdout。
