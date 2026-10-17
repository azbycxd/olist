"""Independent pandas oracle over raw CSVs; no database or SQL execution/imports.

SQL answers must already exist in a validate_gold.py receipt. The pandas
calculators use only question IDs, template IDs and parameters, never SQL text.
"""

import argparse
import hashlib
import json
import math
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from scripts.common import record, start_log
from scripts.evidence import publish_log

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "orders":("olist_orders_dataset.csv", ["order_id","customer_id","order_status","order_purchase_timestamp",
              "order_delivered_customer_date","order_estimated_delivery_date"]),
    "customers":("olist_customers_dataset.csv", ["customer_id","customer_unique_id","customer_state"]),
    "order_items":("olist_order_items_dataset.csv", ["order_id","order_item_id","product_id","seller_id","price","freight_value"]),
    "order_payments":("olist_order_payments_dataset.csv", ["order_id","payment_value"]),
    "order_reviews":("olist_order_reviews_dataset.csv", ["order_id","review_score"]),
    "products":("olist_products_dataset.csv", ["product_id","product_category_name"]),
    "sellers":("olist_sellers_dataset.csv", ["seller_id"]),
    "geolocation":("olist_geolocation_dataset.csv", ["geolocation_zip_code_prefix"]),
    "product_category_name_translation":("product_category_name_translation.csv",
                                           ["product_category_name","product_category_name_english"]),
}
# payment_type is needed for the A08 list, but never for a business SQL join.
FILES["order_payments"][1].append("payment_type")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class RawAnswers:
    def __init__(self, directory):
        self.frames, self.manifest = {}, {}
        for name,(filename,columns) in FILES.items():
            path = directory/filename
            checksum = digest(path)
            frame = pd.read_csv(path, usecols=columns, dtype=str, keep_default_na=False, na_values=[""])
            self.frames[name] = frame
            self.manifest[name] = {"file":filename,"sha256":checksum,"rows":len(frame)}
        self.directory = directory
        self.version = hashlib.sha256(json.dumps(self.manifest,sort_keys=True).encode()).hexdigest()
        self.o, self.i, self.p, self.r = [self.frames[n].copy() for n in ("orders","order_items","order_payments","order_reviews")]
        for name in ("order_purchase_timestamp","order_delivered_customer_date","order_estimated_delivery_date"):
            self.o[name] = pd.to_datetime(self.o[name])
        for frame,columns in ((self.i,["price","freight_value"]),(self.p,["payment_value"]),(self.r,["review_score"])):
            for column in columns:
                frame[column] = pd.to_numeric(frame[column],errors="raise")
        customers = self.frames["customers"].set_index("customer_id")
        self.o["buyer"] = self.o.customer_id.map(customers.customer_unique_id)
        self.o["state"] = self.o.customer_id.map(customers.customer_state)
        self.i["state"] = self.i.order_id.map(self.o.set_index("order_id").state)
        self.i["category"] = self.i.product_id.map(self.frames["products"].set_index("product_id").product_category_name)
        translation = self.frames["product_category_name_translation"].set_index("product_category_name").product_category_name_english
        self.i["english"] = self.i.category.map(translation)

    def verify_unchanged(self):
        for source in self.manifest.values():
            if digest(self.directory/source["file"]) != source["sha256"]:
                raise ValueError("CSV changed while cross-checking: "+source["file"])

    def orders(self, start=None, end=None, state=None, delivered=False, valid_gmv=False):
        frame = self.o
        if start:
            frame = frame[(frame.order_purchase_timestamp >= start) & (frame.order_purchase_timestamp < end)]
        if state:
            frame = frame[frame.state == state]
        if delivered:
            frame = frame[frame.order_status == "delivered"]
        if valid_gmv:
            frame = frame[~frame.order_status.isin(["canceled","unavailable"])]
        return frame

    def items(self, orders):
        return self.i[self.i.order_id.isin(orders.order_id)]

    @staticmethod
    def delivery_days(orders):
        complete = orders[(orders.order_status == "delivered") & orders.order_delivered_customer_date.notna()]
        return (complete.order_delivered_customer_date-complete.order_purchase_timestamp).dt.total_seconds().mean()/86400

    @staticmethod
    def leaders(items, group):
        return items.groupby(group).price.sum().rename("amount").reset_index().sort_values(["amount",group],ascending=[False,True])

    def calculate(self, q):
        ident, template, params = q["id"], q.get("template_id"), q.get("parameters",{})
        if template:
            orders = self.orders(params["start"],params["end"],
                                 params.get("state") if template != "C_boundary_month" else None)
            items = self.items(orders)
            if template in {"C_unique_customer","E_customer_identity"}:
                return orders.buyer.nunique()
            if template == "C_gmv_status":
                return self.items(orders[~orders.order_status.isin(["canceled","unavailable"])]).price.sum()
            if template in {"C_freight","E_sales_amount"}:
                return items.price.sum()
            if template == "C_join_grain":
                return items[items.order_id.isin(self.p.order_id)].price.sum()
            if template == "C_boundary_month":
                return orders.order_purchase_timestamp.dt.normalize().nunique()
            if template == "C_category_coverage":
                return items.english.isna().sum()
            if template == "C_delivery_null":
                return ((orders.order_status == "delivered") & orders.order_delivered_customer_date.isna()).sum()
            if template == "C_review_grain":
                return orders.order_id.isin(self.r.order_id).sum()
            if template == "E_order_status":
                return (orders.order_status == "delivered").sum()
            if template == "E_geography":
                return (orders.state == "SP").sum()
            if template == "E_delivery_duration":
                return self.delivery_days(orders)
            raise ValueError("No independent calculator for "+template)

        if ident == "A01": return len(self.o)
        if ident == "A02": return (self.o.order_status == "delivered").sum()
        if ident == "A03": return len(self.frames["products"])
        if ident == "A04": return len(self.frames["sellers"])
        if ident == "A05": return sorted(self.o.order_status.unique().tolist())
        if ident == "A06": return len(self.orders("2017-11-01","2017-12-01"))
        if ident == "A07": return self.i.freight_value.sum()
        if ident == "A08": return sorted(self.p.payment_type.unique().tolist())
        if ident == "A09": return (self.r.review_score == 1).sum()
        if ident == "A10": return len(self.orders("2018-05-01","2018-06-01"))
        if ident == "B01": return (self.o.state == "SP").sum()
        if ident == "B02": return self.i.loc[self.i.english == "health_beauty","price"].sum()
        if ident == "B03": return self.p.loc[self.p.order_id.isin(self.orders("2018-01-01","2018-04-01").order_id),"payment_value"].sum()
        if ident == "B04": return self.i.loc[self.i.state == "RJ","seller_id"].nunique()
        if ident == "B05": return self.orders("2017-01-01","2018-01-01").order_id.isin(self.r.order_id).sum()
        if ident == "B06": return self.leaders(self.i,"state").state.head(5).tolist()
        if ident == "B07": return (self.i.english == "computers_accessories").sum()
        if ident == "B08": return self.i.loc[self.i.state == "MG","freight_value"].sum()
        if ident == "B09": return self.leaders(self.items(self.orders("2018-04-01","2018-07-01")),"seller_id").seller_id.head(3).tolist()
        if ident == "B10": return (self.items(self.orders("2018-01-01","2018-02-01")).groupby("order_id").product_id.nunique() >= 2).sum()

        q1, q2 = self.orders("2018-01-01","2018-04-01"), self.orders("2018-04-01","2018-07-01")
        if ident in {"D01","D02"}:
            first, second = [self.items(o[~o.order_status.isin(["canceled","unavailable"])]) for o in (q1,q2)]
            if ident == "D01":
                a,b = first.price.sum(),second.price.sum()
                return {"q1_gmv":a,"q2_gmv":b,"change_pct":100*(b/a-1)}
            amounts = pd.concat([first.groupby("category").price.sum().rename("q1"),
                                 second.groupby("category").price.sum().rename("q2")],axis=1,join="inner")
            drops = amounts[amounts.q1 > amounts.q2].copy()
            drops["drop"] = drops.q1-drops.q2
            leader = drops.reset_index().sort_values(["drop","category"],ascending=[False,True]).iloc[0]
            return {"declining_categories":len(drops),"largest_drop_category":leader.category,"largest_drop_amount":leader["drop"]}
        if ident == "D03":
            result = {}
            for state in ("SP","RJ"):
                subset = q2[q2.state == state]
                result[state.lower()+"_buyers"] = subset.buyer.nunique()
                result[state.lower()+"_gmv"] = self.items(subset[~subset.order_status.isin(["canceled","unavailable"])]).price.sum()
            return result
        if ident == "D04":
            a,b = self.delivery_days(q1),self.delivery_days(q2)
            return {"q1_days":a,"q2_days":b,"change_days":b-a}
        if ident == "D05":
            complete = q2[(q2.order_status == "delivered") & q2.order_delivered_customer_date.notna()]
            late = (complete.order_delivered_customer_date > complete.order_estimated_delivery_date).sum()
            return {"late_orders":late,"measured_orders":len(complete),"late_pct":100*late/len(complete)}
        if ident == "D06":
            items = self.items(q2)
            return {"item_total":items.price.sum(),"freight_total":items.freight_value.sum(),
                    "payment_total":self.p.loc[self.p.order_id.isin(q2.order_id),"payment_value"].sum()}
        if ident == "D07":
            frequency = self.orders("2017-01-01","2018-01-01").groupby("buyer").size()
            repeats = (frequency >= 2).sum()
            return {"buyers":len(frequency),"repeat_buyers":repeats,"repeat_pct":100*repeats/len(frequency)}
        if ident == "D08":
            return {"orders":len(q2),"reviewed_orders":q2.order_id.isin(self.r.order_id).sum(),
                    "review_rows":self.r.order_id.isin(q2.order_id).sum()}
        if ident == "D09":
            items = self.items(q2)
            missing = items[items.english.isna()]
            return {"untranslated_items":len(missing),"untranslated_price":missing.price.sum(),"all_items":len(items)}
        if ident == "D10":
            frequency = self.p.groupby("order_id").size()
            items = self.items(q2)
            items = items[items.order_id.isin(frequency.index)]
            correct = items.price.sum()
            inflated = (items.price*items.order_id.map(frequency)).sum()
            return {"correct_price":correct,"naive_price":inflated,"overcount":inflated-correct}
        if ident == "D11":
            a,b = (q1.order_status == "canceled").sum(),(q2.order_status == "canceled").sum()
            return {"q1_canceled":a,"q2_canceled":b,"q1_cancel_pct":100*a/len(q1),"q2_cancel_pct":100*b/len(q2)}
        if ident == "D12":
            amounts = self.leaders(self.items(q2[q2.order_status == "delivered"]),"seller_id").amount
            top,total = amounts.head(3).sum(),amounts.sum()
            return {"top3_amount":top,"all_amount":total,"top3_pct":100*top/total}
        raise ValueError("No independent calculator for "+ident)


