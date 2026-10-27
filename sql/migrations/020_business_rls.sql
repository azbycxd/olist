-- database: olist
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agent_ro' AND (rolsuper OR rolbypassrls)) OR
       EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename IN
               ('customers','orders','order_items','order_payments','order_reviews') AND tableowner='agent_ro') THEN
        RAISE EXCEPTION 'agent_ro must not own business tables or bypass RLS';
    END IF;
END $$;
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_reviews ENABLE ROW LEVEL SECURITY;
CREATE POLICY customer_states ON customers FOR SELECT TO agent_ro USING (
    current_setting('app.allowed_states',true)='ALL' OR
    customer_state=ANY(string_to_array(NULLIF(current_setting('app.allowed_states',true),''),',')));
CREATE POLICY order_states ON orders FOR SELECT TO agent_ro USING (
    current_setting('app.allowed_states',true)='ALL' OR
    EXISTS (SELECT 1 FROM customers c WHERE c.customer_id=orders.customer_id));
CREATE POLICY item_states ON order_items FOR SELECT TO agent_ro USING (
    current_setting('app.allowed_states',true)='ALL' OR
    EXISTS (SELECT 1 FROM orders o WHERE o.order_id=order_items.order_id));
CREATE POLICY payment_states ON order_payments FOR SELECT TO agent_ro USING (
    current_setting('app.allowed_states',true)='ALL' OR
    EXISTS (SELECT 1 FROM orders o WHERE o.order_id=order_payments.order_id));
CREATE POLICY review_states ON order_reviews FOR SELECT TO agent_ro USING (
    current_setting('app.allowed_states',true)='ALL' OR
    EXISTS (SELECT 1 FROM orders o WHERE o.order_id=order_reviews.order_id));
