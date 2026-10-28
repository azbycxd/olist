-- database: olist
CREATE TABLE order_scope (
    order_id text PRIMARY KEY REFERENCES orders(order_id) ON UPDATE CASCADE ON DELETE CASCADE,
    customer_state varchar(2) NOT NULL
);
GRANT SELECT ON order_scope TO agent_ro;
CREATE TRIGGER data_version_write AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON order_scope
FOR EACH STATEMENT EXECUTE FUNCTION advance_data_version();
INSERT INTO order_scope SELECT o.order_id,c.customer_state FROM orders o JOIN customers c USING(customer_id);

CREATE FUNCTION sync_order_scope_orders() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
    -- Serialize with concurrent customer state edits before taking the state snapshot.
    PERFORM c.customer_id FROM public.customers c JOIN new_orders n USING(customer_id)
        ORDER BY c.customer_id FOR SHARE OF c;
    INSERT INTO public.order_scope(order_id,customer_state)
        SELECT n.order_id,c.customer_state FROM new_orders n JOIN public.customers c USING(customer_id)
        ON CONFLICT(order_id) DO UPDATE SET customer_state=excluded.customer_state;
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION sync_order_scope_orders() FROM PUBLIC;
CREATE TRIGGER order_scope_insert AFTER INSERT ON orders REFERENCING NEW TABLE AS new_orders
FOR EACH STATEMENT EXECUTE FUNCTION sync_order_scope_orders();
CREATE TRIGGER order_scope_update AFTER UPDATE ON orders REFERENCING NEW TABLE AS new_orders
FOR EACH STATEMENT EXECUTE FUNCTION sync_order_scope_orders();

CREATE FUNCTION sync_order_scope_customers() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
    UPDATE public.order_scope s SET customer_state=c.customer_state
        FROM public.orders o JOIN new_customers c USING(customer_id)
        WHERE s.order_id=o.order_id AND s.customer_state IS DISTINCT FROM c.customer_state;
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION sync_order_scope_customers() FROM PUBLIC;
CREATE TRIGGER order_scope_customer_update AFTER UPDATE ON customers REFERENCING NEW TABLE AS new_customers
FOR EACH STATEMENT EXECUTE FUNCTION sync_order_scope_customers();

ALTER POLICY customer_states ON customers USING (
    CASE WHEN current_setting('app.allowed_states',true)='ALL' THEN true ELSE
    customer_state=ANY(string_to_array(NULLIF(current_setting('app.allowed_states',true),''),',')) END);
ALTER POLICY order_states ON orders USING (
    CASE WHEN current_setting('app.allowed_states',true)='ALL' THEN true ELSE
    order_id IN (SELECT s.order_id FROM order_scope s WHERE
        s.customer_state=ANY(string_to_array(NULLIF(current_setting('app.allowed_states',true),''),','))) END);
ALTER POLICY item_states ON order_items USING (
    CASE WHEN current_setting('app.allowed_states',true)='ALL' THEN true ELSE
    order_id IN (SELECT s.order_id FROM order_scope s WHERE
        s.customer_state=ANY(string_to_array(NULLIF(current_setting('app.allowed_states',true),''),','))) END);
ALTER POLICY payment_states ON order_payments USING (
    CASE WHEN current_setting('app.allowed_states',true)='ALL' THEN true ELSE
    order_id IN (SELECT s.order_id FROM order_scope s WHERE
        s.customer_state=ANY(string_to_array(NULLIF(current_setting('app.allowed_states',true),''),','))) END);
ALTER POLICY review_states ON order_reviews USING (
    CASE WHEN current_setting('app.allowed_states',true)='ALL' THEN true ELSE
    order_id IN (SELECT s.order_id FROM order_scope s WHERE
        s.customer_state=ANY(string_to_array(NULLIF(current_setting('app.allowed_states',true),''),','))) END);
ANALYZE order_scope;
