# Daily.co Webhook Router

A Cloudflare Worker that routes Daily.co webhooks to different endpoints in your flow application.

## Why This Exists

Daily.co only allows **one webhook endpoint** to be configured. This worker acts as a router, receiving all webhooks from Daily.co and forwarding them to the appropriate endpoints in your flow application based on the event type.

## How It Works

1. **Daily.co sends webhook** → This worker receives it
2. **Worker checks event type** (e.g., `room.started`, `recording.completed`)
3. **Worker forwards to correct endpoint** (e.g., `/webhooks/room-started`)

## Setup

### 1. Install Dependencies

```bash
cd workers
npm install
```

### 2. Configure Environment Variables

Set the base URL of your flow application:

```bash
# Using wrangler secret (recommended for production)
wrangler secret put FLOW_WEBHOOK_BASE_URL
# Enter: https://your-flow-app.com

# Or set in wrangler.toml for local development
```

### 3. Local Development

```bash
npm run dev
```

This will start a local development server. You can test webhooks locally using tools like `ngrok` or `cloudflared`.

### 4. Deploy to Cloudflare

```bash
npm run deploy
```

After deployment, you'll get a URL like: `https://pailkit-webhook-router.your-subdomain.workers.dev`

### 5. Configure Daily.co Webhook

1. Go to your Daily.co dashboard
2. Navigate to Webhooks settings
3. Set the webhook URL to your Cloudflare Worker URL:
   ```
   https://pailkit-webhook-router.your-subdomain.workers.dev
   ```

## Webhook Routing

The worker automatically routes webhooks based on event type:

| Daily.co Event | Route in Flow App |
|---------------|-------------------|
| `recording.ready-to-download` | `/webhooks/recording-ready-to-download` |
| `transcript.ready-to-download` | `/webhooks/transcript-ready-to-download` |

**Note:** We only handle these two events. Other webhook events will be ignored.

## Environment Variables

- `FLOW_WEBHOOK_BASE_URL` (required): Base URL for **production** rooms
  - Example: `https://your-flow-app.com`
  - Used for all rooms that don't start with "dev"

- `FLOW_WEBHOOK_DEV_BASE_URL` (required): Base URL for **dev** rooms
  - Example: `http://localhost:8001` (when running locally)
  - Example: Wrangler tunnel URL (when using `wrangler dev`)
  - Used for rooms with names starting with "dev"

- `DAILY_API_KEY` (required): Daily.co API key
  - Required for transcript webhooks to look up room names
  - Get from: https://dashboard.daily.co/developers

- `DAILY_WEBHOOK_SECRET` (optional): Secret for verifying webhook signatures
  - Not currently used, but reserved for future signature verification

### Setting Environment Variables

```bash
# Set production URL
wrangler secret put FLOW_WEBHOOK_BASE_URL

# Set dev URL (can be localhost when developing locally)
wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL

# Set Daily.co API key
wrangler secret put DAILY_API_KEY
```

**Local Development:**
When you run `wrangler dev`, Wrangler automatically creates a secure tunnel from Cloudflare's edge to your laptop. You can:
- Use `http://localhost:8001` as `FLOW_WEBHOOK_DEV_BASE_URL` (if your flow app is running locally)
- Or use the Wrangler tunnel URL that's displayed when you run `wrangler dev`

## Routing Logic

**Simple rule:** The worker routes based on room name, not Wrangler environment.

- **If room name starts with "dev"** → Routes to `FLOW_WEBHOOK_DEV_BASE_URL`
- **Otherwise** → Routes to `FLOW_WEBHOOK_BASE_URL`

**For Recordings:**
- Room name is directly available in the webhook payload
- Checked immediately

**For Transcripts:**
- Room name is looked up via Daily.co API
- Uses transcript ID → gets room_id → gets room_name
- Then checks if room_name starts with "dev"

**Example:**
- Room "abc123" → Routes to `FLOW_WEBHOOK_BASE_URL` (production)
- Room "dev-test" → Routes to `FLOW_WEBHOOK_DEV_BASE_URL` (dev/local)

**Local Development:**
When you run `wrangler dev`, Wrangler automatically creates a tunnel. Daily.co sends webhooks to your deployed worker, which checks the room name and forwards dev rooms to your local server via the tunnel. No ngrok needed!

## Testing

You can test the worker locally by sending a test webhook:

```bash
# Test recording ready to download
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{
    "event": "recording.ready-to-download",
    "id": "test-123",
    "room_name": "test-room",
    "recording": {
      "id": "rec-123",
      "download_url": "https://example.com/recording.mp4"
    },
    "timestamp": 1234567890
  }'

# Test transcript ready to download
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{
    "event": "transcript.ready-to-download",
    "id": "test-456",
    "room_name": "test-room",
    "transcript": {
      "id": "trans-123",
      "download_url": "https://example.com/transcript.json"
    },
    "timestamp": 1234567890
  }'
```

## Monitoring

View logs in real-time:

```bash
npm run tail
```

This shows all webhook requests and routing decisions in real-time.
