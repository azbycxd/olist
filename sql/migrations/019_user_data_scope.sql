-- database: agent
ALTER TABLE users ADD COLUMN data_scope text[] NOT NULL DEFAULT '{}';
ALTER TABLE users ADD CONSTRAINT users_data_scope_valid CHECK (
    data_scope = ARRAY['ALL'] OR
    (array_position(data_scope, NULL) IS NULL AND
     data_scope <@ ARRAY['AC','AL','AP','AM','BA','CE','DF','ES','GO','MA','MT','MS','MG','PA','PB','PR','PE','PI','RJ','RN','RS','RO','RR','SC','SP','SE','TO']));
-- Preserve existing users/evaluation access; new public registrations deny by default.
UPDATE users SET data_scope=ARRAY['ALL'];
