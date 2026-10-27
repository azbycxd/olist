"""Database-serialized provider/model circuit; only the trusted parent imports this."""
import os
from urllib.parse import urlsplit
from config import PROVIDER_FAILURE_THRESHOLD, PROVIDER_COOLDOWN_SECONDS, MODEL_TIMEOUT


def provider_key():
    url = urlsplit(os.getenv('OPENAI_BASE_URL') or 'https://api.openai.com/v1')
    # No userinfo, query string or credentials enter the database/telemetry key.
    return f'{url.scheme}://{url.hostname}' + (f':{url.port}' if url.port else '') + url.path.rstrip('/')


def admit(conn, call, model, deadline):
    from scripts.task_limits import TaskStopped
    provider = provider_key()
    conn.execute('INSERT INTO provider_health(provider,model) VALUES(%s,%s) ON CONFLICT DO NOTHING',(provider,model))
    row = conn.execute('SELECT state,generation,open_until>clock_timestamp(),probe_until>clock_timestamp() FROM provider_health WHERE provider=%s AND model=%s FOR UPDATE',(provider,model)).fetchone()
    state,generation,cooling,probing = row
    if (state=='open' and cooling) or (state=='half_open' and probing):
        raise TaskStopped('provider_unavailable')
    if state != 'closed':
        generation += 1
        conn.execute("UPDATE provider_health SET state='half_open',generation=%s,probe_call_id=%s,probe_until=LEAST(%s,clock_timestamp()+%s*interval '1 second'),updated_at=clock_timestamp() WHERE provider=%s AND model=%s",
            (generation,call,deadline,MODEL_TIMEOUT,provider,model))
    return provider,generation


def record(conn, call, payload):
    row = conn.execute('SELECT provider,model,provider_generation,health_recorded FROM model_reservations WHERE call_id=%s FOR UPDATE',(call,)).fetchone()
    if not row or not row[0] or row[3]: return
    provider,model,generation,_ = row
    health = conn.execute('SELECT state,failure_count,generation,probe_call_id FROM provider_health WHERE provider=%s AND model=%s FOR UPDATE',(provider,model)).fetchone()
    conn.execute('UPDATE model_reservations SET health_recorded=true WHERE call_id=%s',(call,))
    if not health or health[2] != generation: return  # stale in-flight result cannot close a newer circuit
    state,count,_,probe = health
    error = payload.get('error_class')
    success = error is None and not payload.get('error')
    if state=='half_open' and str(probe)==str(call):
        opening = not success
        count = 0 if success else max(count,PROVIDER_FAILURE_THRESHOLD)
    elif state=='closed':
        count = count+1 if error=='retryable' else 0 if success else count
        opening = count >= PROVIDER_FAILURE_THRESHOLD
    else: return
    conn.execute("UPDATE provider_health SET state=%s,failure_count=%s,generation=generation+%s,open_until=CASE WHEN %s THEN clock_timestamp()+%s*interval '1 second' ELSE NULL END,probe_call_id=NULL,probe_until=NULL,updated_at=clock_timestamp() WHERE provider=%s AND model=%s",
        ('open' if opening else 'closed',count,1 if opening else 0,opening,PROVIDER_COOLDOWN_SECONDS,provider,model))
