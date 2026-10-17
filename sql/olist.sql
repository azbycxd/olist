CREATE TABLE IF NOT EXISTS customers (
    customer_id text PRIMARY KEY,
    customer_unique_id text NOT NULL,
    customer_zip_code_prefix varchar(5) NOT NULL,
    customer_city text NOT NULL,
    customer_state varchar(2) NOT NULL
);
CREATE INDEX IF NOT EXISTS customers_unique_id_idx ON customers (customer_unique_id);
CREATE INDEX IF NOT EXISTS customers_state_idx ON customers (customer_state);

CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geolocation_zip_code_prefix varchar(5) NOT NULL,
    geolocation_lat double precision NOT NULL,
    geolocation_lng double precision NOT NULL,
    geolocation_city text NOT NULL,
    geolocation_state varchar(2) NOT NULL
);
CREATE INDEX IF NOT EXISTS geolocation_zip_idx ON geolocation (geolocation_zip_code_prefix);

CREATE TABLE IF NOT EXISTS product_category_name_translation (
    product_category_name text PRIMARY KEY,
    product_category_name_english text NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id text PRIMARY KEY,
    product_category_name text,
    product_name_lenght integer,
    product_description_lenght integer,
    product_photos_qty integer,
    product_weight_g integer,
    product_length_cm integer,
    product_height_cm integer,
    product_width_cm integer
);
CREATE INDEX IF NOT EXISTS products_category_idx ON products (product_category_name);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id text PRIMARY KEY,
    seller_zip_code_prefix varchar(5) NOT NULL,
    seller_city text NOT NULL,
    seller_state varchar(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id text PRIMARY KEY,
    customer_id text NOT NULL REFERENCES customers(customer_id),
    order_status text NOT NULL,
    order_purchase_timestamp timestamp NOT NULL,
    order_approved_at timestamp,
    order_delivered_carrier_date timestamp,
    order_delivered_customer_date timestamp,
    order_estimated_delivery_date timestamp NOT NULL
);
CREATE INDEX IF NOT EXISTS orders_customer_idx ON orders (customer_id);
CREATE INDEX IF NOT EXISTS orders_purchase_idx ON orders (order_purchase_timestamp);
CREATE INDEX IF NOT EXISTS orders_status_idx ON orders (order_status);

CREATE TABLE IF NOT EXISTS order_items (
    order_id text NOT NULL REFERENCES orders(order_id),
    order_item_id integer NOT NULL,
    product_id text NOT NULL REFERENCES products(product_id),
    seller_id text NOT NULL REFERENCES sellers(seller_id),
    shipping_limit_date timestamp NOT NULL,
    price numeric(12,2) NOT NULL,
    freight_value numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS order_items_product_idx ON order_items (product_id);
CREATE INDEX IF NOT EXISTS order_items_seller_idx ON order_items (seller_id);

CREATE TABLE IF NOT EXISTS order_payments (
    order_id text NOT NULL REFERENCES orders(order_id),
    payment_sequential integer NOT NULL,
    payment_type text NOT NULL,
    payment_installments integer NOT NULL,
    payment_value numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS order_reviews (
    review_id text NOT NULL,
    order_id text NOT NULL REFERENCES orders(order_id),
    review_score integer NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title text,
    review_comment_message text,
    review_creation_date timestamp NOT NULL,
    review_answer_timestamp timestamp NOT NULL,
    PRIMARY KEY (review_id, order_id)
);
CREATE INDEX IF NOT EXISTS order_reviews_order_idx ON order_reviews (order_id);

CREATE TABLE IF NOT EXISTS data_imports (
    import_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_version text NOT NULL,
    manifest jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE data_imports IS 'Successful CSV imports with source hashes and verified row counts';
COMMENT ON TABLE customers IS 'Order-level customer IDs; customer_unique_id identifies returning customers';
COMMENT ON TABLE geolocation IS 'Raw geolocation rows; ZIP codes are not unique';
COMMENT ON TABLE products IS 'Source products, including untranslated or missing category names';
COMMENT ON TABLE orders IS 'Orders, statuses and source timestamps without timezone information';
COMMENT ON TABLE order_items IS 'One row per order item; price excludes freight';
COMMENT ON TABLE order_payments IS 'One row per payment sequence; orders can have multiple payments';
COMMENT ON TABLE order_reviews IS 'Review ID is not globally unique; an order can have multiple reviews';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_ro;
