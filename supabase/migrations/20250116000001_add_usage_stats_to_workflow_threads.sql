-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add usage_stats JSONB column to workflow_threads table
-- Stores aggregated LLM usage statistics per workflow run

-- Add usage_stats column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'usage_stats') THEN
        ALTER TABLE workflow_threads
        ADD COLUMN usage_stats JSONB;
    END IF;
END $$;

-- Create GIN index for efficient JSONB queries
CREATE INDEX IF NOT EXISTS idx_workflow_threads_usage_stats ON workflow_threads USING GIN (usage_stats);

-- Add comment to document the column
COMMENT ON COLUMN workflow_threads.usage_stats IS 'Aggregated LLM usage statistics: {total_tokens, total_cost_usd, llm_calls, models_used, posthog_trace_id}';
