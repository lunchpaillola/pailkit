-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add duration field to usage_transactions table
-- Tracks bot usage duration in seconds for analytics and billing

-- Add duration column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'usage_transactions' AND column_name = 'duration') THEN
        ALTER TABLE usage_transactions
        ADD COLUMN duration INTEGER;
    END IF;
END $$;

-- Create index for efficient queries by duration (optional, for analytics)
CREATE INDEX IF NOT EXISTS idx_usage_transactions_duration ON usage_transactions(duration);

-- Add comment to document the column
COMMENT ON COLUMN usage_transactions.duration IS 'Duration in seconds for bot usage transactions';
