-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add unkey_key_id column to workflow_threads table
-- Links workflow threads to Unkey API keys for usage tracking

-- Add unkey_key_id column if it doesn't exist
-- This stores the Unkey key identifier directly (e.g., "key_abc123")
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'unkey_key_id') THEN
        ALTER TABLE workflow_threads
        ADD COLUMN unkey_key_id TEXT;
    END IF;
END $$;

-- Create index for efficient lookups by unkey_key_id
CREATE INDEX IF NOT EXISTS idx_workflow_threads_unkey_key_id ON workflow_threads(unkey_key_id);

-- Add comment to document the column
COMMENT ON COLUMN workflow_threads.unkey_key_id IS 'Unkey key identifier (keyId) that created this workflow thread (for usage tracking)';
