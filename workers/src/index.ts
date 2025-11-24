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
  // When running locally with `wrangler dev`, this can be your local server
  // Wrangler automatically creates a tunnel, so you can use localhost or the tunnel URL
  // Example: http://localhost:8001 or the Wrangler tunnel URL
  FLOW_WEBHOOK_DEV_BASE_URL: string;

  // Daily.co API key (required for transcript webhooks to look up room names)
  // Get this from: https://dashboard.daily.co/developers
  DAILY_API_KEY: string;

  // Optional: Secret for verifying Daily.co webhook signatures
  // Set this if you want to verify webhook authenticity
  DAILY_WEBHOOK_SECRET?: string;
}

/**
 * Daily.co webhook event types
 * Based on: https://docs.daily.co/reference/rest-api/webhooks
 *
 * We only handle these two events:
 * - recording.ready-to-download: When a recording is ready to download
 * - transcript.ready-to-download: When a transcript is ready to download
 */
type DailyWebhookEvent =
  | "recording.ready-to-download"
  | "transcript.ready-to-download";

interface DailyWebhookPayload {
  version?: string;
  type: DailyWebhookEvent;
  id: string;
  payload: {
    room_name?: string;
    room_id?: string;
    recording_id?: string;
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
 * For transcript webhooks, we need to look up the room name by calling
 * Daily.co's API. We use the transcript ID to get transcript info, which
 * includes the room_id, then we get the room info to get the room_name.
 */
async function getRoomNameFromTranscript(
  transcriptId: string,
  apiKey: string
): Promise<string | null> {
  try {
    // Step 1: Get transcript information (includes room_id)
    const transcriptResponse = await fetch(
      `https://api.daily.co/v1/transcript/${transcriptId}`,
      {
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!transcriptResponse.ok) {
      console.error(
        `Failed to get transcript info: ${transcriptResponse.status} ${transcriptResponse.statusText}`
      );
      return null;
    }

    const transcriptData = await transcriptResponse.json();
    const roomId = transcriptData.room_id;

    if (!roomId) {
      console.error("No room_id found in transcript data");
      return null;
    }

    // Step 2: Get room information (includes room_name)
    const roomResponse = await fetch(`https://api.daily.co/v1/rooms/${roomId}`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
    });

    if (!roomResponse.ok) {
      console.error(
        `Failed to get room info: ${roomResponse.status} ${roomResponse.statusText}`
      );
      return null;
    }

    const roomData = await roomResponse.json();
    return roomData.name || null;
  } catch (error) {
    console.error(`Error getting room name from transcript: ${error}`);
    return null;
  }
}

/**
 * Determine if webhook should go to dev or production
 *
 * **Simple Explanation:**
 * Checks if the room name starts with "dev" to determine routing.
 * For recordings, we can check directly. For transcripts, we need to
 * look up the room name via API.
 */
async function isDevEnvironment(
  payload: DailyWebhookPayload,
  apiKey: string
): Promise<boolean> {
  // For recording webhooks, room_name is directly available
  if (payload.type === "recording.ready-to-download") {
    const roomName = payload.payload?.room_name;
    if (roomName) {
      return roomName.toLowerCase().startsWith("dev");
    }
  }

  // For transcript webhooks, we need to look up the room name
  if (payload.type === "transcript.ready-to-download") {
    // Get transcript ID from payload
    const transcriptId = payload.payload?.id;
    if (!transcriptId) {
      console.error("No transcript ID found in payload");
      return false; // Default to production if we can't determine
    }

    const roomName = await getRoomNameFromTranscript(transcriptId, apiKey);
    if (roomName) {
      return roomName.toLowerCase().startsWith("dev");
    }
  }

  // Default to production if we can't determine
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

    return response;
  } catch (error) {
    console.error(`Error forwarding webhook to ${url}:`, error);
    return new Response(
      JSON.stringify({
        error: "Failed to forward webhook",
        message: error instanceof Error ? error.message : "Unknown error",
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

      // Check that we have the required URLs configured
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

      if (!env.FLOW_WEBHOOK_DEV_BASE_URL) {
        console.error("FLOW_WEBHOOK_DEV_BASE_URL is not configured");
        return new Response(
          JSON.stringify({ error: "Webhook router not configured: missing FLOW_WEBHOOK_DEV_BASE_URL" }),
          {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }
        );
      }

      if (!env.DAILY_API_KEY) {
        console.error("DAILY_API_KEY is not configured");
        return new Response(
          JSON.stringify({ error: "Webhook router not configured: missing DAILY_API_KEY" }),
          {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }
        );
      }

      try {
        // Parse the webhook payload from Daily.co
        const payload: DailyWebhookPayload = await request.json();

        // Validate that we have an event type
        // Daily.co uses "type" field in newer webhook format
        const eventType = payload.type || (payload as any).event;
        if (!eventType) {
          return new Response(
            JSON.stringify({ error: "Missing event type in webhook payload" }),
            {
              status: 400,
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
        const isDev = await isDevEnvironment(payload, env.DAILY_API_KEY);

        // Simple routing: dev rooms → dev URL, everything else → production URL
        const baseUrl = isDev
          ? env.FLOW_WEBHOOK_DEV_BASE_URL.replace(/\/$/, "")
          : env.FLOW_WEBHOOK_BASE_URL.replace(/\/$/, "");

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
        console.error(
          `Failed to forward ${payload.type} webhook: ${response.status} ${response.statusText}`
        );
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
