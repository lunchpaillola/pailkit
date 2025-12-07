# Bot Simplification Plan

## Goal
Simplify the bot system to just join existing Daily rooms, transcribe, and process results. Remove all room creation, complex workflows, and unnecessary steps.

---

## What to Keep

### Core Bot Functionality
- ✅ `flow/steps/interview/bot_service.py` - Core bot service (join, transcribe, converse)
- ✅ `flow/steps/interview/bot.py` - Standalone bot script (for Fly.io machines)
- ✅ `flow/steps/interview/process_transcript.py` - Process transcript after bot finishes
- ✅ `flow/steps/interview/extract_insights.py` - Extract insights from processed transcript
- ✅ `flow/hosting/meeting.html` - Meeting page (just pass room_url in URL params)

### Supporting Files
- ✅ `flow/steps/interview/base.py` - Base step class (if needed for process/extract)
- ✅ Database functions (for saving transcripts)

---

## What to Delete

### Room Creation & Management
- ❌ `flow/steps/interview/create_room.py` - No longer creating rooms
- ❌ `flow/steps/interview/join_bot.py` - Can be simplified or removed

### Workflow Orchestration
- ❌ `flow/workflows/ai_interviewer.py` - Complex workflow, replace with simple API
- ❌ `flow/workflows/one_time_meeting.py` - Not needed if not creating rooms

### Unnecessary Steps
- ❌ `flow/steps/interview/configure_agent.py` - Bot config comes from API request
- ❌ `flow/steps/interview/generate_questions.py` - Questions come from bot_config
- ❌ `flow/steps/interview/conduct_interview.py` - Bot already does this
- ❌ `flow/steps/interview/generate_summary.py` - Optional, can merge into extract_insights if needed
- ❌ `flow/steps/interview/package_results.py` - Just return data directly

---

## What to Build

### 1. Simple Bot API Endpoint

**Location:** `api/routers/bot.py` (new file)

**Endpoint:** `POST /api/bot/join`

**Request:**
```json
{
  "room_url": "https://domain.daily.co/room-name",
  "token": "optional-meeting-token",
  "bot_config": {
    "bot_prompt": "You are a helpful AI assistant...",
    "name": "BotName",
    "video_mode": "static",
    "static_image": "robot01.png"
  },
  "process_insights": true  // optional: whether to extract insights
}
```

**Response:**
```json
{
  "status": "started",
  "bot_id": "uuid",
  "room_url": "https://domain.daily.co/room-name"
}
```

**Flow:**
1. Validate request
2. Start bot via `bot_service.start_bot(room_url, token, bot_config)`
3. Return immediately (bot runs in background)

---

### 2. Bot Status/Results Endpoint

**Endpoint:** `GET /api/bot/{bot_id}/status`

**Response (while running):**
```json
{
  "status": "running",
  "room_url": "https://domain.daily.co/room-name",
  "started_at": "2025-01-15T10:00:00Z"
}
```

**Response (when finished):**
```json
{
  "status": "completed",
  "room_url": "https://domain.daily.co/room-name",
  "started_at": "2025-01-15T10:00:00Z",
  "completed_at": "2025-01-15T10:30:00Z",
  "transcript": "full transcript text...",
  "qa_pairs": [...],
  "insights": {...}
}
```

---

### 3. Modify Bot Service

**File:** `flow/steps/interview/bot_service.py`

**Changes:**
- When bot finishes (participant leaves), automatically:
  1. Process transcript using `ProcessTranscriptStep`
  2. Extract insights using `ExtractInsightsStep` (if enabled)
  3. Store results in database with bot_id
  4. Mark bot as completed

**Add to BotService:**
- Track bot_id for each bot instance
- Store results when bot completes
- Allow querying results by bot_id

---

### 4. Simplify meeting.html

**File:** `flow/hosting/meeting.html`

**Changes:**
- Accept `room_url` as URL parameter: `?room_url=https://domain.daily.co/room-name`
- Accept `token` as URL parameter: `&token=optional-token`
- Remove room creation logic
- Just join the existing room

---

## Implementation Steps

### Phase 1: Clean Up
1. Delete unnecessary step files:
   - `create_room.py`
   - `configure_agent.py`
   - `generate_questions.py`
   - `conduct_interview.py`
   - `generate_summary.py`
   - `package_results.py`
   - `join_bot.py` (or simplify it)

2. Delete workflow files:
   - `workflows/ai_interviewer.py`
   - `workflows/one_time_meeting.py` (if not used elsewhere)

3. Update `flow/steps/interview/__init__.py` to remove deleted imports

### Phase 2: Build Simple API
1. Create `api/routers/bot.py`:
   - `POST /api/bot/join` - Start bot
   - `GET /api/bot/{bot_id}/status` - Get status/results

2. Register router in `api/main.py`:
   ```python
   from api.routers.bot import router as bot_router
   app.include_router(bot_router, prefix="/api/bot", tags=["Bot"])
   ```

### Phase 3: Modify Bot Service
1. Add bot_id tracking to `BotService`
2. Add automatic post-processing when bot finishes:
   - Process transcript
   - Extract insights (if enabled)
   - Store results
3. Add method to get results by bot_id

### Phase 4: Update meeting.html
1. Read `room_url` from URL params
2. Read `token` from URL params (optional)
3. Join room directly (no creation)

### Phase 5: Testing
1. Test bot joining existing Daily room
2. Test transcript processing
3. Test insights extraction
4. Test API endpoints

---

## Database Schema (if needed)

**Bot Sessions Table:**
```sql
CREATE TABLE bot_sessions (
  bot_id UUID PRIMARY KEY,
  room_url TEXT NOT NULL,
  room_name TEXT,
  status TEXT, -- 'running', 'completed', 'failed'
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  transcript_text TEXT,
  qa_pairs JSONB,
  insights JSONB,
  error TEXT
);
```

---

## Benefits

✅ **Much simpler** - Single API endpoint, no complex workflows
✅ **More scalable** - Bot just joins existing rooms, no room management
✅ **Easier to maintain** - Fewer files, clearer flow
✅ **Flexible** - Can use any Daily room (static or dynamic)
✅ **Provider-agnostic** - DailyTransport only, other providers via recall.ai

---

## Notes

- **No Daily API Key needed** - Bot only needs room_url and optional token
- **No room creation** - All rooms are created externally
- **Static rooms work** - Bot can join any existing Daily room
- **meeting.html** - Just pass room_url in URL, it joins directly
- **Future providers** - Use recall.ai for Zoom/Teams/etc, completely separate

---

## Migration Path

1. Keep old code in a branch (backup)
2. Implement new simple API alongside old code
3. Test thoroughly
4. Switch over
5. Delete old code
