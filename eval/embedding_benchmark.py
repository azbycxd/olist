"""Measure the configured local model with real HTTP inference, no chat calls."""
import hashlib
import math
from time import perf_counter

from config import ROOT
from eval.dataset import load_questions, QUESTION_FILE
from mcp_olist.embedding_config import provenance
from mcp_olist.knowledge import embed
from scripts.common import start_log, record
from scripts.evidence import publish_log


def execute(args):
    logger, path = start_log('eval_' + args.tag)
    started = perf_counter()
    identity = provenance(used=True)
    load_request_ms = (perf_counter() - started) * 1000
    questions = [q for q in load_questions() if q['category'] == 'C' and q['split'] == args.split]
    record(logger, 'embedding_benchmark_started', embedding=identity,
        model_info_request_ms=load_request_ms, question_file_sha256=hashlib.sha256(QUESTION_FILE.read_bytes()).hexdigest(),
        benchmark_sha256=hashlib.sha256((ROOT / 'eval/embedding_benchmark.py').read_bytes()).hexdigest())
    # Warm up before collecting per-query latency; startup/download measured separately.
    embed([questions[0]['question']], query=True)
    rows = []
    for q in questions:
        started = perf_counter()
        vector = embed([q['question']], query=True)[0]
        row = {'question_id': q['id'], 'latency_ms': (perf_counter() - started) * 1000,
            'dimensions': len(vector), 'l2_norm': math.sqrt(sum(x*x for x in vector))}
        if len(vector) != identity['dimensions'] or not math.isclose(row['l2_norm'], 1, abs_tol=1e-5):
            raise ValueError('Invalid embedding dimensions or normalization')
        rows.append(row)
        record(logger, 'embedding_benchmark_case', **row)
    times = sorted(r['latency_ms'] for r in rows)
    record(logger, 'embedding_benchmark_summary', embedding=identity, total=len(rows), split=args.split,
        mean_query_latency_ms=sum(times)/len(times), p95_query_latency_ms=times[math.ceil(len(times)*0.95)-1],
        max_query_latency_ms=max(times), model_info_request_ms=load_request_ms,
        limitations='One CPU host; sequential warmed HTTP calls, no concurrency or GPU claims; no chat model usage')
    print('Evidence:', publish_log(path).name)
