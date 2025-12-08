-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Ensure all necessary columns exist in workflow_threads table
-- This migration is idempotent - safe to run multiple times
-- Adds any missing columns needed for email/webhook and candidate configuration

-- Add email/webhook columns if they don't exist
DO $$
BEGIN
    -- Email and webhook configuration
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'email_results_to') THEN
        ALTER TABLE workflow_threads ADD COLUMN email_results_to TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'webhook_callback_url') THEN
        ALTER TABLE workflow_threads ADD COLUMN webhook_callback_url TEXT;
    END IF;

    -- Candidate information
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'candidate_name') THEN
        ALTER TABLE workflow_threads ADD COLUMN candidate_name TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'candidate_email') THEN
        ALTER TABLE workflow_threads ADD COLUMN candidate_email TEXT;
    END IF;

    -- Interview configuration
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'interview_type') THEN
        ALTER TABLE workflow_threads ADD COLUMN interview_type TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'position') THEN
        ALTER TABLE workflow_threads ADD COLUMN position TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'interviewer_context') THEN
        ALTER TABLE workflow_threads ADD COLUMN interviewer_context TEXT;
    END IF;

    -- Analysis prompts
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'analysis_prompt') THEN
        ALTER TABLE workflow_threads ADD COLUMN analysis_prompt TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'summary_format_prompt') THEN
        ALTER TABLE workflow_threads ADD COLUMN summary_format_prompt TEXT;
    END IF;

    -- Bot configuration
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'bot_config') THEN
        ALTER TABLE workflow_threads ADD COLUMN bot_config JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'bot_id') THEN
        ALTER TABLE workflow_threads ADD COLUMN bot_id TEXT;
    END IF;

    -- Room information
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'room_url') THEN
        ALTER TABLE workflow_threads ADD COLUMN room_url TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'room_id') THEN
        ALTER TABLE workflow_threads ADD COLUMN room_id TEXT;
    END IF;

    -- Processing status
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'email_sent') THEN
        ALTER TABLE workflow_threads ADD COLUMN email_sent BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'webhook_sent') THEN
        ALTER TABLE workflow_threads ADD COLUMN webhook_sent BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'transcript_processed') THEN
        ALTER TABLE workflow_threads ADD COLUMN transcript_processed BOOLEAN DEFAULT FALSE;
    END IF;

    -- Results
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'candidate_summary') THEN
        ALTER TABLE workflow_threads ADD COLUMN candidate_summary TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'insights') THEN
        ALTER TABLE workflow_threads ADD COLUMN insights JSONB;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'qa_pairs') THEN
        ALTER TABLE workflow_threads ADD COLUMN qa_pairs JSONB;
    END IF;

    -- Transcript
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'transcript_text') THEN
        ALTER TABLE workflow_threads ADD COLUMN transcript_text TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'transcript_id') THEN
        ALTER TABLE workflow_threads ADD COLUMN transcript_id TEXT;
    END IF;

    -- Workflow state
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'workflow_paused') THEN
        ALTER TABLE workflow_threads ADD COLUMN workflow_paused BOOLEAN DEFAULT FALSE;
    END IF;

    -- Metadata
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'workflow_threads' AND column_name = 'metadata') THEN
        ALTER TABLE workflow_threads ADD COLUMN metadata JSONB;
    END IF;
END $$;

-- Add comments to document the columns
COMMENT ON COLUMN workflow_threads.email_results_to IS 'Email address to send interview results to';
COMMENT ON COLUMN workflow_threads.webhook_callback_url IS 'Webhook URL to send interview results to';
COMMENT ON COLUMN workflow_threads.candidate_name IS 'Name of the candidate/participant';
COMMENT ON COLUMN workflow_threads.candidate_email IS 'Email address of the candidate';
COMMENT ON COLUMN workflow_threads.interview_type IS 'Type of interview (e.g., Technical Interview)';
COMMENT ON COLUMN workflow_threads.position IS 'Job position being interviewed for';
COMMENT ON COLUMN workflow_threads.interviewer_context IS 'Context about the interviewer/interview';
COMMENT ON COLUMN workflow_threads.analysis_prompt IS 'Custom prompt for AI analysis of the interview';
COMMENT ON COLUMN workflow_threads.summary_format_prompt IS 'Custom prompt for formatting the summary';
