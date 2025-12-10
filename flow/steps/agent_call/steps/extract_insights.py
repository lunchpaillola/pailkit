# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Extract Insights Step

This step extracts insights and assesses competencies from the interview.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, cast

from flow.steps.agent_call.steps.base import InterviewStep

logger = logging.getLogger(__name__)


class ExtractInsightsStep(InterviewStep):
    """
    Extract insights and assess competencies.
    """

    def __init__(self):
        super().__init__(
            name="extract_insights",
            description="Extract insights and assess candidate competencies",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute insight extraction using AI analysis.

        Args:
            state: Current workflow state containing qa_pairs and interview_config

        Returns:
            Updated state with insights
        """
        # Validate required state
        if not self.validate_state(state, ["qa_pairs"]):
            return self.set_error(state, "Missing required state: qa_pairs")

        qa_pairs = state.get("qa_pairs", [])
        meeting_config = state.get("meeting_config", {})
        interview_config = state.get("interview_config", {})

        # Get analysis prompt - this is the main way to configure analysis
        # Can come from meeting_config or interview_config (for backwards compatibility)
        analysis_prompt = (
            meeting_config.get("analysis_prompt")
            or interview_config.get("analysis_prompt")
            or None
        )

        logger.info("🧠 Extracting insights using AI analysis")
        if analysis_prompt:
            logger.info(
                f"   Using custom analysis prompt ({len(analysis_prompt)} chars)"
            )
        else:
            logger.info("   Using default analysis prompt")

        # Get workflow_thread_id for usage tracking
        workflow_thread_id = state.get("workflow_thread_id")
        room_name = state.get("room_name")

        # Get PostHog-wrapped OpenAI client (with graceful degradation)
        # Simple Explanation: This gets an OpenAI client that automatically tracks
        # all LLM calls to PostHog. If PostHog isn't configured, it returns a
        # regular OpenAI client without tracking.
        from flow.utils.posthog_config import get_posthog_llm_client
        from flow.utils.usage_tracking import update_workflow_usage_cost
        from flow.db import get_workflow_thread_data

        client, is_posthog_enabled = get_posthog_llm_client()

        if not client:
            logger.warning("⚠️ Cannot create OpenAI client - using placeholder insights")
            return self._create_placeholder_insights(state, qa_pairs, [])

        # Generate a reference ID for this workflow execution (for our own tracking)
        # Note: This is NOT PostHog's trace_id. PostHog generates its own trace_id server-side
        # and doesn't return it in the response. To find traces in PostHog, search by:
        # - distinct_id (should be workflow_thread_id or unkey_key_id)
        # - timestamp (when the call was made)
        # - model name (e.g., "gpt-4.1")
        posthog_trace_id = None
        if workflow_thread_id:
            thread_data = get_workflow_thread_data(workflow_thread_id)
            if thread_data and thread_data.get("usage_stats"):
                posthog_trace_id = thread_data["usage_stats"].get("posthog_trace_id")

        if not posthog_trace_id:
            posthog_trace_id = str(uuid.uuid4())
            logger.debug(f"Generated new reference ID for tracking: {posthog_trace_id}")

        # Get distinct_id for PostHog (unkey_key_id if available, fallback to workflow_thread_id)
        # Simple Explanation: distinct_id identifies who made the API call. We prefer
        # the API key ID (unkey_key_id) if available, otherwise use workflow_thread_id.
        posthog_distinct_id = workflow_thread_id or "unknown"
        if workflow_thread_id:
            thread_data = get_workflow_thread_data(workflow_thread_id)
            if thread_data:
                unkey_key_id = thread_data.get("unkey_key_id")
                if unkey_key_id:
                    posthog_distinct_id = unkey_key_id

        try:

            # Build transcript text from Q&A pairs
            qa_text = "\n\n".join(
                [
                    f"Q{i+1}: {qa.get('question', '')}\nA{i+1}: {qa.get('answer', '')}"
                    for i, qa in enumerate(qa_pairs)
                ]
            )

            # Use custom analysis prompt if provided, otherwise use default
            if analysis_prompt:
                # User provided a custom prompt - inject the transcript into it
                # Look for placeholders like {transcript} or {qa_text} or just append
                if "{transcript}" in analysis_prompt:
                    final_prompt = analysis_prompt.replace("{transcript}", qa_text)
                elif "{qa_text}" in analysis_prompt:
                    final_prompt = analysis_prompt.replace("{qa_text}", qa_text)
                else:
                    # No placeholder found - append transcript at the end
                    final_prompt = (
                        f"{analysis_prompt}\n\nConversation Transcript:\n{qa_text}"
                    )
            else:
                # Default analysis prompt (generic, not interview-specific)
                final_prompt = f"""Analyze this conversation transcript and provide a comprehensive assessment.

Conversation Transcript:
{qa_text}

Please provide a JSON response with the following structure:
{{
    "overall_score": <number 0-10>,
    "competency_scores": {{
        "<competency_name>": <score 0-10>,
        ...
    }},
    "strengths": ["<strength1>", "<strength2>", ...],
    "weaknesses": ["<weakness1>", "<weakness2>", ...],
    "question_assessments": [
        {{
            "question": "<question text>",
            "answer": "<answer text>",
            "score": <number 0-10>,
            "notes": "<brief assessment notes>"
        }},
        ...
    ]
}}

Guidelines:
- Analyze the conversation objectively
- Identify key themes, competencies, or topics discussed
- Provide specific, constructive feedback
- Score each Q&A pair individually (0-10)
- Focus on what was actually said in the transcript

Return ONLY valid JSON, no additional text."""

            # Call OpenAI API with PostHog tracking
            logger.info("🤖 Calling OpenAI API for analysis...")
            if is_posthog_enabled:
                # Use PostHog-wrapped client with responses.create()
                # Simple Explanation: PostHog's wrapper uses responses.create() instead of
                # chat.completions.create(). We use the input parameter (same structure as messages)
                # PostHog automatically tracks all calls made through this client.
                # Note: response_format is not supported, so we rely on the prompt to request JSON format.
                # PostHog tracking parameters:
                # - posthog_distinct_id: Identifies the user/API key (required for tracking)
                # - posthog_trace_id: Optional trace ID for correlating events
                # - posthog_properties: Optional additional properties for the event
                posthog_properties = {
                    "workflow_thread_id": workflow_thread_id,
                    "room_name": room_name,
                    "step_name": "extract_insights",
                }
                logger.debug(
                    f"📊 PostHog tracking parameters: distinct_id={posthog_distinct_id}, "
                    f"trace_id={posthog_trace_id}, properties={posthog_properties}"
                )
                response = await client.responses.create(
                    model="gpt-4.1",
                    input=[
                        {
                            "role": "system",
                            "content": "You are an expert call evaluator. Always respond with valid JSON only.",
                        },
                        {"role": "user", "content": final_prompt},
                    ],
                    temperature=0.3,  # Lower temperature for more consistent analysis
                    posthog_distinct_id=posthog_distinct_id,
                    posthog_trace_id=posthog_trace_id,
                    posthog_properties=posthog_properties,
                )
            else:
                # Fallback to regular OpenAI API (no PostHog tracking)
                response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert interview evaluator. Always respond with valid JSON only.",
                        },
                        {"role": "user", "content": final_prompt},
                    ],
                    temperature=0.3,  # Lower temperature for more consistent analysis
                    response_format={"type": "json_object"},
                )

            # Parse response
            # Simple Explanation: PostHog-wrapped responses use output_text attribute
            # instead of the standard OpenAI response structure. For fallback (non-PostHog),
            # we still use the standard structure.
            if is_posthog_enabled:
                response_text = response.output_text
            else:
                response_text = response.choices[0].message.content
            insights = json.loads(response_text)

            # Extract cost and trace_id from PostHog response and update usage_stats
            # Simple Explanation: PostHog automatically calculates the cost and adds it
            # to the response as $ai_total_cost_usd. We extract it and save it to the
            # database so we can track total costs per workflow. PostHog also generates
            # its own trace_id which we should extract and use instead of generating our own.
            cost_usd = 0.0
            actual_posthog_trace_id = None
            if is_posthog_enabled and workflow_thread_id:
                # Extract cost from PostHog response
                # Simple Explanation: PostHog adds cost information to the response object
                # as an attribute. We use getattr() to safely get it, defaulting to 0.0.
                cost_usd = getattr(response, "$ai_total_cost_usd", 0.0) or 0.0

                # Extract trace_id from PostHog response (PostHog generates its own)
                # Try common attribute names that PostHog might use
                for attr_name in [
                    "trace_id",
                    "$trace_id",
                    "posthog_trace_id",
                    "$posthog_trace_id",
                ]:
                    trace_id_value = getattr(response, attr_name, None)
                    if trace_id_value:
                        actual_posthog_trace_id = str(trace_id_value)
                        logger.debug(
                            f"✅ Found PostHog trace_id in response.{attr_name}: {actual_posthog_trace_id}"
                        )
                        break

                # If we found a trace_id from PostHog, use it; otherwise use the one we generated
                if actual_posthog_trace_id:
                    posthog_trace_id = actual_posthog_trace_id
                    logger.info(
                        f"✅ Using PostHog trace_id from response: {posthog_trace_id}"
                    )
                else:
                    # PostHog doesn't return trace_id in response - it generates its own server-side
                    # The trace_id we're using is just for our own reference in the database
                    logger.info(
                        f"ℹ️ PostHog generates its own trace_id server-side (not in response). "
                        f"Using reference ID for database: {posthog_trace_id}"
                    )
                    logger.info(
                        f"   To find this trace in PostHog dashboard, search by: "
                        f"distinct_id={posthog_distinct_id}, model=gpt-4.1, timestamp={workflow_thread_id}"
                    )

                logger.debug(
                    f"💰 Cost extracted: ${cost_usd:.6f}, posthog_trace_id: {posthog_trace_id}"
                )

                if cost_usd > 0:
                    logger.info(
                        f"💰 LLM call cost: ${cost_usd:.6f} (tracked by PostHog)"
                    )
                    # Update usage_stats in database
                    success = update_workflow_usage_cost(
                        workflow_thread_id, cost_usd, posthog_trace_id
                    )
                    if success:
                        logger.info(
                            f"✅ Cost saved to database for {workflow_thread_id}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Failed to save cost to database for {workflow_thread_id}"
                        )
                else:
                    logger.warning(
                        "💰 No cost information in PostHog response (cost is 0 or not available)"
                    )
                    # Even if cost is 0, we should still save the trace_id if available
                    if posthog_trace_id:
                        logger.debug(
                            f"💰 Saving PostHog trace_id even though cost is 0: {posthog_trace_id}"
                        )
                        update_workflow_usage_cost(
                            workflow_thread_id, 0.0, posthog_trace_id
                        )
            elif not is_posthog_enabled:
                logger.debug("💰 PostHog tracking not enabled - cost not tracked")

            # Validate and normalize insights
            try:
                insights = self._validate_insights(insights, qa_pairs)
            except Exception as validation_error:
                logger.error(
                    f"❌ Error validating insights structure: {validation_error}",
                    exc_info=True,
                )
                logger.warning("⚠️ Using placeholder insights due to validation error")
                return self._create_placeholder_insights(state, qa_pairs, [])

            state["insights"] = insights
            state = self.update_status(state, "insights_extracted")

            logger.info(f"✅ Extracted insights for {len(qa_pairs)} questions")
            logger.info(f"   Overall Score: {insights.get('overall_score', 0.0)}/10")
            logger.info(
                f"   Competencies: {len(insights.get('competency_scores', {}))}"
            )
            logger.info(f"   Strengths: {len(insights.get('strengths', []))}")
            logger.info(f"   Weaknesses: {len(insights.get('weaknesses', []))}")

            return state

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse AI response as JSON: {e}")
            logger.error(
                f"   Response: {response_text[:500] if 'response_text' in locals() else 'N/A'}"
            )
            logger.warning("⚠️ Using placeholder insights due to JSON parsing error")
            return self._create_placeholder_insights(state, qa_pairs, [])
        except Exception as e:
            error_type = type(e).__name__
            logger.error(
                f"❌ Error during AI analysis ({error_type}): {e}",
                exc_info=True,
            )
            logger.warning("⚠️ Using placeholder insights due to analysis error")
            return self._create_placeholder_insights(state, qa_pairs, [])

    def _validate_insights(
        self, insights: Dict[str, Any], qa_pairs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate and normalize insights structure.
        """
        # Validate qa_pairs structure - ensure all items are dictionaries
        if not isinstance(qa_pairs, list):
            logger.warning(
                f"⚠️ qa_pairs is not a list (got {type(qa_pairs).__name__}), converting to empty list"
            )
            qa_pairs = []

        # Filter out any non-dict items from qa_pairs
        valid_qa_pairs = []
        invalid_qa_count = 0
        for qa in qa_pairs:
            if isinstance(qa, dict):
                valid_qa_pairs.append(qa)
            else:
                invalid_qa_count += 1
                logger.warning(
                    f"⚠️ Skipping invalid qa_pair (expected dict, got {type(qa).__name__}): {qa}"
                )

        if invalid_qa_count > 0:
            logger.warning(f"⚠️ Filtered out {invalid_qa_count} invalid qa_pair(s)")
            qa_pairs = valid_qa_pairs

        # Start with all fields from insights to preserve custom fields
        # (e.g., person_name, problem, timeline, etc. for lead qualification)
        validated = dict(insights)

        # Ensure all required fields exist with defaults
        validated.setdefault("overall_score", 0.0)
        validated.setdefault("competency_scores", {})
        validated.setdefault("strengths", [])
        validated.setdefault("weaknesses", [])
        validated.setdefault("question_assessments", [])

        # Normalize required fields
        validated["overall_score"] = float(validated["overall_score"])

        # Clamp scores to 0-10
        validated["overall_score"] = max(0.0, min(10.0, validated["overall_score"]))

        # Clamp competency scores
        for comp in validated["competency_scores"]:
            validated["competency_scores"][comp] = max(
                0.0, min(10.0, float(validated["competency_scores"][comp]))
            )

        # Ensure question_assessments match qa_pairs
        # First, filter out any non-dict items from question_assessments
        raw_assessments = insights.get("question_assessments", [])
        valid_assessments = []
        invalid_count = 0
        for a in raw_assessments:
            if isinstance(a, dict):
                valid_assessments.append(a)
            else:
                invalid_count += 1
                logger.warning(
                    f"⚠️ Skipping invalid assessment item (expected dict, got {type(a).__name__}): {a}"
                )

        if invalid_count > 0:
            logger.warning(
                f"⚠️ Filtered out {invalid_count} invalid assessment item(s) from AI response"
            )

        if len(validated["question_assessments"]) != len(qa_pairs):
            # Rebuild assessments from qa_pairs if they don't match
            validated["question_assessments"] = []
            for qa in qa_pairs:
                # Validate qa is a dict before accessing properties
                if not isinstance(qa, dict):
                    logger.warning(
                        f"⚠️ Skipping invalid qa_pair (expected dict, got {type(qa).__name__}): {qa}"
                    )
                    # Create a placeholder assessment for this invalid qa_pair
                    validated["question_assessments"].append(
                        {
                            "question": str(qa) if qa else "",
                            "answer": "",
                            "score": 0.0,
                            "notes": "",
                        }
                    )
                    continue

                # Try to find matching assessment
                matching = next(
                    (
                        a
                        for a in valid_assessments
                        if isinstance(a, dict)
                        and a.get("question") == qa.get("question")
                    ),
                    None,
                )
                if matching:
                    matching["score"] = max(
                        0.0, min(10.0, float(matching.get("score", 0.0)))
                    )
                    validated["question_assessments"].append(matching)
                else:
                    # Only create placeholder if we truly don't have an assessment
                    # Otherwise, try to extract from existing assessments
                    validated["question_assessments"].append(
                        {
                            "question": qa.get("question", ""),
                            "answer": qa.get("answer", ""),
                            "score": 0.0,
                            "notes": "",  # Empty notes instead of "Assessment pending"
                        }
                    )

        # Ensure strengths and weaknesses are lists of strings
        if not isinstance(validated["strengths"], list):
            validated["strengths"] = []
        if not isinstance(validated["weaknesses"], list):
            validated["weaknesses"] = []

        return validated

    def _create_placeholder_insights(
        self,
        state: Dict[str, Any],
        qa_pairs: List[Dict[str, Any]],
        competencies: List[str],
    ) -> Dict[str, Any]:
        """
        Create placeholder insights when AI analysis is not available.
        """
        # Validate and filter qa_pairs
        if not isinstance(qa_pairs, list):
            logger.warning(
                f"⚠️ qa_pairs is not a list in placeholder creation (got {type(qa_pairs).__name__}), using empty list"
            )
            qa_pairs = []

        valid_qa_pairs = [qa for qa in qa_pairs if isinstance(qa, dict)]

        # Check if we have any real Q&A pairs (not just fallback entries)
        has_real_qa_pairs = any(
            qa.get("question", "") != "Full Interview Transcript"
            for qa in valid_qa_pairs
        )

        insights: Dict[str, Any] = {
            "overall_score": 0.0,
            "competency_scores": (
                {comp: 0.0 for comp in competencies} if competencies else {}
            ),
            "strengths": ["Analysis pending - AI analysis unavailable"],
            "weaknesses": ["Analysis pending - AI analysis unavailable"],
            "question_assessments": [],
        }

        # Create basic assessments for each Q&A pair
        for i, qa in enumerate(valid_qa_pairs):
            question = qa.get("question", "")
            answer = qa.get("answer", "")

            # Use more appropriate message for fallback entries
            if question == "Full Interview Transcript":
                notes = "No structured Q&A pairs found in transcript - full transcript used as fallback"
            else:
                notes = "Assessment pending - AI analysis unavailable"

            assessment = {
                "question": question,
                "answer": answer,
                "score": 0.0,
                "notes": notes,
            }
            cast(List[Dict[str, Any]], insights["question_assessments"]).append(
                assessment
            )

        state["insights"] = insights
        state = self.update_status(state, "insights_extracted")

        if not has_real_qa_pairs and valid_qa_pairs:
            logger.info(
                f"✅ Created placeholder insights for {len(valid_qa_pairs)} fallback entry/entries (no structured Q&A pairs found)"
            )
        else:
            logger.info(
                f"✅ Created placeholder insights for {len(valid_qa_pairs)} questions"
            )

        return state
