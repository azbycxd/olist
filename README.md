# Olist 经营分析 Agent

面向中文经营分析的手写 Agent：规划、多步查数与证据审核，每条结论都能追溯到 SQL 和完整查询结果。当前实现范围为 Step 0（环境与数据入库），完整计划见 [docs/Plan.md](docs/Plan.md)。

## Step 0：启动

需要 Docker Desktop（Linux 容器）与 Docker Compose。容器内脚本使用 Python 3.11，数据库使用 PostgreSQL 16 + pgvector。宿主机无需安装 Python。

将 Kaggle Olist 数据集的全部原始 CSV 放入 `data/raw/`，包括客户、地理位置、订单、订单商品、支付、评价、商品、卖家和品类翻译表。原始数据、密码和完整运行日志不提交到 Git；关键的小型证据保存在 evidence/ 并提交。

```powershell
Copy-Item .env.example .env
# 首次启动前按需修改 .env 中的本地数据库密码和端口。
docker compose up -d --build
docker compose wait init-data
docker compose logs init-data
```

`db` 健康后 `init-data` 自动执行尚未执行的编号迁移，再导入全部 CSV，随后生成 `docs/data_profile.md`。`up -d` 返回只表示容器已启动；应等待 `init-data` 正常退出后再使用业务数据。缺少文件或导入失败会返回非零退出码，错误在容器日志与 `logs/load_olist_*.jsonl` 中。

默认地址为 `localhost:5432`，库名为 `olist`、`agent`。`agent_ro` 仅有业务库 SELECT 权限，默认查询超时为 10 秒；`agent_app` 用于 Agent 库写入。密码见 `.env`，未配置时 Compose 使用 `.env.example` 中的本地开发默认值。端口只绑定回环地址。

初始化脚本仅在首次创建数据卷时运行；修改 `.env` 不会自动修改现有角色密码。业务数据重新导入也不会清空 Agent 库。

每次 `init-data` 启动都会先运行 [编号迁移](sql/migrations/README.md)。`agent.schema_migrations` 记录执行时间与文件哈希；已执行迁移不可编辑，所有后续表结构变更新增迁移文件。现有 Step 0 数据可以直接升级，无需删除数据卷。

## 重跑与画像

```powershell
# 相同输入跳过重复导入，并重新生成画像。
docker compose run --rm init-data
# 单独重新生成画像。
docker compose run --rm init-data python scripts/profile_data.py
```

输入文件变化时脚本会拒绝覆盖已有数据。确实需要替换业务数据时，显式运行：

```powershell
docker compose run --rm init-data python scripts/load_olist.py --replace --profile
```

该命令在事务内替换业务表，更新数据版本；旧证据保留原始版本。不可通过删除 Docker 数据卷进行日常重导，否则 Agent 数据也会丢失。

如需在宿主机运行（Python 3.11 或更高）：

```powershell
python -m pip install -e '.[dev]'
python scripts/load_olist.py --profile
python scripts/profile_data.py
```

## 验收

```powershell
docker compose run --rm -e RUN_DB_TESTS=1 init-data python -m pytest -q
```

验收连接真实数据库，检查两个库、pgvector、核心表、CSV 与入库行数一致、只读权限、跨库隔离、事件只追加和完整证据存储。测试写入全部回滚。未设置 `RUN_DB_TESTS=1` 时只运行不依赖数据库的检查，其余明确跳过，不代表数据库验收通过。

本机实际验收已完成：

- 迁移升级验收：`22 passed`，包含全新数据库、重复启动、失败回滚和跨库提交间隙恢复；见 [升级验收 XML](evidence/step0_migrations_20261017T062040Z.xml)。

- `db` 健康，`init-data` 退出码为 `0`，全部原始 CSV 已导入，两个库均可连接。
- `19 passed`，含真实数据库权限和事件不可变性检查。逐用例结果：[JUnit XML](evidence/step0_pytest_20261017T061031Z.xml)。
- 首次导入日志：[load_olist_20261017T061005Z_cb15c045.jsonl](evidence/load_olist_20261017T061005Z_cb15c045.summary.json)。
- 重复执行返回 `already_loaded`，行数与数据版本保持一致。日志：[load_olist_20261017T061052Z_251dff07.jsonl](evidence/load_olist_20261017T061052Z_251dff07.summary.json)。
- 数据画像已生成，来源日志：[profile_data_20261017T061022Z_8f7105c7.jsonl](evidence/profile_data_20261017T061022Z_8f7105c7.summary.json)。关键证据随 Git 保存；完整运行日志仍保存在本机 logs/。

## 可追溯记录

- [数据画像](docs/data_profile.md)：业务数据统计，包含来源 SQL、数据版本和画像日志文件名。
- [设计决策](docs/DECISIONS.md)：问题、候选方案、选择原因和验证依据。
- [评测结果](docs/RESULTS.md)：仅由后续 `eval/run.py` 的真实运行追加，未运行指标留空。环境测试和数据画像不计为 Agent 评测成绩。

按 Step 顺序推进；Step 1、Step 2、Step 6 完成后等待用户确认再继续。当前尚未实现 Agent 循环与评测器。
