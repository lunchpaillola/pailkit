# Database Schema Overview

Complete schema for PailFlow unified data and billing platform.

## Tables Created

### 1. **users** - User Accounts
- User accounts for the platform
- Linked to Stripe for billing (`stripe_customer_id`)
- Tracks login activity and account status

**Key Fields:**
- `id` (UUID) - Primary key
- `email` (unique) - User email
- `stripe_customer_id` - Stripe customer ID for billing
- `is_active` - Account status

### 2. **api_keys** - API Key Management (Unkey Integration)
- API keys managed via Unkey
- Links to users
- Tracks usage and expiration

**Key Fields:**
- `id` (UUID) - Primary key
- `user_id` - Foreign key to users
- `unkey_key_id` - Unkey key identifier (unique)
- `name`, `description` - User-friendly labels
- `last_used_at` - Last usage timestamp
- `usage_count` - Usage counter
- `is_active` - Key status

### 3. **meetings** - Meeting Records (Daily.co Integration)
- Meeting records from Daily.co
- Links to users
- Tracks meeting lifecycle and metadata

**Key Fields:**
- `id` (UUID) - Primary key
- `user_id` - Foreign key to users
- `room_name` (unique) - Daily.co room identifier
- `daily_meeting_id` - Daily.co meeting ID
- `status` - Meeting status (scheduled, in_progress, ended, cancelled)
- `started_at`, `ended_at` - Meeting timestamps
- `duration_seconds` - Calculated duration
- `recording_url`, `transcript_url` - Media URLs
- `metadata` (JSONB) - Additional Daily.co metadata

### 4. **participants** - Meeting Participants (Daily.co Integration)
- Meeting participants from Daily.co
- Links to meetings
- Tracks participant join/leave times

**Key Fields:**
- `id` (UUID) - Primary key
- `meeting_id` - Foreign key to meetings
- `daily_participant_id` - Daily.co participant identifier
- `name`, `email` - Participant info
- `role` - Participant role (host, guest, bot)
- `joined_at`, `left_at` - Participation timestamps
- `duration_seconds` - Calculated duration
- `metadata` (JSONB) - Additional participant metadata

### 5. **openai_usage** - OpenAI Token Usage Tracking
- OpenAI API token usage for billing
- Links to users, meetings, and API keys
- Tracks costs for usage-based billing

**Key Fields:**
- `id` (UUID) - Primary key
- `user_id` - Foreign key to users
- `meeting_id` - Foreign key to meetings (optional)
- `api_key_id` - Foreign key to api_keys (optional)
- `model` - OpenAI model used (e.g., 'gpt-4', 'gpt-3.5-turbo')
- `prompt_tokens`, `completion_tokens`, `total_tokens` - Token counts
- `cost_usd` - Cost in USD for this API call
- `request_id` - OpenAI request ID for tracking
- `metadata` (JSONB) - Additional usage metadata

### 6. **rooms** - Room Session Data (Existing)
- Room session data (migrated from SQLite)
- Stores interview/meeting session state
- Encrypted sensitive fields

## Relationships

```
users
  ├── api_keys (one-to-many)
  ├── meetings (one-to-many)
  └── openai_usage (one-to-many)

meetings
  ├── participants (one-to-many)
  └── openai_usage (one-to-many, optional)

api_keys
  └── openai_usage (one-to-many, optional)
```

## Integrations

### Unkey (API Keys)
- `api_keys.unkey_key_id` stores Unkey key identifiers
- Track API key usage and expiration
- Link API keys to users for billing

### Daily.co (Meetings)
- `meetings.room_name` stores Daily.co room identifiers
- `meetings.daily_meeting_id` stores Daily.co meeting IDs
- `participants.daily_participant_id` stores Daily.co participant IDs
- Track meeting lifecycle and participant data

### OpenAI (Usage Tracking)
- `openai_usage` table tracks all OpenAI API calls
- Calculate costs per model
- Link usage to users, meetings, and API keys
- Support usage-based billing

### Stripe (Billing)
- `users.stripe_customer_id` links users to Stripe
- `openai_usage.cost_usd` tracks costs per API call
- Aggregate usage for billing calculations

## Security

- **Row Level Security (RLS)** enabled on all tables
- Service role key bypasses RLS for backend operations
- Sensitive tables (api_keys, openai_usage) have restricted access
- Future: Add user-specific policies for multi-tenant access

## Performance

- Indexes on all foreign keys
- Indexes on frequently queried fields (email, room_name, timestamps)
- Composite indexes for common query patterns
- JSONB fields for flexible metadata storage

## Next Steps

1. Run the migration: `supabase/migrations/20251202170734_add_all_tables.sql`
2. Integrate Unkey API for key management
3. Integrate Daily.co webhooks to populate meetings/participants
4. Integrate OpenAI usage tracking in API calls
5. Integrate Stripe for usage-based billing
