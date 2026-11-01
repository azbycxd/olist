"""User-supplied N01–N12: separate SQL and raw-CSV pandas calculations; no model."""
import argparse
import hashlib
import json
from pathlib import Path

from eval.step13_errors import ROOT, read, sha, write

# Verbatim user text and explicit public fields. SQL below is not used by pandas.
SUPPLIED = [
('2017 年哪个月的订单最多、哪个月最少?各有多少单?按下单时间归月,所有状态计入。','key_facts','peak_month peak_orders low_month low_orders'),
('圣保罗市(São Paulo 市)2018 年 Q1 的客户下了多少单?按客户所在城市,所有状态计入。','number',''),
('里约热内卢市(Rio de Janeiro 市)和圣保罗市,2018 年 Q2 的 GMV 各是多少?GMV 按知识库口径。','key_facts','rio_gmv sao_paulo_gmv'),
('2018 年 1–8 月的 GMV 比 2017 年同期增长了多少(百分数)?GMV 排除取消及不可用订单。','key_facts','gmv_2017 gmv_2018 growth_pct'),
('2018 年用信用卡的支付记录里,最常见的是分几期?占信用卡支付记录的百分之几?按支付记录计,按订单下单时间归年。','key_facts','mode_installments share_pct'),
('2018 年 Q2 运费占(商品金额 + 运费)的比例是多少?按客户所在州看,这个比例最高的州是哪个、是多少?所有状态计入,百分数。','key_facts','freight_pct top_state top_state_pct'),
('2018 年 Q2 已送达、且有实际送达时间的订单里,从下单到送达超过 30 天的有多少单?占比多少(百分数)?','key_facts','over30_orders measured_orders over30_pct'),
('2018 年 Q2,已送达订单不少于 50 单的卖家里,迟到率最高的是哪个卖家?迟到率多少?一个订单含多个卖家时,计入每个卖家;迟到指实际送达晚于预计送达。','key_facts','worst_seller late_pct'),
('2018 年 Q1 商品金额前三的英文品类是哪些?不含运费,所有状态计入。','list',''),
('2017 年 11 月的订单量是 2017 年月均订单量的多少倍?按下单时间归月,所有状态计入,结果保留两位小数。','key_facts','nov_orders monthly_avg ratio'),
('2018 年 Q2 有多少个真实客户在不同的州下过单(至少两个州)?所有状态计入。','number',''),
('2018 年 Q2 平均每笔订单包含几件商品?包含两件及以上商品的订单占多少(百分数)?只算有商品明细的订单,件数按明细行数。','key_facts','avg_items multi_item_pct'),
]

