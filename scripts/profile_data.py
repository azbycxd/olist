"""Generate a data profile from live SELECT queries, with a JSONL audit log."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg.rows import dict_row

from config import ROOT, db_kwargs
from scripts.common import record, start_log
from scripts.evidence import publish_log

QUERIES = {
    "订单时间范围": """SELECT count(*) AS orders,
        min(order_purchase_timestamp) AS first_purchase,
        max(order_purchase_timestamp) AS last_purchase FROM orders""",
    "每月订单数": """WITH months AS (
        SELECT generate_series(date_trunc('month', min(order_purchase_timestamp)),
            date_trunc('month', max(order_purchase_timestamp)), interval '1 month') AS month
        FROM orders)
        SELECT to_char(m.month, 'YYYY-MM') AS month, count(o.order_id) AS orders,
            min(o.order_purchase_timestamp)::date AS first_observed_day,
            max(o.order_purchase_timestamp)::date AS last_observed_day
        FROM months m LEFT JOIN orders o
          ON o.order_purchase_timestamp >= m.month
         AND o.order_purchase_timestamp < m.month + interval '1 month'
        GROUP BY m.month ORDER BY m.month""",
    "订单状态分布": """SELECT order_status, count(*) AS orders
        FROM orders GROUP BY order_status ORDER BY orders DESC, order_status""",
    "客户标识与复购": """SELECT count(*) AS customer_ids,
        count(DISTINCT customer_unique_id) AS unique_customers,
        count(*) - count(DISTINCT customer_unique_id) AS id_difference,
        (SELECT count(*) FROM (SELECT customer_unique_id FROM customers
         GROUP BY customer_unique_id HAVING count(*) > 1) c) AS customers_with_multiple_ids
        FROM customers""",
    "品类翻译覆盖率": """SELECT count(*) AS products,
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
        FROM products p LEFT JOIN product_category_name_translation t USING (product_category_name)""",
    "未翻译的非空品类": """SELECT p.product_category_name, count(*) AS products
        FROM products p LEFT JOIN product_category_name_translation t USING (product_category_name)
        WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL
        GROUP BY p.product_category_name ORDER BY p.product_category_name""",
    "子表粒度与订单缺失关联": """SELECT
        (SELECT count(*) FROM (SELECT order_id FROM order_items GROUP BY order_id HAVING count(*) > 1) i) AS multi_item_orders,
        (SELECT count(*) FROM (SELECT order_id FROM order_payments GROUP BY order_id HAVING count(*) > 1) p) AS multi_payment_orders,
        (SELECT count(*) FROM (SELECT order_id FROM order_reviews GROUP BY order_id HAVING count(*) > 1) r) AS multi_review_orders,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)) AS orders_without_items,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM order_payments p WHERE p.order_id = o.order_id)) AS orders_without_payments,
        count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM order_reviews r WHERE r.order_id = o.order_id)) AS orders_without_reviews
        FROM orders o""",
    "金额口径与关联膨胀": """SELECT
        (SELECT sum(price) FROM order_items) AS item_price_total,
        (SELECT sum(freight_value) FROM order_items) AS freight_total,
        (SELECT sum(payment_value) FROM order_payments) AS payment_total,
        (SELECT sum(i.price) FROM order_items i JOIN order_payments p USING (order_id)) AS naive_join_item_price_total,
        (SELECT sum(i.price) FROM order_items i JOIN orders o USING (order_id)
         WHERE o.order_status IN ('canceled', 'unavailable')) AS canceled_unavailable_item_price""",
    "交付时间缺失": """SELECT order_status, count(*) AS orders,
        count(*) FILTER (WHERE order_delivered_customer_date IS NULL) AS missing_customer_delivery,
        count(*) FILTER (WHERE order_delivered_carrier_date IS NULL) AS missing_carrier_delivery,
        count(*) FILTER (WHERE order_approved_at IS NULL) AS missing_approval
        FROM orders GROUP BY order_status ORDER BY order_status""",
    "评价与地理位置键": """SELECT
        (SELECT count(*) FROM order_reviews) AS reviews,
        (SELECT count(DISTINCT review_id) FROM order_reviews) AS distinct_review_ids,
        (SELECT count(*) FROM order_reviews WHERE review_comment_message IS NULL) AS reviews_without_text,
        (SELECT count(*) FROM geolocation) AS geolocation_rows,
        (SELECT count(DISTINCT geolocation_zip_code_prefix) FROM geolocation) AS distinct_zip_prefixes""",
}


def markdown_table(rows):
    if not rows:
        return "（查询未返回记录）\n"
    columns = list(rows[0])

    def cell(value):
        return "NULL" if value is None else str(value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    lines.extend("| " + " | ".join(cell(row[c]) for c in columns) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def generate(output: Path | None = None, import_log: str | None = None):
    logger, log_path = start_log("profile_data")
    output = output or ROOT / "docs" / "data_profile.md"
    try:
        with psycopg.connect(**db_kwargs(role="reader"), row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            source = conn.execute("SELECT data_version, manifest, imported_at FROM data_imports ORDER BY import_id DESC LIMIT 1").fetchone()
            if not source:
                raise ValueError("No completed CSV import found; run scripts/load_olist.py first")
            record(logger, "profile_source", **source, import_log=import_log)
            observations = {}
            for name, query in QUERIES.items():
                rows = conn.execute(query).fetchall()
                observations[name] = rows
                record(logger, "query_result", name=name, sql=query, rows=rows)
        receipt_name = log_path.stem + ".summary.json"
        text = ["# Olist 数据画像", "",
                "本文件由 `scripts/profile_data.py` 连接业务库、执行只读 SQL 生成；不是评测结果。",
                f"生成时间（UTC）：{datetime.now(timezone.utc).isoformat()}", "",
                f"数据版本（源文件清单的 SHA-256）：`{source['data_version']}`", "",
                f"画像来源证据：[{receipt_name}](../evidence/{receipt_name})；原始运行日志：`{log_path.name}`", ""]
        if import_log:
            receipt_name = Path(import_log).stem + ".summary.json"
            text += [f"导入来源证据：[{receipt_name}](../evidence/{receipt_name})；原始运行日志：`{import_log}`", ""]
        text += ["## 原始文件与入库行数", "",
                 markdown_table([{"table": t, **values} for t, values in source["manifest"].items()])]
        for name, rows in observations.items():
            text += [f"## {name}", "", markdown_table(rows), "<details><summary>来源 SQL</summary>", "",
                     "```sql", QUERIES[name].strip(), "```", "", "</details>", ""]
        text += ["## 分析约束", "",
                 "- 复购应先明确客户标识；`customer_id` 是订单关联标识，跨订单识别客户要使用 `customer_unique_id`。",
                 "- 每月表包含没有订单的月份。首尾月份及稀疏月份需要审查后再做环比；观察到的日期边界不能证明采集完整性。",
                 "- 商品金额、运费、支付金额分别列出。GMV 是否排除取消／不可用订单属于业务口径选择，数据本身不能替代定义。",
                 "- 商品、支付、评价子表均可能每订单多行。先聚合到订单粒度再关联，避免金额重复累加；参见关联膨胀查询。",
                 "- 品类覆盖率分别按非空品类数、非空品类商品数和全部商品数计算；缺少翻译的商品通过 LEFT JOIN 保留。",
                 "- 交付耗时应使用实际交付时间并说明空值处理；预计交付时间不代表实际交付。",
                 "- 邮编不能作为地理位置的唯一键；直接与其关联可能放大订单或客户数。",
                 "- review_id 不能单独作主键；评价数、评价文本数与订单数需要分别统计。",
                 "- 时间字段保留源数据的无时区 timestamp 语义，不能未经依据换算为 UTC。", ""]
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".md.tmp")
        temporary.write_text("\n".join(text), encoding="utf-8")
        temporary.replace(output)
        record(logger, "profile_written", output=str(output))
        publish_log(log_path)
        return output
    except Exception as exc:
        record(logger, "failed", error=str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "data_profile.md")
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
