#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    --set=reader_password="$AGENT_RO_PASSWORD" --set=app_password="$AGENT_DB_PASSWORD" <<'SQL'
CREATE ROLE agent_ro LOGIN PASSWORD :'reader_password';
ALTER ROLE agent_ro SET statement_timeout = '10s';
ALTER ROLE agent_ro SET default_transaction_read_only = on;
CREATE ROLE agent_app LOGIN PASSWORD :'app_password';
CREATE DATABASE olist;
CREATE DATABASE agent;
REVOKE ALL ON DATABASE olist FROM PUBLIC;
REVOKE ALL ON DATABASE agent FROM PUBLIC;
GRANT CONNECT ON DATABASE olist TO agent_ro;
GRANT CONNECT ON DATABASE agent TO agent_app;
\connect olist
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agent_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE olist_admin IN SCHEMA public
    GRANT SELECT ON TABLES TO agent_ro;
\connect agent
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agent_app;
CREATE EXTENSION IF NOT EXISTS vector;
SQL
