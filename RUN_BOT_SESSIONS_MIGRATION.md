# How to Run the Bot Sessions Migration

## Step-by-Step Instructions

### 1. Open Supabase Dashboard
Go to: https://supabase.com/dashboard/project/ohvptrhbbfbudgckagne

### 2. Open SQL Editor
- Click **"SQL Editor"** in the left sidebar
- Click **"New query"** button (top right)

### 3. Copy the Migration SQL
Open this file: `supabase/migrations/20250115000000_add_bot_sessions.sql`

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
2. You should see a table called **`bot_sessions`**
3. Click on it to see all the columns:
   - `bot_id` (UUID, primary key)
   - `room_url`, `room_name`
   - `status` (running, completed, failed)
   - `started_at`, `completed_at`
   - `bot_config` (JSONB)
   - `transcript_text` (encrypted)
   - `qa_pairs`, `insights` (JSONB)
   - `error`

### 7. Test Your Connection
```bash
python flow/scripts/view_database.py
```

You should see the database connection working. ✅

---

## If You Get Errors

### Error: "relation already exists"
- The table already exists - that's okay!
- The migration uses `CREATE TABLE IF NOT EXISTS` so it's safe to run again

### Error: "permission denied"
- Make sure you're using the **service role** API key (not publishable)
- Check your `.env` file has `SUPABASE_SERVICE_ROLE_KEY` set correctly

### Error: "syntax error"
- Make sure you copied the ENTIRE migration file
- Don't copy just part of it

---

## What This Migration Creates

✅ **bot_sessions** table for tracking bot sessions:
- Stores bot status and configuration
- Tracks transcript, Q&A pairs, and insights
- Encrypts sensitive transcript data
- Indexes for efficient queries
- Auto-updates `updated_at` timestamp

This table is used by the new simplified bot API (`/api/bot/join` and `/api/bot/{bot_id}/status`).
