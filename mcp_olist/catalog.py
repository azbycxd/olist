"""Structural descriptions only; business metric rules belong to Step 4."""

TABLES = {
    "orders": "订单、状态和各阶段时间。",
    "customers": "订单关联的客户记录、客户标识与地区。",
    "order_items": "订单商品明细、卖家、商品价格与运费。",
    "order_payments": "订单的各笔支付记录。",
    "order_reviews": "订单评价、分数与原始评价文字。",
    "products": "商品属性和原始品类名称。",
    "sellers": "卖家与所在地区。",
    "geolocation": "邮编前缀、坐标和地区记录。",
    "product_category_name_translation": "葡文品类名与英文品类名对照。",
}
