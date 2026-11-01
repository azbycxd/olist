# 历史原文证据扫描诊断

24条试验，仅复测当前checker的数字支持，不调用score，不改历史成绩。类型由本轮复核确认，原文从原收据直接复制。

| 试验 | 当前claim.text未支持数字 | 状态 |
|---|---:|---|
|step9-dev-final:C18|0|historical_false_positive_now_fixed|
|step9-dev-final:C23|0|historical_false_positive_now_fixed|
|step9-dev-final:D07|0|historical_false_positive_now_fixed|
|step9-dev-final:E10|1|false_positive_still_present|
|holdout-r1:A08|1|real_unsupported_still_detected|
|holdout-r1:A09|1|false_positive_still_present|
|holdout-r1:A10|0|historical_false_positive_now_fixed|
|holdout-r1:B10|0|historical_false_positive_now_fixed|
|holdout-r1:C13|0|historical_false_positive_now_fixed|
|holdout-r1:C22|0|historical_false_positive_now_fixed|
|holdout-r2:A08|1|real_unsupported_still_detected|
|holdout-r2:A09|1|false_positive_still_present|
|holdout-r2:A10|0|historical_false_positive_now_fixed|
|holdout-r2:B10|0|historical_false_positive_now_fixed|
|holdout-r2:C22|0|historical_false_positive_now_fixed|
|holdout-r3:A08|1|real_unsupported_still_detected|
|holdout-r3:A09|1|false_positive_still_present|
|holdout-r3:A10|0|historical_false_positive_now_fixed|
|holdout-r3:B10|0|historical_false_positive_now_fixed|
|holdout-r3:C13|0|historical_false_positive_now_fixed|
|holdout-r3:C22|0|historical_false_positive_now_fixed|
|step12-v2:E10|1|false_positive_still_present|
|slot-dev:D01|8|false_positive_still_present|
|slot-dev:D08|1|false_positive_still_present|

## step9-dev-final:C18

原始日志：`logs/eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl`；SHA-256：`efb4620ceee3d746e3c5eadf3315877f8c3506a9252bfc16c2360b6f2feb503a`。

```text
RJ 州 2018-01-01 至 2018-06-30（按购买时间，含 1 月 1 日、不含 7 月 1 日）英文品类报表中待归类（原始品类为空或无英文翻译）的商品明细行数为 65。
```

当前未支持数字：0。


## step9-dev-final:C23

原始日志：`logs/eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl`；SHA-256：`efb4620ceee3d746e3c5eadf3315877f8c3506a9252bfc16c2360b6f2feb503a`。

```text
MG 州客户在 2018-02-01 至 2018-02-28（按购买时间，含 2 月整月）下的订单中，获得评价的订单数为 796 单（按订单去重计数，一单多条评价只计一次）。
```

当前未支持数字：0。


## step9-dev-final:D07

原始日志：`logs/eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl`；SHA-256：`efb4620ceee3d746e3c5eadf3315877f8c3506a9252bfc16c2360b6f2feb503a`。

```text
2017 自然年内（保留所有订单状态）有过下单的真实客户数（customer_unique_id 去重）为 43,713 人
```

当前未支持数字：0。

```text
2017 年内下单至少两单的复购客户数为 1,256 人
```

当前未支持数字：0。

```text
2017 年内复购率为 2.8733%（复购客户数／同窗口全部下单客户数）
```

当前未支持数字：0。


## step9-dev-final:E10

原始日志：`logs/eval_step9-dev-final_20261017T102853Z_45a71d7d.jsonl`；SHA-256：`efb4620ceee3d746e3c5eadf3315877f8c3506a9252bfc16c2360b6f2feb503a`。

```text
按设定口径（仅 delivered 且实际送达时间非空，按购买到实际送达的秒数/86400 取平均），2018-04-01 至 2018-07-01（不含）购买区间内订单平均交付天数为 10.77030644457265900003 天，样本订单数 19643。
```

当前未支持数字：1。


## holdout-r1:A08

原始日志：`logs/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`；SHA-256：`22512c9322f5201b7fd5ad26213b399f193109309b02d8dcc5e5bdd8367fd387`。

```text
order_payments 中共有 5 种支付方式：boleto、credit_card、debit_card、not_defined、voucher。
```

