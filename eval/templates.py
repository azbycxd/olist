"""Human-reviewable C/E SQL templates; values are bound as SQL literals at generation."""

TEMPLATES = [
    {
        "id": "C_unique_customer", "source": "客户标识与复购", "answer_type": "number",
        "dev": "{state} 州从 {start} 到 {last_day} 有多少客户？",
        "holdout": "帮我看一下 {start} 至 {last_day} 这段时间，{state} 州的买家规模有多大？",
        "sql": "SELECT count(DISTINCT c.customer_unique_id) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
        "naive_sql": "SELECT count(DISTINCT c.customer_id) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
        "cases": [("2017-01-01", "2018-01-01", "SP"), ("2018-01-01", "2018-07-01", "RJ"), ("2017-07-01", "2018-01-01", "MG"), ("2018-04-01", "2018-07-01", "SP")],
    },
    {
        "id": "C_gmv_status", "source": "金额口径与关联膨胀", "answer_type": "number",
        "dev": "{state} 州从 {start} 到 {last_day} 的 GMV 是多少？",
        "holdout": "我要做 {state} 州的经营汇报，{start} 至 {last_day} 这段时间的 GMV 总共有多少？",
        "sql": "SELECT coalesce(sum(i.price),0) AS value FROM orders o JOIN customers c USING(customer_id) JOIN order_items i USING(order_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND o.order_status NOT IN ('canceled','unavailable')",
        "naive_sql": "SELECT coalesce(sum(i.price),0) AS value FROM orders o JOIN customers c USING(customer_id) JOIN order_items i USING(order_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
        "cases": [("2017-07-01", "2017-08-01", "SP"), ("2018-02-01", "2018-03-01", "RJ"), ("2018-07-01", "2018-08-01", "MG")],
    },
    {
        "id": "C_freight", "source": "金额口径与关联膨胀", "answer_type": "number",
        "dev": "{state} 州从 {start} 到 {last_day} 的商品销售额是多少？",
        "holdout": "{start} 至 {last_day}，{state} 州的商品一共卖了多少钱？",
        "sql": "SELECT coalesce(sum(i.price),0) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
        "naive_sql": "SELECT coalesce(sum(i.price+i.freight_value),0) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
    },
    {
        "id": "C_join_grain", "source": "子表粒度与订单缺失关联", "answer_type": "number",
        "dev": "{state} 州从 {start} 到 {last_day} 的已付款订单，商品销售额是多少？",
        "holdout": "帮我核对 {state} 州 {start} 至 {last_day} 这段时间收到付款的订单，商品总共卖了多少钱？",
        "sql": "SELECT coalesce(sum(i.price),0) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND EXISTS (SELECT 1 FROM order_payments p WHERE p.order_id=o.order_id)",
        "naive_sql": "SELECT coalesce(sum(i.price),0) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) JOIN order_payments p USING(order_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
    },
    {
        "id": "C_boundary_month", "source": "每月订单数", "answer_type": "number",
        "dev": "{start} 至 {last_day} 这段时间，成交记录覆盖了多少天？",
        "holdout": "我想了解 {start} 到 {last_day} 这份数据的覆盖情况：有多少天的成交数据？",
        "sql": "SELECT count(DISTINCT order_purchase_timestamp::date) AS value FROM orders WHERE order_purchase_timestamp >= {start} AND order_purchase_timestamp < {end}",
        "naive_sql": "SELECT {end}::date - {start}::date AS value",
        "cases": [("2016-09-01", "2016-10-01", "SP"), ("2018-10-01", "2018-11-01", "SP"), ("2018-09-01", "2018-10-01", "SP")],
    },
    {
        "id": "C_category_coverage", "source": "品类翻译覆盖率", "answer_type": "number",
        "dev": "{state} 州 {start} 至 {last_day} 的英文品类报表里，待归类的商品明细有多少？",
        "holdout": "帮我核对 {state} 州 {start} 到 {last_day} 的英文品类报表，未知品类这一栏有多少条商品明细？",
        "sql": "SELECT count(*) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) JOIN products p USING(product_id) LEFT JOIN product_category_name_translation t USING(product_category_name) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND t.product_category_name IS NULL",
        "naive_sql": "SELECT count(*) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) JOIN products p USING(product_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND p.product_category_name NOT IN (SELECT product_category_name FROM product_category_name_translation)",
    },
    {
        "id": "C_delivery_null", "source": "交付时间缺失", "answer_type": "number",
        "dev": "{state} 州从 {start} 到 {last_day} 下的订单，有多少笔需要补录签收时间？",
        "holdout": "物流正在核对签收信息，{state} 州 {start} 至 {last_day} 的订单里有多少笔待补签收记录？",
        "sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND o.order_status='delivered' AND o.order_delivered_customer_date IS NULL",
        "naive_sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND o.order_delivered_customer_date IS NULL",
        "cases": [("2017-01-01", "2018-01-01", "SP"), ("2017-01-01", "2018-01-01", "RS"), ("2018-01-01", "2018-08-01", "SP")],
    },
    {
        "id": "C_review_grain", "source": "评价与地理位置键", "answer_type": "number",
        "dev": "{state} 州从 {start} 到 {last_day} 下的订单，有多少单获得了评价？",
        "holdout": "看看 {state} 州 {start} 至 {last_day} 的购买情况，买家给多少笔订单留过评价？",
        "sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state} AND EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id=o.order_id)",
        "naive_sql": "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) JOIN order_reviews r USING(order_id) WHERE o.order_purchase_timestamp >= {start} AND o.order_purchase_timestamp < {end} AND c.customer_state={state}",
        "cases": [("2018-02-01", "2018-03-01", "MG"), ("2018-02-01", "2018-03-01", "RS"), ("2017-11-01", "2017-12-01", "BA")],
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
