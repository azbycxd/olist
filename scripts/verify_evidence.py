"""Audit measured RESULTS cells, immutable logs, documentation links and secret leakage."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from config import ROOT
from scripts.common import start_log,record
from scripts.evidence import write_evidence


def main():
    logger,path=start_log('evidence_integrity')
    count=0
    pct=lambda n:'' if n is None else f'{n*100:.2f}%'
    for line in (ROOT/'docs/RESULTS.md').read_text(encoding='utf-8').splitlines():
        if not line.startswith('| ') or '汇总证据' in line or line.startswith('| ---'):continue
        cells=[c.strip() for c in line.strip().strip('|').split('|')]
        assert len(cells)==20,(len(cells),cells[0])
        name=re.search(r'\.\./evidence/([^)]*)',cells[-1]).group(1)
        data=json.loads((ROOT/'evidence'/name).read_text(encoding='utf-8'))
        assert cells[-2].strip('`')==data['source_log'],name
        log=ROOT/'logs'/data['source_log']
        assert hashlib.sha256(log.read_bytes()).hexdigest()==data['source_log_sha256'],name
        m=data['metrics']
        if 'bm25' in m:
            methods=['weighted'] if cells[0].endswith('-weighted') else ['bm25','vector','hybrid']
            slots=[17] if methods==['weighted'] else [15,16,17]
            for method,slot in zip(methods,slots):assert cells[slot]==pct(m[method]),name
        else:
            u=data['usage']
            expected={3:f"{m['correct']} / {m['total']}",4:pct(m['accuracy']),5:pct(m['fact_hit_rate']),
                6:pct(m['unsupported_claim_ratio']),7:pct(m['d_unsupported_number_ratio']),
                8:'' if m['judge_mean'] is None else f"{m['judge_mean']:.3f}",
                9:'' if u['total_tokens'] is None else str(u['total_tokens']),10:u['cost_usd'] or '',
                11:str(m.get('peak_context_tokens','')),12:pct(m.get('completion_rate')),
                13:'' if m.get('average_tokens') is None else f"{m['average_tokens']:.2f}",
                14:'' if m.get('average_latency_ms') is None else f"{m['average_latency_ms']:.2f}"}
            for slot,value in expected.items():
                if cells[slot]:assert cells[slot]==value,(name,slot,cells[slot],value)
        count+=1
    links=0
    for doc in [ROOT/'README.md',ROOT/'docs/DECISIONS.md',ROOT/'docs/RESULTS.md',ROOT/'docs/REVIEW_COMPARISON.md',ROOT/'docs/FINDING_REUSE.md']:
        for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if target.startswith(('https:','http:','#')):continue
            target=target.split('#')[0]
            if 'UUID' in target:continue
            assert (doc.parent/target).is_file(),(doc.name,target)
            links+=1
    # Never print a secret or matching content. Public template defaults are excluded.
    template=(ROOT/'.env.example').read_text(encoding='utf-8')
    secrets=[]
    for line in (ROOT/'.env').read_text(encoding='utf-8').splitlines():
        if '=' not in line or line.startswith('#'):continue
        key,value=line.split('=',1);value=value.strip().strip('"\'')
        if re.search(r'KEY|PASSWORD|TOKEN|SECRET',key) and len(value)>=16 and value not in template:secrets.append(value.encode())
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    leaked=[]
    for name in names:
        file=ROOT/name
        if file.is_file() and any(secret in file.read_bytes() for secret in secrets):leaked.append(name)
    assert not leaked,('Secret found in candidate commit files',leaked)
    summary={'results_rows_checked':count,'documentation_links_checked':links,'secret_matches':len(leaked),
        'source_log':path.name,'checks':['RESULTS populated cells match real receipts','source log hashes match','all checked documentation links resolve','candidate Git files contain no configured secrets']}
    record(logger,'integrity_summary',**summary)
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    print('Evidence:',receipt.name)


if __name__=='__main__':main()