当前未支持数字：1。


## holdout-r1:A09

原始日志：`logs/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`；SHA-256：`22512c9322f5201b7fd5ad26213b399f193109309b02d8dcc5e5bdd8367fd387`。

```text
order_reviews 表中 review_score = 1 的评价记录共 11424 条（按评价记录行计，非订单数）。
```

当前未支持数字：1。


## holdout-r1:A10

原始日志：`logs/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`；SHA-256：`22512c9322f5201b7fd5ad26213b399f193109309b02d8dcc5e5bdd8367fd387`。

```text
2018 年 5 月（order_purchase_timestamp 在 2018-05-01 至 2018-06-01 之间）的订单数为 6873 单，按订单表全部状态统计。
```

当前未支持数字：0。


## holdout-r1:B10

原始日志：`logs/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`；SHA-256：`22512c9322f5201b7fd5ad26213b399f193109309b02d8dcc5e5bdd8367fd387`。

```text
2018 年 1 月（order_purchase_timestamp 在 2018-01-01 至 2018-02-01 之前）购买的订单中，包含至少两个不同 product_id 的订单数为 264。
```

当前未支持数字：0。


## holdout-r1:C13

原始日志：`logs/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`；SHA-256：`22512c9322f5201b7fd5ad26213b399f193109309b02d8dcc5e5bdd8367fd387`。

```text
MG 州 2018-04-01 至 2018-06-30（按购买时间，含 6 月 30 日全天）内至少有一笔支付记录的订单，其商品销售额（order_items.price 之和，不含运费，保留全部订单状态）为 321126.96 巴西雷亚尔，涉及 2262 个订单。
```

当前未支持数字：0。


## holdout-r1:C22

原始日志：`logs/eval_step9-holdout-r1_20261017T104235Z_7648ab8d.jsonl`；SHA-256：`22512c9322f5201b7fd5ad26213b399f193109309b02d8dcc5e5bdd8367fd387`。

```text
SP 州 2018-01-01 至 2018-07-31（按购买时间，含 7 月 31 日全天）的订单中，状态为 delivered 但实际送达客户时间为空的待补签收记录共 6 笔。
```

当前未支持数字：0。


## holdout-r2:A08

原始日志：`logs/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl`；SHA-256：`9a268909bc8ae27ce9f6d7bf4e6238de8f813dd6cc66ac1a5c996544a56ff678`。

```text
订单支付表中出现的支付方式共 5 种：boleto、credit_card、debit_card、not_defined、voucher。
```

当前未支持数字：1。


## holdout-r2:A09

原始日志：`logs/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl`；SHA-256：`9a268909bc8ae27ce9f6d7bf4e6238de8f813dd6cc66ac1a5c996544a56ff678`。

```text
评价得分为 1 的评价记录共 11424 条（按评价记录行计数，非订单数）。
```

当前未支持数字：1。


## holdout-r2:A10

原始日志：`logs/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl`；SHA-256：`9a268909bc8ae27ce9f6d7bf4e6238de8f813dd6cc66ac1a5c996544a56ff678`。

```text
2018 年 5 月（order_purchase_timestamp 在 2018-05-01 至 2018-06-01 之前）下单的订单数为 6873 单，包含全部订单状态。
```

当前未支持数字：0。


## holdout-r2:B10

原始日志：`logs/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl`；SHA-256：`9a268909bc8ae27ce9f6d7bf4e6238de8f813dd6cc66ac1a5c996544a56ff678`。

```text
2018 年 1 月（order_purchase_timestamp 在 2018-01-01 至 2018-02-01 之前）购买的订单中，包含至少两个不同 product_id 的订单数为 264。
```

当前未支持数字：0。


## holdout-r2:C22

原始日志：`logs/eval_step9-holdout-r2_20261017T104451Z_7e1a9d1a.jsonl`；SHA-256：`9a268909bc8ae27ce9f6d7bf4e6238de8f813dd6cc66ac1a5c996544a56ff678`。

```text
SP 州 2018-01-01 至 2018-07-31（按购买时间，含 7 月 31 日全天）的订单中，状态为 delivered 但实际送达客户时间为空的待补签收记录共 6 笔。
```

当前未支持数字：0。


## holdout-r3:A08

