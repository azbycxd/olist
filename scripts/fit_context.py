"""Read-only nearest-rank 95% fit on historical real-model dev logs."""
import hashlib
import json
import math
from pathlib import Path


def quantile(values,p):
    return sorted(values)[max(0,math.ceil(len(values)*p)-1)]


def fit(rows):
    if not rows:raise ValueError('No observed dev prompt usage')
    coefficient=quantile([r['prompt_tokens']/r['characters'] for r in rows],.95)
    errors=[math.ceil(r['characters']*coefficient)-r['prompt_tokens'] for r in rows]
    return {'method':'nearest-rank p95(prompt_tokens / message_characters), no mean or parameter search',
            'samples':len(rows),'coefficient':coefficient,'coverage':sum(e>=0 for e in errors)/len(rows),
            'signed_error_tokens_p50':quantile(errors,.5),'signed_error_tokens_p95':quantile(errors,.95),
            'absolute_error_tokens_p50':quantile([abs(e) for e in errors],.5),
            'absolute_error_tokens_p95':quantile([abs(e) for e in errors],.95),
            'relative_error_p50':quantile([e/r['prompt_tokens'] for e,r in zip(errors,rows)],.5),
            'relative_error_p95':quantile([e/r['prompt_tokens'] for e,r in zip(errors,rows)],.95),
            'max_underestimate_tokens':max(0,-min(errors))}


def main():
    rows=[];sources=[]
    for path in sorted(Path('logs').glob('eval_*.jsonl')):
        records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        start=next((r for r in records if r.get('event')=='run_started'),{})
        if start.get('split')!='dev':continue
        found=[]
        for index,r in enumerate(records,1):
            if r.get('event')!='model_call':continue
            p=r.get('payload',{});usage=p.get('usage') or {}
            chars=p.get('input_summary',{}).get('characters');tokens=usage.get('prompt_tokens')
            if r.get('event')=='model_call' and p.get('requested_model')=='deepseek-flash' and isinstance(chars,int) and chars>0 and isinstance(tokens,int) and tokens>0:
                found.append({'log':path.name,'line':index,'characters':chars,'prompt_tokens':tokens,'role':p.get('role')})
        if found:
            rows.extend(found);sources.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'samples':len(found)})
    result={**fit(rows),'model':'deepseek-flash','data':'historical dev logs only; excludes holdout and HTTP doubles',
            'sources':sources,'observations':rows,'real_model_calls':0}
    out=Path('evidence/step12_context_fit.json')
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in {'sources','observations'}},ensure_ascii=False))


if __name__=='__main__':main()
