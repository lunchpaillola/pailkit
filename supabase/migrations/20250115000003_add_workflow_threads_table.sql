-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Migration: Create workflow_threads table
-- This table organizes all data by workflow_thread_id, allowing rooms to be reused
-- Each workflow run gets its own row, even if it uses the same room

-- Create workflow_threads table
CREATE TABLE IF NOT EXISTS workflow_threads (
    workflow_thread_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Room information (which room this workflow is using)
    room_name TEXT NOT NULL,
    room_url TEXT, -- Full Daily.co room URL
    room_id TEXT, -- Daily.co room/meeting ID

    -- User/Candidate information (encrypted)
    candidate_name TEXT,
    candidate_email TEXT,
    session_id TEXT,

    -- Interview configuration
    interview_type TEXT,
    position TEXT,
    difficulty_level TEXT,
    interviewer_context TEXT,
    analysis_prompt TEXT,
    summary_format_prompt TEXT,

    -- Bot configuration
    bot_enabled BOOLEAN DEFAULT FALSE,
    bot_id TEXT,
    bot_config JSONB, -- Store full bot config as JSON

    -- Meeting lifecycle
    meeting_status TEXT DEFAULT 'in_progress',
    meeting_start_time TIMESTAMPTZ,
    meeting_end_time TIMESTAMPTZ,
    duration INTEGER, -- Duration in seconds

    -- Transcript information (encrypted)
    transcript_text TEXT,
    transcript_id TEXT, -- Daily.co transcript ID (if using Daily.co transcription)

    -- Processing state
    transcript_processed BOOLEAN DEFAULT FALSE,
    transcript_processing BOOLEAN DEFAULT FALSE,
    email_sent BOOLEAN DEFAULT FALSE,
    webhook_sent BOOLEAN DEFAULT FALSE,

    -- Results (encrypted)
    candidate_summary TEXT,
    insights JSONB, -- Store insights as JSON
    qa_pairs JSONB, -- Store Q&A pairs as JSON

    -- Webhooks and notifications
    webhook_callback_url TEXT,
    email_results_to TEXT,

    -- Workflow state
    workflow_paused BOOLEAN DEFAULT FALSE,
    waiting_for_meeting_ended BOOLEAN DEFAULT FALSE,
    waiting_for_transcript_webhook BOOLEAN DEFAULT FALSE,

    -- Metadata
    metadata JSONB -- Additional metadata
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_workflow_threads_room_name ON workflow_threads(room_name);
CREATE INDEX IF NOT EXISTS idx_workflow_threads_created_at ON workflow_threads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflow_threads_meeting_status ON workflow_threads(meeting_status);
CREATE INDEX IF NOT EXISTS idx_workflow_threads_bot_id ON workflow_threads(bot_id);
CREATE INDEX IF NOT EXISTS idx_workflow_threads_session_id ON workflow_threads(session_id);

-- Create function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_workflow_threads_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger
CREATE TRIGGER update_workflow_threads_updated_at
    BEFORE UPDATE ON workflow_threads
    FOR EACH ROW
    EXECUTE FUNCTION update_workflow_threads_updated_at();

-- Enable Row Level Security
ALTER TABLE workflow_threads ENABLE ROW LEVEL SECURITY;

-- Policy: Allow service role full access
CREATE POLICY "Service role can manage all workflow_threads"
    ON workflow_threads
    FOR ALL
    USING (true)
    WITH CHECK (true);
