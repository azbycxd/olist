# 后台任务控制（Step 11）

仅后台 API 任务受这些服务端控制；可信离线评测/CLI 继续使用 Agent 的步数和 token 预算。参数是可配置的安全护栏，不是从 holdout 调出的最优值。

| 配置 | 默认 | 行为 |
| --- | --- | --- |
| `TASK_MAX_SECONDS` | 300 秒 | 从 API 入队开始，包含排队、计划确认和重试。租约恢复不重置截止时间。旧任务没有截止字段时在首次新领取时初始化。 |
| `USER_MAX_RUNNING_TASKS` | 2 | 按用户计算有效租约下的 planning/running；多余任务排队，其他用户可继续领取。等待计划确认不占运行槽，但继续计时。 |
| `USER_DAILY_TOKEN_QUOTA` | 1000000 | 按 UTC 请求日期，所有角色与重试共用；下一次请求无法预留时任务失败，原因 `daily_token_quota`。 |

`POST /tasks/{task_id}/cancel` 使用登录 Bearer token，只能取消本人任务。pending/planning/running/awaiting_confirmation 均可取消；重复取消返回 canceled，已完成或失败返回 409，别人的任务返回 404。取消立即清理租约并记录原因，worker 每次模型调用前和运行期间每半秒检查；即使 HTTP 请求阻塞，也会终止其模型子进程。MCP 保存结果和 Memory 写入同时核对租约、取消标记及总截止时间，避免迟到结果写回。

`GET /quota` 返回 UTC 日期、已确认的 `used_tokens`、尚未结算的 `held_tokens`、可预留余额及限制配置。`GET /tasks/{task_id}` 增加 `deadline_at`、`cancel_requested_at`，usage 中区分已知量和不确定预留量。

每日额度采用数据库事务预留，锁顺序为用户、任务、请求记录。模型子进程没有数据库凭据：通过父子进程的 JSON 行协议申请许可，父进程提交预留后才放行。请求预算使用输入 JSON 的 UTF-8 字节数、固定协议余量与输出上限作保守预留；它不是实测 token。成功返回后按供应商 usage 结算并释放差额；usage 缺失、429 无 usage、进程中断等情况保留当日预留额，不把未知费用算成零。跨 UTC 午夜的迟到结算仍记在请求发起日。

这个额度是本服务的请求准入护栏，不是供应商账单的绝对上限。自定义供应商若报告大于预留的 usage，记录实际量并失败终止，不继续请求；账单仍应在供应商端配置限制。取消可停止本地后续调用，不能保证远端已经收到的请求不计费。模型使用量未知时，完整总量留空。

网络访问不持有用户额度锁；Memory 的写入锁顺序已统一。当前 API/worker 正常运行时会清理过期任务；服务整体停机期间无后台清理，重启后的队列扫描执行清理。运行中业务只读 SQL 仍可能在 MCP 侧运行到数据库语句超时，但失效租约不能再保存新证据。

新增表与字段全部通过 [009 迁移](../sql/migrations/009_task_controls.sql)，既有迁移未修改。[迁移证据](../evidence/migrate_20261017T113606Z_b7319959.summary.json)，日志 `migrate_20261017T113606Z_b7319959.jsonl`。

验证：最终完整测试 [XML](../evidence/step11_final_tests.xml) 中 216 项通过，包含并发抢槽/额度预留、取消授权与幂等、排队/确认超时、阻塞子进程终止、UTC 分日结算、真实子进程与本地 HTTP 模型替身握手、MCP 租约失效、事务开始后仍按实际时钟判断截止时间与迁移恢复。HTTP 替身的零 usage 是测试数据，不是模型费用证据。首轮 [测试记录](../evidence/step11_controls_initial.xml) 的失败来自新测试未设置测试用 JWT secret，修正测试夹具后通过；失败记录保留。

[GitHub Actions](../.github/workflows/unit-tests.yml) 对 push 和 pull_request 运行 Python 3.11 离线测试，不需要密钥、原始 CSV、Postgres、MCP 或向量服务。显式排除 integration；`CI_OFFLINE=1` 下测试连接数据库或网络会直接失败。[最终本地同配置 XML](../evidence/step11_final_offline_tests.xml)：175 项通过，41 项集成测试不进入该作业。动作版本按 [checkout 官方用法](https://github.com/actions/checkout)和 [setup-python 官方用法](https://github.com/actions/setup-python)配置。
