"""Real-model extraction audit with predeclared quotes; human review stays blank."""
import asyncio
import json
import hashlib
from pathlib import Path
from openai import AsyncOpenAI
from config import OPENAI_BASE_URL,OPENAI_MODEL,MODEL_TIMEOUT
from agent.preferences import extract
from scripts.common import start_log,record
from scripts.evidence import publish_log
from mcp_olist.embedding_config import provenance

CASES=[
('sales_amount_definition',q) for q in ['以后销售额都只算商品价格，不包含运费。','请记住我的销售额口径：商品价格加运费。','以后商品销售额保留所有订单状态。','从现在起销售额只看已送达订单的商品金额。']
]+[('customer_identity',q) for q in ['以后客户数统一按 customer_unique_id 去重。','请记住，客户统计按 customer_id，不使用真实人标识。','以后买家规模只数不同的 customer_unique_id。','默认客户数按所有状态下单的 customer_unique_id 统计。']
]+[('order_status_scope',q) for q in ['以后订单数只统计 delivered。','以后订单量保留全部状态。','记住订单数不包括 canceled 和 unavailable。','默认只看 canceled 状态的订单数量。']
]+[('default_state',q) for q in ['以后经营数字默认只看客户 SP 州。','请记住默认分析 RJ 州客户的订单。','以后所有报表默认地区用 MG 客户州。','默认地区改成 RS 州，指客户所在地。']
]+[('delivery_duration',q) for q in ['以后平均交付天数用购买到实际签收的秒数除以 86400。','以后交付时长只看 delivered 且实际送达时间非空。','默认配送时长从批准订单算到实际送达。','记住交付时长保留小数天，不要只取日期差。']]


async def main():
    logger,path=start_log('memory_audit')
    record(logger,'audit_started',model=OPENAI_MODEL,embedding=provenance(used=False),
        extractor_sha256=hashlib.sha256((Path(__file__).resolve().parents[1]/'agent/preferences.py').read_bytes()).hexdigest(),
        cases_sha256=hashlib.sha256(json.dumps(CASES,ensure_ascii=False).encode()).hexdigest())
    outcomes=[]
    async with AsyncOpenAI(base_url=OPENAI_BASE_URL,max_retries=0,timeout=MODEL_TIMEOUT) as client:
        for index,(key,quote) in enumerate(CASES):
            def emit(kind,payload,tokens=0,latency_ms=0): record(logger,kind,case=index,payload=payload,tokens=tokens,latency_ms=latency_ms)
            try:
                items=await extract(quote,client,OPENAI_MODEL,emit)
                correct=len(items)==1 and items[0]['key']==key and items[0]['source_quote']==quote and items[0]['value']==quote
                row={'case':index,'user_quote':quote,'expected_key':key,'extracted':items,'automatic_exact_match':correct,'human_verdict':None}
            except Exception as exc: row={'case':index,'user_quote':quote,'expected_key':key,'error':type(exc).__name__,'automatic_exact_match':False,'human_verdict':None}
            outcomes.append(row);record(logger,'memory_audit_case',**row)
    record(logger,'memory_audit_summary',total=len(outcomes),automatic_exact_matches=sum(r['automatic_exact_match'] for r in outcomes),human_review='pending',limitations='Author-written examples; exact quote/key check is not human validation or deployment accuracy')
    print('Evidence:',publish_log(path).name)

if __name__=='__main__': asyncio.run(main())
