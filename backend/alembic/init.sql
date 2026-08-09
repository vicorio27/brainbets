-- Initial PostgreSQL setup for BrainBets
-- Extensions and base configuration

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- The full schema is managed by Alembic migrations.
-- This file ensures required extensions exist before migrations run.
