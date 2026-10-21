-- Carbon module audit log table
-- PostgreSQL only stores audit trail, NOT telemetry.
-- Telemetry goes through Orion-LD -> telemetry-worker -> TimescaleDB.

CREATE TABLE IF NOT EXISTS admin_platform.carbon_calculations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(63) NOT NULL,
    entity_id VARCHAR(255) NOT NULL,
    assessment_entity_id VARCHAR(255),
    tier INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
    methodology VARCHAR(100) NOT NULL,
    data_sources JSONB NOT NULL DEFAULT '[]',
    input_params JSONB NOT NULL DEFAULT '{}',
    results JSONB NOT NULL DEFAULT '{}',
    confidence DECIMAL(4, 3),
    confidence_interval_pct DECIMAL(5, 1),
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    calculated_by VARCHAR(100) NOT NULL DEFAULT 'scheduler'
);

CREATE INDEX IF NOT EXISTS idx_carbon_calculations_entity_date
    ON admin_platform.carbon_calculations (tenant_id, entity_id, calculated_at DESC);
