"""Retention-independent rollups and current-state gauges; bounded labels only."""
from collections import Counter
from prometheus_client import CollectorRegistry,generate_latest
from prometheus_client.core import GaugeMetricFamily,CounterMetricFamily,HistogramMetricFamily
from db_pool import connection
import config

REASONS=set('final_answer model_error model_fatal provider_unavailable rate_limited context_limit task_timeout canceled claim_limit_exceeded daily_token_quota token_budget usage_unavailable no_progress repeated_tool_calls max_steps bootstrap_error summary_error provider_usage_exceeds_reservation infra_retryable infra_unavailable context_limit_preflight'.split())


def reason(value):
    if value is None:return 'none'
    if value.startswith('claim_limit_exceeded:'):return 'claim_limit_exceeded'
    return value if value in REASONS else 'other'


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
            rollup={(metric,label):float(value) for metric,label,value in conn.execute('SELECT metric,label,value FROM metrics_rollup')}
            def get(name,label=''):return rollup.get((name,label),0)
            for name,label_name in [('olist_model_calls','error_class'),('olist_tokens','kind')]:
                family=CounterMetricFamily(name,'Durable observed total',labels=[label_name])
                for (metric,label),value in sorted(rollup.items()):
                    if metric==name:family.add_metric([label],value)
                yield family
            for name in ('olist_cache_usage_missing','olist_lease_takeovers','olist_gate_replacements'):
                yield CounterMetricFamily(name,'Durable observed total',value=get(name))
            if get('cache_known_input'):
                yield GaugeMetricFamily('olist_cache_hit_ratio','Reported-cache calls only',value=get('cache_known_cached')/get('cache_known_input'))
            prices=(config.TOKEN_PRICE_INPUT,config.TOKEN_PRICE_CACHED_INPUT,config.TOKEN_PRICE_OUTPUT)
            if get('cost_calls') and None not in prices:
                cost=sum(get(name)*price for name,price in zip(('cost_input','cost_cached','cost_output'),prices))/1_000_000
                yield GaugeMetricFamily('olist_observed_cost_yuan','Known usage at current prices',value=cost)
            for name in ('olist_model_duration_seconds','olist_sql_duration_seconds','olist_queue_wait_seconds'):
                buckets=sorted(((label,n) for (metric,label),n in rollup.items() if metric==name+'_bucket'),key=lambda x:float(x[0]))
                family=HistogramMetricFamily(name,'Durable observed duration in seconds')
                family.add_metric([],buckets,get(name+'_sum'))
                yield family
            import os
            from scripts.provider_health import provider_key
            row=conn.execute('SELECT state FROM provider_health WHERE provider=%s AND model=%s',(provider_key(),os.getenv('OPENAI_MODEL') or 'unconfigured')).fetchone()
            yield GaugeMetricFamily('olist_circuit_state','Configured circuit: closed=0, half_open=1, open=2',value={'closed':0,'half_open':1,'open':2}.get(row[0] if row else 'closed',0))


def render():
    registry=CollectorRegistry();registry.register(DurableMetrics())
    return generate_latest(registry)