原始日志：`logs/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`；SHA-256：`18782df1e380718ac05a72d6a7794b4166e3c6d675f04b255ee88802867d280c`。

```text
订单支付表中出现的支付方式共 5 种：boleto、credit_card、debit_card、not_defined、voucher。
```

当前未支持数字：1。


## holdout-r3:A09

原始日志：`logs/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`；SHA-256：`18782df1e380718ac05a72d6a7794b4166e3c6d675f04b255ee88802867d280c`。

```text
order_reviews 中 review_score = 1 的评价记录共 11424 条（按评价记录行计，非订单数）。
```

当前未支持数字：1。


## holdout-r3:A10

原始日志：`logs/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`；SHA-256：`18782df1e380718ac05a72d6a7794b4166e3c6d675f04b255ee88802867d280c`。

```text
2018 年 5 月（order_purchase_timestamp 在 2018-05-01 至 2018-06-01 之前）下单的订单数为 6873 单，统计口径为 orders 表全部订单状态。
```

当前未支持数字：0。


## holdout-r3:B10

原始日志：`logs/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`；SHA-256：`18782df1e380718ac05a72d6a7794b4166e3c6d675f04b255ee88802867d280c`。

```text
2018 年 1 月（order_purchase_timestamp 在 2018-01-01 至 2018-02-01 之前）购买的订单中，包含至少两个不同 product_id 的订单数为 264。
```

当前未支持数字：0。


## holdout-r3:C13

原始日志：`logs/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`；SHA-256：`18782df1e380718ac05a72d6a7794b4166e3c6d675f04b255ee88802867d280c`。

```text
MG 州 2018-04-01 至 2018-06-30（按购买时间，含 6 月 30 日全天）且至少有一条支付记录的订单，商品销售额（order_items.price 之和，不含运费，保留全部订单状态）为 321126.96 巴西雷亚尔，涉及 2262 个订单。
```

当前未支持数字：0。


## holdout-r3:C22

原始日志：`logs/eval_step9-holdout-r3_20261017T104707Z_e9d273ef.jsonl`；SHA-256：`18782df1e380718ac05a72d6a7794b4166e3c6d675f04b255ee88802867d280c`。

```text
SP 州 2018-01-01 至 2018-07-31（按购买时间，含 7 月 31 日全天）的订单中，状态为 delivered 但 order_delivered_customer_date 为空的待补签收记录共 6 笔。
```

当前未支持数字：0。


## step12-v2:E10

原始日志：`logs/eval_step12-regression-v2-once_20261028T011034Z_c949fe88.jsonl`；SHA-256：`83cd407ae5f2cdfcaf6bc1bc5216f9b7aaddeea8da48a29c4adacafc238d63b1`。

```text
按设定口径（仅 delivered 且实际送达时间非空，按购买到实际送达的秒数/86400 求平均），2018-04-01 至 2018-07-01（不含）购买区间内订单平均交付天数为 10.77030644457265900003 天，样本订单数 19643。
```

当前未支持数字：1。


## slot-dev:D01

原始日志：`logs/eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl`；SHA-256：`559543714a676646ca221880570cf6c0e523db38b6efddb973f6595fe120baba`。

```text
2018 年 Q1（1/1–3/31）GMV 为 2,764,402.78，Q2（4/1–6/30）为 2,849,730.26，环比变化率 +3.09%（已排除 canceled 与 unavailable 订单，仅计商品价格不含运费）。
```

当前未支持数字：8。


## slot-dev:D08

原始日志：`logs/eval_step12-slot-once_20261028T045020Z_5df1fb4e.jsonl`；SHA-256：`559543714a676646ca221880570cf6c0e523db38b6efddb973f6595fe120baba`。

```text
2018 Q2 订单总数 19,979 单（全部状态，按下单时间半开区间）
```

当前未支持数字：0。

```text
2018 Q2 已评价订单数（按 order_id 去重）19,863 单，评价覆盖率 99.42%
```

当前未支持数字：0。

```text
2018 Q2 评价记录数 19,889 行，比已评价订单数多 26，相当于已评价订单数的 100.13%
```

当前未支持数字：0。

```text
多评价订单分布：26 个订单各有 2 条评价，单订单最多 2 条，无 3 条及以上
```

当前未支持数字：1。
