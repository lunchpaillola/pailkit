-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add processing_status_by_key column to rooms table
-- This allows tracking processing status per workflow_thread_id, enabling room reuse

-- Add processing_status_by_key column as JSONB
-- This stores processing status keyed by workflow_thread_id (or room_name as fallback)
-- Format: {"thread_id_1": {"transcript_processed": true, "email_sent": true, ...}, ...}
ALTER TABLE rooms
ADD COLUMN IF NOT EXISTS processing_status_by_key JSONB DEFAULT '{}'::jsonb;

-- Add index for JSONB queries (useful for querying by thread_id)
CREATE INDEX IF NOT EXISTS idx_rooms_processing_status_by_key
ON rooms USING GIN (processing_status_by_key);
