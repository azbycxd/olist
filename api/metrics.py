"""Prometheus snapshots from shared durable data, with bounded label vocabularies."""
from collections import Counter
from prometheus_client import CollectorRegistry,generate_latest
from prometheus_client.core import GaugeMetricFamily,CounterMetricFamily,HistogramMetricFamily
from db_pool import connection
from telemetry import usage_summary
from config import METRIC_DURATION_BUCKETS

REASONS=set('final_answer model_error model_fatal provider_unavailable rate_limited context_limit task_timeout canceled claim_limit_exceeded daily_token_quota token_budget usage_unavailable no_progress repeated_tool_calls max_steps bootstrap_error summary_error provider_usage_exceeds_reservation'.split())
ERRORS={'success','retryable','fatal','context_limit','unknown'}
BUCKETS=METRIC_DURATION_BUCKETS


def reason(value):
    if value is None:return 'none'
    if value.startswith('claim_limit_exceeded:'):return 'claim_limit_exceeded'
    return value if value in REASONS else 'other'


def histogram(conn,name,query,params=()):
    fields=','.join('count(*) FILTER(WHERE seconds<=%s)' for _ in BUCKETS)
    row=conn.execute('SELECT count(*),COALESCE(sum(seconds),0),'+fields+' FROM ('+query+') samples',(*BUCKETS,*params)).fetchone()
    family=HistogramMetricFamily(name,'Observed duration in seconds')
    family.add_metric([],[(str(b),n) for b,n in zip(BUCKETS,row[2:])]+[('+Inf',row[0])],float(row[1]))
    return family


class DurableMetrics:
    def collect(self):
        with connection('api') as conn:
            task_counts=Counter()
            for status,error,count in conn.execute('SELECT status,error,count(*) FROM tasks GROUP BY status,error'):
                task_counts[(status,reason(error or ('final_answer' if status=='completed' else None)))]+=count
            family=GaugeMetricFamily('olist_tasks','Tasks currently in each status',labels=['status','reason'])
            for labels,count in task_counts.items():family.add_metric(labels,count)
            yield family
            yield GaugeMetricFamily('olist_queue_depth','Pending task count',value=sum(n for (s,r),n in task_counts.items() if s=='pending'))
            calls=Counter();tokens=Counter();known_input=0;known_cache=0;unknown_cache=0;cost=0.0;cost_known=0
            # Only usage and a bounded classification are read. Content never enters labels.
            for error,usage in conn.execute("SELECT payload->>'error_class',payload->'usage' FROM events WHERE type='model_call'"):
                classification=error or 'success';calls[classification if classification in ERRORS else 'unknown']+=1
                summary=usage_summary(usage)
                for kind,key in [('input','input_tokens'),('cached','cached_tokens'),('output','output_tokens')]:
                    if summary[key] is not None:tokens[kind]+=summary[key]
                if summary['cached_tokens'] is not None and summary['input_tokens'] is not None:
                    known_input+=summary['input_tokens'];known_cache+=summary['cached_tokens']
                elif summary['input_tokens'] is not None:unknown_cache+=1
                if summary['cost_yuan'] is not None:cost+=summary['cost_yuan'];cost_known+=1
            family=CounterMetricFamily('olist_model_calls','Model attempts',labels=['error_class'])
            for error,count in calls.items():family.add_metric([error],count)
            yield family
            family=CounterMetricFamily('olist_tokens','Observed tokens; cached is a subset of input',labels=['kind'])
            for kind in ('input','cached','output'):family.add_metric([kind],tokens[kind])
            yield family
            yield CounterMetricFamily('olist_cache_usage_missing','Calls with input usage but no cache field',value=unknown_cache)
            if known_input:yield GaugeMetricFamily('olist_cache_hit_ratio','Ratio for calls with reported cache usage only',value=known_cache/known_input)
            if cost_known:yield GaugeMetricFamily('olist_observed_cost_yuan','Known usage cost at currently configured prices',value=cost)
            for kind in ('model_call','sql_execution'):
                yield histogram(conn,'olist_'+('model' if kind=='model_call' else 'sql')+'_duration_seconds',
                    'SELECT latency_ms/1000 AS seconds FROM events WHERE type=%s',(kind,))
            yield histogram(conn,'olist_queue_wait_seconds',"""SELECT EXTRACT(EPOCH FROM(min(e.created_at)-t.created_at)) AS seconds
                FROM tasks t JOIN events e USING(task_id) WHERE e.type='worker_claimed' GROUP BY t.task_id""")
            recovered=conn.execute("SELECT count(*) FROM events WHERE type='worker_claimed' AND payload->>'recovered'='true'").fetchone()[0]
            yield CounterMetricFamily('olist_lease_takeovers','Expired lease takeovers',value=recovered)
            replaced=conn.execute("SELECT COALESCE(sum(jsonb_array_length(payload->'replaced')),0) FROM events WHERE type='number_gate' AND jsonb_typeof(payload->'replaced')='array'").fetchone()[0]
            yield CounterMetricFamily('olist_gate_replacements','Replaced unsupported numeric occurrences',value=replaced)
            # Only the configured endpoint/model: old deployments and fixture model names
            # must not become unbounded provider/model labels.
            import os
            from scripts.provider_health import provider_key
            row=conn.execute('SELECT state FROM provider_health WHERE provider=%s AND model=%s',(provider_key(),os.getenv('OPENAI_MODEL') or 'unconfigured')).fetchone()
            yield GaugeMetricFamily('olist_circuit_state','Configured provider circuit: closed=0, half_open=1, open=2',value={'closed':0,'half_open':1,'open':2}.get(row[0] if row else 'closed',0))


def render():
    registry=CollectorRegistry()
    registry.register(DurableMetrics())
    return generate_latest(registry)
