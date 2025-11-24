# Setting Up the Daily.co Webhook Router

This guide will walk you through setting up the Cloudflare Worker to route Daily.co webhooks.

## Prerequisites

1. **Cloudflare account** - Sign up at https://cloudflare.com
2. **Cloudflare CLI (Wrangler)** - Already installed (you mentioned you have it)
3. **Node.js** - Version 18 or higher

## Step-by-Step Setup

### 1. Install Dependencies

```bash
cd workers
npm install
```

This installs:
- `wrangler` - Cloudflare CLI tool
- `typescript` - For type checking
- `@cloudflare/workers-types` - TypeScript types for Cloudflare Workers

### 2. Configure Environment Variables

**Simple setup:** You just need two URLs - one for production, one for dev.

```bash
# Set production URL (for normal rooms)
wrangler secret put FLOW_WEBHOOK_BASE_URL
# When prompted, enter: https://your-flow-app.com

# Set dev URL (for rooms starting with "dev")
wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL
# When prompted, enter: http://localhost:8001 (or your dev server URL)

# Set Daily.co API key
wrangler secret put DAILY_API_KEY
# When prompted, enter your Daily.co API key from https://dashboard.daily.co/developers
```

**For Local Development:**

Create `workers/.dev.vars`:
```
FLOW_WEBHOOK_BASE_URL=https://your-production-flow-app.com
FLOW_WEBHOOK_DEV_BASE_URL=http://localhost:8001
DAILY_API_KEY=your-daily-api-key-here
```

**How it works:**
- When you run `wrangler dev`, Wrangler automatically creates a secure tunnel
- Daily.co sends webhooks to your deployed worker
- Worker checks room name: if it starts with "dev", routes to `FLOW_WEBHOOK_DEV_BASE_URL`
- Otherwise, routes to `FLOW_WEBHOOK_BASE_URL`
- No ngrok needed - Wrangler handles the tunnel automatically!

### 3. Test Locally

```bash
npm run dev
```

This starts a local development server (usually at `http://localhost:8787`).

You can test it with:

```bash
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -d '{
    "event": "room.started",
    "id": "test-123",
    "room_name": "test-room",
    "timestamp": 1234567890
  }'
```

### 4. Deploy to Cloudflare

```bash
npm run deploy
```

After deployment, you'll get a URL like:
```
https://pailkit-webhook-router.your-subdomain.workers.dev
```

**Important:** Save this URL - you'll need it for Daily.co!

### 5. Configure Daily.co Webhook

1. Go to your Daily.co dashboard: https://dashboard.daily.co
2. Navigate to **Settings** → **Webhooks**
3. Click **Add Webhook** or **Edit Webhook**
4. Set the webhook URL to your Cloudflare Worker URL:
   ```
   https://pailkit-webhook-router.your-subdomain.workers.dev
   ```
5. Select the events you want to receive (or select all)
6. Save the webhook

### 6. Verify It's Working

You can monitor webhook activity in real-time:

```bash
npm run tail
```

This shows all webhook requests and routing decisions.

## How It Works

1. **Daily.co sends webhook** → Your Cloudflare Worker receives it
2. **Worker checks event type** → Looks at `payload.type` (e.g., `"recording.ready-to-download"`)
3. **Worker checks room name**:
   - For recordings: Checks if `room_name` starts with "dev"
   - For transcripts: Looks up room name via Daily.co API, then checks if it starts with "dev"
4. **Worker routes based on room name**:
   - Room starts with "dev" → Routes to `FLOW_WEBHOOK_DEV_BASE_URL`
   - Otherwise → Routes to `FLOW_WEBHOOK_BASE_URL`
5. **Worker forwards to endpoint** → Forwards to `/webhooks/recording-ready-to-download` or `/webhooks/transcript-ready-to-download`
6. **Flow app processes** → Your handler function processes the webhook

**Local Development Magic:**
- Run `wrangler dev` → Wrangler creates a tunnel automatically
- Set `FLOW_WEBHOOK_DEV_BASE_URL=http://localhost:8001`
- Daily.co webhooks hit your deployed worker
- Worker sees "dev" room → forwards to your local server via Wrangler tunnel
- No ngrok needed!

## Troubleshooting

### Webhooks not arriving?

1. Check that your flow app is running and accessible
2. Verify `FLOW_WEBHOOK_BASE_URL` is set correctly
3. Check Cloudflare Worker logs: `npm run tail`
4. Verify Daily.co webhook is configured correctly

### Getting 500 errors?

1. Check that your flow app endpoints exist (e.g., `/webhooks/room-started`)
2. Check flow app logs for errors
3. Verify the webhook payload format matches what Daily.co sends

### Testing locally with Daily.co?

Use a tool like `ngrok` or `cloudflared` to expose your local worker:

```bash
# Using cloudflared (if you have it)
cloudflared tunnel --url http://localhost:8787

# This gives you a public URL you can use in Daily.co
```

## Next Steps

- Customize webhook handlers in `flow/webhooks/handlers.py`
- Add more event types as needed
- Set up monitoring/alerting for webhook failures
