/**
 * Cloudflare Worker to route Daily.co webhooks
 *
 * **Simple Explanation:**
 * Daily.co only allows one webhook endpoint, but we need to route different
 * webhook events to different handlers. This worker acts as a router:
 *
 * 1. Receives webhook from Daily.co
 * 2. Looks at the event type (e.g., "room.started", "recording.completed")
 * 3. Forwards the webhook to the appropriate endpoint in your flow application
 *
 * **How it works:**
 * - Daily.co sends webhook → This worker receives it
 * - Worker checks the event type in the payload
 * - Worker forwards to the correct endpoint (e.g., /webhooks/room-started)
 */

export interface Env {
  // Base URL for PRODUCTION rooms (where most webhooks go)
  // Example: https://your-flow-app.com
  FLOW_WEBHOOK_BASE_URL: string;

  // Base URL for DEV rooms (rooms with names starting with "dev")
  // OPTIONAL: If not set, dev rooms will use the production URL
  // When running locally with `wrangler dev`, this can be your local server
  // Wrangler automatically creates a tunnel, so you can use localhost or the tunnel URL
  // Example: http://localhost:8001 or the Wrangler tunnel URL
  // In production, you can omit this and dev rooms will route to production
  FLOW_WEBHOOK_DEV_BASE_URL?: string;

  // Daily.co API key (optional - no longer needed since room_name is in payload)
  // Get this from: https://dashboard.daily.co/developers
  DAILY_API_KEY?: string;

  // Optional: Secret for verifying Daily.co webhook signatures
  // Set this if you want to verify webhook authenticity
  DAILY_WEBHOOK_SECRET?: string;
}

/**
 * Daily.co webhook event types
 * Based on: https://docs.daily.co/reference/rest-api/webhooks
 *
 * We handle these events:
 * - recording.ready-to-download: When a recording is ready to download
 * - transcript.ready-to-download: When a transcript is ready to download
 * - meeting.ended: When a meeting ends (for bot-enabled workflows)
 */
type DailyWebhookEvent =
  | "recording.ready-to-download"
  | "transcript.ready-to-download"
  | "meeting.ended";

interface DailyWebhookPayload {
  version?: string;
  type: DailyWebhookEvent;
  id: string;
  payload: {
    // Common fields
    room_name?: string; // Used by recording and transcript webhooks
    room?: string; // Used by meeting.ended (this is the room name)
    room_id?: string;
    meeting_id?: string; // Used by meeting.ended
    recording_id?: string;
    start_ts?: number; // Used by meeting.ended
    end_ts?: number; // Used by meeting.ended
    [key: string]: unknown;
  };
  event_ts?: number;
  timestamp?: number;
  [key: string]: unknown; // Allow other fields
}

/**
 * Route webhook events to different endpoints
 *
 * **Simple Explanation:**
 * This function decides where to send each webhook based on its event type.
 * For example:
 * - "recording.ready-to-download" → /webhooks/recording-ready-to-download
 * - "transcript.ready-to-download" → /webhooks/transcript-ready-to-download
 */
function getWebhookRoute(event: DailyWebhookEvent): string {
  // Convert event type to route path
  // "recording.ready-to-download" → "recording-ready-to-download"
  const route = event.replace(/\./g, "-");
  return `/webhooks/${route}`;
}

/**
 * Get room name from Daily.co API for transcript webhooks
 *
 * **Simple Explanation:**
 * This function is kept for backwards compatibility, but room_name is now
 * included directly in the transcript webhook payload, so we don't need
 * to make API calls anymore.
 *
 * @deprecated Room name is now available directly in the payload
 */
async function getRoomNameFromTranscript(
  transcriptId: string,
  apiKey: string
): Promise<string | null> {
  // This function is no longer needed since room_name is in the payload
  // Keeping it for backwards compatibility but it shouldn't be called
  console.warn("getRoomNameFromTranscript called but room_name should be in payload");
  return null;
}

/**
 * Determine if webhook should go to dev or production
 *
 * **Simple Explanation:**
 * Checks if the room name starts with "dev" to determine routing.
 * Different webhook types use different field names:
 * - recording.ready-to-download and transcript.ready-to-download use "room_name"
 * - meeting.ended uses "room" (which is the room name)
 */
