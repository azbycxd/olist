"""Read-only analysis of saved chaos receipts and their existing task events."""
import hashlib
import json
from pathlib import Path

import psycopg
from config import ROOT, db_kwargs
from scripts.step12_chaos import write_report


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    text=json.dumps(value,ensure_ascii=False,indent=2,default=str)
    path.write_text(text.replace('{\n  "model_kind": "模型替身",','{"model_kind": "模型替身",',1)+'\n',encoding='utf8',newline='\n')


def main():
    evidence=ROOT/'evidence'
    for mode in ('network_baseline','latency','packet_loss','load','db_restart'):
        path=evidence/f'step12_chaos_{mode}.json'
        if not path.exists():continue
        value=json.loads(path.read_text(encoding='utf8'))
        value.setdefault('source_hash_capture','report_creation_working_tree; product code unchanged across all five runs; harness was edited for later scenarios, so its digest is not a loaded-source snapshot')
        ids=[row['task_id'] for row in value['tasks']]
        # Only diagnostic fields; no prompts, SQL text, results or credentials.
        with psycopg.connect(**db_kwargs('agent','app')) as conn:
            events=[dict(zip(('task_id','seq','type','error','latency_ms'),[str(row[0]),*row[1:]])) for row in conn.execute(
                "SELECT task_id,seq,type,payload->>'error',latency_ms FROM events WHERE task_id=ANY(%s::uuid[]) AND type IN ('mcp_call','mcp_result','sql_execution') ORDER BY task_id,seq",(ids,))]
        event_path=evidence/f'step12_chaos_{mode}_events.jsonl'
        event_path.write_text(''.join(json.dumps(row,ensure_ascii=False,default=str)+'\n' for row in events),encoding='utf8',newline='\n')
        value['diagnostic_events']={'path':event_path.name,'sha256':digest(event_path)}
        logs=[ROOT/entry['path'] for entry in value['process_logs'] if entry['path'].endswith('_mcp.txt')]
        mcp_text='\n'.join(p.read_text(encoding='utf8') for p in logs)
        received=mcp_text.count('Processing request of type CallToolRequest')
        logical=value['tool_event_counts'].get('mcp_call',0)
        value['server_tool_requests']=received
        value['extra_server_tool_requests']=max(0,received-logical)
        value['retry_observation']='Server tools/call count minus persisted logical mcp_call count; lower bound, not a per-key transport retry counter.'
        value['pool_connect_timeout_log_count']=mcp_text.count('connection timeout expired')
        value['mcp_error_max_latency_ms']=max((float(e['latency_ms']) for e in events if e['type']=='mcp_result' and e['error']),default=None)
        if mode=='network_baseline':
            value['conclusion']='模型替身：5/5任务成功，未观察到超时或重复传输；作为相同代理拓扑的无故障基线。未修改产品代码。'
        elif mode=='latency':
            base=json.loads((evidence/'step12_chaos_network_baseline.json').read_text(encoding='utf8'))
            value['baseline']={'path':'step12_chaos_network_baseline.json','sql_mean_ms':base['sql_mean_ms'],'elapsed_seconds':base['elapsed_seconds']}
            value['conclusion']='模型替身：500ms下行延迟下5/5成功；多次数据库往返累积，SQL均值和任务总耗时明显上升。MCP的agent/olist两个池均经过代理；API/worker直连。未合并事务或更改SQL/重试规则，未修改产品代码。'
        elif mode=='packet_loss':
            value['fault_semantics']='Toxiproxy 2.13.0 packet_loss: downstream TCP chunks, loss_rate=0.1, correlation=0, toxicity=1; removed after 45 seconds. This is not kernel IP packet loss/retransmission.'
            value['baseline']={'path':'step12_chaos_network_baseline.json','sql_mean_ms':json.loads((evidence/'step12_chaos_network_baseline.json').read_text(encoding='utf8'))['sql_mean_ms']}
            value['conclusion']='模型替身：5任务仅1成功，3个bootstrap_error、1个RuntimeError；观察到池连接超时和MCP重复传输。故障撤除后后续任务成功；仅1个SQL耗时样本，不能解释为丢失提高性能。当前初始化/工具故障不保证任务自动重排，未扩大重排范围或修改产品代码。'
        elif mode=='load':
            value['conclusion']='模型替身：已实际建立100个同时SSE连接后启动4个worker；结果、排队分位数和吞吐按实测计算。连接峰值按采样得到，公式只约束应用池，另列含观察连接的数据库总客户端峰值。未修改产品代码。'
        elif mode=='db_restart':
            signal_path=ROOT/'logs/step12_chaos_db_signal.json'
            signal_data=json.loads(signal_path.read_text(encoding='utf-8-sig'))
            value['restart_signal']={**signal_data,'path':signal_path.relative_to(ROOT).as_posix(),'sha256':digest(signal_path)}
            observations=[json.loads(line) for line in (evidence/value['source_log']).read_text(encoding='utf8').splitlines()]
            health=[row['health_sample'] for row in observations if 'health_sample' in row]
            after=[row for row in health if row['unix_seconds']>=signal_data['started_unix_seconds']]
            for component in ('api','mcp'):
                failed=[row for row in after if row.get(component+'_readyz')!=200]
                recovered=next((row for row in after if failed and row['unix_seconds']>failed[0]['unix_seconds'] and row.get(component+'_readyz')==200),None)
                value[component+'_pool_recovery_seconds_from_restart']=(recovered['unix_seconds']-signal_data['started_unix_seconds']) if recovered else None
                value[component+'_ready_failures_observed']=len(failed)
            marker_path=ROOT/'logs/step12_chaos_db_restart_ready.json'
            marker=json.loads(marker_path.read_text(encoding='utf8'))
            value['clock_anchor']={**marker,'path':marker_path.relative_to(ROOT).as_posix(),'sha256':digest(marker_path)}
            offset=marker['unix_seconds']-marker['at']
            samples=[row['connection_sample'] for row in observations if 'connection_sample' in row]
            restored={}
            for component in ('api','mcp','worker'):
                first=next((row for row in samples if row['at']+offset>=signal_data['completed_unix_seconds']
                            and any(key.startswith('olist:'+component+':') for key in row['counts'])),None)
                restored[component]=(first['at']+offset-signal_data['started_unix_seconds']) if first else None
            value['first_observed_replacement_connection_seconds_from_restart']=restored
            value['conclusion']='模型替身：实际重启PostgreSQL容器，逐次healthz/readyz响应、任务状态、worker退出情况和连接池恢复采样已保留。未修改产品代码；恢复时间为离散探测上界，未观测到就绪失败时不推算恢复时间。'
        save(path,value)

    reused=[]
    for name in ('step12_b1_signal_before_20261027T145755Z_c28e6ca2.summary.json',
                 'step12_b1_signal_after_20261027T151113Z_bfe476ea.summary.json',
                 'step12_review3_503_after_20261027T153551Z_ae4867a3.summary.json'):
        path=evidence/name;old=json.loads(path.read_text(encoding='utf8'))
        reused.append({'path':name,'sha256':digest(path),'source_log':old['source_log'],'source_log_sha256':old['source_log_sha256'],
                       'measurements':{k:old[k] for k in ('signal_to_claim_ms','claim_count','released_count','charged_claims','request_count','deadline_failed','provider_unavailable_failed','wall_ms') if k in old}})
    write_report('reused',{'reused_receipts':reused,'rerun':False,'changed_code':False,
                         'conclusion':'模型替身：按指令复用第1批SIGTERM与持续503收据，未重跑。SIGTERM主动释放减少计费领取次数；持续503报告属于加入PROVIDER_REQUEUE_MAX=3之前的版本，不能当作当前重排上限的再次验收。'},reused)


if __name__=='__main__':main()
