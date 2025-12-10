---
name: Bot Usage Cost Tracking
overview: Implement cost category tracking for bot usage metrics, allowing separate tracking of bot costs vs insights costs in the database. Update the UsageMetricsProcessor to use pricing.py and integrate it into the bot pipeline.
todos:
  - id: "1"
    content: Update usage_tracking.py to add cost_category parameter and implement category-specific cost tracking
    status: pending
  - id: "2"
    content: Update metrics_processor.py to use pricing.py calculate_cost and call update_workflow_usage_cost with cost_category="bot"
    status: pending
  - id: "3"
    content: Integrate UsageMetricsProcessor into bot_executor.py pipeline after LLM service
    status: pending
  - id: "4"
    content: Update extract_insights.py to use cost_category="insights" when calling update_workflow_usage_cost
    status: pending
---

# Bot Usage Cost Tracking Implementation

## Overview

Implement cost category tracking to separately track bot LLM costs and insights costs in the `workflow_threads.usage_stats` JSONB column. This prevents cost overwriting and provides granular cost breakdown.

## Database Structure

The `usage_stats` JSONB will store:

```json
{
  "bot_cost_usd": 0.12,        // Accumulated from bot LLM calls
  "insights_cost_usd": 0.03,   // Accumulated from extract_insights
  "total_cost_usd": 0.15,      // Sum of all categories
  "posthog_trace_id": "..."
}
```

## Implementation Steps

### 1. Update `flow/utils/usage_tracking.py`

Add `cost_category` parameter to `update_workflow_usage_cost`:

- Add optional `cost_category: str | None = None` parameter
- If `cost_category` is provided, update `{cost_category}_cost_usd` field in `usage_stats`
- Always update `total_cost_usd` (sum of all categories)
- Add debug logging for category-specific costs

**File**: `flow/utils/usage_tracking.py`

**Function**: `update_workflow_usage_cost`

### 2. Update `flow/steps/agent_call/bot/metrics_processor.py`

Fix LLM cost calculation and database tracking:

- Replace hardcoded pricing with `calculate_cost` from `flow/utils/pricing.py`
- Remove import of non-existent `aggregate_usage_stats` from `flow.db`
- Replace `aggregate_usage_stats` call with `update_workflow_usage_cost` from `flow/utils/usage_tracking.py`
- Pass `cost_category="bot"` when calling `update_workflow_usage_cost`
- Extract model name from `LLMUsageMetricsData` (check `model` attribute)
- Keep PostHog tracking via `capture_llm_generation`

**File**: `flow/steps/agent_call/bot/metrics_processor.py`

**Method**: `_process_llm_metrics`

### 3. Integrate UsageMetricsProcessor into Bot Pipeline

Add `UsageMetricsProcessor` to the Pipecat pipeline:

- Import `UsageMetricsProcessor` in `bot_executor.py`
- Create instance with `workflow_thread_id` parameter
- Insert processor after `llm` service in `pipeline_components` list (before `tts`)
- This ensures it captures all LLM usage metrics from the bot

**File**: `flow/steps/agent_call/bot/bot_executor.py`

**Method**: `run` (around line 258-270)

### 4. Update `flow/steps/agent_call/steps/extract_insights.py`

Add cost category for insights tracking:

- Update `update_workflow_usage_cost` call to include `cost_category="insights"`
- This ensures insights costs are tracked separately from bot costs

**File**: `flow/steps/agent_call/steps/extract_insights.py`

**Location**: Around line 343-345

## Testing Considerations

- Verify bot LLM calls are tracked with `bot_cost_usd` category
- Verify insights LLM calls are tracked with `insights_cost_usd` category
- Verify `total_cost_usd` is the sum of both categories
- Verify PostHog tracking still works for both bot and insights calls
- Test with multiple LLM calls in a single workflow to ensure accumulation works

## Future Enhancements (Not in this plan)

- TTS cost tracking (currently commented out in `metrics_processor.py`)
- STT (Deepgram) cost tracking
- Per-minute runtime tracking
