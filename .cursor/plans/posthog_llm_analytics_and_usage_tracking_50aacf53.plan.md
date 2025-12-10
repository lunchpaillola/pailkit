---
name: PostHog LLM Analytics and Usage Tracking
overview: Integrate PostHog LLM analytics to track all LLM usage (tokens, costs, latency) and store aggregated usage statistics in workflow_threads table. Track usage at API key level only (simple approach, not multi-tenant yet).
todos:
  - id: enhance_unkey_middleware
    content: Enhance Unkey middleware to extract api_key_id from Unkey API response and store in request.state
    status: completed
  - id: add_api_key_tracking_migration
    content: Create migration to add api_key_id column to workflow_threads table
    status: completed
  - id: add_usage_stats_migration
    content: Create migration to add usage_stats JSONB column to workflow_threads table
    status: completed
  - id: install_posthog
    content: Add posthog package to requirements.txt
    status: completed
  - id: create_posthog_config
    content: Create PostHog configuration module with client initialization and helper functions
    status: completed
  - id: integrate_posthog_extract_insights
    content: Wrap OpenAI client in ExtractInsightsStep with PostHog SDK for automatic tracking
    status: completed
  - id: track_pipecat_usage
    content: Implement manual usage tracking for pipecat-ai bot LLM calls (OpenAILLMService)
    status: completed
  - id: pass_api_key_context
    content: Update API endpoints to extract api_key_id from request.state and pass to workflows
    status: completed
  - id: update_db_helpers
    content: Update save_workflow_thread_data() and related functions to handle api_key_id and usage_stats
    status: completed
  - id: aggregate_usage_stats
    content: Implement usage aggregation logic to collect and store stats from all LLM calls in a workflow
    status: completed
---

# PostHog LLM Analytics and Usage Tracking Integration

## Overview

Integrate PostHog LLM analytics to automatically capture all LLM interactions (inputs, outputs, tokens, costs, latency) and store aggregated usage statistics in the `workflow_threads` table. Track usage at the API key level for simplicity (not multi-tenant yet - can add user-level tracking later when needed).

## Architecture

### Data Flow

```
API Request → Unkey Middleware (extract api_key_id)
  → Workflow Execution → LLM Calls (wrapped with PostHog)
  → Usage Aggregation → Save to workflow_threads
```

### Key Components

1. **Authentication Enhancement**: Extract `api_key_id` from Unkey verification
2. **PostHog Integration**: Wrap OpenAI clients with PostHog SDK for automatic tracking
3. **Usage Aggregation**: Collect usage stats per workflow run
4. **Database Schema**: Add `api_key_id` and usage columns to `workflow_threads`

## Implementation Plan

### 1. Enhance Unkey Middleware to Extract Unkey Key ID

**File**: `shared/auth/unkey_middleware.py`

- Modify Unkey verification to extract `keyId` (Unkey key identifier, e.g., "key_abc123") from Unkey API response
- Store in FastAPI request state: `request.state.unkey_key_id` (this is the Unkey key identifier, not the UUID)
- Handle cases where Unkey is not configured (dev/local) gracefully - set `unkey_key_id` to None

**Details**:

- Unkey API response includes `data.keyId` (Unkey key identifier string, not UUID)
- Store in request state as `unkey_key_id` for downstream handlers to access
- This will be used to look up the actual `api_keys.id` UUID in the endpoint

### 2. Add API Key Tracking to workflow_threads Table

**File**: `supabase/migrations/[timestamp]_add_api_key_tracking_to_workflow_threads.sql`

- Add `api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE`
- Add index: `idx_workflow_threads_api_key_id`
- Since app isn't live, no backwards compatibility needed - make it required

### 3. Add Usage Statistics Columns to workflow_threads

**File**: `supabase/migrations/[timestamp]_add_usage_stats_to_workflow_threads.sql`

