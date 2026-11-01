# Step 13 补充题 A 段逐题审阅

仅SQL/pandas和离线评分器验证，未调用模型。题干按用户原文录入，split=supplement；等待用户确认后才可进入后续模型协议。

数据库采用agent_ro、REPEATABLE READ READ ONLY，SET LOCAL app.allowed_states=ALL。SQL参考结果见[收据](../evidence/step13_supplement_reference.json)，独立CSV计算见[交叉核对](../evidence/step13_supplement_crosscheck.json)，其中保存源文件/日志名与SHA-256。pandas不读取SQL、SQL结果或旧cross_check计算器，计算完成后才比较；12/12在1%以内，当前记录的数值差为0。

城市真实拼写/行数由[独立SQL](../evidence/step13_supplement_city_sql.json)和原始CSV两边核对：

| 城市 | 客户表行数 | Q1全部订单 | Q2全部订单 | Q2 GMV合格订单 | Q2 GMV商品行 |
|---|---:|---:|---:|---:|---:|
|sao paulo|15540|3286|3442|3415|3994|
|rio de janeiro|6882|1440|1204|1204|1394|

口径与待确认事项：

- N03/N04沿用公开KB：商品price、不含运费、排除canceled/unavailable；按购买时间分期。
- N01全部12个自然月都有订单；最多/最少各唯一。N05众数、N06州、N08卖家最高值均唯一，SQL保留所有并列而不擅自选一个。N09第三名没有并列。
- N08先按卖家+订单去重，50单门槛按已送达订单数；迟到率按KB的完整时间戳比较。合格卖家共8236个卖家-订单对，实际/预计送达缺失均0，因此现有数据无需选择缺失分母处理。
- N09英文名称缺失的商品金额合计52756.30，低于第三名249500.96；不把无英文名称组伪装成英文品类。
- N10用2017全年订单数除以12求月均，比例用未四舍五入的月均计算，最后按题干保留两位小数。
- 当前数据未发现影响唯一答案的并列或缺失口径冲突；新题仍待用户逐题审阅确认，未来数据出现并列时不能沿用任意tie-break。

## N01

2017 年哪个月的订单最多、哪个月最少?各有多少单?按下单时间归月,所有状态计入。

`answer_type=key_facts`；`required_facts=peak_month,peak_orders,low_month,low_orders`。

```sql
WITH m AS (
  SELECT to_char(order_purchase_timestamp, 'YYYY-MM') AS month, count(*) AS orders
  FROM orders WHERE order_purchase_timestamp >= '2017-01-01'
    AND order_purchase_timestamp < '2018-01-01' GROUP BY 1
), hi AS (SELECT * FROM m WHERE orders = (SELECT max(orders) FROM m)),
lo AS (SELECT * FROM m WHERE orders = (SELECT min(orders) FROM m))
SELECT hi.month AS peak_month, hi.orders AS peak_orders,
       lo.month AS low_month, lo.orders AS low_orders FROM hi CROSS JOIN lo;
```

Gold：

```json
{
  "peak_month": "2017-11",
  "peak_orders": 7544,
  "low_month": "2017-01",
  "low_orders": 800
}
```

pandas：

```json
{
  "peak_month": "2017-11",
  "peak_orders": 7544,
  "low_month": "2017-01",
  "low_orders": 800
}
```

一致：True。

## N02

圣保罗市(São Paulo 市)2018 年 Q1 的客户下了多少单?按客户所在城市,所有状态计入。

`answer_type=number`；`required_facts=`。

```sql
SELECT count(*) AS value FROM orders o JOIN customers c USING (customer_id)
WHERE c.customer_city = 'sao paulo' AND o.order_purchase_timestamp >= '2018-01-01'
  AND o.order_purchase_timestamp < '2018-04-01';
```

Gold：

```json
3286
```

pandas：

```json
3286
```

一致：True。

## N03

里约热内卢市(Rio de Janeiro 市)和圣保罗市,2018 年 Q2 的 GMV 各是多少?GMV 按知识库口径。

`answer_type=key_facts`；`required_facts=rio_gmv,sao_paulo_gmv`。

```sql
SELECT sum(i.price) FILTER (WHERE c.customer_city = 'rio de janeiro') AS rio_gmv,
       sum(i.price) FILTER (WHERE c.customer_city = 'sao paulo') AS sao_paulo_gmv
FROM orders o JOIN customers c USING (customer_id) JOIN order_items i USING (order_id)
WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
  AND o.order_status NOT IN ('canceled','unavailable')
  AND c.customer_city IN ('rio de janeiro','sao paulo');
```

Gold：

```json
{
  "rio_gmv": 187039.25,
  "sao_paulo_gmv": 432735.87
}
```

