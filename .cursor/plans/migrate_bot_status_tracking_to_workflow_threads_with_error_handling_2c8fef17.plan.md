---
name: Migrate bot status tracking to workflow_threads with error handling
overview: Migrate all bot status tracking from bot_sessions table to workflow_threads table, add comprehensive error tracking with error stages, and implement proper status state machine (pending → starting → running → completed/failed). This consolidates all bot-related data into workflow_threads for a single source of truth.
todos:
  - id: "1"
    content: Create database migration to add bot_status, error_stage, error_code, error_message, error_details, bot_started_at, bot_completed_at, bot_status_updated_at columns to workflow_threads
    status: pending
  - id: "2"
    content: Update save_workflow_thread_data() and add update_bot_status() helper function in db.py
    status: pending
    dependencies:
      - "1"
  - id: "3"
    content: Add get_workflow_thread_by_bot_id() helper function to lookup by bot_id
    status: pending
    dependencies:
      - "1"
  - id: "4"
    content: Update fly_machine.py to update bot_status (pending → starting) and handle machine start errors
    status: pending
    dependencies:
      - "2"
  - id: "5"
    content: Update bot_executor.py to update bot_status (starting → running) and handle join/runtime errors
    status: pending
    dependencies:
      - "2"
  - id: "6"
    content: Update bot_call.py workflow to update bot_status at each stage and handle workflow errors
    status: pending
    dependencies:
      - "2"
  - id: "7"
    content: Update main.py join_bot() endpoint to use workflow_threads instead of bot_sessions
    status: pending
    dependencies:
      - "2"
      - "3"
  - id: "8"
    content: Update main.py get_bot_status_by_id() endpoint to read from workflow_threads instead of bot_sessions
    status: pending
    dependencies:
      - "2"
      - "3"
  - id: "9"
    content: Update BotStatusResponse model to include error_stage, error_code, error_details fields
    status: pending
  - id: "10"
    content: Update result_processor.py to set bot_status=completed and remove bot_sessions references
    status: pending
    dependencies:
      - "2"
  - id: "11"
    content: Remove all save_bot_session() and get_bot_session() calls throughout codebase
    status: pending
    dependencies:
      - "7"
      - "8"
      - "10"
---

# Migrate Bot Status Tracking to workflow_threads with Error Handling

## Current State

- **bot_sessions table**: Currently used for bot status tracking (`running`, `completed`, `failed`)
- **workflow_threads table**: Already has `bot_id` and bot config, but missing status tracking
- **Status endpoint**: Uses `bot_sessions` table to query by `bot_id`
- **Error tracking**: Basic `error` field, no error stage tracking

## Goal

Consolidate all bot status and error tracking into `workflow_threads` table, eliminating the need for `bot_sessions` table. Add comprehensive error tracking with stages and implement a proper state machine.

## Implementation Plan

### Step 1: Database Migration - Add Status Fields to workflow_threads

**File:** `supabase/migrations/YYYYMMDDHHMMSS_add_bot_status_to_workflow_threads.sql`Add new columns to `workflow_threads` table:

- `bot_status TEXT` - Status: `pending`, `starting`, `running`, `completed`, `failed`
- `bot_status_updated_at TIMESTAMPTZ` - When status last changed
- `error_stage TEXT` - Where error occurred: `machine_start`, `joining`, `running`, `processing`
- `error_code TEXT` - Programmatic error code (e.g., `JOIN_TIMEOUT`, `MACHINE_START_FAILED`)
- `error_message TEXT` - Human-readable error message
- `error_details JSONB` - Structured error details
- `bot_started_at TIMESTAMPTZ` - When bot actually started (different from created_at)
- `bot_completed_at TIMESTAMPTZ` - When bot finished (different from meeting_end_time)

Create index on `bot_status` for efficient queries.

### Step 2: Update Database Helper Functions

**File:** `flow/db.py`

- Update `save_workflow_thread_data()` to handle new bot status fields
- Add helper functions:
- `update_bot_status(workflow_thread_id, status, error_stage=None, error_code=None, error_message=None)`
- `get_workflow_thread_by_bot_id(bot_id)` - Lookup by bot_id instead of workflow_thread_id
- Remove or deprecate `save_bot_session()` and `get_bot_session()` functions

