CREATE TABLE interactive_confirmations (
 workspace_id INTEGER NOT NULL,
 application TEXT NOT NULL,
 request_id TEXT NOT NULL,
 state TEXT NOT NULL,
 PRIMARY KEY(workspace_id, application, request_id),
 FOREIGN KEY(workspace_id,application,request_id)
  REFERENCES interactive_requests(workspace_id,application,request_id)
);
