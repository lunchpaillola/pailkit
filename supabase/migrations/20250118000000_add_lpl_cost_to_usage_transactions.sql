-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Add lpl_cost field to usage_transactions table
-- Tracks actual cost incurred by LPL (LLM, STT, etc.) for internal analytics and margin analysis

-- Add lpl_cost column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'usage_transactions' AND column_name = 'lpl_cost') THEN
        ALTER TABLE usage_transactions
        ADD COLUMN lpl_cost DECIMAL(10, 6);
    END IF;
END $$;

-- Create index for efficient queries by lpl_cost (optional, for analytics)
CREATE INDEX IF NOT EXISTS idx_usage_transactions_lpl_cost ON usage_transactions(lpl_cost);

-- Add comment to document the column
COMMENT ON COLUMN usage_transactions.lpl_cost IS 'Actual cost incurred by LPL (LLM, STT, etc.) for internal analytics and margin analysis';
