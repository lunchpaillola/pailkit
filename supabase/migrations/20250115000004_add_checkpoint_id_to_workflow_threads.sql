-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add checkpoint_id column to workflow_threads table
-- This allows storing LangGraph checkpoint IDs for workflow resumption

-- Add checkpoint_id column (nullable for backward compatibility)
ALTER TABLE workflow_threads
ADD COLUMN IF NOT EXISTS checkpoint_id TEXT;

-- Create index for faster lookups by checkpoint_id
CREATE INDEX IF NOT EXISTS idx_workflow_threads_checkpoint_id ON workflow_threads(checkpoint_id);

-- Add comment to document the column
COMMENT ON COLUMN workflow_threads.checkpoint_id IS 'LangGraph checkpoint ID for resuming paused workflows';
