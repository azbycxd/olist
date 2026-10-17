# 数据表业务含义

## table_orders orders 订单
每行一个 order_id，customer_id 关联客户；order_purchase_timestamp 为购买时间。order_status 是观测状态；approved、carrier、customer、estimated 时间分别为批准、交承运商、实际送达、预计送达。

## table_customers customers 客户
customer_id 关联一次订单客户记录；customer_unique_id 跨订单识别人。customer_state/city 是这条记录地址，zip_code_prefix 是前缀。

## table_items order_items 商品明细
order_id 与 order_item_id 定义订单内明细，product_id 和 seller_id 关联商品和卖家，price 为商品金额、freight_value 为运费。不是一单一行。

## table_payments order_payments 支付明细
order_id/payment_sequential 标识支付序列，payment_type 为方式，payment_installments 为期数，payment_value 为该流水金额。多条付款不能复制商品金额。

## table_reviews order_reviews 评价
order_id 关联订单，review_score 为评分，comment 文本可能为空，review_id 不作为无重复保证；一单可有多条记录。

## table_products products 商品
product_id 标识商品；product_category_name 为原始葡文品类，可能为空。重量和尺寸属于商品属性。

## table_translation product_category_name_translation 品类翻译
将葡文品类映射到英文 product_category_name_english。覆盖不完整，英文报表需要保留未知项。

## table_sellers sellers 卖家
seller_id 标识卖家，seller_state/city 为卖家地区；与客户地区不是同一分析维度。

## table_geolocation geolocation 地理样本
邮编前缀对应经纬度与城市州样本，不保证一前缀唯一。关联前应按场景聚合，避免金额膨胀。