- Add `usage_stats JSONB` column to store aggregated usage per workflow run
  - Structure: `{ "total_tokens": int, "total_cost_usd": float, "llm_calls": int, "models_used": {...}, "posthog_trace_id": str }`
- Alternative: Add individual columns for easier querying:
  - `total_tokens INTEGER DEFAULT 0`
  - `total_cost_usd DECIMAL(10, 6) DEFAULT 0`
  - `llm_calls_count INTEGER DEFAULT 0`
  - `posthog_trace_id TEXT` (for linking to PostHog dashboard)

**Recommendation**: Use JSONB for flexibility, but consider adding computed columns or views for common queries.

### 4. Install PostHog LLM Analytics SDK

**File**: `flow/requirements.txt`

- Add `posthog>=3.0.0` (PostHog Python SDK)
- PostHog LLM analytics is part of the main SDK

### 5. Create PostHog Configuration Module

**File**: `flow/utils/posthog_config.py` (new file)

- Initialize PostHog client with `POSTHOG_API_KEY` and `POSTHOG_HOST` environment variables
- Create helper functions:
  - `get_posthog_client()` - Get singleton PostHog client
  - `capture_llm_generation()` - Manual capture helper (for pipecat-ai)
  - Handle PostHog not configured gracefully (dev/local)

### 6. Integrate PostHog in ExtractInsightsStep

**File**: `flow/steps/agent_call/steps/extract_insights.py`

- Wrap `AsyncOpenAI` client with PostHog's OpenAI wrapper
- PostHog automatically captures: inputs, outputs, tokens, latency, cost
- Extract `workflow_thread_id` and `api_key_id` from state for context
- Store PostHog trace ID in usage_stats for linking

**Implementation**:

```python
from posthog import Posthog
from posthog.openai import openai  # PostHog's OpenAI wrapper

# Initialize PostHog-wrapped OpenAI client
posthog_client = get_posthog_client()
if posthog_client:
    # PostHog automatically wraps OpenAI calls
    client = openai.AsyncOpenAI(api_key=openai_api_key)
else:
    client = AsyncOpenAI(api_key=openai_api_key)
```

### 7. Track Usage from Pipecat-ai Bot Calls via MetricsFrame

**File**: `flow/steps/agent_call/bot/bot_executor.py` and `flow/steps/agent_call/bot/bot.py`

**Solution**: Pipecat-ai has built-in metrics support via `MetricsFrame` events! Metrics are already enabled (`enable_usage_metrics=True`) in both files. We just need to capture and process the MetricsFrame events.

