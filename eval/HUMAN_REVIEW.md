# 标准答案自动交叉验证

按用户要求，用独立 pandas 计算替代 C、E 模板和 D 类 gold SQL 的人工核对。
原始 CSV 直接读取；不执行 SQL、不连接数据库、不导入 SQL 模板或评分实现。数值相对误差不超过 1% 视为一致，列表比较集合，关键事实逐字段比较。

证据：[cross_check_20261017T070428Z_accb136c.summary.json](../evidence/cross_check_20261017T070428Z_accb136c.summary.json)；原始日志：`cross_check_20261017T070428Z_accb136c.jsonl`。

不一致只列出，绝不自动修改 gold。计算一致性不代表归因语义或模型评分已经校准。

## C 类

| 题目 | 模板 | 交叉验证结果 | 差异 |
| --- | --- | --- | --- |
| C01 | C_unique_customer | 一致 |  |
| C02 | C_unique_customer | 一致 |  |
| C03 | C_unique_customer | 一致 |  |
| C04 | C_unique_customer | 一致 |  |
| C05 | C_gmv_status | 一致 |  |
| C06 | C_gmv_status | 一致 |  |
| C07 | C_gmv_status | 一致 |  |
| C08 | C_freight | 一致 |  |
| C09 | C_freight | 一致 |  |
| C10 | C_freight | 一致 |  |
| C11 | C_join_grain | 一致 |  |
| C12 | C_join_grain | 一致 |  |
| C13 | C_join_grain | 一致 |  |
| C14 | C_boundary_month | 一致 |  |
| C15 | C_boundary_month | 一致 |  |
| C16 | C_boundary_month | 一致 |  |
| C17 | C_category_coverage | 一致 |  |
| C18 | C_category_coverage | 一致 |  |
| C19 | C_category_coverage | 一致 |  |
| C20 | C_delivery_null | 一致 |  |
| C21 | C_delivery_null | 一致 |  |
| C22 | C_delivery_null | 一致 |  |
| C23 | C_review_grain | 一致 |  |
| C24 | C_review_grain | 一致 |  |
| C25 | C_review_grain | 一致 |  |

## E 类

| 题目 | 模板 | 交叉验证结果 | 差异 |
| --- | --- | --- | --- |
| E01 | E_sales_amount | 一致 |  |
| E02 | E_sales_amount | 一致 |  |
| E03 | E_customer_identity | 一致 |  |
| E04 | E_customer_identity | 一致 |  |
| E05 | E_order_status | 一致 |  |
| E06 | E_order_status | 一致 |  |
| E07 | E_geography | 一致 |  |
| E08 | E_geography | 一致 |  |
| E09 | E_delivery_duration | 一致 |  |
| E10 | E_delivery_duration | 一致 |  |

## D 类

| 题目 | 模板 | 交叉验证结果 | 差异 |
| --- | --- | --- | --- |
| D01 |  | 一致 |  |
| D02 |  | 一致 |  |
| D03 |  | 一致 |  |
| D04 |  | 一致 |  |
| D05 |  | 一致 |  |
| D06 |  | 一致 |  |
| D07 |  | 一致 |  |
| D08 |  | 一致 |  |
| D09 |  | 一致 |  |
| D10 |  | 一致 |  |
| D11 |  | 一致 |  |
| D12 |  | 一致 |  |

## A 类

| 题目 | 模板 | 交叉验证结果 | 差异 |
| --- | --- | --- | --- |
| A01 |  | 一致 |  |
| A02 |  | 一致 |  |
| A03 |  | 一致 |  |
| A04 |  | 一致 |  |
| A05 |  | 一致 |  |
| A06 |  | 一致 |  |
| A07 |  | 一致 |  |
| A08 |  | 一致 |  |
| A09 |  | 一致 |  |
| A10 |  | 一致 |  |

## B 类

| 题目 | 模板 | 交叉验证结果 | 差异 |
| --- | --- | --- | --- |
| B01 |  | 一致 |  |
| B02 |  | 一致 |  |
| B03 |  | 一致 |  |
| B04 |  | 一致 |  |
| B05 |  | 一致 |  |
| B06 |  | 一致 |  |
| B07 |  | 一致 |  |
| B08 |  | 一致 |  |
| B09 |  | 一致 |  |
| B10 |  | 一致 |  |

## 模型归因评分校准

尚未进行。CSV 交叉验证只校验标准答案的计算一致性，不替代真实 D 类报告的归因评分校准。
待真实报告和模型评分可用后，按同一 rubric 独立评分并保留 run_id、question_id、task_id、证据文件、分数和分歧说明；未运行不填分数。
