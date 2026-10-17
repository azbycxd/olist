# Olist 数据画像

本文件由 `scripts/profile_data.py` 连接业务库、执行只读 SQL 生成；不是评测结果。
生成时间（UTC）：2026-10-17T06:21:11.117184+00:00

数据版本（源文件清单的 SHA-256）：`b258864763600cc722bc17f9962a617e97bf856bbda2a5e8e400e7490bdb663a`

画像来源证据：[profile_data_20261017T062110Z_0ed39854.summary.json](../evidence/profile_data_20261017T062110Z_0ed39854.summary.json)；原始运行日志：`profile_data_20261017T062110Z_0ed39854.jsonl`

导入来源证据：[load_olist_20261017T062107Z_88a9c380.summary.json](../evidence/load_olist_20261017T062107Z_88a9c380.summary.json)；原始运行日志：`load_olist_20261017T062107Z_88a9c380.jsonl`

## 原始文件与入库行数

| table | file | rows | sha256 |
| --- | --- | --- | --- |
| orders | olist_orders_dataset.csv | 99441 | 8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf |
| sellers | olist_sellers_dataset.csv | 3095 | 1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e |
| products | olist_products_dataset.csv | 32951 | 3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc |
| customers | olist_customers_dataset.csv | 99441 | 983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2 |
| geolocation | olist_geolocation_dataset.csv | 1000163 | b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6 |
| order_items | olist_order_items_dataset.csv | 112650 | 0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279 |
| order_reviews | olist_order_reviews_dataset.csv | 99224 | 012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7 |
| order_payments | olist_order_payments_dataset.csv | 103886 | 4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0 |
| product_category_name_translation | product_category_name_translation.csv | 71 | a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278 |

## 订单时间范围

| orders | first_purchase | last_purchase |
| --- | --- | --- |
| 99441 | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 |

<details><summary>来源 SQL</summary>

```sql
SELECT count(*) AS orders,
        min(order_purchase_timestamp) AS first_purchase,
        max(order_purchase_timestamp) AS last_purchase FROM orders
```

</details>

## 每月订单数

| month | orders | first_observed_day | last_observed_day |
| --- | --- | --- | --- |
| 2016-09 | 4 | 2016-09-04 | 2016-09-15 |
| 2016-10 | 324 | 2016-10-02 | 2016-10-22 |
| 2016-11 | 0 | NULL | NULL |
| 2016-12 | 1 | 2016-12-23 | 2016-12-23 |
| 2017-01 | 800 | 2017-01-05 | 2017-01-31 |
| 2017-02 | 1780 | 2017-02-01 | 2017-02-28 |
| 2017-03 | 2682 | 2017-03-01 | 2017-03-31 |
| 2017-04 | 2404 | 2017-04-01 | 2017-04-30 |
| 2017-05 | 3700 | 2017-05-01 | 2017-05-31 |
| 2017-06 | 3245 | 2017-06-01 | 2017-06-30 |
| 2017-07 | 4026 | 2017-07-01 | 2017-07-31 |
| 2017-08 | 4331 | 2017-08-01 | 2017-08-31 |
| 2017-09 | 4285 | 2017-09-01 | 2017-09-30 |
| 2017-10 | 4631 | 2017-10-01 | 2017-10-31 |
| 2017-11 | 7544 | 2017-11-01 | 2017-11-30 |
| 2017-12 | 5673 | 2017-12-01 | 2017-12-31 |
| 2018-01 | 7269 | 2018-01-01 | 2018-01-31 |
| 2018-02 | 6728 | 2018-02-01 | 2018-02-28 |
| 2018-03 | 7211 | 2018-03-01 | 2018-03-31 |
| 2018-04 | 6939 | 2018-04-01 | 2018-04-30 |
| 2018-05 | 6873 | 2018-05-01 | 2018-05-31 |
| 2018-06 | 6167 | 2018-06-01 | 2018-06-30 |
| 2018-07 | 6292 | 2018-07-01 | 2018-07-31 |
| 2018-08 | 6512 | 2018-08-01 | 2018-08-31 |
| 2018-09 | 16 | 2018-09-03 | 2018-09-29 |
| 2018-10 | 4 | 2018-10-01 | 2018-10-17 |