SQL = [
"""WITH m AS (
  SELECT to_char(order_purchase_timestamp, 'YYYY-MM') AS month, count(*) AS orders
  FROM orders WHERE order_purchase_timestamp >= '2017-01-01'
    AND order_purchase_timestamp < '2018-01-01' GROUP BY 1
), hi AS (SELECT * FROM m WHERE orders = (SELECT max(orders) FROM m)),
lo AS (SELECT * FROM m WHERE orders = (SELECT min(orders) FROM m))
SELECT hi.month AS peak_month, hi.orders AS peak_orders,
       lo.month AS low_month, lo.orders AS low_orders FROM hi CROSS JOIN lo""",
"""SELECT count(*) AS value FROM orders o JOIN customers c USING (customer_id)
WHERE c.customer_city = 'sao paulo' AND o.order_purchase_timestamp >= '2018-01-01'
  AND o.order_purchase_timestamp < '2018-04-01'""",
"""SELECT sum(i.price) FILTER (WHERE c.customer_city = 'rio de janeiro') AS rio_gmv,
       sum(i.price) FILTER (WHERE c.customer_city = 'sao paulo') AS sao_paulo_gmv
FROM orders o JOIN customers c USING (customer_id) JOIN order_items i USING (order_id)
WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
  AND o.order_status NOT IN ('canceled','unavailable')
  AND c.customer_city IN ('rio de janeiro','sao paulo')""",
"""WITH g AS (
 SELECT sum(i.price) FILTER (WHERE o.order_purchase_timestamp >= '2017-01-01'
   AND o.order_purchase_timestamp < '2017-09-01') AS gmv_2017,
 sum(i.price) FILTER (WHERE o.order_purchase_timestamp >= '2018-01-01'
   AND o.order_purchase_timestamp < '2018-09-01') AS gmv_2018
 FROM orders o JOIN order_items i USING (order_id)
 WHERE o.order_status NOT IN ('canceled','unavailable')
)
SELECT gmv_2017, gmv_2018, 100.0*(gmv_2018-gmv_2017)/nullif(gmv_2017,0) AS growth_pct FROM g""",
"""WITH counts AS (
 SELECT p.payment_installments, count(*) AS n FROM order_payments p JOIN orders o USING (order_id)
 WHERE p.payment_type = 'credit_card' AND o.order_purchase_timestamp >= '2018-01-01'
   AND o.order_purchase_timestamp < '2019-01-01' GROUP BY p.payment_installments
)
SELECT payment_installments AS mode_installments,
  100.0*n/(SELECT sum(n) FROM counts) AS share_pct
FROM counts WHERE n = (SELECT max(n) FROM counts)""",
"""WITH s AS (
 SELECT c.customer_state, sum(i.freight_value) AS freight, sum(i.price+i.freight_value) AS total
 FROM orders o JOIN customers c USING (customer_id) JOIN order_items i USING (order_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 GROUP BY c.customer_state
), r AS (SELECT *, 100.0*freight/nullif(total,0) AS pct FROM s)
SELECT (SELECT 100.0*sum(freight)/sum(total) FROM s) AS freight_pct,
 customer_state AS top_state, pct AS top_state_pct FROM r WHERE pct = (SELECT max(pct) FROM r)""",
"""WITH m AS (
 SELECT count(*) AS measured_orders,
 count(*) FILTER (WHERE order_delivered_customer_date-order_purchase_timestamp > interval '30 days') AS over30_orders
 FROM orders WHERE order_purchase_timestamp >= '2018-04-01' AND order_purchase_timestamp < '2018-07-01'
 AND order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
)
SELECT over30_orders, measured_orders, 100.0*over30_orders/nullif(measured_orders,0) AS over30_pct FROM m""",
"""WITH pairs AS (
 SELECT DISTINCT i.seller_id, o.order_id, o.order_delivered_customer_date AS actual,
 o.order_estimated_delivery_date AS expected FROM orders o JOIN order_items i USING (order_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 AND o.order_status = 'delivered'
), rates AS (
 SELECT seller_id, 100.0*count(*) FILTER (WHERE actual > expected)
 /nullif(count(*) FILTER (WHERE actual IS NOT NULL),0) AS late_pct
 FROM pairs GROUP BY seller_id HAVING count(*) >= 50
)
SELECT seller_id AS worst_seller, late_pct FROM rates WHERE late_pct = (SELECT max(late_pct) FROM rates)""",
"""WITH amounts AS (
 SELECT t.product_category_name_english AS category, sum(i.price) AS amount
 FROM orders o JOIN order_items i USING (order_id) JOIN products p USING (product_id)
 JOIN product_category_name_translation t USING (product_category_name)
 WHERE o.order_purchase_timestamp >= '2018-01-01' AND o.order_purchase_timestamp < '2018-04-01'
 GROUP BY t.product_category_name_english
), ranked AS (SELECT *, dense_rank() OVER (ORDER BY amount DESC) AS rank FROM amounts)
SELECT category FROM ranked WHERE rank <= 3 ORDER BY amount DESC""",
"""WITH n AS (
 SELECT count(*) FILTER (WHERE order_purchase_timestamp >= '2017-11-01'
   AND order_purchase_timestamp < '2017-12-01') AS nov_orders, count(*)/12.0 AS monthly_avg
 FROM orders WHERE order_purchase_timestamp >= '2017-01-01' AND order_purchase_timestamp < '2018-01-01'
)
SELECT nov_orders, round(monthly_avg,2) AS monthly_avg,
 round(nov_orders/nullif(monthly_avg,0),2) AS ratio FROM n""",
"""SELECT count(*) AS value FROM (
 SELECT c.customer_unique_id FROM orders o JOIN customers c USING (customer_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 GROUP BY c.customer_unique_id HAVING count(DISTINCT c.customer_state) >= 2
) AS multi_state""",
"""WITH n AS (
 SELECT o.order_id, count(*) AS items FROM orders o JOIN order_items i USING (order_id)
 WHERE o.order_purchase_timestamp >= '2018-04-01' AND o.order_purchase_timestamp < '2018-07-01'
 GROUP BY o.order_id
)
SELECT avg(items) AS avg_items, 100.0*count(*) FILTER (WHERE items>=2)/count(*) AS multi_item_pct FROM n""",
]


def create_cases():
    path=ROOT/'eval/step13_supplement_cases.json'
    if path.exists():raise FileExistsError(path)
    write(path,[{'id':f'N{i:02d}','category':'N','question':q,'gold_sql':sql,'answer_type':kind,
        'split':'supplement','required_facts':keys.split(),'rubric_focus':None}
        for i,((q,kind,keys),sql) in enumerate(zip(SUPPLIED,SQL),1)])


def verify_supplied_cases():
    cases=read(ROOT/'eval/step13_supplement_cases.json')
    assert len(cases)==len(SUPPLIED)==12
    for i,(case,(text,kind,keys)) in enumerate(zip(cases,SUPPLIED),1):
        assert case['id']==f'N{i:02d}' and case['question']==text
        assert case['answer_type']==kind and case['required_facts']==keys.split()
        assert case['split']=='supplement'
    return len(cases)


