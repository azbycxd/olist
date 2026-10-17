"""Boot fresh isolated Compose database and model-cache volumes.

This never removes the primary project's volumes. The generated Compose config
contains local secrets, stays in ignored logs/, and is removed after the test.
"""
import hashlib
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from scripts.common import start_log,record
from scripts.evidence import write_evidence
from config import ROOT


def main():
    name='olist-step8-smoke'
    logger,path=start_log('fresh_compose')
    def run(*args):
        return subprocess.run(list(args),cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    result=run('docker','compose','config','--format','json')
    if result.returncode:raise RuntimeError('Cannot read Compose config')
    config=json.loads(result.stdout)
    cached=config['volumes']['embedding_models']['name']
    config['name']=name
    config['services'].pop('agent',None);config['services'].pop('memory-api',None)
    for service,port in [('db',15432),('mcp-olist',18001),('api',18000)]:
        for item in config['services'][service]['ports']:item['published']=str(port)
    config['volumes']['postgres_data']={'name':name+'_postgres_data'}
    config['volumes']['embedding_models']={'name':name+'_embedding_models'}
    config['networks']={'default':{'name':name+'_default'}}
    # Do not overwrite the main workspace's import profile or raw logs.
    root=ROOT/'logs'/'fresh_smoke'
    for leaf in ['docs','logs']:(root/leaf).mkdir(parents=True,exist_ok=True)
    for volume in config['services']['init-data']['volumes']:
        if volume['target'] in ['/app/docs','/app/logs']:
            volume['source']=str(root/volume['target'].rsplit('/',1)[1])
    config_path=ROOT/'logs'/'fresh.compose.private.json'
    config_path.write_text(json.dumps(config),encoding='utf-8')
    command=['docker','compose','-p',name,'-f',str(config_path)]
    assert config['volumes']['postgres_data']['name']==name+'_postgres_data'
    assert config['volumes']['embedding_models']['name']==name+'_embedding_models'
    for volume in [name+'_postgres_data',name+'_embedding_models']:
        if run('docker','volume','inspect',volume).returncode==0:
            raise RuntimeError('Fresh test volume already exists; refusing to call it a clean start')
    record(logger,'fresh_started',project=name,database_volume=name+'_postgres_data',embedding_cache=name+'_embedding_models',
        scope='Fresh database and empty model cache; existing built images and original CSV inputs reused')
    summary={'source_log':path.name,'project':name,'initialized':False,'embedding_cache':name+'_embedding_models',
        'limitations':'Isolated fresh database and empty model cache on this host, using existing built images and original CSV inputs; not a different physical machine.'}
    failure=None
    try:
        result=run(*command,'up','-d')
        record(logger,'compose_up',returncode=result.returncode)
        if result.returncode:
            (root/'compose_startup_error.log').write_text(result.stderr,encoding='utf-8')
            raise RuntimeError('Fresh Compose startup failed; inspect logs/fresh_smoke/compose_startup_error.log')
        # up has already waited for service_completed_successfully. Inspect
        # the exited container itself; compose wait may find no running job.
        result=run(*command,'ps','--all','--format','json')
        if result.returncode:raise RuntimeError('Cannot inspect initialization container')
        initialized=next(r for r in (json.loads(line) for line in result.stdout.splitlines() if line) if r['Service']=='init-data')
        record(logger,'initialization_exit',state=initialized['State'],exit_code=initialized['ExitCode'])
        if initialized['State']!='exited' or initialized['ExitCode']!=0:raise RuntimeError('Fresh initialization failed')
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://localhost:18000/',timeout=2) as response:
                    if response.status==200:break
            except Exception:time.sleep(1)
        else:raise RuntimeError('Fresh API did not become ready')
        ledger=run(*command,'exec','-T','db','psql','-U','olist_admin','-d','agent','-At','-c','SELECT version,filename FROM schema_migrations ORDER BY version')
        assert ledger.returncode==0
        migrations=[line for line in ledger.stdout.splitlines() if line]
        expected=len(list((ROOT/'sql/migrations').glob('[0-9]*.sql')))
        assert len(migrations)==expected
        identity=run(*command,'exec','-T','mcp-olist','python','-c',
            "import httpx,json; print(json.dumps(httpx.get('http://embeddings:8002/model-info',timeout=10).json()))")
        assert identity.returncode==0
        embedding=json.loads(identity.stdout)
        services=run(*command,'ps','--format','json')
        rows=[json.loads(line) for line in services.stdout.splitlines() if line]
        assert all(r['State']=='running' for r in rows)
        status=[{k:r.get(k) for k in ['Service','State','Health','ExitCode']} for r in rows]
        assert {'db','embeddings','mcp-olist','api','worker'}<={r['Service'] for r in status}
        summary={'source_log':path.name,'project':name,'initialized':True,'api_http_status':200,
            'migrations':migrations,'services':status,'embedding_cache':name+'_embedding_models','embedding':embedding,
            'limitations':summary['limitations']}
        record(logger,'fresh_summary',**summary)
    except Exception as exc:
        failure=exc
        summary['error']=type(exc).__name__+': '+str(exc)
        diagnostic=run(*command,'logs','--no-color','--tail','100')
        (root/(path.stem+'.services.log')).write_text(diagnostic.stdout+'\n'+diagnostic.stderr,encoding='utf-8')
        record(logger,'fresh_failed',**summary)
    finally:
        cleanup=run(*command,'down','--volumes')
        record(logger,'cleanup',project=name,returncode=cleanup.returncode,primary_cache_preserved=cached)
        config_path.unlink(missing_ok=True)
    summary['cleanup_success']=cleanup.returncode==0
    summary['source_log_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=write_evidence(path.stem+'.summary.json',summary)
    print('Evidence:',receipt.name)
    if failure:raise failure


if __name__=='__main__':main()
