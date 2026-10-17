"""Handwritten A/B/D cases. SQL is an oracle, never passed to an adapter."""


def cases():
    result = []

    def add(category, question, sql, answer_type="number", facts=None, focus=None):
        number = sum(q["category"] == category for q in result) + 1
        result.append({"id": f"{category}{number:02d}", "category": category,
            "question": question, "gold_sql": sql, "answer_type": answer_type,
            "split": "dev" if number <= (8 if category == "D" else 7) else "holdout",
            "required_facts": facts or [], "rubric_focus": focus})

    add("A", "订单表共有多少订单？", "SELECT count(*) AS value FROM orders")
    add("A", "状态为 delivered 的订单数是多少？", "SELECT count(*) AS value FROM orders WHERE order_status='delivered'")
    add("A", "商品表共有多少种商品？", "SELECT count(*) AS value FROM products")
    add("A", "卖家表共有多少卖家？", "SELECT count(*) AS value FROM sellers")
    add("A", "订单状态有哪些？列出全部状态。", "SELECT DISTINCT order_status FROM orders ORDER BY order_status", "list")
    add("A", "2017 年 11 月购买的订单有多少？", "SELECT count(*) AS value FROM orders WHERE order_purchase_timestamp >= '2017-11-01' AND order_purchase_timestamp < '2017-12-01'")
    add("A", "全部订单商品明细的运费合计是多少？", "SELECT sum(freight_value) AS value FROM order_items")
    add("A", "支付方式有哪些？列出所有支付方式。", "SELECT DISTINCT payment_type FROM order_payments ORDER BY payment_type", "list")
    add("A", "评价得分为 1 的评价记录有多少条？", "SELECT count(*) AS value FROM order_reviews WHERE review_score=1")
    add("A", "2018 年 5 月购买的订单有多少？", "SELECT count(*) AS value FROM orders WHERE order_purchase_timestamp >= '2018-05-01' AND order_purchase_timestamp < '2018-06-01'")

    add("B", "客户在 SP 州的订单有多少？所有状态都计入。", "SELECT count(*) AS value FROM orders o JOIN customers c USING(customer_id) WHERE c.customer_state='SP'")
    add("B", "英文品类为 health_beauty 的商品明细价格合计是多少？不含运费，保留所有订单状态。", "SELECT sum(i.price) AS value FROM order_items i JOIN products p USING(product_id) JOIN product_category_name_translation t USING(product_category_name) WHERE t.product_category_name_english='health_beauty'")
    add("B", "2018 年 Q1 所有购买订单的支付总额是多少？", "SELECT sum(p.payment_value) AS value FROM order_payments p JOIN orders o USING(order_id) WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-04-01'")
    add("B", "向 RJ 州客户卖过商品的不同卖家数是多少？", "SELECT count(DISTINCT i.seller_id) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE c.customer_state='RJ'")
    add("B", "2017 年至少有一条评价的订单数是多少？", "SELECT count(*) AS value FROM orders o WHERE o.order_purchase_timestamp >= '2017-01-01' AND o.order_purchase_timestamp < '2018-01-01' AND EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id=o.order_id)")
    add("B", "按所有状态商品金额排序，客户州排名前五的州代码有哪些？金额并列按州代码升序。", "SELECT c.customer_state FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) GROUP BY c.customer_state ORDER BY sum(i.price) DESC, c.customer_state LIMIT 5", "list")
    add("B", "英文品类 computers_accessories 的全部商品明细有多少行？", "SELECT count(*) AS value FROM order_items i JOIN products p USING(product_id) JOIN product_category_name_translation t USING(product_category_name) WHERE t.product_category_name_english='computers_accessories'")
    add("B", "客户在 MG 州的全部订单商品运费总额是多少？", "SELECT sum(i.freight_value) AS value FROM order_items i JOIN orders o USING(order_id) JOIN customers c USING(customer_id) WHERE c.customer_state='MG'")
    add("B", "按全部商品金额排名，2018 年 Q2 前三个卖家 ID 是哪些？并列时 ID 升序。", "SELECT i.seller_id FROM order_items i JOIN orders o USING(order_id) WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01' GROUP BY i.seller_id ORDER BY sum(i.price) DESC, i.seller_id LIMIT 3", "list")
    add("B", "2018 年 1 月购买的订单中，有至少两个不同商品 ID 的订单数是多少？", "SELECT count(*) AS value FROM (SELECT o.order_id FROM orders o JOIN order_items i USING(order_id) WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-02-01' GROUP BY o.order_id HAVING count(DISTINCT i.product_id)>=2) s")

    add("D", "比较 2018 年 Q1、Q2 的 GMV 和变化率（百分数）。先排除取消及不可用订单，再分析变化；不要把统计相关写成确定原因。", """WITH x AS (
        SELECT sum(i.price) FILTER (WHERE o.order_purchase_timestamp < '2018-04-01') AS q1_gmv,
        sum(i.price) FILTER (WHERE o.order_purchase_timestamp >= '2018-04-01') AS q2_gmv
        FROM orders o JOIN order_items i USING(order_id)
        WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-07-01'
        AND o.order_status NOT IN ('canceled','unavailable'))
        SELECT q1_gmv, q2_gmv, 100.0*(q2_gmv-q1_gmv)/nullif(q1_gmv,0) AS change_pct FROM x""",
        "key_facts", ["q1_gmv", "q2_gmv", "change_pct"], "比较季度变化；区分变化描述与因果假设。")
    add("D", "2018 年 Q2 相比 Q1，有多少个原始葡文品类 GMV 下降？给出降幅金额最大的品类及下降金额，分析可能原因。只比较两个季度都有商品成交的非空品类，排除取消及不可用订单。", """WITH c AS (
        SELECT p.product_category_name AS category,
        sum(i.price) FILTER (WHERE o.order_purchase_timestamp < '2018-04-01') AS q1,
        sum(i.price) FILTER (WHERE o.order_purchase_timestamp >= '2018-04-01') AS q2
        FROM orders o JOIN order_items i USING(order_id) JOIN products p USING(product_id)
        WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-07-01'
        AND o.order_status NOT IN ('canceled','unavailable') AND p.product_category_name IS NOT NULL
        GROUP BY p.product_category_name), d AS (SELECT *, q1-q2 AS drop_amount FROM c WHERE q2<q1)
        SELECT (SELECT count(*) FROM d) AS declining_categories, category AS largest_drop_category,
        drop_amount AS largest_drop_amount FROM d ORDER BY drop_amount DESC, category LIMIT 1""",
        "key_facts", ["declining_categories", "largest_drop_category", "largest_drop_amount"], "说明比较范围和最大拖累品类，原因不能凭空归咎营销或竞争。")
    add("D", "2018 年 Q2，比较 SP 与 RJ 两州的真实下单客户数和 GMV，共四个关键事实。GMV 排除取消及不可用订单，客户数保留所有状态；讨论规模与客单结构。", """WITH c AS (
        SELECT c.customer_state AS state, count(DISTINCT c.customer_unique_id) AS buyers FROM orders o JOIN customers c USING(customer_id)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01' GROUP BY c.customer_state), g AS (
        SELECT c.customer_state AS state, sum(i.price) AS gmv FROM orders o JOIN customers c USING(customer_id) JOIN order_items i USING(order_id)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01' AND o.order_status NOT IN ('canceled','unavailable') GROUP BY c.customer_state)
        SELECT (SELECT buyers FROM c WHERE state='SP') AS sp_buyers, (SELECT buyers FROM c WHERE state='RJ') AS rj_buyers,
        (SELECT gmv FROM g WHERE state='SP') AS sp_gmv, (SELECT gmv FROM g WHERE state='RJ') AS rj_gmv""",
        "key_facts", ["sp_buyers", "rj_buyers", "sp_gmv", "rj_gmv"], "客户范围与 GMV 状态口径不同，不能直接解释成统一口径客单价。")
    add("D", "2018 年 Q1 与 Q2，已送达且有实际送达时间的订单，平均交付天数各是多少、两期相差多少天？按购买日期分期、小数天计算，讨论时效变化。", """WITH x AS (
        SELECT avg(extract(epoch FROM (order_delivered_customer_date-order_purchase_timestamp))/86400.0) FILTER (WHERE order_purchase_timestamp < '2018-04-01') AS q1_days,
        avg(extract(epoch FROM (order_delivered_customer_date-order_purchase_timestamp))/86400.0) FILTER (WHERE order_purchase_timestamp >= '2018-04-01') AS q2_days
        FROM orders WHERE order_purchase_timestamp >= '2018-01-01' AND order_purchase_timestamp < '2018-07-01'
        AND order_status='delivered' AND order_delivered_customer_date IS NOT NULL)
        SELECT *, q2_days-q1_days AS change_days FROM x""", "key_facts", ["q1_days", "q2_days", "change_days"], "使用实际交付时间，区分平均数变化与物流原因。")
    add("D", "2018 年 Q2 的已送达订单中，实际交付晚于预计交付的订单数、实际交付时间完整的订单数、迟到率（百分数）分别是多少？按原始时间戳比较，不截断为日期；解释分母。", """SELECT
        count(*) FILTER (WHERE order_delivered_customer_date > order_estimated_delivery_date) AS late_orders,
        count(*) AS measured_orders,
        100.0*count(*) FILTER (WHERE order_delivered_customer_date > order_estimated_delivery_date)/nullif(count(*),0) AS late_pct
        FROM orders WHERE order_purchase_timestamp >= '2018-04-01' AND order_purchase_timestamp < '2018-07-01'
        AND order_status='delivered' AND order_delivered_customer_date IS NOT NULL""", "key_facts", ["late_orders", "measured_orders", "late_pct"], "空交付时间不得作为按时送达计入分母。")
    add("D", "2018 年 Q2 全部订单的商品金额、运费和支付金额各是多少？对比三者并解释为何不应直接把支付金额当作商品 GMV。", """WITH i AS (
        SELECT sum(i.price) AS item_total, sum(i.freight_value) AS freight_total FROM order_items i JOIN orders o USING(order_id)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'), p AS (
        SELECT sum(p.payment_value) AS payment_total FROM order_payments p JOIN orders o USING(order_id)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01') SELECT * FROM i CROSS JOIN p""",
        "key_facts", ["item_total", "freight_total", "payment_total"], "不同明细粒度单独汇总，不承诺支付额一定等于商品加运费。")
    add("D", "2017 年有过下单的真实客户数、年内至少下单两次的客户数及年内复购率（百分数）是多少？所有状态均保留，分析复购时说明观察窗口。", """WITH c AS (
        SELECT c.customer_unique_id, count(*) AS n FROM orders o JOIN customers c USING(customer_id)
        WHERE o.order_purchase_timestamp >= '2017-01-01' AND o.order_purchase_timestamp < '2018-01-01' GROUP BY c.customer_unique_id)
        SELECT count(*) AS buyers, count(*) FILTER (WHERE n>=2) AS repeat_buyers,
        100.0*count(*) FILTER (WHERE n>=2)/nullif(count(*),0) AS repeat_pct FROM c""", "key_facts", ["buyers", "repeat_buyers", "repeat_pct"], "同人用唯一客户标识；年内复购不能当终身复购。")
    add("D", "2018 年 Q2 的订单总数、已评价订单数和评价记录数各是多少？分析用评价记录数当已评价订单数会怎样。", """SELECT count(*) AS orders,
        count(*) FILTER (WHERE EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id=o.order_id)) AS reviewed_orders,
        (SELECT count(*) FROM order_reviews r JOIN orders x USING(order_id) WHERE x.order_purchase_timestamp >= '2018-04-01' AND x.order_purchase_timestamp < '2018-07-01') AS review_rows
        FROM orders o WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'""", "key_facts", ["orders", "reviewed_orders", "review_rows"], "区分订单覆盖与一单多评，不把评价量直接视为满意人数。")
    add("D", "2018 年 Q2 的全部商品明细里，英文品类缺失的明细行数、对应商品金额及明细总行数是多少？说明内连接翻译表的损失。", """SELECT count(*) FILTER (WHERE t.product_category_name IS NULL) AS untranslated_items,
        coalesce(sum(i.price) FILTER (WHERE t.product_category_name IS NULL),0) AS untranslated_price,
        count(*) AS all_items FROM order_items i JOIN orders o USING(order_id) JOIN products p USING(product_id)
        LEFT JOIN product_category_name_translation t USING(product_category_name)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'""", "key_facts", ["untranslated_items", "untranslated_price", "all_items"], "未知品类保留；不能把未翻译解释成没有销售。")
    add("D", "2018 年 Q2 同时具有商品与支付记录的订单，正确商品总额、直接关联支付明细后的商品总额、被多算的金额各是多少？解释关联粒度。", """WITH base AS (
        SELECT i.order_id, i.price FROM order_items i JOIN orders o USING(order_id)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
        AND EXISTS (SELECT 1 FROM order_payments p WHERE p.order_id=i.order_id)), x AS (
        SELECT (SELECT sum(price) FROM base) AS correct_price,
        (SELECT sum(b.price) FROM base b JOIN order_payments p USING(order_id)) AS naive_price)
        SELECT *, naive_price-correct_price AS overcount FROM x""", "key_facts", ["correct_price", "naive_price", "overcount"], "同一订单集合进行反事实 JOIN 对比，避免缺支付订单混淆差值。")
    add("D", "2018 年 Q1、Q2 的取消订单数和取消率（百分数）各是多少？按购买日期分期，分母为全部订单；解释是否能据此断言取消原因。", """SELECT
        count(*) FILTER (WHERE order_purchase_timestamp < '2018-04-01' AND order_status='canceled') AS q1_canceled,
        count(*) FILTER (WHERE order_purchase_timestamp >= '2018-04-01' AND order_status='canceled') AS q2_canceled,
        100.0*count(*) FILTER (WHERE order_purchase_timestamp < '2018-04-01' AND order_status='canceled')/nullif(count(*) FILTER (WHERE order_purchase_timestamp < '2018-04-01'),0) AS q1_cancel_pct,
        100.0*count(*) FILTER (WHERE order_purchase_timestamp >= '2018-04-01' AND order_status='canceled')/nullif(count(*) FILTER (WHERE order_purchase_timestamp >= '2018-04-01'),0) AS q2_cancel_pct
        FROM orders WHERE order_purchase_timestamp >= '2018-01-01' AND order_purchase_timestamp < '2018-07-01'""", "key_facts", ["q1_canceled", "q2_canceled", "q1_cancel_pct", "q2_cancel_pct"], "状态是观测结果，不能推出库存、价格或物流的确定因果。")
    add("D", "2018 年 Q2 已送达订单，按卖家商品金额排序的前三名合计金额、全部卖家金额、前三名占比（百分数）是多少？分析集中度。并列按卖家 ID 升序。", """WITH s AS (
        SELECT i.seller_id, sum(i.price) AS amount FROM order_items i JOIN orders o USING(order_id)
        WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
        AND o.order_status='delivered' GROUP BY i.seller_id), x AS (
        SELECT (SELECT sum(amount) FROM (SELECT amount FROM s ORDER BY amount DESC,seller_id LIMIT 3) z) AS top3_amount,
        (SELECT sum(amount) FROM s) AS all_amount)
        SELECT *,100.0*top3_amount/nullif(all_amount,0) AS top3_pct FROM x""", "key_facts", ["top3_amount", "all_amount", "top3_pct"], "集中度描述而非风险因果；范围仅为已送达商品金额。")
    return result