def calculate_csv():
    """No SQL argument, DB import, cross_check calculator, or saved answer input."""
    import pandas as pd
    directory=ROOT/'data/raw';manifest=[]
    files={'o':'olist_orders_dataset.csv','c':'olist_customers_dataset.csv',
        'i':'olist_order_items_dataset.csv','p':'olist_order_payments_dataset.csv',
        'products':'olist_products_dataset.csv','translation':'product_category_name_translation.csv'}
    frames={}
    for key,filename in files.items():
        path=directory/filename;frames[key]=pd.read_csv(path)
        manifest.append({'file':'data/raw/'+filename,'sha256':sha(path),'rows':len(frames[key])})
    o,c,i,p,products,t=[frames[k] for k in files]
    for col in ['order_purchase_timestamp','order_delivered_customer_date','order_estimated_delivery_date']:
        o[col]=pd.to_datetime(o[col])
    o=o.merge(c[['customer_id','customer_unique_id','customer_city','customer_state']],on='customer_id',validate='many_to_one')
    def window(start,end):return o[(o.order_purchase_timestamp>=start)&(o.order_purchase_timestamp<end)]
    def items(orders):return i[i.order_id.isin(orders.order_id)]
    year=window('2017-01-01','2018-01-01');q1=window('2018-01-01','2018-04-01');q2=window('2018-04-01','2018-07-01')
    counts=year.groupby(year.order_purchase_timestamp.dt.strftime('%Y-%m')).size().reindex([f'2017-{m:02d}' for m in range(1,13)],fill_value=0)
    peak=counts[counts==counts.max()];low=counts[counts==counts.min()]
    pending=[]
    if len(peak)!=1 or len(low)!=1:pending.append('N01 月份有并列，需用户定契约')
    result={'N01':{'peak_month':peak.index[0] if len(peak)==1 else None,'peak_orders':int(peak.max()),
        'low_month':low.index[0] if len(low)==1 else None,'low_orders':int(low.min())},
        'N02':int((q1.customer_city=='sao paulo').sum())}
    good=q2[~q2.order_status.isin(['canceled','unavailable'])]
    result['N03']={name:float(items(good[good.customer_city==city]).price.sum()) for name,city in [('rio_gmv','rio de janeiro'),('sao_paulo_gmv','sao paulo')]}
    g=[]
    for yr in [2017,2018]:
        orders=window(f'{yr}-01-01',f'{yr}-09-01');orders=orders[~orders.order_status.isin(['canceled','unavailable'])]
        g.append(float(items(orders).price.sum()))
    result['N04']={'gmv_2017':g[0],'gmv_2018':g[1],'growth_pct':100*(g[1]/g[0]-1)}
    pay=p[p.order_id.isin(window('2018-01-01','2019-01-01').order_id)&(p.payment_type=='credit_card')]
    modes=pay.payment_installments.value_counts();modes=modes[modes==modes.max()]
    if len(modes)!=1:pending.append('N05 信用卡分期众数并列')
    result['N05']={'mode_installments':int(modes.index[0]) if len(modes)==1 else None,'share_pct':100*int(modes.max())/len(pay)}
    line=items(q2).merge(q2[['order_id','customer_state']],on='order_id',validate='many_to_one')
    totals=line.groupby('customer_state')[['price','freight_value']].sum();rates=100*totals.freight_value/(totals.price+totals.freight_value)
    top=rates[rates==rates.max()]
    if len(top)!=1:pending.append('N06 最高州运费比例并列')
    result['N06']={'freight_pct':100*line.freight_value.sum()/(line.price+line.freight_value).sum(),
        'top_state':top.index[0] if len(top)==1 else None,'top_state_pct':top.max()}
    measured=q2[(q2.order_status=='delivered')&q2.order_delivered_customer_date.notna()]
    over=((measured.order_delivered_customer_date-measured.order_purchase_timestamp).dt.total_seconds()>30*86400).sum()
    result['N07']={'over30_orders':int(over),'measured_orders':len(measured),'over30_pct':100*int(over)/len(measured)}
    pairs=items(q2).loc[:,['seller_id','order_id']].drop_duplicates().merge(q2[q2.order_status=='delivered'],on='order_id',validate='many_to_one')
    eligible=pairs.groupby('seller_id').size();pairs=pairs[pairs.seller_id.isin(eligible[eligible>=50].index)]
    missing={'actual':int(pairs.order_delivered_customer_date.isna().sum()),'estimated':int(pairs.order_estimated_delivery_date.isna().sum())}
    if any(missing.values()):pending.append('N08 合格卖家缺少交付时间，需确认分母/预计时间口径')
    pairs=pairs[pairs.order_delivered_customer_date.notna()].copy()
    pairs['late']=pairs.order_delivered_customer_date>pairs.order_estimated_delivery_date
    late=pairs.groupby('seller_id').late.mean()*100;worst=late[late==late.max()]
    if len(worst)!=1:pending.append('N08 卖家迟到率最高并列')
    result['N08']={'worst_seller':worst.index[0] if len(worst)==1 else None,'late_pct':worst.max()}
    categories=items(q1).merge(products[['product_id','product_category_name']],on='product_id',validate='many_to_one').merge(t,on='product_category_name',how='left',validate='many_to_one')
    amounts=categories.groupby('product_category_name_english').price.sum().sort_values(ascending=False)
    leaders=amounts[amounts>=amounts.iloc[2]]
    if len(leaders)!=3:pending.append('N09 第三名并列')
    unknown_total=float(categories[categories.product_category_name_english.isna()].price.sum())
    if unknown_total>=amounts.iloc[2]:pending.append('N09 未翻译组足以影响前三名，需确认展示口径')
    result['N09']=leaders.index.tolist()
    nov=int(counts.loc['2017-11']);avg=len(year)/12
    result['N10']={'nov_orders':nov,'monthly_avg':round(avg,2),'ratio':round(nov/avg,2)}
    states=q2.groupby('customer_unique_id').customer_state.nunique()
    result['N11']=int((states>=2).sum())
    sizes=items(q2).groupby('order_id').size()
    result['N12']={'avg_items':float(sizes.mean()),'multi_item_pct':100*float((sizes>=2).mean())}
    cities=[]
    for city in ['sao paulo','rio de janeiro']:
        city_good=good[good.customer_city==city]
        cities.append({'city':city,'customer_rows':int((c.customer_city==city).sum()),
            'q1_all_status_orders':int((q1.customer_city==city).sum()),'q2_all_status_orders':int((q2.customer_city==city).sum()),
            'q2_gmv_eligible_orders':len(city_good),'q2_gmv_item_rows':len(items(city_good))})
    for source in manifest:assert sha(ROOT/source['file'])==source['sha256']
    return {'answers':result,'sources':manifest,'cities':cities,'pending':pending,
        'checks':{'N01_months':len(counts),'N01_peak_ties':len(peak),'N01_low_ties':len(low),
        'N05_mode_ties':len(modes),'N06_top_ties':len(top),'N08_top_ties':len(worst),
        'N08_eligible_seller_order_pairs':len(pairs),'N08_missing':missing,'N09_top_count':len(leaders),
        'N09_unknown_amount':unknown_total,'N09_third_amount':float(amounts.iloc[2])}}