def plain(value):
    if isinstance(value,dict): return {k:plain(v) for k,v in value.items()}
    if isinstance(value,list): return [plain(v) for v in value]
    if hasattr(value,"item"): value = value.item()
    if isinstance(value,float) and not math.isfinite(value):
        raise ValueError("Independent calculation returned a nonfinite answer")
    return value


def differences(actual, expected, path="answer"):
    if isinstance(actual,dict) and isinstance(expected,dict):
        if set(actual) != set(expected): return [{"path":path,"reason":"different_fields"}]
        return [d for key in expected for d in differences(actual[key],expected[key],path+"."+key)]
    if isinstance(actual,list) and isinstance(expected,list):
        return [] if {json.dumps(v,sort_keys=True) for v in actual} == {json.dumps(v,sort_keys=True) for v in expected} else [{"path":path,"reason":"different_set"}]
    if actual is not None and expected is not None and not isinstance(actual,bool) and not isinstance(expected,bool):
        try:
            a,b = Decimal(str(actual)),Decimal(str(expected))
            if a.is_finite() and b.is_finite():
                error = abs(a-b)
                if error <= (abs(b)*Decimal("0.01") if b else Decimal("0.00000001")):
                    return []
                return [{"path":path,"reason":"numeric_difference","absolute_difference":str(error),
                         "relative_difference":str(error/abs(b)) if b else None}]
        except InvalidOperation:
            pass
    return [] if type(actual) is type(expected) and actual == expected else [{"path":path,"reason":"different_value"}]