### Step 3: Update Bot Lifecycle to Track Status

**File:** `flow/steps/agent_call/bot/fly_machine.py`

- When machine is created: Update status to `pending` in workflow_threads
- When machine starts: Update status to `starting` in workflow_threads
- On machine creation failure: Update status to `failed` with `error_stage="machine_start"`

**File:** `flow/steps/agent_call/bot/bot_executor.py`

- When bot joins room: Update status to `running` in workflow_threads
- On join failure: Update status to `failed` with `error_stage="joining"`
- When bot crashes during conversation: Update status to `failed` with `error_stage="running"`
- When bot leaves normally: Status updated to `completed` (handled by workflow resume)

**File:** `flow/workflows/bot_call.py`

- In `_join_bot_node()`: Update status to `pending` when machine is created
- On workflow start failure: Update status to `failed` with appropriate error_stage
- In `_process_transcript_node()`: On processing failure, update status to `failed` with `error_stage="processing"`

### Step 4: Migrate Status Endpoint to Use workflow_threads

**File:** `flow/main.py`

- Update `get_bot_status_by_id()` endpoint:
- Remove `get_bot_session(bot_id)` call
- Use `get_workflow_thread_by_bot_id(bot_id)` instead
- Return data from workflow_threads (status, error fields, transcript, insights, etc.)
- Update `join_bot()` endpoint:
- Remove `save_bot_session()` call
- Update workflow_threads with initial bot status (`pending`)
- Remove bot_session_data creation

### Step 5: Update Error Handling Throughout

**Files:** Multiple files that handle bot errors

- Wrap critical sections in try/catch blocks
- Call `update_bot_status()` with appropriate error_stage and error_code
- Ensure errors are logged and saved to workflow_threads

**Error Stages:**

- `machine_start`: Fly.io machine failed to start
- `joining`: Bot failed to join Daily.co room
- `running`: Bot crashed during conversation
- `processing`: Transcript processing failed

**Error Codes (examples):**

- `MACHINE_START_TIMEOUT`
- `MACHINE_START_FAILED`
- `JOIN_ROOM_TIMEOUT`
- `JOIN_ROOM_AUTH_FAILED`
- `BOT_CRASHED`
- `TRANSCRIPT_PROCESSING_FAILED`

### Step 6: Update Result Processor

**File:** `flow/steps/agent_call/bot/result_processor.py`

- Remove references to `bot_sessions` table
- Update status to `completed` in workflow_threads when processing finishes
- Save all results (transcript, qa_pairs, insights) to workflow_threads

### Step 7: Clean Up bot_sessions References

**Files:** All files that reference bot_sessions

- Remove all `save_bot_session()` and `get_bot_session()` calls
- Remove `get_bot_session_by_room_name()` if no longer needed
- Update any code that queries bot_sessions table

### Step 8: Update API Response Models

**File:** `flow/main.py`

- Update `BotStatusResponse` model to include:
- `error_stage: str | None`
- `error_code: str | None`
- `error_details: dict | None`
- `bot_status_updated_at: str | None`

## State Machine Flow

```javascript
pending → starting → running → completed
         ↓           ↓         ↓
       failed      failed    failed
```

**State Transitions:**

- `pending`: Machine created, waiting to start
- `starting`: Machine starting, bot initializing
- `running`: Bot joined room, active conversation
- `completed`: Bot finished, transcript processed successfully
- `failed`: Error at any stage (with error_stage indicating where)

## Key Benefits

1. **Single Source of Truth**: All bot data in workflow_threads
2. **Better Error Diagnostics**: Know exactly where failures occur
3. **Simpler Architecture**: One table instead of two
4. **Workflow Integration**: Status tied to workflow lifecycle
5. **Query Efficiency**: Can query by bot_id or workflow_thread_id

## Migration Strategy

1. Add new columns to workflow_threads (non-breaking)
2. Update code to write to both tables temporarily (dual-write)
3. Update status endpoint to read from workflow_threads
4. Remove bot_sessions writes
5. Eventually drop bot_sessions table (separate migration)

## Testing Considerations

- Verify status updates at each lifecycle stage
- Test error handling at each error_stage
- Verify status endpoint returns correct data from workflow_threads
