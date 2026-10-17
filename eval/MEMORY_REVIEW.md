# 偏好抽取审查

来源 [memory_audit_20261017T081910Z_35671a53.summary.json](../evidence/memory_audit_20261017T081910Z_35671a53.summary.json)；原始日志 `memory_audit_20261017T081910Z_35671a53.jsonl`。自动全文原话/key 核对不等于人工准确率。人工结果留空，待用户审阅。

| 样例 | 用户原话 | 预期 key | 实际抽取 | 自动严格匹配 | 人工结论 |
| --- | --- | --- | --- | --- | --- |
| 0 | 以后销售额都只算商品价格，不包含运费。 | sales_amount_definition | [{"key": "sales_amount_definition", "source_quote": "以后销售额都只算商品价格，不包含运费。", "value": "以后销售额都只算商品价格，不包含运费。"}] | True |  |
| 1 | 请记住我的销售额口径：商品价格加运费。 | sales_amount_definition | [{"key": "sales_amount_definition", "source_quote": "请记住我的销售额口径：商品价格加运费。", "value": "请记住我的销售额口径：商品价格加运费。"}] | True |  |
| 2 | 以后商品销售额保留所有订单状态。 | sales_amount_definition | [{"key": "sales_amount_definition", "source_quote": "以后商品销售额保留所有订单状态。", "value": "以后商品销售额保留所有订单状态。"}] | True |  |
| 3 | 从现在起销售额只看已送达订单的商品金额。 | sales_amount_definition | [{"key": "sales_amount_definition", "source_quote": "从现在起销售额只看已送达订单的商品金额。", "value": "从现在起销售额只看已送达订单的商品金额。"}] | True |  |
| 4 | 以后客户数统一按 customer_unique_id 去重。 | customer_identity | [{"key": "customer_identity", "source_quote": "以后客户数统一按 customer_unique_id 去重。", "value": "以后客户数统一按 customer_unique_id 去重。"}] | True |  |
| 5 | 请记住，客户统计按 customer_id，不使用真实人标识。 | customer_identity | [{"key": "customer_identity", "source_quote": "请记住，客户统计按 customer_id，不使用真实人标识。", "value": "请记住，客户统计按 customer_id，不使用真实人标识。"}] | True |  |
| 6 | 以后买家规模只数不同的 customer_unique_id。 | customer_identity | [{"key": "customer_identity", "source_quote": "以后买家规模只数不同的 customer_unique_id。", "value": "以后买家规模只数不同的 customer_unique_id。"}] | True |  |
| 7 | 默认客户数按所有状态下单的 customer_unique_id 统计。 | customer_identity | [{"key": "customer_identity", "source_quote": "默认客户数按所有状态下单的 customer_unique_id 统计。", "value": "默认客户数按所有状态下单的 customer_unique_id 统计。"}] | True |  |
| 8 | 以后订单数只统计 delivered。 | order_status_scope | [{"key": "order_status_scope", "source_quote": "以后订单数只统计 delivered。", "value": "以后订单数只统计 delivered。"}] | True |  |
| 9 | 以后订单量保留全部状态。 | order_status_scope | [{"key": "order_status_scope", "source_quote": "以后订单量保留全部状态。", "value": "以后订单量保留全部状态。"}] | True |  |
| 10 | 记住订单数不包括 canceled 和 unavailable。 | order_status_scope | [{"key": "order_status_scope", "source_quote": "记住订单数不包括 canceled 和 unavailable。", "value": "记住订单数不包括 canceled 和 unavailable。"}] | True |  |
| 11 | 默认只看 canceled 状态的订单数量。 | order_status_scope | [{"key": "order_status_scope", "source_quote": "默认只看 canceled 状态的订单数量。", "value": "默认只看 canceled 状态的订单数量。"}] | True |  |
| 12 | 以后经营数字默认只看客户 SP 州。 | default_state | [{"key": "default_state", "source_quote": "以后经营数字默认只看客户 SP 州。", "value": "以后经营数字默认只看客户 SP 州。"}] | True |  |
| 13 | 请记住默认分析 RJ 州客户的订单。 | default_state | [{"key": "default_state", "source_quote": "请记住默认分析 RJ 州客户的订单。", "value": "请记住默认分析 RJ 州客户的订单。"}] | True |  |
| 14 | 以后所有报表默认地区用 MG 客户州。 | default_state | [{"key": "default_state", "source_quote": "以后所有报表默认地区用 MG 客户州。", "value": "以后所有报表默认地区用 MG 客户州。"}] | True |  |
| 15 | 默认地区改成 RS 州，指客户所在地。 | default_state | [{"key": "default_state", "source_quote": "默认地区改成 RS 州，指客户所在地。", "value": "默认地区改成 RS 州，指客户所在地。"}] | True |  |
| 16 | 以后平均交付天数用购买到实际签收的秒数除以 86400。 | delivery_duration | [{"key": "delivery_duration", "source_quote": "以后平均交付天数用购买到实际签收的秒数除以 86400。", "value": "以后平均交付天数用购买到实际签收的秒数除以 86400。"}] | True |  |
| 17 | 以后交付时长只看 delivered 且实际送达时间非空。 | delivery_duration | [{"key": "delivery_duration", "source_quote": "以后交付时长只看 delivered 且实际送达时间非空。", "value": "以后交付时长只看 delivered 且实际送达时间非空。"}] | True |  |
| 18 | 默认配送时长从批准订单算到实际送达。 | delivery_duration | [{"key": "delivery_duration", "source_quote": "默认配送时长从批准订单算到实际送达。", "value": "默认配送时长从批准订单算到实际送达。"}] | True |  |
| 19 | 记住交付时长保留小数天，不要只取日期差。 | delivery_duration | [{"key": "delivery_duration", "source_quote": "记住交付时长保留小数天，不要只取日期差。", "value": "记住交付时长保留小数天，不要只取日期差。"}] | True |  |
