-- ============================================================
-- Mother v2 日志系统 — SQLite Schema
-- 五层日志：events → tasks → steps → error_patterns → metrics
-- ============================================================

-- L1: 事件流（最底层，记录一切）
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    source      TEXT NOT NULL,
    parent_id   TEXT,
    task_id     TEXT,
    data        TEXT,            -- JSON
    level       TEXT DEFAULT 'INFO'
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);

-- L2: 任务追踪（按用户请求聚合）
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    user_input  TEXT NOT NULL,
    user_id     TEXT DEFAULT '',
    status      TEXT DEFAULT 'running',   -- running | done | error
    started_at  REAL,
    finished_at REAL,
    tool_calls  INTEGER DEFAULT 0,
    llm_rounds  INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    result      TEXT,
    error       TEXT
);

-- L3: 步骤追踪（每个工具调用）
CREATE TABLE IF NOT EXISTS steps (
    step_id     TEXT PRIMARY KEY,
    task_id     TEXT REFERENCES tasks(task_id),
    tool_name   TEXT NOT NULL,
    arguments   TEXT,             -- JSON
    status      TEXT DEFAULT 'pending',  -- pending | running | done | error
    started_at  REAL,
    finished_at REAL,
    result      TEXT,
    error       TEXT,
    retry_of    TEXT,             -- 如果是重试，指向原始 step_id
    self_healed INTEGER DEFAULT 0 -- 是否经自我修正后成功
);
CREATE INDEX IF NOT EXISTS idx_steps_task ON steps(task_id);

-- L4: 错误模式（聚合识别）
CREATE TABLE IF NOT EXISTS error_patterns (
    pattern_id  TEXT PRIMARY KEY,
    pattern     TEXT NOT NULL,    -- 人类可读的描述，如 "字段名与字段ID混淆"
    category    TEXT DEFAULT '',  -- api_format | permission | logic | timeout
    count       INTEGER DEFAULT 1,
    first_seen  REAL,
    last_seen   REAL,
    root_cause  TEXT,
    suggestion  TEXT,             -- 自动生成的修复建议
    resolved    INTEGER DEFAULT 0 -- 是否已通过提示词优化解决
);

-- L5: 每日指标（汇总）
CREATE TABLE IF NOT EXISTS metrics (
    date            TEXT PRIMARY KEY,  -- '2026-07-17'
    tasks_total     INTEGER DEFAULT 0,
    tasks_passed    INTEGER DEFAULT 0,
    tasks_failed    INTEGER DEFAULT 0,
    avg_llm_rounds  REAL DEFAULT 0,
    avg_latency_ms  REAL DEFAULT 0,
    tokens_total    INTEGER DEFAULT 0,
    cost_estimate   REAL DEFAULT 0,
    self_heal_count INTEGER DEFAULT 0,
    self_heal_success INTEGER DEFAULT 0
);
