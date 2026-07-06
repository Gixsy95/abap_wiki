-- ============================================================================
-- abap_wiki - SQLite schema (single source of transactional truth for the pipeline)
--
-- What it does: defines the complete SQLite schema - the sole transactional source of truth for
--   the pipeline (objects, dependencies, tasks/lease, gate_decisions, events, slices/gaps L2, ...).
-- How it works: only CREATE TABLE/INDEX/TRIGGER ... IF NOT EXISTS (always the LATEST version);
--   UNIQUE/CHECK constraints and triggers (monotone doc_level, graph bidirectionality) enforce
--   invariants by design. Version is managed in Python (db.SCHEMA_VERSION + migrations/).
-- Connections: applied by core/src/tools/db.py (init_db / apply_migrations); the CHECK enums are
--   aligned 1:1 with core/src/tools/sap_types.py; incremental migrations live in
--   core/src/db/migrations/. Tests: test_migrations.py, test_state_transitions.py.
--
-- Principles (see core/docs/01-pipeline-l0-l1.md):
--   * ONE row per SAP object, global key UNIQUE(sap_type, sap_name):
--     cross-devclass duplicates are an IntegrityError, not a second page.
--   * The filesystem (wiki pages) is a PROJECTION of the rows, never the key.
--   * The dependency graph lives here: used_by/effectively_used_by are views;
--     bidirectionality cannot diverge by construction.
--   * Tasks have an expiring LEASE: an expired lease is re-claimable,
--     zombies are impossible by design.
--   * Every state transition is recorded in events (audit trail).
--
-- Schema version: managed in Python (db.SCHEMA_VERSION + core/src/db/migrations/).
-- This file is ALWAYS the LATEST version (CREATE ... IF NOT EXISTS); init_db sets
-- user_version on new DBs and applies incremental migrations on existing ones.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Object registry
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS objects (
  id               INTEGER PRIMARY KEY,
  sap_name         TEXT NOT NULL,              -- verbatim TADIR, normalised UPPER
  sap_type         TEXT NOT NULL,              -- unique mapping in sap_types.py
  tadir_object     TEXT DEFAULT '',            -- PROG, CLAS, FUGR, ...
  pgmid            TEXT DEFAULT 'R3TR',
  devclass         TEXT DEFAULT '',            -- custom: from TADIR; standard: from MCP ('' while pending)
  is_custom        INTEGER NOT NULL DEFAULT 0,
  namespace        TEXT DEFAULT '',            -- 'Z' | 'Y' | '/ECRS/' | 'standard' | ...
  author           TEXT DEFAULT '',
  created_on       TEXT DEFAULT '',
  changed_on       TEXT DEFAULT '',
  srcsystem        TEXT DEFAULT '',
  origin           TEXT NOT NULL CHECK (origin IN
                     ('tadir','dependency-custom','dependency-standard','manual')),
  derivation_depth INTEGER NOT NULL DEFAULT 0,
  deleted_in_tadir INTEGER NOT NULL DEFAULT 0, -- flag "Object already deleted": tracked, excluded from the queue
  -- state machine (allowed transitions defined in sap_types.ALLOWED_TRANSITIONS)
  state            TEXT NOT NULL DEFAULT 'pending' CHECK (state IN
                     ('pending','l0_done','l1_ready','l1_skipped',
                      'authoring','authored','deepchecking',
                      'gate_accepted','gate_rejected','gate_blocked',
                      'applying','applied','failed',
                      'std_discovered','std_stub_written','std_resolved','std_unresolved')),
  doc_level        TEXT NOT NULL DEFAULT '' CHECK (doc_level IN ('','L0','L1','L2','L3')),
  -- source
  raw_source_path  TEXT DEFAULT '',
  raw_source_status TEXT NOT NULL DEFAULT '' CHECK (raw_source_status IN
                     ('','available','missing','partial','stub','unavailable')),
  source_bytes     INTEGER,
  source_code_lines INTEGER,                   -- non-comment non-blank lines (stub classification)
  source_hash      TEXT DEFAULT '',            -- md5(bytes)[:8] COMPUTED BY PYTHON, never by an LLM
  -- filesystem projection (derived, never the key)
  slug             TEXT NOT NULL,
  wiki_page_path   TEXT DEFAULT '',
  page_sha256      TEXT DEFAULT '',            -- for the crash-recovery check
  -- L1 metrics (cached; the ground truth for edges is in dependencies)
  l1_completed_at  TEXT,
  l1_attempts      INTEGER NOT NULL DEFAULT 0,
  dep_total INTEGER, dep_custom INTEGER, dep_standard INTEGER,
  bug_total INTEGER, bug_blocker INTEGER, bug_major INTEGER,
  bug_minor INTEGER, bug_smell INTEGER, bug_dead_code INTEGER,
  patterns_count INTEGER,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (sap_type, sap_name)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_objects_slug ON objects(slug);
CREATE INDEX IF NOT EXISTS ix_objects_state ON objects(state);
CREATE INDEX IF NOT EXISTS ix_objects_devclass ON objects(devclass, state);
CREATE INDEX IF NOT EXISTS ix_objects_name_nocase ON objects(sap_name COLLATE NOCASE);

-- doc_level can only increase (inviolable rule, enforced by the DB engine).
-- Explicit map ''=0 < L0=1 < L1=2 < L2=3 < L3=4.
CREATE TRIGGER IF NOT EXISTS trg_doc_level_monotone
BEFORE UPDATE OF doc_level ON objects
WHEN (CASE NEW.doc_level WHEN '' THEN 0 WHEN 'L0' THEN 1 WHEN 'L1' THEN 2
                         WHEN 'L2' THEN 3 WHEN 'L3' THEN 4 END)
   < (CASE OLD.doc_level WHEN '' THEN 0 WHEN 'L0' THEN 1 WHEN 'L1' THEN 2
                         WHEN 'L2' THEN 3 WHEN 'L3' THEN 4 END)
BEGIN
  SELECT RAISE(ABORT, 'doc_level downgrade forbidden');
END;

-- ----------------------------------------------------------------------------
-- Runs and batches
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
  run_id     TEXT PRIMARY KEY,                 -- e.g. 'run-20260615-073000'
  role       TEXT NOT NULL CHECK (role IN ('author','deepcheck','apply','mixed')),
  started_at TEXT NOT NULL,
  ended_at   TEXT,
  git_sha_start TEXT DEFAULT '',
  notes      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS batches (
  batch_id   TEXT PRIMARY KEY,                 -- e.g. 'b-20260615-074512'
  run_id     TEXT NOT NULL REFERENCES runs(run_id),
  created_at TEXT NOT NULL,
  size       INTEGER,
  package_filter TEXT DEFAULT '',
  git_commit_sha TEXT DEFAULT ''
);

-- ----------------------------------------------------------------------------
-- Claimable tasks (the LEASE lives here, not on the object)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY,
  object_id   INTEGER NOT NULL REFERENCES objects(id),
  kind        TEXT NOT NULL CHECK (kind IN
               ('l0_stub','l1_author','l1_deepcheck','l1_apply','mcp_lookup','project')),
  status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN
               ('queued','claimed','done','failed','cancelled')),
  attempt     INTEGER NOT NULL DEFAULT 0,      -- incremented AT CLAIM
  max_attempts INTEGER NOT NULL DEFAULT 3,
  run_id      TEXT REFERENCES runs(run_id),
  batch_id    TEXT REFERENCES batches(batch_id),
  worker_id   TEXT DEFAULT '',
  claimed_at  TEXT, lease_expires_at TEXT, heartbeat_at TEXT,
  started_at  TEXT, finished_at TEXT, duration_sec REAL,
  input_ref   TEXT DEFAULT '',
  output_ref  TEXT DEFAULT '',
  error       TEXT DEFAULT ''                  -- truncated to 300 chars by the code
);
-- at most ONE active task per (object, kind)
CREATE UNIQUE INDEX IF NOT EXISTS ix_tasks_active ON tasks(object_id, kind)
  WHERE status IN ('queued','claimed');