**Reference**: [Pipecat Metrics Documentation](https://docs.pipecat.ai/guides/fundamentals/metrics) - MetricsFrame contains LLMUsageMetricsData with prompt_tokens and completion_tokens

**Implementation**:

1. **Create MetricsFrame Processor**: Create a custom `FrameProcessor` that captures `MetricsFrame` events

   - File: `flow/steps/agent_call/bot/metrics_processor.py` (new file)
   - Import: `from pipecat.frames.frames import MetricsFrame`
   - Import: `from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData`
   - Extract `LLMUsageMetricsData` from `MetricsFrame.data` (contains `prompt_tokens` and `completion_tokens`)
   - Extract `TTSUsageMetricsData` if needed (character count)
   - Store metrics in workflow_thread_data via `workflow_thread_id` (passed to processor)
   - Use `flow.db.save_workflow_thread_data()` to update usage_stats incrementally

2. **Add Metrics Processor to Pipeline**: Insert the metrics processor into the pipeline after the LLM service

   - Add to `pipeline_components` list in both `bot_executor.py` and `bot.py`
   - Place after `llm` but before `tts` to capture LLM metrics
   - Pass `workflow_thread_id` to the processor constructor so it can update workflow_thread_data
   - Example: `UsageMetricsProcessor(workflow_thread_id=workflow_thread_id)`

3. **Aggregate and Send to PostHog**:

   - Accumulate token usage from multiple MetricsFrame events per workflow run
   - Calculate total tokens: `total_tokens = prompt_tokens + completion_tokens`
   - Calculate cost using OpenAI pricing (based on model used - gpt-4o, gpt-4.1, etc.)
   - Send aggregated usage to PostHog using `capture_llm_generation()` or PostHog's manual capture API
   - Store aggregated stats in workflow_threads `usage_stats` JSONB column

**Note**: Metrics are already enabled (`enable_usage_metrics=True`) in both `bot_executor.py` and `bot.py` - we just need to capture the MetricsFrame events.

### 8. Aggregate and Store Usage Statistics

**File**: `flow/db.py`

- Modify `save_workflow_thread_data()` to accept and save usage_stats
- Create helper function `aggregate_usage_stats()` to combine usage from multiple LLM calls
- Update usage_stats when saving workflow thread data

**File**: `flow/workflows/bot_call.py` and `flow/steps/agent_call/steps/process_transcript.py`

- Extract api_key_id from request context (passed through workflow)
- Aggregate usage stats from all LLM calls in the workflow
- Save aggregated stats to workflow_threads at workflow completion

### 9. Associate API Key When Creating workflow_thread_id

**File**: `flow/main.py` (in `/api/bot/join` endpoint)

- Extract `api_key_id` from `request.state.api_key_id` (set by Unkey middleware)
- Add `api_key_id` to `workflow_thread_data` dictionary when creating workflow_thread_id (around line 343-361)
- Save it directly to workflow_threads table - no need to pass through workflows since workflow_thread_id already exists

**Note**: Since `workflow_thread_id` is created in the API endpoint before the workflow starts, we can associate `api_key_id` at creation time. The workflow can then read it from `workflow_thread_data` if needed.

### 10. Update Database Helper Functions

**File**: `flow/db.py`

- Update `save_workflow_thread_data()` to handle `api_key_id` and `usage_stats`
- Update `get_workflow_thread_data()` to return usage_stats
- Add helper function `get_usage_stats_by_api_key_id()` for analytics queries

## LLM Usage Points

1. **ExtractInsightsStep** (`flow/steps/agent_call/steps/extract_insights.py`):

   - Direct OpenAI API call (gpt-4o) - Can use PostHog wrapper directly

2. **BotExecutor/Bot** (`flow/steps/agent_call/bot/bot_executor.py`, `flow/steps/agent_call/bot/bot.py`):

   - Pipecat-ai's `OpenAILLMService` - Requires manual tracking or wrapper

## Environment Variables

Add to `flow/env.example`:

```
# PostHog Configuration
POSTHOG_API_KEY=phx_...  # PostHog project API key
POSTHOG_HOST=https://app.posthog.com  # PostHog host (or https://eu.posthog.com for EU)
```

## Testing Strategy

1. **Unit Tests**: Test PostHog integration with mocked PostHog client
2. **Integration Tests**: Verify usage stats are saved correctly to workflow_threads
3. **Manual Testing**: Run a workflow and verify PostHog dashboard shows LLM generations
4. **Edge Cases**: Test with PostHog not configured, Unkey not configured, missing api_key_id

## Migration Strategy

1. Add columns as nullable for backwards compatibility
2. Backfill api_key_id for existing workflow_threads (if possible)
3. Gradually enable PostHog tracking (feature flag)
4. Monitor PostHog event volume and costs

## Considerations

- **PostHog Costs**: PostHog LLM analytics has a free tier (100K events/month), then usage-based pricing
- **Pipecat-ai Limitation**: Manual tracking required for bot LLM calls (no direct OpenAI client access)
- **Performance**: PostHog tracking is async and shouldn't block workflow execution
- **Privacy**: Ensure sensitive data (transcripts) isn't sent to PostHog
- **Future Multi-tenant**: When adding user-level tracking later, can add `user_id` column and link via `api_keys.user_id`