pandas：

```json
{
  "rio_gmv": 187039.25,
  "sao_paulo_gmv": 432735.87
}
```

一致：True。

## N04

2018 年 1–8 月的 GMV 比 2017 年同期增长了多少(百分数)?GMV 排除取消及不可用订单。

`answer_type=key_facts`；`required_facts=gmv_2017,gmv_2018,growth_pct`。

```sql
WITH g AS (
 SELECT sum(i.price) FILTER (WHERE o.order_purchase_timestamp >= '2017-01-01'
   AND o.order_purchase_timestamp < '2017-09-01') AS gmv_2017,
 sum(i.price) FILTER (WHERE o.order_purchase_timestamp >= '2018-01-01'
   AND o.order_purchase_timestamp < '2018-09-01') AS gmv_2018
 FROM orders o JOIN order_items i USING (order_id)
 WHERE o.order_status NOT IN ('canceled','unavailable')
)
SELECT gmv_2017, gmv_2018, 100.0*(gmv_2018-gmv_2017)/nullif(gmv_2017,0) AS growth_pct FROM g;
```

Gold：

```json
{
  "gmv_2017": 3080850.81,
  "gmv_2018": 7341037.41,
  "growth_pct": 138.2795488237225
}
```

pandas：

```json
{
  "gmv_2017": 3080850.81,
  "gmv_2018": 7341037.41,
  "growth_pct": 138.2795488237225
}
```

一致：True。

## N05

2018 年用信用卡的支付记录里,最常见的是分几期?占信用卡支付记录的百分之几?按支付记录计,按订单下单时间归年。

`answer_type=key_facts`；`required_facts=mode_installments,share_pct`。

```sql
WITH counts AS (
 SELECT p.payment_installments, count(*) AS n FROM order_payments p JOIN orders o USING (order_id)
 WHERE p.payment_type = 'credit_card' AND o.order_purchase_timestamp >= '2018-01-01'
   AND o.order_purchase_timestamp < '2019-01-01' GROUP BY p.payment_installments
)
SELECT payment_installments AS mode_installments,
  100.0*n/(SELECT sum(n) FROM counts) AS share_pct
FROM counts WHERE n = (SELECT max(n) FROM counts);
```

Gold：

```json
{
  "mode_installments": 1,
  "share_pct": 35.959875145941055
}
```

pandas：

```json
{
  "mode_installments": 1,
  "share_pct": 35.959875145941055
}
```

一致：True。

## N06

2018 年 Q2 运费占(商品金额 + 运费)的比例是多少?按客户所在州看,这个比例最高的州是哪个、是多少?所有状态计入,百分数。

`answer_type=key_facts`；`required_facts=freight_pct,top_state,top_state_pct`。

```sql
WITH s AS (
 SELECT c.customer_state, sum(i.freight_value) AS freight, sum(i.price+i.freight_value) AS total
 FROM orders o JOIN customers c USING (customer_id) JOIN order_items i USING (order_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 GROUP BY c.customer_state
), r AS (SELECT *, 100.0*freight/nullif(total,0) AS pct FROM s)
SELECT (SELECT 100.0*sum(freight)/sum(total) FROM s) AS freight_pct,
 customer_state AS top_state, pct AS top_state_pct FROM r WHERE pct = (SELECT max(pct) FROM r);
```

Gold：

```json
{
  "freight_pct": 14.221035631463664,
  "top_state": "AP",
  "top_state_pct": 21.55846249974805
}
```

pandas：

```json
{
  "freight_pct": 14.221035631463664,
  "top_state": "AP",
  "top_state_pct": 21.55846249974805
}
```

一致：True。

## N07

2018 年 Q2 已送达、且有实际送达时间的订单里,从下单到送达超过 30 天的有多少单?占比多少(百分数)?

`answer_type=key_facts`；`required_facts=over30_orders,measured_orders,over30_pct`。

```sql
WITH m AS (
 SELECT count(*) AS measured_orders,
 count(*) FILTER (WHERE order_delivered_customer_date-order_purchase_timestamp > interval '30 days') AS over30_orders
 FROM orders WHERE order_purchase_timestamp >= '2018-04-01' AND order_purchase_timestamp < '2018-07-01'
 AND order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
)
SELECT over30_orders, measured_orders, 100.0*over30_orders/nullif(measured_orders,0) AS over30_pct FROM m;
```

Gold：

```json
{
  "over30_orders": 522,
  "measured_orders": 19643,
  "over30_pct": 2.6574352186529553
}
```

pandas：

```json
{
  "over30_orders": 522,
  "measured_orders": 19643,
  "over30_pct": 2.6574352186529553
}
```

一致：True。

## N08

