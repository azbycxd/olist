-- database: agent
CREATE TABLE maintenance_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action text NOT NULL CHECK(action IN ('retention','user_delete')),
    subject_id uuid,
    details jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
GRANT SELECT ON maintenance_audit TO agent_app;
ALTER TABLE tasks ADD COLUMN retained_at timestamptz;

-- All owner/task dependencies must cascade on an explicit user deletion.
DO $$ DECLARE row record; BEGIN
    FOR row IN SELECT c.conname,c.conrelid::regclass AS relation,pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c WHERE c.contype='f' AND c.confrelid IN
        ('users'::regclass,'tasks'::regclass,'query_results'::regclass) LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',row.relation,row.conname);
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s ON DELETE CASCADE',row.relation,row.conname,row.definition);
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION reject_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('olist.maintenance',true)='on' AND current_user=
       (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.events'::regclass) THEN
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'events is append-only' USING ERRCODE='42501';
END $$;

CREATE FUNCTION retained_result_refs(value jsonb) RETURNS SETOF uuid LANGUAGE sql IMMUTABLE AS $$
    SELECT (m[1])::uuid FROM regexp_matches(value::text,
      '([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})','g') m;
$$;

CREATE FUNCTION retain_task_details(days integer) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public SET olist.maintenance='on' AS $$
DECLARE cutoff timestamptz; ids uuid[]; deleted_events bigint; deleted_results bigint; kept uuid[]; report jsonb;
BEGIN
    IF days<1 OR days>36500 THEN RAISE EXCEPTION 'Invalid retention days'; END IF;
    PERFORM pg_advisory_xact_lock(730021);
    cutoff=clock_timestamp()-days*interval '1 day';
    SELECT array_agg(task_id) INTO ids FROM (SELECT task_id FROM tasks
        WHERE status IN ('completed','failed','canceled') AND updated_at<cutoff AND retained_at IS NULL
        ORDER BY task_id FOR UPDATE SKIP LOCKED) picked;
    ids=COALESCE(ids,'{}'::uuid[]);
    -- Preserve stored final answers, including pre-retention CLI/evaluator paths.
    UPDATE tasks t SET result=COALESCE(t.result,
        (SELECT s.report FROM task_state s WHERE s.task_id=t.task_id),
        (SELECT e.payload->'response' FROM events e WHERE e.task_id=t.task_id AND e.type='eval_result'
         AND jsonb_typeof(e.payload->'response')='object' ORDER BY e.seq DESC LIMIT 1)) WHERE t.task_id=ANY(ids);
    DELETE FROM events WHERE task_id=ANY(ids) AND created_at<cutoff;
    GET DIAGNOSTICS deleted_events=ROW_COUNT;
    -- Keep references from final answers, findings, surviving events/boards and
    -- source-result chains. UUID extraction conservatively retains extra matches.
    WITH RECURSIVE roots(id) AS (
        SELECT retained_result_refs(result) FROM tasks WHERE result IS NOT NULL
        UNION SELECT retained_result_refs(evidence) FROM memories WHERE evidence IS NOT NULL
        UNION SELECT retained_result_refs(payload) FROM events
        UNION SELECT retained_result_refs(subtasks) FROM task_state WHERE NOT(task_id=ANY(ids))
        UNION SELECT result_id FROM query_results WHERE NOT(task_id=ANY(ids)) OR created_at>=cutoff
    ), refs(id) AS (
        SELECT id FROM roots UNION SELECT q.source_result_id FROM query_results q JOIN refs r ON q.result_id=r.id
        WHERE q.source_result_id IS NOT NULL
    ) SELECT array_agg(id) INTO kept FROM refs;
    kept=COALESCE(kept,'{}'::uuid[]);
    DELETE FROM tool_calls WHERE task_id=ANY(ids);
    DELETE FROM query_results WHERE task_id=ANY(ids) AND created_at<cutoff AND NOT(result_id=ANY(kept));
    GET DIAGNOSTICS deleted_results=ROW_COUNT;
    DELETE FROM task_state WHERE task_id=ANY(ids);
    DELETE FROM model_reservations WHERE task_id=ANY(ids);
    UPDATE tasks SET question='[retained final answer]',run_config='{}',error=NULL,traceparent=NULL,
        lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,retained_at=clock_timestamp() WHERE task_id=ANY(ids);
    report=jsonb_build_object('days',days,'tasks_redacted',cardinality(ids),'events_deleted',deleted_events,'results_deleted',deleted_results);
    INSERT INTO maintenance_audit(action,details) VALUES('retention',report);
    RETURN report;
END $$;

CREATE FUNCTION delete_user_data(subject uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public SET olist.maintenance='on' AS $$
DECLARE deleted bigint; report jsonb;
BEGIN
    PERFORM pg_advisory_xact_lock(730021);
    PERFORM 1 FROM users WHERE user_id=subject FOR UPDATE;
    DELETE FROM users WHERE user_id=subject;
    GET DIAGNOSTICS deleted=ROW_COUNT;
    report=jsonb_build_object('users_deleted',deleted);
    INSERT INTO maintenance_audit(action,subject_id,details) VALUES('user_delete',subject,report);
    RETURN report;
END $$;
REVOKE ALL ON FUNCTION retain_task_details(integer),delete_user_data(uuid),retained_result_refs(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION retain_task_details(integer),delete_user_data(uuid) TO agent_app;
