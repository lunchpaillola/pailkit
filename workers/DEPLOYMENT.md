# Deployment Guide

**Simple Explanation:**
This guide explains how to deploy the webhook router worker and configure Daily.co webhooks.

## Quick Start

### 1. Deploy the Worker

You can run the deploy script from anywhere:

```bash
# From project root:
./workers/deploy.sh

# Or from workers directory:
cd workers
./deploy.sh
```

**What this does:**
- Checks that you're logged into Cloudflare (runs `wrangler login` if needed)
- Verifies all required secrets are set
- Deploys the worker to Cloudflare
- Shows you the worker URL

**Before running, make sure you have:**
- A Cloudflare account (free tier works!)
- Wrangler CLI installed (`npm install -g wrangler`)
- All secrets configured (see below)

### 2. Configure Daily.co Webhooks

After deployment, set up the webhooks:

```bash
# From project root
DAILY_API_KEY=your-key WEBHOOK_URL=https://your-worker.workers.dev python scripts/setup_daily_webhooks.py
```

**What this does:**
- Creates a webhook in Daily.co pointing to your worker
- Subscribes to `transcript.ready-to-download` and `recording.ready-to-download` events
- Updates existing webhooks if they point to the same URL

## Setting Up Secrets

Before deploying, you need to set these secrets in Cloudflare:

```bash
# From the workers directory:
cd workers

# Production webhook URL (where production rooms' webhooks go)
wrangler secret put FLOW_WEBHOOK_BASE_URL
# Enter: https://your-production-flow-app.com

# Dev webhook URL (where dev rooms' webhooks go)
wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL
# Enter: https://dev.your-flow-app.com or http://localhost:8001

# Daily.co API key
wrangler secret put DAILY_API_KEY
# Enter: Your Daily.co API key from https://dashboard.daily.co/developers
```

**Simple Explanation:**
Secrets are stored securely in Cloudflare and used when your worker runs. They're separate from your local `.env` file.

## Manual Deployment

If you prefer to deploy manually:

```bash
cd workers
wrangler deploy
```

## Manual Webhook Setup

If you prefer to set up webhooks manually via Daily.co dashboard:

1. Go to https://dashboard.daily.co/settings/webhooks
2. Click "Add Webhook" or "Edit Webhook"
3. Set the webhook URL to your Cloudflare Worker URL
4. Select these events:
   - `transcript.ready-to-download`
   - `recording.ready-to-download`
5. Save

## Testing

### Test the Worker

Monitor logs in real-time:

```bash
cd workers
wrangler tail
```

This shows all webhook requests and routing decisions.

### Test Webhook Creation

When you create a webhook via the script, Daily.co will send a test request. The worker should:
1. Receive the test request
2. Return 200 OK immediately
3. Log "Received Daily.co test webhook request"

If the test fails, check:
- Worker is deployed: `wrangler deploy`
- Worker logs: `wrangler tail`
- Webhook URL is correct

## Troubleshooting

### "Authentication required" error

```bash
wrangler login
```

### "Secret not found" error

Make sure you set all required secrets:

```bash
wrangler secret list
```

If any are missing, set them:

```bash
wrangler secret put SECRET_NAME
```

### Webhook creation fails with 400 error

This usually means Daily.co's test request failed. Check:

1. **Worker is deployed:**
   ```bash
   cd workers
   wrangler deploy
   ```

2. **Worker is responding:**
   ```bash
   curl -X POST https://your-worker.workers.dev \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```
   Should return: `{"status":"ok","message":"Webhook endpoint is working"}`

3. **Check worker logs:**
   ```bash
   wrangler tail
   ```

### Worker URL not working

1. Verify deployment: `wrangler deploy`
2. Check Cloudflare dashboard: https://dash.cloudflare.com
3. Verify the URL in the deployment output

## Environment-Specific Deployment

### Staging

Deploy to staging environment:

```bash
cd workers
wrangler deploy --env staging
```

Set staging secrets:

```bash
wrangler secret put FLOW_WEBHOOK_BASE_URL --env staging
wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL --env staging
wrangler secret put DAILY_API_KEY --env staging
```

### Production

Deploy to production (default):

```bash
cd workers
wrangler deploy
# or
wrangler deploy --env production
```

## How It Works

**Simple Explanation:**

1. **Daily.co sends webhook** → Your Cloudflare Worker receives it
2. **Worker checks event type** → Determines which endpoint to forward to
3. **Worker checks room name** → Routes to dev or production URL
4. **Worker forwards webhook** → Sends to your flow application

**Routing Logic:**
- Rooms starting with "dev" → `FLOW_WEBHOOK_DEV_BASE_URL`
- All other rooms → `FLOW_WEBHOOK_BASE_URL`

**Event Types:**
- `recording.ready-to-download` → `/webhooks/recording-ready-to-download`
- `transcript.ready-to-download` → `/webhooks/transcript-ready-to-download`

## Next Steps

After deployment:

1. ✅ Worker is deployed and running
2. ✅ Webhooks are configured in Daily.co
3. ✅ Test with a real recording/transcript
4. ✅ Monitor logs: `wrangler tail`

Your webhook router is now live! 🎉
