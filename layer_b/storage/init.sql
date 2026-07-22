CREATE TABLE sessions (
    session_id       UUID PRIMARY KEY,
    parent_goal      TEXT,
    agent_type       TEXT,
    started_at       TIMESTAMPTZ DEFAULT now(),
    ended_at         TIMESTAMPTZ,
    final_decision   TEXT,
    total_steps      INT
);

CREATE TABLE intent_events (
    intent_id            UUID PRIMARY KEY,
    session_id           UUID REFERENCES sessions(session_id),
    step_id              TEXT NOT NULL,
    step_index           INT,
    node_name            TEXT,
    parent_goal          TEXT,
    current_objective    TEXT,
    available_tools      JSONB,
    selected_action      TEXT,
    selection_rationale  TEXT,
    guardrail_checks     JSONB,
    goal_alignment_check TEXT,
    created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE logit_telemetry (
    id               BIGSERIAL PRIMARY KEY,
    session_id       UUID,
    step_id          TEXT,
    request_id       TEXT,
    timestamp_ns     BIGINT,
    top_k_token_ids  JSONB,
    top_k_probs      JSONB,
    sampling_margin  DOUBLE PRECISION,
    fragility_flag   BOOLEAN,
    confidence_label TEXT
);

CREATE TABLE moe_telemetry (
    id                 BIGSERIAL PRIMARY KEY,
    session_id         UUID,
    step_id            TEXT,
    timestamp_ns       BIGINT,
    layer_idx          INT,
    num_experts_total  INT,
    experts_per_token  INT,
    avg_routing_margin DOUBLE PRECISION,
    routing_fragile    BOOLEAN,
    expert_load        JSONB
);

CREATE TABLE hardware_telemetry (
    id                   BIGSERIAL PRIMARY KEY,
    timestamp_ns         BIGINT,
    gpu_vram_used_gb     DOUBLE PRECISION,
    gpu_vram_pressure    DOUBLE PRECISION,
    gpu_sm_utilization   DOUBLE PRECISION,
    gpu_memory_bandwidth DOUBLE PRECISION,
    gpu_temperature_c    DOUBLE PRECISION,
    gpu_power_watts      DOUBLE PRECISION
);

CREATE TABLE sglang_metrics (
    id               BIGSERIAL PRIMARY KEY,
    timestamp_ns     BIGINT,
    ttft_ms          DOUBLE PRECISION,
    tokens_per_sec   DOUBLE PRECISION,
    queue_depth      INT,
    kv_cache_usage   DOUBLE PRECISION,
    running_requests INT,
    latency_p95_ms   DOUBLE PRECISION
);

CREATE TABLE failure_reports (
    id               BIGSERIAL PRIMARY KEY,
    session_id       UUID,
    failed_at_step   INT,
    category         TEXT,
    evidence         JSONB,
    recommended_fix  TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Indexes for query performance
CREATE INDEX idx_intent_session ON intent_events(session_id);
CREATE INDEX idx_logit_session  ON logit_telemetry(session_id, step_id);
CREATE INDEX idx_moe_session    ON moe_telemetry(session_id, step_id);
CREATE INDEX idx_logit_fragile  ON logit_telemetry(fragility_flag) WHERE fragility_flag = true;