2018 年 Q2,已送达订单不少于 50 单的卖家里,迟到率最高的是哪个卖家?迟到率多少?一个订单含多个卖家时,计入每个卖家;迟到指实际送达晚于预计送达。

`answer_type=key_facts`；`required_facts=worst_seller,late_pct`。

```sql
WITH pairs AS (
 SELECT DISTINCT i.seller_id, o.order_id, o.order_delivered_customer_date AS actual,
 o.order_estimated_delivery_date AS expected FROM orders o JOIN order_items i USING (order_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 AND o.order_status = 'delivered'
), rates AS (
 SELECT seller_id, 100.0*count(*) FILTER (WHERE actual > expected)
 /nullif(count(*) FILTER (WHERE actual IS NOT NULL),0) AS late_pct
 FROM pairs GROUP BY seller_id HAVING count(*) >= 50
)
SELECT seller_id AS worst_seller, late_pct FROM rates WHERE late_pct = (SELECT max(late_pct) FROM rates);
```

Gold：

```json
{
  "worst_seller": "06a2c3af7b3aee5d69171b0e14f0ee87",
  "late_pct": 17.801047120418847
}
```

pandas：

```json
{
  "worst_seller": "06a2c3af7b3aee5d69171b0e14f0ee87",
  "late_pct": 17.801047120418847
}
```

一致：True。

## N09

2018 年 Q1 商品金额前三的英文品类是哪些?不含运费,所有状态计入。

`answer_type=list`；`required_facts=`。

```sql
WITH amounts AS (
 SELECT t.product_category_name_english AS category, sum(i.price) AS amount
 FROM orders o JOIN order_items i USING (order_id) JOIN products p USING (product_id)
 JOIN product_category_name_translation t USING (product_category_name)
 WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-04-01'
 GROUP BY t.product_category_name_english
), ranked AS (SELECT *, dense_rank() OVER (ORDER BY amount DESC) AS rank FROM amounts)
SELECT category FROM ranked WHERE rank <= 3 ORDER BY amount DESC;
```

Gold：

```json
[
  "computers_accessories",
  "sports_leisure",
  "health_beauty"
]
```

pandas：

```json
[
  "computers_accessories",
  "sports_leisure",
  "health_beauty"
]
```

一致：True。

## N10

2017 年 11 月的订单量是 2017 年月均订单量的多少倍?按下单时间归月,所有状态计入,结果保留两位小数。

`answer_type=key_facts`；`required_facts=nov_orders,monthly_avg,ratio`。

```sql
WITH n AS (
 SELECT count(*) FILTER (WHERE order_purchase_timestamp >= '2017-11-01'
   AND order_purchase_timestamp < '2017-12-01') AS nov_orders, count(*)/12.0 AS monthly_avg
 FROM orders WHERE order_purchase_timestamp >= '2017-01-01' AND order_purchase_timestamp < '2018-01-01'
)
SELECT nov_orders, round(monthly_avg,2) AS monthly_avg,
 round(nov_orders/nullif(monthly_avg,0),2) AS ratio FROM n;
```

Gold：

```json
{
  "nov_orders": 7544,
  "monthly_avg": 3758.42,
  "ratio": 2.01
}
```

pandas：

```json
{
  "nov_orders": 7544,
  "monthly_avg": 3758.42,
  "ratio": 2.01
}
```

一致：True。

## N11

2018 年 Q2 有多少个真实客户在不同的州下过单(至少两个州)?所有状态计入。

`answer_type=number`；`required_facts=`。

```sql
SELECT count(*) AS value FROM (
 SELECT c.customer_unique_id FROM orders o JOIN customers c USING (customer_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 GROUP BY c.customer_unique_id HAVING count(DISTINCT c.customer_state) >= 2
) AS multi_state;
```

Gold：

```json
2
```

pandas：

```json
2
```

一致：True。

## N12

2018 年 Q2 平均每笔订单包含几件商品?包含两件及以上商品的订单占多少(百分数)?只算有商品明细的订单,件数按明细行数。

`answer_type=key_facts`；`required_facts=avg_items,multi_item_pct`。

```sql
WITH n AS (
 SELECT o.order_id, count(*) AS items FROM orders o JOIN order_items i USING (order_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 GROUP BY o.order_id
)
SELECT avg(items) AS avg_items, 100.0*count(*) FILTER (WHERE items>=2)/count(*) AS multi_item_pct FROM n;
```

Gold：

```json
{
  "avg_items": 1.1519526745876574,
  "multi_item_pct": 10.482779365318093
}
```

pandas：

```json
{
  "avg_items": 1.1519526745876574,
  "multi_item_pct": 10.482779365318093
}
```

一致：True。
