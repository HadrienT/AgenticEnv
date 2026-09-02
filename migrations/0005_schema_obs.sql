-- WP01 corelib: obs schema, used by every MCP server to record tool invocations
-- (07-ERRORS-AND-LOGGING.md §5, 04-DATA-MODEL.md §4).
CREATE SCHEMA IF NOT EXISTS obs;

CREATE TABLE IF NOT EXISTS obs.tool_invocations (
    id              text PRIMARY KEY,
    ts              timestamptz NOT NULL,
    server          text NOT NULL,
    tool            text NOT NULL,
    args            jsonb NOT NULL,
    args_sha        text NOT NULL,
    status          text NOT NULL,
    duration_ms     int NOT NULL,
    error_code      text,
    error_message   text,
    caller          text,
    correlation_id  text
);

CREATE INDEX IF NOT EXISTS ix_tool_invocations_ts ON obs.tool_invocations (ts);
CREATE INDEX IF NOT EXISTS ix_tool_invocations_server_tool ON obs.tool_invocations (server, tool);