def update_review(questions, comparisons, receipt, source_log):
    by_id = {r["question_id"]:r for r in comparisons}
    lines = ["# 标准答案自动交叉验证", "", "按用户要求，用独立 pandas 计算替代 C、E 模板和 D 类 gold SQL 的人工核对。",
             "原始 CSV 直接读取；不执行 SQL、不连接数据库、不导入 SQL 模板或评分实现。数值相对误差不超过 1% 视为一致，列表比较集合，关键事实逐字段比较。",
             "", f"证据：[{receipt.name}](../evidence/{receipt.name})；原始日志：`{source_log}`。", "",
             "不一致只列出，绝不自动修改 gold。计算一致性不代表归因语义或模型评分已经校准。", ""]
    for category in ("C","E","D","A","B"):
        lines += [f"## {category} 类", "", "| 题目 | 模板 | 交叉验证结果 | 差异 |", "| --- | --- | --- | --- |"]
        for q in questions:
            if q["id"][0] != category: continue
            row = by_id[q["id"]]
            detail = row.get("error") or "; ".join(d["path"]+": "+d["reason"] for d in row["differences"])
            lines.append(f"| {q['id']} | {q.get('template_id') or ''} | {'一致' if row['matched'] else '不一致'} | {detail} |")
        lines.append("")
    lines += ["## 模型归因评分校准", "",
              "尚未进行。CSV 交叉验证只校验标准答案的计算一致性，不替代真实 D 类报告的归因评分校准。",
              "待真实报告和模型评分可用后，按同一 rubric 独立评分并保留 run_id、question_id、task_id、证据文件、分数和分歧说明；未运行不填分数。", ""]
    (ROOT/"eval/HUMAN_REVIEW.md").write_text("\n".join(lines),encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-evidence",type=Path,required=True)
    parser.add_argument("--raw-dir",type=Path,default=ROOT/"data/raw")
    args = parser.parse_args()
    logger,path = start_log("cross_check")
    question_path = ROOT/"eval/questions.jsonl"
    # Discard all SQL fields immediately; they are not inputs to the calculators.
    questions = [{k:v for k,v in json.loads(line).items() if k in {"id","template_id","parameters"}}
                 for line in question_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    receipt = json.loads(args.gold_evidence.read_text(encoding="utf-8"))
    started = next(r for r in receipt["records"] if r["event"] == "validation_started")
    raw = RawAnswers(args.raw_dir)
    if started["question_file_sha256"] != digest(question_path) or started["data_version"] != raw.version:
        raise ValueError("Gold receipt does not match the current question file and raw CSV manifest")
    oracles = {r["question_id"]:r["gold_value"] for r in receipt["records"] if r["event"] == "gold_validated" and "gold_value" in r}
    record(logger,"cross_check_started",gold_evidence=args.gold_evidence.name,gold_evidence_sha256=digest(args.gold_evidence),
           gold_source_log=receipt["source_log"],question_file_sha256=digest(question_path),
           data_version=raw.version,raw_manifest=raw.manifest,calculator_sha256=digest(Path(__file__)),pandas_version=pd.__version__)
    comparisons = []
    for q in questions:
        result = {"question_id":q["id"],"template_id":q.get("template_id"),"matched":False,"differences":[]}
        try:
            result["pandas_value"] = plain(raw.calculate(q))
            result["gold_value"] = oracles[q["id"]]
            result["differences"] = differences(result["pandas_value"],result["gold_value"])
            result["matched"] = not result["differences"]
        except Exception as exc:
            result["error"] = str(exc)
        comparisons.append(result)
        record(logger,"answer_compared",**result)
    raw.verify_unchanged()
    mismatches = [r["question_id"] for r in comparisons if not r["matched"]]
    record(logger,"cross_check_summary",total=len(questions),matched=len(questions)-len(mismatches),mismatches=mismatches)
    output = publish_log(path)
    update_review(questions,comparisons,output,path.name)
    print("Evidence:",output.name)
    return bool(mismatches)


if __name__ == "__main__":
    raise SystemExit(main())
