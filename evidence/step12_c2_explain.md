# Step12 C2 RLS 执行计划诊断

固定SQL，无模型、无评分。按原改后收据耗时降序选择D03、D02、D01、D06、D08；没有挑选优化后有利的查询。独立数据库step12_rls_diag从当前olist完整复制，ANALYZE后使用相同数据/统计/agent_ro账号，分别禁用与启用五张表的RLS采集EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)。只在副本切换策略，正式库未禁用RLS。权限均为事务内SET LOCAL ALL；不更改JIT、索引或成本参数。

这重建了RLS开关前后状态，并非在历史运行时保存的计划；缓存与副本统计不同，不能把本表时长代替原31条SQL的前后收据。完整节点、估计/实际行数、循环数和BUFFERS见[原始计划](step12_c2_explain_plans.json)。

| SQL | 无RLS执行ms | 原RLS执行ms | 无RLS JIT ms | 原RLS JIT ms |
| --- | ---: | ---: | ---: | ---: |
| D03 | 89.155 | 842.896 | 0.000 | 0.000 |
| D02 | 57.354 | 558.293 | 0.000 | 283.381 |
| D01 | 29.405 | 345.861 | 0.000 | 206.901 |
| D06 | 56.235 | 489.663 | 0.000 | 331.277 |
| D08 | 98.309 | 453.639 | 6.147 | 334.231 |

## 诊断结论（优化之前）

主要是(a)嵌套权限子计划的规划成本及行数估计影响，不是ALL用户实际逐行执行嵌套EXISTS：所有权限子计划Actual Loops=0，说明ALL已在执行阶段短路。但是计划仍保留这些分支，D01/D02/D06/D08总估计成本升到约71–79万，触发含优化/内联的JIT，编译耗时207–334ms。D03没有JIT，主要是错误行数估计导致连接次序变化：customers每个并行分片实际49720行，orders_customer_idx查找99441次，两处重复；无RLS时采用一次日期Bitmap Scan加Hash Join。

(b)在这五条中没有得到索引不能下推的证据：D01/D02/D06/D08的日期范围仍出现在orders_purchase_idx的Index Cond；D03改走customers驱动的订单客户索引，日期条件作为过滤存在，不能据此称日期索引被security barrier禁用。RLS确实能约束非leakproof表达式的执行顺序，但这不是本次记录中已证实的主要瓶颈。

实施决定：新增order_scope(order_id PK,customer_state)映射，所有订单子表及orders只访问该单层映射；使用非关联IN子查询，让计划可选择一次构造哈希集合，避免嵌套相关子计划的逐行高成本估计。用CASE明确ALL分支执行时短路；不宣称它在计划阶段消除分支。customers同样CASE表达，避免OR组合形成极低选择率估计。无更换账号、BYPASSRLS或全局关闭RLS。

方案②不能通过把current_setting包装成IMMUTABLE安全实现：值随事务权限改变，缓存计划可能固化旧权限。PostgreSQL明确要求依赖配置的函数不能错误标IMMUTABLE；保持动态读取，并用同一generic prepared plan在ALL→SP→空权限验证隔离。来源：[函数易变性](https://www.postgresql.org/docs/16/xfunc-volatility.html)、[RLS与leakproof](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)。

映射随导入COPY、订单增改删、客户州变化事务性维护，包含C5版本触发器。agent_ro仅获SELECT，SQL白名单不包含该表；正式数据仅新增派生映射，不改业务行。优化后完整31条仅重测一次，不按结果反复修改或重测。

- `evidence/step12_c2_explain_plans.json` SHA256 `50c92a86b4b543336180f426e0b32c268bbfe8d7b0c055fe3c79d9f93dcbcbb5`
- `logs/step12_c2_explain.txt` SHA256 `fa1844ef32897926db1b771e51222d56d4092345646c5bb1266b29922d8d489b`
- `logs/step12_c2_diag_setup.txt` SHA256 `8bd57b82fe4beb46c0b9be8495da3d69f2141ed1e1a8ce8cabb4b4d4c6168692`
