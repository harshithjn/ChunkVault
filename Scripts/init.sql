-- ChunkVault PostgreSQL initialization script
-- This script sets up the initial database structure

-- Create database if it doesn't exist (handled by POSTGRES_DB env var)
-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone
SET timezone = 'UTC';

-- Create initial admin user (will be created by the application)
-- This is just a placeholder for any additional initialization