CREATE INDEX IF NOT EXISTS ix_tasks_claim ON tasks(kind, status, lease_expires_at);
CREATE INDEX IF NOT EXISTS ix_tasks_batch ON tasks(batch_id);

-- ----------------------------------------------------------------------------
-- Dependency graph: edges ONLY. used_by = reverse query.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dependencies (
  id            INTEGER PRIMARY KEY,
  src_object_id INTEGER NOT NULL REFERENCES objects(id),
  tgt_object_id INTEGER NOT NULL REFERENCES objects(id),
  dep_kind      TEXT NOT NULL DEFAULT 'uses',
  call_context  TEXT DEFAULT '',
  is_effective  INTEGER NOT NULL DEFAULT 0,
  validated     TEXT NOT NULL DEFAULT 'pending' CHECK (validated IN
                 ('pending','confirmed','corrected','rejected')),
  validation_note TEXT DEFAULT '',
  first_seen_batch TEXT DEFAULT '',
  CHECK (src_object_id <> tgt_object_id),      -- self-dependencies impossible
  UNIQUE (src_object_id, tgt_object_id, dep_kind)
);
CREATE INDEX IF NOT EXISTS ix_dep_tgt ON dependencies(tgt_object_id);

-- ----------------------------------------------------------------------------
-- Deepcheck gate verdicts
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS verdicts (
  id              INTEGER PRIMARY KEY,
  object_id       INTEGER NOT NULL REFERENCES objects(id),
  deepcheck_task_id INTEGER NOT NULL REFERENCES tasks(id),
  author_task_id  INTEGER NOT NULL REFERENCES tasks(id),
  author_yaml_sha256 TEXT NOT NULL,            -- freezes the judged artifact
  outcome         TEXT NOT NULL CHECK (outcome IN ('accept','reject','blocked')),
  claims_total INTEGER, claims_not_supported INTEGER,
  deps_confirmed INTEGER, deps_rejected INTEGER,
  verdict_path    TEXT NOT NULL,
  payload_json    TEXT DEFAULT '{}',
  decided_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_verdicts_obj ON verdicts(object_id, decided_at);

-- ----------------------------------------------------------------------------
-- SAP standard accumulator (row created AT DISCOVERY, status tracks MCP)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS standard_lookup (
  object_id     INTEGER PRIMARY KEY REFERENCES objects(id),
  lookup_status TEXT NOT NULL DEFAULT 'pending' CHECK (lookup_status IN
                 ('pending','success','not-found','error')),
  attempts      INTEGER NOT NULL DEFAULT 0,
  last_attempt_at TEXT,
  resolved_devclass TEXT DEFAULT '',
  last_error    TEXT DEFAULT ''
);

-- ----------------------------------------------------------------------------
-- Persistent intermediate artifacts (every step repeatable without re-invoking the LLM)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifacts (
  id         INTEGER PRIMARY KEY,
  object_id  INTEGER NOT NULL REFERENCES objects(id),
  task_id    INTEGER REFERENCES tasks(id),
  kind       TEXT NOT NULL CHECK (kind IN
              ('author_yaml','deps_json','summary_md','analysis_doc','deepcheck_json')),
  path       TEXT NOT NULL,
  sha256     TEXT NOT NULL,
  bytes      INTEGER NOT NULL,
  verified   INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (object_id, kind, task_id)
);

-- ----------------------------------------------------------------------------
-- Append-only event log (dashboard, throughput, transition audit)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
  id        INTEGER PRIMARY KEY,
  ts        TEXT NOT NULL DEFAULT (datetime('now')),
  run_id    TEXT, batch_id TEXT, object_id INTEGER, task_id INTEGER,
  event     TEXT NOT NULL,                     -- 'claim','author_done','verdict','apply','state:<from>-><to>',...
  payload   TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);

