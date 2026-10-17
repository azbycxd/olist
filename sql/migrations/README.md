# 迁移约定

文件按 `001_name.sql`、`002_name.sql` 连续编号，首行必须为 `-- database: agent` 或 `-- database: olist`。已执行的迁移禁止修改、删除或改名；任何表、索引、约束、函数、权限变更均新增迁移。初始化脚本只负责创建数据库、登录角色及基础扩展，不能承担后续表结构变更。

`init-data` 运行导入前自动调用 `scripts/migrate.py`。也可单独运行 `python scripts/migrate.py`。`agent.schema_migrations` 记录编号、文件名、SHA-256、目标库和执行时间；每次启动校验所有历史记录。版本缺失或内容被修改即报错，不继续导入。

每个迁移在事务内执行，不得自行 BEGIN／COMMIT，不支持需要脱离事务的 DDL（如 CREATE INDEX CONCURRENTLY）。全局迁移锁避免并发执行。业务库另有同名的内部收据表，DDL 与收据在目标库内原子提交，随后将收据镜像到 Agent 库；进程在两个库提交之间退出时，下次运行修复镜像而不重复执行 DDL。

初始迁移兼容已经通过 Step 0 验收的数据库，用 IF NOT EXISTS 接入其原有表，不重建或清空数据。它不用于自动修复人工修改过的旧表；历史数据库存在未知结构时应先核对并编写单独迁移。
