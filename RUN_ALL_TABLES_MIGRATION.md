# Run All Tables Migration

This migration creates all the tables needed for the unified data and billing platform.

## What This Migration Creates

✅ **users** - User accounts with Stripe integration
✅ **api_keys** - API key management with Unkey integration
✅ **meetings** - Meeting records from Daily.co
✅ **participants** - Meeting participants from Daily.co
✅ **openai_usage** - OpenAI token usage tracking for billing

Plus the existing **rooms** table (already created).

## How to Run

### Step 1: Open Supabase Dashboard
Go to: https://supabase.com/dashboard/project/ohvptrhbbfbudgckagne

### Step 2: Open SQL Editor
- Click **"SQL Editor"** in the left sidebar
- Click **"New query"** button

### Step 3: Copy the Migration SQL
Open this file: `supabase/migrations/20251202170734_add_all_tables.sql`

**Copy ALL the contents** of that file.

### Step 4: Paste and Run
1. Paste the SQL into the SQL Editor
2. Click **"Run"** button (or press `Cmd+Enter` / `Ctrl+Enter`)
3. Wait a few seconds

### Step 5: Verify Success
You should see:
- ✅ "Success. No rows returned" (green message)

### Step 6: Verify Tables Were Created
1. Click **"Table Editor"** in the left sidebar
2. You should see these tables:
   - ✅ `users`
   - ✅ `api_keys`
   - ✅ `meetings`
   - ✅ `participants`
   - ✅ `openai_usage`
   - ✅ `rooms` (already existed)

### Step 7: Test Your Connection
```bash
python flow/scripts/view_database.py
```

You should still see: **"Database is empty. No session data stored yet."** ✅

---

## What's Included

### Tables with Relationships
- **users** → **api_keys** (one-to-many)
- **users** → **meetings** (one-to-many)
- **users** → **openai_usage** (one-to-many)
- **meetings** → **participants** (one-to-many)
- **meetings** → **openai_usage** (one-to-many, optional)
- **api_keys** → **openai_usage** (one-to-many, optional)

### Security
- Row Level Security (RLS) enabled on all tables
- Service role policies for backend access
- Ready for future user-specific policies

### Performance
- Indexes on all foreign keys
- Indexes on frequently queried fields
- Composite indexes for common queries

### Integrations Ready
- **Unkey**: `api_keys.unkey_key_id` field
- **Daily.co**: `meetings.room_name`, `meetings.daily_meeting_id`
- **OpenAI**: `openai_usage` table with cost tracking
- **Stripe**: `users.stripe_customer_id` field

---

## Troubleshooting

### Error: "relation already exists"
- Some tables might already exist - that's okay!
- The migration uses `CREATE TABLE IF NOT EXISTS` so it's safe to run again

### Error: "permission denied"
- Make sure you're using the **secret** API key in your `.env`
- Check `SUPABASE_SECRET_KEY` is set correctly

### Error: "syntax error"
- Make sure you copied the ENTIRE migration file
- Don't copy just part of it

---

## After Migration

Your database is now ready for:
1. ✅ User management with Stripe billing
2. ✅ API key management with Unkey
3. ✅ Meeting tracking with Daily.co
4. ✅ Participant tracking
5. ✅ OpenAI usage tracking for billing
6. ✅ Room session data (existing)

All tables are connected and ready to use! 🎉