<details><summary>来源 SQL</summary>

```sql
WITH months AS (
        SELECT generate_series(date_trunc('month', min(order_purchase_timestamp)),
            date_trunc('month', max(order_purchase_timestamp)), interval '1 month') AS month
        FROM orders)
        SELECT to_char(m.month, 'YYYY-MM') AS month, count(o.order_id) AS orders,
            min(o.order_purchase_timestamp)::date AS first_observed_day,
            max(o.order_purchase_timestamp)::date AS last_observed_day
        FROM months m LEFT JOIN orders o
          ON o.order_purchase_timestamp >= m.month
         AND o.order_purchase_timestamp < m.month + interval '1 month'
        GROUP BY m.month ORDER BY m.month
```

</details>

## 订单状态分布

| order_status | orders |
| --- | --- |
| delivered | 96478 |
| shipped | 1107 |
| canceled | 625 |
| unavailable | 609 |
| invoiced | 314 |
| processing | 301 |
| created | 5 |
| approved | 2 |

<details><summary>来源 SQL</summary>

```sql
SELECT order_status, count(*) AS orders
        FROM orders GROUP BY order_status ORDER BY orders DESC, order_status
```

</details>

## 客户标识与复购

| customer_ids | unique_customers | id_difference | customers_with_multiple_ids |
| --- | --- | --- | --- |
| 99441 | 96096 | 3345 | 2997 |

<details><summary>来源 SQL</summary>

```sql
SELECT count(*) AS customer_ids,
        count(DISTINCT customer_unique_id) AS unique_customers,
        count(*) - count(DISTINCT customer_unique_id) AS id_difference,
        (SELECT count(*) FROM (SELECT customer_unique_id FROM customers
         GROUP BY customer_unique_id HAVING count(*) > 1) c) AS customers_with_multiple_ids
        FROM customers
```

</details>

## 品类翻译覆盖率

| products | products_with_category | products_missing_category | translated_products | observed_categories | translated_categories | category_coverage_pct | named_product_coverage_pct | all_product_coverage_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32951 | 32341 | 610 | 32328 | 73 | 71 | 97.2603 | 99.9598 | 98.1093 |

<details><summary>来源 SQL</summary>

```sql
SELECT count(*) AS products,
        count(p.product_category_name) AS products_with_category,
        count(*) FILTER (WHERE p.product_category_name IS NULL) AS products_missing_category,
        count(t.product_category_name) AS translated_products,
        count(DISTINCT p.product_category_name) AS observed_categories,
        count(DISTINCT t.product_category_name) AS translated_categories,
        round(100.0 * count(DISTINCT t.product_category_name) /
          nullif(count(DISTINCT p.product_category_name), 0), 4) AS category_coverage_pct,
        round(100.0 * count(t.product_category_name) /
          nullif(count(p.product_category_name), 0), 4) AS named_product_coverage_pct,
        round(100.0 * count(t.product_category_name) / nullif(count(*), 0), 4) AS all_product_coverage_pct
        FROM products p LEFT JOIN product_category_name_translation t USING (product_category_name)
```

</details>

## 未翻译的非空品类

| product_category_name | products |
| --- | --- |
| pc_gamer | 3 |
| portateis_cozinha_e_preparadores_de_alimentos | 10 |

<details><summary>来源 SQL</summary>

```sql
SELECT p.product_category_name, count(*) AS products
        FROM products p LEFT JOIN product_category_name_translation t USING (product_category_name)
        WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL
        GROUP BY p.product_category_name ORDER BY p.product_category_name
```

</details>

## 子表粒度与订单缺失关联

| multi_item_orders | multi_payment_orders | multi_review_orders | orders_without_items | orders_without_payments | orders_without_reviews |
| --- | --- | --- | --- | --- | --- |
| 9803 | 2961 | 547 | 775 | 1 | 768 |

<details><summary>来源 SQL</summary>

```sql
SELECT
        (SELECT count(*) FROM (SELECT order_id FROM order_items GROUP BY order_id HAVING count(*) > 1) i) AS multi_item_orders,
        (SELECT count(*) FROM (SELECT order_id FROM order_payments GROUP BY order_id HAVING count(*) > 1) p) AS multi_payment_orders,
        (SELECT count(*) FROM (SELECT order_id FROM order_reviews GROUP BY order_id HAVING count(*) > 1) r) AS multi_review_orders,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)) AS orders_without_items,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM order_payments p WHERE p.order_id = o.order_id)) AS orders_without_payments,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id = o.order_id)) AS orders_without_reviews
        FROM orders o
```

