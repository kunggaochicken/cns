CREATE NODE TABLE IF NOT EXISTS Thought(
  id STRING, content STRING, source STRING, created_at TIMESTAMP,
  metadata STRING, embedding_id STRING, content_hash STRING,
  PRIMARY KEY (id)
);

// Backfill column for DBs created before content_hash existed.
ALTER TABLE Thought ADD IF NOT EXISTS content_hash STRING DEFAULT '';

// UMAP 2D coords for frontend brain-view positioning. NULL until first
// `gigabrain umap recompute` run. Visualization-only — NOT a graph atom.
// IMPORTANT: do NOT add `DEFAULT NULL` — Kuzu 0.11 cannot bind a NULL literal
// in a DEFAULT clause, the WAL records the failed DDL, and the DB fails to
// reopen with "Trying to create a vector with ANY type". Omitting DEFAULT
// produces the same nullable-NULL behavior we want.
ALTER TABLE Thought ADD IF NOT EXISTS umap_x DOUBLE;
ALTER TABLE Thought ADD IF NOT EXISTS umap_y DOUBLE;

CREATE NODE TABLE IF NOT EXISTS Bet(
  id STRING, slug STRING, title STRING, vault_path STRING,
  owner STRING, horizon STRING, confidence STRING, created_at TIMESTAMP,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Task(
  id STRING, linear_id STRING, title STRING, status STRING,
  created_at TIMESTAMP, embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Decision(
  id STRING, content STRING, decided_at TIMESTAMP, decided_by STRING,
  reasoning STRING, embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Conflict(
  id STRING, summary STRING, severity STRING, detected_at TIMESTAMP,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Outcome(
  id STRING, summary STRING, success BOOL, recorded_at TIMESTAMP,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS AgentFiring(
  id STRING, agent_id STRING, trace_id STRING, started_at TIMESTAMP,
  completed_at TIMESTAMP, outcome STRING, embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS CodeChange(
  id STRING, repo STRING, sha STRING, summary STRING, created_at TIMESTAMP,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Conversation(
  id STRING, summary STRING, vault_path STRING, created_at TIMESTAMP,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Doc(
  id STRING, vault_path STRING, title STRING, updated_at TIMESTAMP,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS GateItem(
  id STRING, prompt STRING, urgency STRING, created_at TIMESTAMP,
  resolved_at TIMESTAMP, decision STRING, reasoning STRING,
  embedding_id STRING,
  PRIMARY KEY (id)
);

CREATE NODE TABLE IF NOT EXISTS Agent(
  id STRING, role STRING, persona STRING, state STRING,
  current_firing STRING, last_active TIMESTAMP,
  created_at TIMESTAMP, enabled BOOL, embedding_id STRING,
  PRIMARY KEY (id)
);
