"""Human-reviewable C/E SQL templates; values are bound as SQL literals at generation."""

TEMPLATES = [
    {
        "id": "C_unique_customer", "source": "客户标识与复购", "answer_type": "number",
        "dev": "{start} 至 {end}（不含结束日），{state} 州有过下单的真实客户有多少？按人去重。",
        "holdout": "把同一个人换订单产生的客户编号合并后，{state} 州在 [{start}, {end}) 的买家规模是多少？",
        "sql": "SELECT count(DISTINCT c.customer_unique_id) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
        "cases": [("2017-01-01", "2018-01-01", "SP"), ("2018-01-01", "2018-07-01", "RJ"), ("2017-07-01", "2018-01-01", "MG"), ("2018-04-01", "2018-07-01", "SP")],
    },
    {
        "id": "C_gmv_status", "source": "金额口径与关联膨胀", "answer_type": "number",
        "dev": "{state} 州在 [{start}, {end}) 的 GMV 是多少？使用项目默认 GMV 口径。",
        "holdout": "财务要核对 {state} 州 [{start}, {end}) 的有效商品成交额，取消和不可用订单应剔除，不含配送费；金额是多少？",
        "sql": "SELECT coalesce(sum(i.price),0) AS value FROM orders o JOIN customers c USING(customer_id) JOIN order_items i USING(order_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND o.order_status NOT IN ('canceled','unavailable')",
    },
    {
        "id": "C_freight", "source": "金额口径与关联膨胀", "answer_type": "number",
        "dev": "[{start}, {end}) 下单、客户位于 {state} 州的全部订单，其商品价格合计是多少？不含运费，不筛订单状态。",
        "holdout": "只把 {state} 州 [{start}, {end}) 的商品明细 price 相加，保留所有状态，不把支付额或配送费算进去，结果是多少？",
        "sql": "SELECT coalesce(sum(i.price),0) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
    },
    {
        "id": "C_join_grain", "source": "子表粒度与订单缺失关联", "answer_type": "number",
        "dev": "{state} 州 [{start}, {end}) 同时有商品明细和支付记录的订单，商品金额合计是多少？每个商品明细只计一次，所有状态均保留。",
        "holdout": "核对 {state} 州 [{start}, {end}) 有支付记录的订单商品总价：分次付款不能把商品金额乘多次，也不要加入运费。总价是多少？",
        "sql": "SELECT coalesce(sum(i.price),0) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND EXISTS (SELECT 1 FROM order_payments p WHERE p.order_id=o.order_id)",
    },
    {
        "id": "C_boundary_month", "source": "每月订单数", "answer_type": "number",
        "dev": "数据画像标记的边界月 {start} 起至 {end}（不含），实际有订单的日期有几天？不据此计算月环比。",
        "holdout": "{start} 到 {end} 前的订单不是完整月度样本。先查有购买记录的自然日数量，不把整个月天数当作观测天数。",
        "sql": "SELECT count(DISTINCT order_purchase_timestamp::date) AS value FROM orders WHERE order_purchase_timestamp >= {start} AND order_purchase_timestamp < {end}",
        "cases": [("2016-09-01", "2016-10-01", "SP"), ("2018-10-01", "2018-11-01", "SP"), ("2018-09-01", "2018-10-01", "SP")],
    },
    {
        "id": "C_category_coverage", "source": "品类翻译覆盖率", "answer_type": "number",
        "dev": "{state} 州 [{start}, {end}) 的订单商品里，品类没有英文翻译的明细有多少行？包括品类名缺失的商品。",
        "holdout": "为 {state} 州 [{start}, {end}) 的商品明细做英文品类报表时，不能因空品类或翻译缺项丢行；需要放进未知品类桶的明细数是多少？",
        "sql": "SELECT count(*) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) JOIN products p USING(product_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND t.product_category_name IS NULL",
    },
    {
        "id": "C_delivery_null", "source": "交付时间缺失", "answer_type": "number",
        "dev": "{state} 州 [{start}, {end}) 下单且状态为 delivered 的订单，实际交付时间缺失的订单有多少？",
        "holdout": "不能用预计送达替代实际送达。请统计 {state} 州 [{start}, {end}) 标为已送达但没有客户签收时间的订单数。",
        "sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND o.order_status='delivered' AND o.order_delivered_customer_date IS NULL",
    },
    {
        "id": "C_review_grain", "source": "评价与地理位置键", "answer_type": "number",
        "dev": "{state} 州 [{start}, {end}) 的订单中，至少有一条评价的订单有多少？同一订单只算一次。",
        "holdout": "一单多评也只能算一个已评价订单。{state} 州 [{start}, {end}) 的购买订单里，这类订单共有多少？",
        "sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id=o.order_id)",
    },
]

DEFAULT_CASES = [("2017-01-01", "2018-01-01", "SP"), ("2018-01-01", "2018-07-01", "RJ"), ("2018-04-01", "2018-07-01", "MG")]

PREFERENCES = [
    {"id": "E_sales_amount", "quote": "以后我说销售额，指商品价格之和，不含运费，保留所有订单状态。", "key": "sales_amount_definition",
     "prompts": ["{start} 到 {end}（不含）下单的销售额是多少？", "按我之前的销售额口径，算一下 [{start}, {end}) 的总额。"],
     "sql": "SELECT coalesce(sum(i.price),0) AS value FROM order_items i JOIN orders o USING(order_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end}"},
    {"id": "E_customer_identity", "quote": "以后客户数按 customer_unique_id 去重，统计所有下单客户，不筛订单状态。", "key": "customer_identity",
     "prompts": ["[{start}, {end}) 的客户数是多少？", "沿用之前的客户口径，[{start}, {end}) 一共有多少买家？"],
     "sql": "SELECT count(DISTINCT c.customer_unique_id) AS value FROM customers c JOIN orders o USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end}"},
    {"id": "E_order_status", "quote": "以后我说订单数，只统计 delivered 状态。", "key": "order_status_scope",
     "prompts": ["[{start}, {end}) 有多少订单？", "用我之前要求的状态范围，统计 [{start}, {end}) 的订单数量。"],
     "sql": "SELECT count(*) AS value FROM orders WHERE order_purchase_timestamp >= {start} AND order_purchase_timestamp < {end} AND order_status='delivered'"},
    {"id": "E_geography", "quote": "以后经营数字默认只看客户在 SP 州的订单，不限制状态。", "key": "default_state",
     "prompts": ["[{start}, {end}) 的订单数是多少？", "按我设置的地区范围，汇总 [{start}, {end}) 的订单量。"],
     "sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state='SP'"},
    {"id": "E_delivery_duration", "quote": "以后平均交付天数只看已送达且实际送达时间存在的订单，从购买到实际送达按秒除以 86400 算小数天。", "key": "delivery_duration",
     "prompts": ["[{start}, {end}) 下单的平均交付天数是多少？", "按我设定的算法，[{start}, {end}) 购买的订单平均要多久送到？"],
     "sql": "SELECT avg(extract(epoch FROM (order_delivered_customer_date-order_purchase_timestamp))/86400.0) AS value FROM orders WHERE order_purchase_timestamp >= {start} AND order_purchase_timestamp < {end} AND order_status='delivered' AND order_delivered_customer_date IS NOT NULL"},
]
