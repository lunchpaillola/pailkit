-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Generalize Bot API and Remove Interview-Specific Fields
-- This migration:
-- 1. Adds new generalized fields: email, provider
-- 2. Migrates data from candidate_email to email (if any exists)
-- 3. Removes interview-specific fields: candidate_name, candidate_email, interview_type, position, interviewer_context
--
-- Note: Since we're at launch, no backward compatibility is needed

-- ============================================================================
-- WORKFLOW_THREADS TABLE
-- ============================================================================

-- Ensure the trigger function is correct (fixes any potential corruption)
CREATE OR REPLACE FUNCTION update_workflow_threads_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Temporarily disable the update trigger to avoid conflicts during ALTER TABLE
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'update_workflow_threads_updated_at'
        AND tgrelid = 'workflow_threads'::regclass
    ) THEN
        ALTER TABLE workflow_threads DISABLE TRIGGER update_workflow_threads_updated_at;
    END IF;
END $$;

-- Add new generalized fields
DO $$
BEGIN
    -- Add email column (replaces candidate_email)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'email') THEN
        ALTER TABLE workflow_threads ADD COLUMN email TEXT;
    END IF;

    -- Add provider column (for future multi-provider support)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'provider') THEN
        ALTER TABLE workflow_threads ADD COLUMN provider TEXT DEFAULT 'daily';
    END IF;
END $$;

-- Migrate existing data from candidate_email to email (if any exists)
UPDATE workflow_threads
SET email = candidate_email
WHERE email IS NULL AND candidate_email IS NOT NULL;

-- Drop old interview-specific columns
ALTER TABLE workflow_threads
    DROP COLUMN IF EXISTS candidate_name,
    DROP COLUMN IF EXISTS candidate_email,
    DROP COLUMN IF EXISTS interview_type,
    DROP COLUMN IF EXISTS position,
    DROP COLUMN IF EXISTS interviewer_context;

-- Re-enable the update trigger
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'update_workflow_threads_updated_at'
        AND tgrelid = 'workflow_threads'::regclass
    ) THEN
        ALTER TABLE workflow_threads ENABLE TRIGGER update_workflow_threads_updated_at;
    END IF;
END $$;

-- ============================================================================
-- ROOMS TABLE
-- ============================================================================

-- Ensure the trigger function is correct (fixes any potential corruption)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Temporarily disable the update trigger to avoid conflicts during ALTER TABLE
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'update_rooms_updated_at'
        AND tgrelid = 'rooms'::regclass
    ) THEN
        ALTER TABLE rooms DISABLE TRIGGER update_rooms_updated_at;
    END IF;
END $$;

-- Add new generalized fields
DO $$
BEGIN
    -- Add email column (replaces candidate_email)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'rooms' AND column_name = 'email') THEN
        ALTER TABLE rooms ADD COLUMN email TEXT;
    END IF;

    -- Add provider column (for future multi-provider support)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'rooms' AND column_name = 'provider') THEN
        ALTER TABLE rooms ADD COLUMN provider TEXT DEFAULT 'daily';
    END IF;
END $$;

-- Migrate existing data from candidate_email to email (if any exists)
UPDATE rooms
SET email = candidate_email
WHERE email IS NULL AND candidate_email IS NOT NULL;

-- Drop old interview-specific columns
ALTER TABLE rooms
    DROP COLUMN IF EXISTS candidate_name,
    DROP COLUMN IF EXISTS candidate_email,
    DROP COLUMN IF EXISTS interview_type,
    DROP COLUMN IF EXISTS position,
    DROP COLUMN IF EXISTS interviewer_context;

-- Re-enable the update trigger
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'update_rooms_updated_at'
        AND tgrelid = 'rooms'::regclass
    ) THEN
        ALTER TABLE rooms ENABLE TRIGGER update_rooms_updated_at;
    END IF;
END $$;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON COLUMN workflow_threads.email IS 'Email address to send results to (generalized, replaces candidate_email)';
COMMENT ON COLUMN workflow_threads.provider IS 'Provider identifier (default: daily, for future multi-provider support)';
COMMENT ON COLUMN rooms.email IS 'Email address to send results to (generalized, replaces candidate_email)';
COMMENT ON COLUMN rooms.provider IS 'Provider identifier (default: daily, for future multi-provider support)';
