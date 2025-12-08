-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Bot Sessions Table Migration
-- Creates table for tracking bot sessions and their results

-- Create bot_sessions table
CREATE TABLE IF NOT EXISTS bot_sessions (
    bot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_url TEXT NOT NULL,
    room_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running', -- 'running', 'completed', 'failed'
    started_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    completed_at TIMESTAMPTZ,
    process_insights BOOLEAN DEFAULT TRUE,
    bot_config JSONB, -- Store bot configuration (bot_prompt, name, video_mode, etc.)
    transcript_text TEXT, -- Full transcript (encrypted)
    qa_pairs JSONB, -- Q&A pairs extracted from transcript
    insights JSONB, -- Extracted insights and assessments
    error TEXT, -- Error message if bot failed
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_bot_sessions_room_name ON bot_sessions(room_name);
CREATE INDEX IF NOT EXISTS idx_bot_sessions_status ON bot_sessions(status);
CREATE INDEX IF NOT EXISTS idx_bot_sessions_started_at ON bot_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_bot_sessions_created_at ON bot_sessions(created_at DESC);

-- Create function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_bot_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger
CREATE TRIGGER update_bot_sessions_updated_at
    BEFORE UPDATE ON bot_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_bot_sessions_updated_at();

-- Enable Row Level Security
ALTER TABLE bot_sessions ENABLE ROW LEVEL SECURITY;

-- Create policy to allow service role to access all bot sessions
-- (Service role bypasses RLS, but this is good practice for future user-specific access)
CREATE POLICY "Service role can access all bot sessions"
    ON bot_sessions
    FOR ALL
    USING (true)
    WITH CHECK (true);