</details>

## 金额口径与关联膨胀

| item_price_total | freight_total | payment_total | naive_join_item_price_total | canceled_unavailable_item_price |
| --- | --- | --- | --- | --- |
| 13591643.70 | 2251909.54 | 16008872.12 | 14209115.34 | 97242.96 |

<details><summary>来源 SQL</summary>

```sql
SELECT
        (SELECT sum(price) FROM order_items) AS item_price_total,
        (SELECT sum(freight_value) FROM order_items) AS freight_total,
        (SELECT sum(payment_value) FROM order_payments) AS payment_total,
        (SELECT sum(i.price) FROM order_items i JOIN order_payments p USING (order_id)) AS naive_join_item_price_total,
        (SELECT sum(i.price) FROM order_items i JOIN orders o USING (order_id)
         WHERE o.order_status IN ('canceled', 'unavailable')) AS canceled_unavailable_item_price
```

</details>

## 交付时间缺失

| order_status | orders | missing_customer_delivery | missing_carrier_delivery | missing_approval |
| --- | --- | --- | --- | --- |
| approved | 2 | 2 | 2 | 0 |
| canceled | 625 | 619 | 550 | 141 |
| created | 5 | 5 | 5 | 5 |
| delivered | 96478 | 8 | 2 | 14 |
| invoiced | 314 | 314 | 314 | 0 |
| processing | 301 | 301 | 301 | 0 |
| shipped | 1107 | 1107 | 0 | 0 |
| unavailable | 609 | 609 | 609 | 0 |

<details><summary>来源 SQL</summary>

```sql
SELECT order_status, count(*) AS orders,
        count(*) FILTER (WHERE order_delivered_customer_date IS NULL) AS missing_customer_delivery,
        count(*) FILTER (WHERE order_delivered_carrier_date IS NULL) AS missing_carrier_delivery,
        count(*) FILTER (WHERE order_approved_at IS NULL) AS missing_approval
        FROM orders GROUP BY order_status ORDER BY order_status
```

</details>

## 评价与地理位置键

| reviews | distinct_review_ids | reviews_without_text | geolocation_rows | distinct_zip_prefixes |
| --- | --- | --- | --- | --- |
| 99224 | 98410 | 58247 | 1000163 | 19015 |

<details><summary>来源 SQL</summary>

```sql
SELECT
        (SELECT count(*) FROM order_reviews) AS reviews,
        (SELECT count(DISTINCT review_id) FROM order_reviews) AS distinct_review_ids,
        (SELECT count(*) FROM order_reviews WHERE review_comment_message IS NULL) AS reviews_without_text,
        (SELECT count(*) FROM geolocation) AS geolocation_rows,
        (SELECT count(DISTINCT geolocation_zip_code_prefix) FROM geolocation) AS distinct_zip_prefixes
```

</details>

## 分析约束

- 复购应先明确客户标识；`customer_id` 是订单关联标识，跨订单识别客户要使用 `customer_unique_id`。
- 每月表包含没有订单的月份。首尾月份及稀疏月份需要审查后再做环比；观察到的日期边界不能证明采集完整性。
- 商品金额、运费、支付金额分别列出。GMV 是否排除取消／不可用订单属于业务口径选择，数据本身不能替代定义。
- 商品、支付、评价子表均可能每订单多行。先聚合到订单粒度再关联，避免金额重复累加；参见关联膨胀查询。
- 品类覆盖率分别按非空品类数、非空品类商品数和全部商品数计算；缺少翻译的商品通过 LEFT JOIN 保留。
- 交付耗时应使用实际交付时间并说明空值处理；预计交付时间不代表实际交付。
- 邮编不能作为地理位置的唯一键；直接与其关联可能放大订单或客户数。
- review_id 不能单独作主键；评价数、评价文本数与订单数需要分别统计。
- 时间字段保留源数据的无时区 timestamp 语义，不能未经依据换算为 UTC。
