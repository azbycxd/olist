-- database: agent
-- Retention-independent counters. Histogram boundaries are fixed for this ledger.
LOCK TABLE events IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE metrics_rollup (
    metric text NOT NULL,
    label text NOT NULL DEFAULT '',
    value numeric NOT NULL DEFAULT 0 CHECK(value>=0),
    PRIMARY KEY(metric,label)
);
ALTER TABLE tasks ADD COLUMN metrics_queue_observed boolean NOT NULL DEFAULT false;
GRANT SELECT ON metrics_rollup TO agent_app;
INSERT INTO metrics_rollup(metric,label)
SELECT name||'_bucket',boundary FROM
unnest(ARRAY['olist_model_duration_seconds','olist_sql_duration_seconds','olist_queue_wait_seconds']) name
CROSS JOIN unnest(ARRAY['0.005','0.01','0.025','0.05','0.1','0.25','0.5','1','2.5','5','10','30','60','120','300','+Inf']) boundary;

CREATE FUNCTION metric_uint(v jsonb) RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN jsonb_typeof(v)='number' AND v#>>'{}' ~ '^[0-9]+$' THEN (v#>>'{}')::numeric END
$$;
CREATE FUNCTION metric_event_delta(kind text,p jsonb,ms double precision,queue_seconds numeric)
RETURNS TABLE(metric text,label text,value numeric) LANGUAGE plpgsql STABLE AS $$
DECLARE incoming numeric; outgoing numeric; cached numeric; usage jsonb;
        classification text; histogram text; seconds numeric;
BEGIN
    IF kind='model_call' THEN
        classification=COALESCE(p->>'error_class','success');
        IF classification NOT IN ('success','retryable','fatal','context_limit','unknown') THEN classification='unknown'; END IF;
        RETURN QUERY SELECT 'olist_model_calls',classification,1::numeric;
        usage=COALESCE(p->'usage','{}'::jsonb);
        incoming=metric_uint(COALESCE(usage->'prompt_tokens',usage->'input_tokens'));
        outgoing=metric_uint(COALESCE(usage->'completion_tokens',usage->'output_tokens'));
        cached=metric_uint(COALESCE(usage->'prompt_cache_hit_tokens',usage#>'{prompt_tokens_details,cached_tokens}',usage#>'{input_tokens_details,cached_tokens}'));
        IF cached>incoming THEN cached=NULL; END IF;
        RETURN QUERY SELECT 'olist_tokens',v.k,v.n FROM (VALUES('input',incoming),('output',outgoing),('cached',cached)) v(k,n) WHERE v.n IS NOT NULL;
        IF incoming IS NOT NULL AND cached IS NOT NULL THEN
            RETURN QUERY VALUES ('cache_known_input','',incoming),('cache_known_cached','',cached);
        ELSIF incoming IS NOT NULL THEN
            RETURN QUERY SELECT 'olist_cache_usage_missing','',1::numeric;
        END IF;
        IF incoming IS NOT NULL AND outgoing IS NOT NULL AND cached IS NOT NULL THEN
            RETURN QUERY VALUES ('cost_input','',incoming-cached),('cost_cached','',cached),('cost_output','',outgoing),('cost_calls','',1::numeric);
        END IF;
        histogram='olist_model_duration_seconds'; seconds=ms::numeric/1000;
    ELSIF kind='sql_execution' THEN
        histogram='olist_sql_duration_seconds'; seconds=ms::numeric/1000;
    ELSIF kind='worker_claimed' THEN
        IF p->>'recovered'='true' THEN RETURN QUERY SELECT 'olist_lease_takeovers','',1::numeric; END IF;
        IF queue_seconds IS NOT NULL THEN histogram='olist_queue_wait_seconds'; seconds=greatest(0,queue_seconds); END IF;
    ELSIF kind='number_gate' AND jsonb_typeof(p->'replaced')='array' THEN
        RETURN QUERY SELECT 'olist_gate_replacements','',jsonb_array_length(p->'replaced')::numeric;
    END IF;
    IF histogram IS NOT NULL THEN
        RETURN QUERY VALUES (histogram||'_count','',1::numeric),(histogram||'_sum','',seconds);
        RETURN QUERY SELECT r.metric,r.label,1::numeric FROM metrics_rollup r
            WHERE r.metric=histogram||'_bucket' AND CASE WHEN r.label='+Inf' THEN true ELSE seconds<=r.label::numeric END;
    END IF;
END $$;

-- One backfill statement also durably marks first queue observations. No task/user
-- labels enter the ledger, and deleting events/tasks can never subtract a delta.
WITH first_claim AS (
    SELECT task_id,min(created_at) claimed FROM events WHERE type='worker_claimed' GROUP BY task_id
), marked AS (
    UPDATE tasks t SET metrics_queue_observed=true FROM first_claim f WHERE t.task_id=f.task_id
), numbered AS (
    SELECT e.*,row_number() OVER(PARTITION BY e.task_id,e.type ORDER BY e.created_at,e.event_id) ordinal
    FROM events e WHERE e.type IN ('model_call','sql_execution','worker_claimed','number_gate')
), deltas AS (
    SELECT d.* FROM numbered e JOIN tasks t USING(task_id)
    CROSS JOIN LATERAL metric_event_delta(e.type,e.payload,e.latency_ms,
        CASE WHEN e.type='worker_claimed' AND e.ordinal=1 THEN EXTRACT(EPOCH FROM(e.created_at-t.created_at)) END) d
)
INSERT INTO metrics_rollup(metric,label,value)
SELECT metric,label,sum(value) FROM deltas GROUP BY metric,label ORDER BY metric,label
ON CONFLICT(metric,label) DO UPDATE SET value=metrics_rollup.value+excluded.value;

CREATE FUNCTION rollup_event() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE born timestamptz; waited numeric;
BEGIN
    IF NEW.type='worker_claimed' THEN
        UPDATE public.tasks SET metrics_queue_observed=true
            WHERE task_id=NEW.task_id AND NOT metrics_queue_observed RETURNING created_at INTO born;
        IF born IS NOT NULL THEN waited=EXTRACT(EPOCH FROM(NEW.created_at-born)); END IF;
    END IF;
    INSERT INTO public.metrics_rollup(metric,label,value)
    SELECT metric,label,sum(value) FROM public.metric_event_delta(NEW.type,NEW.payload,NEW.latency_ms,waited)
    GROUP BY metric,label ORDER BY metric,label
    ON CONFLICT(metric,label) DO UPDATE SET value=metrics_rollup.value+excluded.value;
    RETURN NEW;
END $$;
CREATE TRIGGER events_metrics_rollup AFTER INSERT ON events FOR EACH ROW
    WHEN (NEW.type IN ('model_call','sql_execution','worker_claimed','number_gate')) EXECUTE FUNCTION rollup_event();
REVOKE ALL ON FUNCTION metric_uint(jsonb),metric_event_delta(text,jsonb,double precision,numeric),rollup_event() FROM PUBLIC;