-- ----------------------------------------------------------------------------
-- Dependency guardrail warnings (the md report is a projection)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dep_warnings (
  id INTEGER PRIMARY KEY,
  object_id INTEGER NOT NULL REFERENCES objects(id),
  batch_id TEXT DEFAULT '',
  warn_type TEXT NOT NULL,                     -- name-not-in-source|ns-autocorrect|field-not-object|...
  dep_name TEXT DEFAULT '',
  detail TEXT DEFAULT '',
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- Shared pages to be regenerated on the next 'project' run
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dirty_pages (
  object_id INTEGER PRIMARY KEY REFERENCES objects(id),
  reason TEXT DEFAULT '',
  marked_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- Gate quality (decisions, spot-checks, overrides)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gate_decisions (
  id          INTEGER PRIMARY KEY,
  run_id      TEXT, batch_id TEXT,
  object_id   INTEGER NOT NULL REFERENCES objects(id),
  attempt     INTEGER NOT NULL DEFAULT 1,
  outcome     TEXT NOT NULL CHECK (outcome IN ('accept','revert','blocked','revert-hygiene')),
  s1_bug_ns_high INTEGER DEFAULT 0,
  s2_dep_rejected_high INTEGER DEFAULT 0,
  s3_other_ns_high INTEGER DEFAULT 0,
  reasons_json TEXT DEFAULT '[]',
  override_id INTEGER,
  decided_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_gate_decisions_obj ON gate_decisions(object_id);

CREATE TABLE IF NOT EXISTS spot_checks (
  id          INTEGER PRIMARY KEY,
  checked_at  TEXT NOT NULL DEFAULT (datetime('now')),
  object_id   INTEGER NOT NULL REFERENCES objects(id),
  accepted_run_id TEXT DEFAULT '',
  semantic_accuracy REAL,
  verdict     TEXT CHECK (verdict IN ('CONFIRM','MINOR_ISSUES','MAJOR_ISSUES')),
  defects_json TEXT DEFAULT '[]',
  seed        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS gate_overrides (
  id          INTEGER PRIMARY KEY,
  run_id      TEXT NOT NULL,
  object_id   INTEGER REFERENCES objects(id),
  operator    TEXT NOT NULL,                   -- who authorised (mandatory)
  reason      TEXT NOT NULL,                   -- justification (mandatory)
  threshold_used INTEGER NOT NULL,             -- S3 threshold used instead of the default
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- L2 process (tables ready; tooling on roadmap - see core/docs/03-l2-process.md)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slices (
  slice_id  TEXT PRIMARY KEY,
  title     TEXT NOT NULL,
  owner     TEXT NOT NULL,                     -- lint blocks 'TBD'
  status    TEXT NOT NULL DEFAULT 'draft' CHECK (status IN
             ('draft','researching','awaiting-experts','l2-complete')),
  manifest_path TEXT NOT NULL,
  last_qa   TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS slice_membership (
  slice_id  TEXT NOT NULL REFERENCES slices(slice_id),
  object_id INTEGER NOT NULL REFERENCES objects(id),
  hop       INTEGER NOT NULL,
  role      TEXT DEFAULT '',                   -- anchor|member|utility|context
  source    TEXT NOT NULL DEFAULT 'derived' CHECK (source IN ('derived','anchor')),
  PRIMARY KEY (slice_id, object_id)
);

CREATE TABLE IF NOT EXISTS gaps (
  gap_id    TEXT PRIMARY KEY,
  slice_id  TEXT NOT NULL REFERENCES slices(slice_id),
  class     TEXT NOT NULL CHECK (class IN
             ('PURPOSE','TRIGGER','ACTOR','FIELD-SEMANTICS','BUSINESS-RULE',
              'INTEGRATION','DATA-LIFECYCLE','CONFIG')),
  load_bearing INTEGER NOT NULL DEFAULT 0,
  description TEXT NOT NULL,
  hypothesis  TEXT DEFAULT '',
  confidence  TEXT DEFAULT '' CHECK (confidence IN ('','high','medium','low')),
  status    TEXT NOT NULL DEFAULT 'open' CHECK (status IN
             ('open','auto-answered','asked','answered','wont-answer')),
  resolution_ref TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  closed_at  TEXT
);

CREATE TABLE IF NOT EXISTS gap_entities (
  gap_id    TEXT NOT NULL REFERENCES gaps(gap_id),
  object_id INTEGER NOT NULL REFERENCES objects(id),
  PRIMARY KEY (gap_id, object_id)
);

CREATE TABLE IF NOT EXISTS questions (
  question_id TEXT PRIMARY KEY,
  gap_id      TEXT NOT NULL REFERENCES gaps(gap_id),
  questionnaire_file TEXT NOT NULL,
  recipient   TEXT NOT NULL,
  assigned_to TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'sent' CHECK (status IN
                ('draft','sent','partially-answered','closed')),
  sent_at     TEXT,
  answered_at TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
  id        INTEGER PRIMARY KEY,
  file_path TEXT NOT NULL,
  source    TEXT NOT NULL CHECK (source IN ('mcp','wiki','raw-docs','sap-standard','expert')),
  query     TEXT DEFAULT '',
  date      TEXT NOT NULL,
  gap_id    TEXT REFERENCES gaps(gap_id)
);

-- ----------------------------------------------------------------------------
-- Views (projections, no duplicated state)
-- ----------------------------------------------------------------------------

-- used_by computed, never stored
CREATE VIEW IF NOT EXISTS v_used_by AS
  SELECT d.tgt_object_id AS object_id,
         s.slug          AS used_by_slug,
         d.dep_kind, d.is_effective
  FROM dependencies d
  JOIN objects s ON s.id = d.src_object_id
  WHERE d.validated IN ('confirmed','corrected');

-- layout compatible with the old state file (for Excel export)
CREATE VIEW IF NOT EXISTS v_export_l1 AS
  SELECT o.tadir_object AS obj_type, o.sap_name AS obj_name, o.devclass,
         o.state, o.doc_level, o.l1_attempts, o.l1_completed_at,
         o.source_hash, o.raw_source_status,
         o.dep_total, o.dep_custom, o.dep_standard,
         o.bug_total, o.bug_blocker, o.bug_major, o.bug_minor, o.bug_smell,
         o.bug_dead_code, o.patterns_count,
         t.batch_id, t.run_id, t.error AS last_error, t.duration_sec
  FROM objects o
  LEFT JOIN tasks t ON t.object_id = o.id AND t.kind = 'l1_author'
       AND t.id = (SELECT MAX(id) FROM tasks WHERE object_id = o.id AND kind = 'l1_author');
