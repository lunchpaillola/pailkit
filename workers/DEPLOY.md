# Deploying the Webhook Router Worker

This guide explains how to deploy your Cloudflare Worker to production.

## Prerequisites

1. **Cloudflare account** - Sign up at https://cloudflare.com (free tier works!)
2. **Wrangler CLI** - Already installed (you mentioned you have it)

## Step 1: Sign In to Wrangler

First, you need to authenticate with Cloudflare:

```bash
cd workers
wrangler login
```

**What this does:**
- Opens your browser to Cloudflare's login page
- You sign in with your Cloudflare account
- Wrangler gets permission to deploy workers on your behalf
- This is a one-time setup (unless you log out)

**If you don't have a Cloudflare account:**
1. Go to https://cloudflare.com
2. Sign up for a free account
3. Then run `wrangler login`

## Step 2: Set Production Secrets

After signing in, set your production secrets. These are stored securely in Cloudflare and used when your worker runs in production:

```bash
# Set production webhook URL (where production rooms' webhooks go)
wrangler secret put FLOW_WEBHOOK_BASE_URL
# When prompted, enter your production flow app URL, e.g.:
# https://your-flow-app.com

# Set dev webhook URL (where dev rooms' webhooks go)
# This can be a staging URL or a localhost tunnel URL
wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL
# When prompted, enter your dev/staging URL, e.g.:
# https://dev.your-flow-app.com
# OR if using a tunnel: https://your-tunnel-url.ngrok.io

# Set Daily.co API key
wrangler secret put DAILY_API_KEY
# When prompted, enter your Daily.co API key from:
# https://dashboard.daily.co/developers
```

**Important Notes:**
- These secrets are stored securely in Cloudflare
- They're only used in production (when deployed)
- For local development, use `.dev.vars` instead (which we already set up)
- You can update secrets anytime with the same command

## Step 3: Deploy the Worker

Deploy your worker to Cloudflare:

```bash
npm run deploy
```

Or directly with Wrangler:

```bash
wrangler deploy
```

**What happens:**
- Wrangler builds your TypeScript code
- Uploads it to Cloudflare
- Deploys it to the edge network
- Gives you a URL like: `https://pailkit-webhook-router.your-subdomain.workers.dev`

**Save this URL!** You'll need it for Daily.co.

## Step 4: Configure Daily.co Webhook

1. Go to your Daily.co dashboard: https://dashboard.daily.co
2. Navigate to **Settings** → **Webhooks**
3. Click **Add Webhook** or **Edit Webhook**
4. Set the webhook URL to your Cloudflare Worker URL:
   ```
   https://pailkit-webhook-router.your-subdomain.workers.dev
   ```
5. Select the events you want:
   - `recording.ready-to-download`
   - `transcript.ready-to-download`
6. Save the webhook

## Step 5: Verify It's Working

Monitor your worker logs in real-time:

```bash
npm run tail
```

Or:

```bash
wrangler tail
```

**What you'll see:**
- All webhook requests coming in
- Which URL they're being forwarded to (dev vs production)
- Any errors that occur

## Updating Secrets Later

If you need to update a secret:

```bash
wrangler secret put SECRET_NAME
```

To delete a secret:

```bash
wrangler secret delete SECRET_NAME
```

To list all secrets (names only, not values):

```bash
wrangler secret list
```

## Deploying to Staging

You can also deploy to a staging environment. Check `wrangler.toml` - there's already a staging environment configured:

```bash
wrangler deploy --env staging
```

Then set staging-specific secrets:

```bash
wrangler secret put FLOW_WEBHOOK_BASE_URL --env staging
wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL --env staging
wrangler secret put DAILY_API_KEY --env staging
```

## Troubleshooting

### "Authentication required" error?

Run `wrangler login` again.

### "Account ID not found" error?

You might need to set your account ID in `wrangler.toml`. Wrangler will usually prompt you, or you can find it in your Cloudflare dashboard.

### Secrets not working?

Make sure you set them for the correct environment:
- Production: `wrangler secret put SECRET_NAME`
- Staging: `wrangler secret put SECRET_NAME --env staging`

### Worker URL not working?

1. Check that deployment succeeded: `wrangler deploy`
2. Check worker logs: `wrangler tail`
3. Verify the URL in your Cloudflare dashboard

## Summary

**Quick deployment checklist:**
1. ✅ `wrangler login` (one-time setup)
2. ✅ `wrangler secret put FLOW_WEBHOOK_BASE_URL`
3. ✅ `wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL`
4. ✅ `wrangler secret put DAILY_API_KEY`
5. ✅ `npm run deploy` or `wrangler deploy`
6. ✅ Copy the worker URL
7. ✅ Configure Daily.co webhook with the worker URL
8. ✅ Test with `wrangler tail`

That's it! Your worker is now live and routing webhooks. 🎉