def consistent(sql,pandas):
    if isinstance(sql,dict):return set(sql)==set(pandas) and all(consistent(v,pandas[k]) for k,v in sql.items())
    if isinstance(sql,list):return sql==pandas
    if isinstance(sql,(int,float)) and isinstance(pandas,(int,float)):
        return abs(sql-pandas)<=max(abs(sql)*.01,1e-8)
    return sql==pandas


def load_crosscheck():return read(ROOT/'evidence/step13_supplement_crosscheck.json')


def crosscheck():
    from eval.step13_grader import load_fixture,plain
    fixture=load_fixture('evidence/step13_supplement_reference.json')
    raw=plain(calculate_csv());log=ROOT/'logs/step13_supplement_pandas.jsonl'
    if log.exists():raise FileExistsError('Preserve original pandas receipt')
    with log.open('w',encoding='utf-8',newline='\n') as f:
        for qid,answer in raw['answers'].items():f.write(json.dumps({'id':qid,'pandas':answer},ensure_ascii=False)+'\n')
    cases=[{'id':r['question']['id'],'sql':r['question']['gold_sql'],'gold':r['gold'],
        'pandas':raw['answers'][r['question']['id']],'consistent':consistent(r['gold'],raw['answers'][r['question']['id']])} for r in fixture['records']]
    report={**raw,'cases':cases,'model_calls':0,'source_log':log.relative_to(ROOT).as_posix(),'source_log_sha256':sha(log),
        'sql_fixture_sha256':sha(ROOT/'evidence/step13_supplement_reference.json'),'calculator_sha256':sha(Path(__file__)),
        'policy':'Independent raw CSV pandas calculations, relative tolerance <=1%; original questions unchanged; not authorized for model evaluation'}
    write(ROOT/'evidence/step13_supplement_crosscheck.json',report)
    print(json.dumps({'consistent':sum(c['consistent'] for c in cases),'pending':raw['pending'],'cities':raw['cities'],'checks':raw['checks']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--create',action='store_true');args=parser.parse_args()
    if args.create:create_cases()
    else:verify_supplied_cases();crosscheck()
