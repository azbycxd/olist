"""Offline acceptance for honest chaos/load reporting; no model or database."""
import json
import pytest


def test_load_statistics_use_observed_times_and_successes():
    from scripts.step12_chaos import summarize
    tasks=[{'status':'completed','error':None,'queue_seconds':n} for n in [1,2,3]]
    tasks.append({'status':'failed','error':'task_timeout','queue_seconds':4})
    value=summarize(tasks,60)
    assert value['throughput_tasks_per_minute']==3
    assert value['queue_wait_p50_seconds']==2.5
    assert value['queue_wait_p95_seconds']==pytest.approx(3.85)
    assert value['error_types']=={'task_timeout':1}


def test_100_sse_acceptance_requires_observed_simultaneous_connections():
    from scripts.step12_chaos import verify_load
    with pytest.raises(AssertionError):verify_load({'workers':4,'task_count':100,'sse_peak':99})
    verify_load({'workers':4,'task_count':100,'sse_peak':100})


def test_chaos_report_marks_double_on_first_line_and_hashes_raw_log(tmp_path):
    from scripts.step12_chaos import write_report
    output=write_report('fixture',{'conclusion':'fixture observation','changed_code':False},[{'observed':1}],directory=tmp_path)
    assert '模型替身' in output.read_text(encoding='utf8').splitlines()[0]
    value=json.loads(output.read_text(encoding='utf8'))
    import hashlib
    raw=tmp_path/value['source_log']
    assert hashlib.sha256(raw.read_bytes()).hexdigest()==value['source_log_sha256']
