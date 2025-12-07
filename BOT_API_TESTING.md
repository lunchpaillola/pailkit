# Bot API Testing Guide

## Quick Start

### 1. Run the Migration

First, apply the `bot_sessions` table migration:
- See `RUN_BOT_SESSIONS_MIGRATION.md` for detailed instructions
- Or copy `supabase/migrations/20250115000000_add_bot_sessions.sql` to Supabase SQL Editor and run it

### 2. Test the Bot API

Run the test script:
```bash
python flow/demos/test_bot_api.py
```

This will:
1. Create a Daily room (or use `TEST_ROOM_URL` if set)
2. Start a bot via `POST /api/bot/join`
3. Poll `GET /api/bot/{bot_id}/status` to check progress
4. Show results when complete

## How the Flow Works

### New Simplified Bot System

The new bot system works like this:

1. **Start Bot**: `POST /api/bot/join`
   - Creates a bot session in `bot_sessions` table
   - Starts bot in background
   - Returns `bot_id` immediately

2. **Bot Runs**:
   - Joins the Daily room
   - Transcribes conversation (using Deepgram STT)
   - Has conversations based on `bot_config.bot_prompt`
   - Saves transcript to database in real-time

3. **Bot Finishes** (when participant leaves):
   - Automatically processes transcript:
     - Extracts Q&A pairs (`process_transcript.py`)
     - Extracts insights (`extract_insights.py`) - if enabled
   - Saves results to both:
     - `rooms` table (for backwards compatibility)
     - `bot_sessions` table (for bot-specific tracking)

4. **Check Status**: `GET /api/bot/{bot_id}/status`
   - Returns current status and results
   - Includes transcript, Q&A pairs, and insights when complete

### Integration with Existing Code

✅ **`process_transcript.py`** - Still works!
- Called automatically by `BotService._process_bot_results()`
- Processes transcript and extracts Q&A pairs
- No changes needed

✅ **`extract_insights.py`** - Still works!
- Called automatically by `BotService._process_bot_results()` if `process_insights=True`
- Extracts insights using AI analysis
- No changes needed

✅ **`flow/main.py`** - Updated gracefully
- Webhook handlers check if workflows exist before using them
- New bot system doesn't need webhooks (processes automatically)
- Old workflow-based system still works if workflows are available

## Environment Variables

Required:
- `DAILY_API_KEY` - For creating rooms
- `OPENAI_API_KEY` - For bot LLM and insights
- `DEEPGRAM_API_KEY` - For speech-to-text
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `ENCRYPTION_KEY` - Encryption key (at least 32 characters)

Optional:
- `API_BASE_URL` - API base URL (defaults to `http://localhost:8000`)
- `TEST_ROOM_URL` - Use existing room instead of creating one

## Example Usage

### Using the Test Script

```bash
# Set environment variables
export DAILY_API_KEY="your-daily-key"
export OPENAI_API_KEY="your-openai-key"
export DEEPGRAM_API_KEY="your-deepgram-key"
export SUPABASE_URL="https://xxxxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
export ENCRYPTION_KEY="your-32-char-encryption-key"

# Run test
python flow/demos/test_bot_api.py
```

### Using the API Directly

```python
import httpx

# Start bot
response = httpx.post(
    "http://localhost:8000/api/bot/join",
    json={
        "room_url": "https://domain.daily.co/room-name",
        "bot_config": {
            "bot_prompt": "You are a helpful assistant...",
            "name": "BotName",
            "video_mode": "static",
            "static_image": "robot01.png"
        },
        "process_insights": True
    },
    headers={"Authorization": "Bearer your-api-key"}
)
bot_id = response.json()["bot_id"]

# Check status
status = httpx.get(
    f"http://localhost:8000/api/bot/{bot_id}/status",
    headers={"Authorization": "Bearer your-api-key"}
).json()

print(f"Status: {status['status']}")
if status["status"] == "completed":
    print(f"Transcript: {status['transcript']}")
    print(f"Insights: {status['insights']}")
```

## Troubleshooting

### Bot doesn't start
- Check API authentication (Authorization header)
- Check server logs for errors
- Verify environment variables are set

### Bot starts but doesn't process
- Check that `process_insights` is set to `True` if you want insights
- Verify `OPENAI_API_KEY` is set for insights extraction
- Check server logs for processing errors

### Status endpoint returns 404
- Bot session may have been cleaned up
- Check that `bot_id` is correct
- Verify database connection

### Transcript not appearing
- Check that bot actually joined the room
- Verify `DEEPGRAM_API_KEY` is set
- Check server logs for transcription errors

## Next Steps

1. ✅ Run migration (`RUN_BOT_SESSIONS_MIGRATION.md`)
2. ✅ Test with script (`python flow/demos/test_bot_api.py`)
3. ✅ Integrate into your application
4. ✅ Customize `bot_config.bot_prompt` for your use case
