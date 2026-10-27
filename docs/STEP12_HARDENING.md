# Step 12 工程化加固

执行范围以对话里的批次指令为准。第 1 批为 12.1（A1–A4）和 12.2（B1–B2），按顺序完成。冻结 Step 9 holdout，不重跑、不重新计分；题库、gold、核查器、知识库及既有迁移保持不变。

## 起始基线

- 起始提交：`22cb974`；默认配置仍为 single + NUMBER_GATE + RAG inject + vector + Memory + context none，DIMENSION_PRECHECK=true、BOUNDARY_GUARDS=false。
- 本地 Linux Compose 完整测试：[241 项通过](../evidence/step12_baseline_full.xml)。CI 同构离线测试：[200 项通过](../evidence/step12_baseline_linux_offline.xml)。
- 额外尝试的 Windows 离线测试失败：[原始 XML](../evidence/step12_baseline_offline.xml)。其网络禁止夹具拦截 Windows asyncio 自管道，沙箱也限制 pytest 临时目录；因此本批统一在与 CI 一致的 Linux 容器验证，不为此修改产品代码。
- [起始文件哈希](../evidence/step12_start_reference.json)用于结束时核对冻结文件；`agent/loop.py`允许工程改动，但其中系统提示必须保持原文。

## 12.1 / A1 模型重试与熔断

### 旧问题

所有异常均请求四次并等待 1/2/4 秒；忽略 Retry-After、任务剩余时长，没有跨任务熔断。

### 改法与进度

当前为测试先行阶段，尚未修改运行时。新增失败测试：[离线 XML](../evidence/step12_a1_red.xml)（10 项失败），[数据库 XML](../evidence/step12_a1_circuit_red.xml)（5 项失败）。后续修复独立提交。

### 前后对比

HTTP 模型替身持续返回 503，经后台 API 入队并由一个 worker 顺序处理 10 个任务；为隔离模型调用，实验显式关闭 RAG 和 Memory。不是实际模型性能或质量数据。

| 指标 | 改前 | 改后 |
| --- | ---: | ---: |
| 10 个任务总耗时（ms） | 84130.051 | |
| HTTP 替身请求数 | 40 | |

[改前收据](../evidence/step12_a1_before_20261027T143800Z_9303e8a3.summary.json)包含源码哈希、日志文件名和 SHA-256；[原始实验日志](../evidence/step12_a1_before_20261027T143800Z_9303e8a3.jsonl)保留任务事件。

### 已知局限

CLI / 评测路径没有 worker 预扣回调，不经过共享熔断。总任务耗时包含子进程启动和 MCP 初始化；100ms 验收针对预扣熔断拒绝，不等于整个后台任务的端到端耗时。
