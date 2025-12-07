-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Initial schema migration for PailFlow
-- Creates the rooms table for storing room session data

-- Enable UUID extension (if needed in future)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create rooms table
CREATE TABLE IF NOT EXISTS rooms (
    room_name TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    session_id TEXT,
    workflow_thread_id TEXT,
    meeting_status TEXT DEFAULT 'in_progress',
    meeting_start_time TIMESTAMPTZ,
    meeting_end_time TIMESTAMPTZ,
    interview_type TEXT,
    difficulty_level TEXT,
    position TEXT,
    bot_enabled BOOLEAN DEFAULT FALSE,
    waiting_for_meeting_ended BOOLEAN DEFAULT FALSE,
    waiting_for_transcript_webhook BOOLEAN DEFAULT FALSE,
    transcript_processed BOOLEAN DEFAULT FALSE,
    transcript_processing BOOLEAN DEFAULT FALSE,
    email_sent BOOLEAN DEFAULT FALSE,
    workflow_paused BOOLEAN DEFAULT FALSE,
    webhook_callback_url TEXT,
    email_results_to TEXT,
    candidate_name TEXT,
    candidate_email TEXT,
    interviewer_context TEXT,
    analysis_prompt TEXT,
    summary_format_prompt TEXT,
    transcript_text TEXT,
    candidate_summary TEXT
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_rooms_session_id ON rooms(session_id);
CREATE INDEX IF NOT EXISTS idx_rooms_created_at ON rooms(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rooms_meeting_status ON rooms(meeting_status);
CREATE INDEX IF NOT EXISTS idx_rooms_workflow_thread_id ON rooms(workflow_thread_id);

-- Create function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger
CREATE TRIGGER update_rooms_updated_at
    BEFORE UPDATE ON rooms
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Enable Row Level Security
ALTER TABLE rooms ENABLE ROW LEVEL SECURITY;

-- Policy: Allow service role full access (for backend operations)
-- Note: service_role key automatically bypasses RLS, but this policy ensures compatibility
CREATE POLICY "Service role can manage all rooms"
    ON rooms
    FOR ALL
    USING (true)
    WITH CHECK (true);
