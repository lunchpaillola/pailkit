-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add bot timing columns to workflow_threads table
-- Tracks when bot joins and leaves the room, and calculates duration

-- Add bot_join_time column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'bot_join_time') THEN
        ALTER TABLE workflow_threads
        ADD COLUMN bot_join_time TIMESTAMPTZ;
    END IF;
END $$;

-- Add bot_leave_time column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'bot_leave_time') THEN
        ALTER TABLE workflow_threads
        ADD COLUMN bot_leave_time TIMESTAMPTZ;
    END IF;
END $$;

-- Add bot_duration column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'bot_duration') THEN
        ALTER TABLE workflow_threads
        ADD COLUMN bot_duration INTEGER;
    END IF;
END $$;

-- Create indexes for efficient queries by bot timing
CREATE INDEX IF NOT EXISTS idx_workflow_threads_bot_join_time ON workflow_threads(bot_join_time);
CREATE INDEX IF NOT EXISTS idx_workflow_threads_bot_leave_time ON workflow_threads(bot_leave_time);
CREATE INDEX IF NOT EXISTS idx_workflow_threads_bot_duration ON workflow_threads(bot_duration);

-- Add comments to document the columns
COMMENT ON COLUMN workflow_threads.bot_join_time IS 'Timestamp when bot joined the room (UTC)';
COMMENT ON COLUMN workflow_threads.bot_leave_time IS 'Timestamp when bot left the room (UTC)';
COMMENT ON COLUMN workflow_threads.bot_duration IS 'Duration in seconds that bot was in the room (calculated from bot_join_time and bot_leave_time)';
