-- database: olist
CREATE TABLE data_change_counter (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    version bigint NOT NULL DEFAULT 0 CHECK(version>=0)
);
INSERT INTO data_change_counter(singleton,version) VALUES(true,0);
GRANT SELECT ON data_change_counter TO agent_ro;
CREATE FUNCTION advance_data_version() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
BEGIN
    UPDATE data_change_counter SET version=version+1 WHERE singleton;
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION advance_data_version() FROM PUBLIC;
DO $$ DECLARE name text; BEGIN
    FOREACH name IN ARRAY ARRAY['customers','orders','order_items','order_payments','order_reviews',
        'products','sellers','geolocation','product_category_name_translation'] LOOP
        EXECUTE format('CREATE TRIGGER data_version_write AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION advance_data_version()',name);
    END LOOP;
END $$;
CREATE FUNCTION current_data_version() RETURNS text LANGUAGE sql STABLE
SET search_path=pg_catalog,public AS $$
    SELECT i.data_version || ':' || c.version::text FROM data_imports i CROSS JOIN data_change_counter c
    WHERE c.singleton ORDER BY i.import_id DESC LIMIT 1;
$$;
REVOKE ALL ON FUNCTION current_data_version() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION current_data_version() TO agent_ro;
