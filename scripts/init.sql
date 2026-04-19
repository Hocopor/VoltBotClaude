-- VOLTAGE Bot — PostgreSQL initialization
-- Runs once when the postgres container first starts

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Set timezone
SET timezone = 'UTC';
