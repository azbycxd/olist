# 经营指标

默认定义可由用户明确偏好覆盖；问题中明确指定的范围优先。以下 SQL 为不含时间和地区筛选的结构示例，应按问题添加购买时间半开区间和客户州筛选，不能把示例直接当答案。金额以数据原币种计算，所有差额和比率也由 SQL 求值。

## buyers 客户数／真实客户／买家规模
统计观察窗口内有订单的 customer_unique_id 去重数，默认保留所有订单状态。customer_id 是订单关联标识，同人跨订单可能不同。
```sql
SELECT count(DISTINCT c.customer_unique_id) AS buyers FROM orders o JOIN customers c USING(customer_id);
```

## gmv GMV／成交商品金额
GMV 为 order_items.price 之和，不含 freight_value，排除 canceled 和 unavailable。它不等于支付流水金额。按订单购买时间分期，地区使用客户州，不是卖家州。
```sql
SELECT sum(i.price) AS gmv FROM orders o JOIN order_items i USING(order_id) WHERE o.order_status NOT IN ('canceled','unavailable');
```

## sales 商品销售额／商品卖了多少钱／商品金额
商品销售额为 order_items.price 之和，不含运费，默认保留所有订单状态。此指标与排除 canceled/unavailable 的 GMV 不同。问题明确状态时依问题。
```sql
SELECT sum(price) AS sales FROM order_items;
```

## paid_sales 已付款订单的商品销售额／收到付款的订单
先用 EXISTS 筛选至少有一条 payment 的订单，再求商品价格总和，保留全部状态且不含运费。不得直接 JOIN 支付明细再 SUM 商品金额，一单多次付款会放大金额。
```sql
SELECT sum(i.price) AS paid_sales FROM order_items i WHERE EXISTS (SELECT 1 FROM order_payments p WHERE p.order_id=i.order_id);
```

## observed_days 成交覆盖天数／有成交数据的天数
是观察窗口内 order_purchase_timestamp::date 的不同实际有订单日期数，不是日历天数，也不是日期差。首尾和稀疏月份可能缺天；没有订单不能证明业务停运。
```sql
SELECT count(DISTINCT order_purchase_timestamp::date) AS observed_days FROM orders;
```

## unknown_category 英文品类报表待归类／未知品类明细
统计英文翻译缺失的商品明细行数，包括原始 product_category_name 为空和非空但无翻译两种情况。LEFT JOIN 翻译表后判断翻译键 IS NULL；NOT IN 会漏掉 NULL。
```sql
SELECT count(*) AS unknown_items FROM order_items i JOIN products p USING(product_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE t.product_category_name IS NULL;
```

## missing_signature 待补签收记录／补录签收时间
只指状态为 delivered 但 order_delivered_customer_date 为空的订单。其他未完成或取消订单没有实际送达时间是正常情况，不能全当作待补录签收。
```sql
SELECT count(*) AS missing_signature FROM orders WHERE order_status='delivered' AND order_delivered_customer_date IS NULL;
```

## reviewed_orders 已评价订单／多少单获得评价
按订单计算是否存在评价，不能用评价行数代替订单数。一个订单可能有多条评价。
```sql
SELECT count(*) AS reviewed_orders FROM orders o WHERE EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id=o.order_id);
```

## repeat_rate 复购客户数／复购率
观察窗口内按 customer_unique_id 汇总订单数，至少两单为复购客户；分母为同窗口全部下单客户，默认所有状态。窗口内复购不是终身复购。
```sql
WITH c AS (SELECT customer_unique_id,count(*) AS n FROM orders JOIN customers USING(customer_id) GROUP BY customer_unique_id) SELECT count(*) AS buyers,count(*) FILTER(WHERE n>=2) AS repeat_buyers,100.0*count(*) FILTER(WHERE n>=2)/nullif(count(*),0) AS repeat_pct FROM c;
```

## delivery_days 平均交付天数／配送时长
只看 delivered 且实际送达时间非空，从购买到实际送达的秒数除以 86400 后平均，保留小数天。不能用 DATE 相减丢失时分秒。按购买时间分期。
```sql
SELECT avg(extract(epoch FROM(order_delivered_customer_date-order_purchase_timestamp))/86400.0) AS delivery_days FROM orders WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL;
```

## late_rate 迟到率／交付晚于预计
分母为 delivered 且实际交付时间存在的订单，分子按完整原始时间戳比较实际大于预计；不截断日期。缺预计时间应另行说明，不能自行填补。
```sql
SELECT count(*) AS measured_orders,count(*) FILTER(WHERE order_delivered_customer_date>order_estimated_delivery_date) AS late_orders,100.0*count(*) FILTER(WHERE order_delivered_customer_date>order_estimated_delivery_date)/nullif(count(*),0) AS late_pct FROM orders WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL;
```

## payment 支付总额／实付流水
按 payment_value 求和。支付表一单多行，每行是支付序列，先按订单聚合再与商品聚合关联。支付总额不保证恒等于商品加运费。
```sql
SELECT sum(payment_value) AS payment_total FROM order_payments;
```

## freight 运费／运输费用
order_items.freight_value 是商品明细分摊运费，汇总需在商品明细粒度求和，不能重复关联支付或评价。
```sql
SELECT sum(freight_value) AS freight_total FROM order_items;
```

## orders_count 订单数／订单量
默认订单表全部状态的行数。状态偏好如 delivered 应明确过滤，订单明细的行数是件次而不是订单数。
```sql
SELECT count(*) AS orders FROM orders;
```

## cancellation 取消订单与取消率
分子为 canceled，分母同窗口全部订单，按购买时间分期。unavailable 不自动算作 canceled。状态数据不能单独解释取消原因。
```sql
SELECT count(*) FILTER(WHERE order_status='canceled') AS canceled,100.0*count(*) FILTER(WHERE order_status='canceled')/nullif(count(*),0) AS cancel_pct FROM orders;
```