function isDevEnvironment(payload: DailyWebhookPayload): boolean {
  let roomName: string | undefined;

  // Different webhook types use different field names for the room
  if (payload.type === "meeting.ended") {
    // meeting.ended uses "room" field (which is the room name)
    roomName = payload.payload?.room as string | undefined;
  } else {
    // recording and transcript webhooks use "room_name"
    roomName = payload.payload?.room_name as string | undefined;
  }

  if (roomName) {
    return roomName.toLowerCase().startsWith("dev");
  }

  // If room name is missing, log a warning and default to production
  console.warn(
    `No room name found in ${payload.type} webhook payload. Defaulting to production.`
  );
  return false;
}

/**
 * Forward webhook to the flow application
 *
 * **Simple Explanation:**
 * This function takes the webhook from Daily.co and forwards it to your
 * flow application at the correct endpoint (dev or production).
 */
async function forwardWebhook(
  url: string,
  payload: DailyWebhookPayload,
  originalRequest: Request
): Promise<Response> {
  try {
    console.log(`Attempting to forward webhook to: ${url}`);

    // Forward the webhook with the same headers and body
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Forward important headers from Daily.co
        "User-Agent": originalRequest.headers.get("User-Agent") || "Daily.co",
        "X-Daily-Event": payload.type,
        "X-Daily-Webhook-Id": payload.id,
      },
      body: JSON.stringify(payload),
    });

    console.log(`Response from ${url}: ${response.status} ${response.statusText}`);
    return response;
  } catch (error) {
    console.error(`Error forwarding webhook to ${url}:`, error);
    const errorMessage = error instanceof Error ? error.message : "Unknown error";
    console.error(`Error details: ${errorMessage}`);

    return new Response(
      JSON.stringify({
        error: "Failed to forward webhook",
        message: errorMessage,
        target_url: url,
        event_type: payload.type,
      }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}

/**
 * Main request handler
 *
 * **Simple Explanation:**
 * This is the entry point for all requests to the worker.
 * It:
 * 1. Checks if it's a POST request (webhooks are POST)
 * 2. Parses the webhook payload
 * 3. Determines the route based on event type
 * 4. Forwards to the flow application
 */
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only handle POST requests (webhooks are POST)
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

      try {
        // Parse the webhook payload from Daily.co
        // Handle potential JSON parsing errors (e.g., empty body for test requests)
        let payload: DailyWebhookPayload;
        try {
          payload = await request.json();
        } catch (jsonError) {
          // If JSON parsing fails, it might be a test request with empty/invalid body
          // Daily.co test requests might not have valid JSON
          // Return 200 OK to pass the test (even without secrets configured)
          console.log("Received request with invalid/empty JSON - treating as test request");
          return new Response(
            JSON.stringify({ status: "ok", message: "Webhook endpoint is working" }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        // Handle Daily.co's test webhook request
        // When creating a webhook, Daily.co sends a test request to verify the endpoint
        // We need to return 200 quickly to avoid webhook creation failure
        // IMPORTANT: Return 200 for test requests even if secrets aren't configured yet
        // Daily.co test requests might have various formats, so we check multiple conditions
        const payloadKeys = Object.keys(payload);
        const isTestRequest =
          payload.type === "webhook.test" ||
          payload.type === "test" ||
          (payload as any).test === true ||
          (payload as any).event === "webhook.test" ||
          (payload as any).event === "test" ||
          // If payload is empty or very minimal, treat as test
          (payloadKeys.length === 0) ||
          (!payload.type && !payload.id && payloadKeys.length <= 2);

        if (isTestRequest) {
          console.log("Received Daily.co test webhook request - returning 200 immediately");
          return new Response(
            JSON.stringify({ status: "ok", message: "Webhook endpoint is working" }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        // Now check that we have the required URLs configured (only for real webhooks)
        if (!env.FLOW_WEBHOOK_BASE_URL) {
          console.error("FLOW_WEBHOOK_BASE_URL is not configured");
          return new Response(
            JSON.stringify({ error: "Webhook router not configured: missing FLOW_WEBHOOK_BASE_URL" }),
            {
              status: 500,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        // FLOW_WEBHOOK_DEV_BASE_URL is optional - if not set, dev rooms will use production URL
        // This is useful in production where you don't have a separate dev server
        if (!env.FLOW_WEBHOOK_DEV_BASE_URL) {
          console.warn("FLOW_WEBHOOK_DEV_BASE_URL is not configured - dev rooms will use production URL");
        }

        // DAILY_API_KEY is no longer required since room_name is in the payload
        // Keeping this check for backwards compatibility but it's optional now
        if (!env.DAILY_API_KEY) {
          console.warn("DAILY_API_KEY is not configured (optional - room_name is now in payload)");
        }

        // Validate that we have an event type
        // Daily.co uses "type" field in newer webhook format
        const eventType = payload.type || (payload as any).event;
        if (!eventType) {
          // If no event type, this might be a test request or unknown format
          // Return 200 OK to be safe (Daily.co test requests might not have event types)
          console.log("Received request without event type - treating as test/unknown request");
          return new Response(
            JSON.stringify({ status: "ok", message: "Webhook endpoint is working" }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        // Normalize the event type
        payload.type = eventType as DailyWebhookEvent;

        // Only handle specific events we care about
        const supportedEvents = [
          "recording.ready-to-download",
          "transcript.ready-to-download",
          "meeting.ended",
        ];

        if (!supportedEvents.includes(payload.type)) {
          // Ignore unsupported events
          console.log(
            `Ignoring unsupported webhook event: ${payload.type} (${payload.id})`
          );
          return new Response(
            JSON.stringify({
              status: "ignored",
              event: payload.type,
              message: "Event type not handled by this router",
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        // Determine if this is a dev or production webhook based on room name
        // room_name is now included directly in the payload, no API call needed
        const isDev = isDevEnvironment(payload);

        // Simple routing: dev rooms → dev URL (or production if dev URL not set), everything else → production URL
        // If FLOW_WEBHOOK_DEV_BASE_URL is not set, dev rooms will use production URL
        // This allows production to work without a separate dev server
        const baseUrl = isDev && env.FLOW_WEBHOOK_DEV_BASE_URL
          ? env.FLOW_WEBHOOK_DEV_BASE_URL.replace(/\/$/, "")
          : env.FLOW_WEBHOOK_BASE_URL.replace(/\/$/, "");

        // Check if baseUrl is localhost (which won't work from Cloudflare Workers)
        if (baseUrl.includes("localhost") || baseUrl.includes("127.0.0.1")) {
          console.error(
            `ERROR: ${isDev ? "FLOW_WEBHOOK_DEV_BASE_URL" : "FLOW_WEBHOOK_BASE_URL"} is set to localhost: ${baseUrl}`
          );
          console.error(
            "Cloudflare Workers cannot reach localhost. Use a public URL or tunnel (e.g., ngrok, wrangler dev tunnel)."
          );
          return new Response(
            JSON.stringify({
              error: "Invalid webhook URL configuration",
              message: `Cannot use localhost URL: ${baseUrl}. Cloudflare Workers need a publicly accessible URL.`,
              hint: "Use a public URL, ngrok tunnel, or wrangler dev tunnel URL instead.",
            }),
            {
              status: 500,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        // Get the route for this event type
        const route = getWebhookRoute(payload.type);

        // Build the full URL to forward to
        const targetUrl = `${baseUrl}${route}`;

        const envLabel = isDev ? "DEV" : "PROD";
        console.log(
          `Routing ${payload.type} webhook (${payload.id}) to ${envLabel}: ${targetUrl}`
        );

        // Forward the webhook to the flow application
        const response = await forwardWebhook(targetUrl, payload, request);

      // Log the result
      if (response.ok) {
        console.log(
          `Successfully forwarded ${payload.type} webhook to ${targetUrl}`
        );
      } else {
        // Get response body for better error debugging
        let responseText = "";
        try {
          responseText = await response.clone().text();
        } catch (e) {
          responseText = "Could not read response body";
        }

        console.error(
          `Failed to forward ${payload.type} webhook: ${response.status} ${response.statusText}`
        );
        console.error(`Target URL: ${targetUrl}`);
        console.error(`Response body: ${responseText}`);
      }

      return response;
    } catch (error) {
      console.error("Error processing webhook:", error);
      return new Response(
        JSON.stringify({
          error: "Error processing webhook",
          message: error instanceof Error ? error.message : "Unknown error",
        }),
        {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }
      );
    }
  },
};
