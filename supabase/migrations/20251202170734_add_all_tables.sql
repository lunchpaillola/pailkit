-- Copyright 2025 Lunch Pail Labs, LLC
-- Licensed under the Apache License, Version 2.0
--
-- Complete schema migration for PailFlow
-- Creates all tables: users, api_keys, meetings, participants, openai_usage
-- Integrates with Unkey (API keys), Daily (meetings), OpenAI (usage), Stripe (billing)

-- ============================================================================
-- USERS TABLE
-- ============================================================================
-- User accounts for the platform
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    stripe_customer_id TEXT UNIQUE, -- Stripe customer ID for billing
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes for users
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer_id ON users(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);

-- ============================================================================
-- API_KEYS TABLE
-- ============================================================================
-- API keys managed via Unkey integration
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unkey_key_id TEXT UNIQUE NOT NULL, -- Unkey key identifier
    name TEXT, -- User-friendly name for the key
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ, -- Optional expiration
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0 -- Track how many times it's been used
);

-- Indexes for api_keys
CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_unkey_key_id ON api_keys(unkey_key_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys(is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_last_used_at ON api_keys(last_used_at DESC);

-- ============================================================================
-- MEETINGS TABLE
-- ============================================================================
-- Meeting records from Daily.co
CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    room_name TEXT UNIQUE NOT NULL, -- Daily.co room identifier
    daily_meeting_id TEXT, -- Daily.co meeting ID
    daily_room_id TEXT, -- Daily.co room ID
    title TEXT,
    status TEXT DEFAULT 'scheduled', -- scheduled, in_progress, ended, cancelled
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER, -- Calculated duration in seconds
    recording_url TEXT, -- URL to Daily.co recording if available
    transcript_url TEXT, -- URL to transcript if available
    metadata JSONB -- Additional metadata from Daily.co
);

-- Indexes for meetings
CREATE INDEX IF NOT EXISTS idx_meetings_user_id ON meetings(user_id);
CREATE INDEX IF NOT EXISTS idx_meetings_room_name ON meetings(room_name);
CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(status);
CREATE INDEX IF NOT EXISTS idx_meetings_created_at ON meetings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_daily_meeting_id ON meetings(daily_meeting_id);

-- ============================================================================
-- PARTICIPANTS TABLE
-- ============================================================================
-- Meeting participants from Daily.co
CREATE TABLE IF NOT EXISTS participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    daily_participant_id TEXT, -- Daily.co participant identifier
    name TEXT,
    email TEXT,
    role TEXT, -- e.g., 'host', 'guest', 'bot'
    joined_at TIMESTAMPTZ NOT NULL,
    left_at TIMESTAMPTZ,
    duration_seconds INTEGER, -- Calculated duration in seconds
    metadata JSONB -- Additional participant metadata
);

-- Indexes for participants
CREATE INDEX IF NOT EXISTS idx_participants_meeting_id ON participants(meeting_id);
CREATE INDEX IF NOT EXISTS idx_participants_daily_participant_id ON participants(daily_participant_id);
CREATE INDEX IF NOT EXISTS idx_participants_email ON participants(email);
CREATE INDEX IF NOT EXISTS idx_participants_joined_at ON participants(joined_at DESC);

-- ============================================================================
-- OPENAI_USAGE TABLE
-- ============================================================================
-- OpenAI API token usage tracking for billing
CREATE TABLE IF NOT EXISTS openai_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL, -- Optional: link to meeting
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL, -- Optional: link to API key used
    model TEXT NOT NULL, -- e.g., 'gpt-4', 'gpt-3.5-turbo'
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10, 6) DEFAULT 0, -- Cost in USD
    request_id TEXT, -- OpenAI request ID for tracking
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    metadata JSONB -- Additional usage metadata
);

-- Indexes for openai_usage
CREATE INDEX IF NOT EXISTS idx_openai_usage_user_id ON openai_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_openai_usage_meeting_id ON openai_usage(meeting_id);
CREATE INDEX IF NOT EXISTS idx_openai_usage_api_key_id ON openai_usage(api_key_id);
CREATE INDEX IF NOT EXISTS idx_openai_usage_created_at ON openai_usage(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_openai_usage_model ON openai_usage(model);

-- Composite index for user usage queries
CREATE INDEX IF NOT EXISTS idx_openai_usage_user_created ON openai_usage(user_id, created_at DESC);

-- ============================================================================
-- UPDATE TRIGGERS
-- ============================================================================
-- Function to auto-update updated_at (already exists, but ensure it's available)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add updated_at triggers to tables that need them
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_api_keys_updated_at
    BEFORE UPDATE ON api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE openai_usage ENABLE ROW LEVEL SECURITY;

-- Users table policies
CREATE POLICY "Service role can manage all users"
    ON users
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- API keys table policies (sensitive - restrict access)
CREATE POLICY "Service role can manage all api_keys"
    ON api_keys
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Meetings table policies
CREATE POLICY "Service role can manage all meetings"
    ON meetings
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Participants table policies
CREATE POLICY "Service role can manage all participants"
    ON participants
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- OpenAI usage table policies (sensitive - restrict access)
CREATE POLICY "Service role can manage all openai_usage"
    ON openai_usage
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================
COMMENT ON TABLE users IS 'User accounts for the platform, linked to Stripe for billing';
COMMENT ON TABLE api_keys IS 'API keys managed via Unkey integration, linked to users';
COMMENT ON TABLE meetings IS 'Meeting records from Daily.co, linked to users';
COMMENT ON TABLE participants IS 'Meeting participants from Daily.co, linked to meetings';
COMMENT ON TABLE openai_usage IS 'OpenAI API token usage tracking for billing, linked to users and meetings';

COMMENT ON COLUMN users.stripe_customer_id IS 'Stripe customer ID for usage-based billing';
COMMENT ON COLUMN api_keys.unkey_key_id IS 'Unkey key identifier for API key management';
COMMENT ON COLUMN meetings.room_name IS 'Daily.co room identifier (unique)';
COMMENT ON COLUMN openai_usage.cost_usd IS 'Cost in USD for this API call';
