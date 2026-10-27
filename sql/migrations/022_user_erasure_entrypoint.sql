-- database: agent
-- User erasure must pass the audited SECURITY DEFINER entrypoint. Retention
-- retains independent aggregate metrics; application SQL cannot bypass audit.
REVOKE DELETE ON users FROM agent_app;
