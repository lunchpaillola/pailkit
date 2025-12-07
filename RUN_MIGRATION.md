# How to Run the Database Migration in Supabase

## Step-by-Step Instructions

### 1. Open Supabase Dashboard
Go to: https://supabase.com/dashboard/project/ohvptrhbbfbudgckagne

### 2. Open SQL Editor
- Click **"SQL Editor"** in the left sidebar
- Click **"New query"** button (top right)

### 3. Copy the Migration SQL
Open this file: `supabase/migrations/20251202170733_init_schema.sql`

**Copy ALL the contents** (from `-- Copyright` to the end)

### 4. Paste and Run
1. Paste the SQL into the SQL Editor
2. Click **"Run"** button (or press `Cmd+Enter` / `Ctrl+Enter`)
3. Wait a few seconds

### 5. Verify Success
You should see:
- ✅ "Success. No rows returned" (green message)
- OR check the bottom panel for any errors

### 6. Verify Table Was Created
1. Click **"Table Editor"** in the left sidebar
2. You should see a table called **`rooms`**
3. Click on it to see all the columns

### 7. Test Your Connection
```bash
python flow/scripts/view_database.py
```

You should see: **"Database is empty. No session data stored yet."** ✅

---

## If You Get Errors

### Error: "relation already exists"
- The table already exists - that's okay!
- The migration uses `CREATE TABLE IF NOT EXISTS` so it's safe to run again

### Error: "permission denied"
- Make sure you're using the **secret** API key (not publishable)
- Check your `.env` file has `SUPABASE_SECRET_KEY` set correctly

### Error: "syntax error"
- Make sure you copied the ENTIRE migration file
- Don't copy just part of it

---

## Quick Copy-Paste Method

If you want to copy the SQL directly, here's the full migration:

```sql
-- Enable UUID extension
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

-- Policy: Allow service role full access
CREATE POLICY "Service role can manage all rooms"
    ON rooms
    FOR ALL
    USING (true)
    WITH CHECK (true);
```

Copy the above SQL and paste it into Supabase SQL Editor, then click Run!
