CREATE TABLE interactive_definitions (
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  application TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
  definition TEXT NOT NULL, PRIMARY KEY(workspace_id, application, id, version)
);
CREATE TABLE interactive_requests (
  workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
  application TEXT NOT NULL, request_id TEXT NOT NULL, body TEXT NOT NULL,
  channel TEXT NOT NULL, nonce TEXT NOT NULL UNIQUE, buttons TEXT NOT NULL,
  delivery TEXT NOT NULL, message_ts TEXT, response TEXT, team_id TEXT NOT NULL, app_id TEXT NOT NULL,
  PRIMARY KEY(workspace_id, application, request_id)
);
