"""Content-free OpenTelemetry spans and observed token accounting."""
import atexit
import math
import os
import threading
from contextlib import contextmanager
from urllib.parse import urlsplit

from opentelemetry import trace
from opentelemetry.trace import SpanKind,Status,StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
import config

_providers={}
_lock=threading.Lock()
_propagator=TraceContextTextMapPropagator()


def provider(component):
    with _lock:
        if component not in _providers:
            value=TracerProvider(resource=Resource.create({'service.name':'olist-'+component}))
            endpoint=config.OTEL_EXPORTER_OTLP_ENDPOINT
            if endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                value.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip('/')+'/v1/traces')))
            _providers[component]=value
        return _providers[component]


@contextmanager
def span(name,component,*,parent=None,attributes=None,kind=SpanKind.INTERNAL,start_time=None):
    context=_propagator.extract({'traceparent':parent}) if parent else None
    # Exception messages and stack traces can contain SQL or model content.
    with provider(component).get_tracer('olist.step12').start_as_current_span(
            name,context=context,attributes=attributes,kind=kind,start_time=start_time,
            record_exception=False,set_status_on_exception=False) as current:
        try:yield current
        except BaseException:
            current.set_status(Status(StatusCode.ERROR))
            raise


def traceparent():
    carrier={};_propagator.inject(carrier)
    return carrier.get('traceparent')


def flush():
    for value in list(_providers.values()):value.force_flush()


atexit.register(flush)


def usage_summary(usage):
    usage=usage or {}
    def number(value):return value if isinstance(value,int) and not isinstance(value,bool) and value>=0 else None
    incoming=number(usage.get('prompt_tokens',usage.get('input_tokens')))
    outgoing=number(usage.get('completion_tokens',usage.get('output_tokens')))
    cached=number(usage.get('prompt_cache_hit_tokens',
        (usage.get('prompt_tokens_details') or usage.get('input_tokens_details') or {}).get('cached_tokens')))
    if cached is not None and incoming is not None and cached>incoming:cached=None
    prices=(config.TOKEN_PRICE_INPUT,config.TOKEN_PRICE_CACHED_INPUT,config.TOKEN_PRICE_OUTPUT)
    cost=None
    if None not in (incoming,outgoing,cached,*prices):
        cost=((incoming-cached)*prices[0]+cached*prices[1]+outgoing*prices[2])/1_000_000
    return {'input_tokens':incoming,'output_tokens':outgoing,'cached_tokens':cached,
            'cache_hit_ratio':cached/incoming if cached is not None and incoming else None,'cost_yuan':cost}


def model_attributes(payload):
    value=usage_summary(payload.get('usage'))
    attrs={'error_class':payload.get('error_class') or 'success'}
    for key,field in [('input_tokens','input_tokens'),('output_tokens','output_tokens'),('cache_read.input_tokens','cached_tokens')]:
        if value[field] is not None:attrs['gen_ai.usage.'+key]=value[field]
    if payload.get('response_model'):attrs['gen_ai.response.model']=payload['response_model']
    return attrs


def model_span_attributes(model):
    host=urlsplit(config.OPENAI_BASE_URL).hostname or ''
    provider_name='deepseek' if host.endswith('deepseek.com') else 'openai' if host=='api.openai.com' else 'other'
    return {'gen_ai.operation.name':'chat','gen_ai.request.model':model,'gen_ai.provider.name':provider_name}


def tool_attributes(result):
    return {key:value for key,value in {
        'result_id':result.get('result_id'),'row_count':result.get('row_count'),
        'truncated':result.get('truncated'),'error_class':result.get('error')}.items() if value is not None}
