#!/bin/bash
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

set -e  # Exit on any error

# Simple Explanation:
# This script deploys the Cloudflare Worker that routes Daily.co webhooks.
# It checks that you're logged in, verifies secrets are set, and deploys the worker.

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to the script's directory (workers folder)
cd "$SCRIPT_DIR"

echo "🚀 Deploying PailKit Webhook Router Worker..."
echo ""

# Check if we're in the workers directory (should have wrangler.toml)
if [ ! -f "wrangler.toml" ]; then
    echo "❌ Error: wrangler.toml not found"
    echo "   This script should be in the workers/ directory"
    exit 1
fi

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo "❌ Error: wrangler CLI is not installed"
    echo "   Install it with: npm install -g wrangler"
    exit 1
fi

# Check if user is logged in
echo "🔐 Checking Wrangler authentication..."
if ! wrangler whoami &> /dev/null; then
    echo "⚠️  Not logged in to Wrangler"
    echo ""
    echo "   You need to sign in to deploy workers."
    echo "   This is a one-time setup (unless you log out)."
    echo ""
    echo "   Running: wrangler login"
    echo "   (This will open your browser to authenticate with Cloudflare)"
    echo ""
    read -p "   Press Enter to continue with login, or Ctrl+C to cancel..."
    wrangler login
    echo ""
    echo "✅ Login successful!"
    echo ""
fi

# Check if secrets are set
echo "🔍 Checking secrets..."
echo ""

MISSING_WEBHOOK_URLS=0
MISSING_API_KEY=0

# Check FLOW_WEBHOOK_BASE_URL
if ! wrangler secret list 2>/dev/null | grep -q "FLOW_WEBHOOK_BASE_URL"; then
    echo "⚠️  FLOW_WEBHOOK_BASE_URL is not set"
    echo "   (You can set this after deploying your flow app)"
    MISSING_WEBHOOK_URLS=1
fi

# Check FLOW_WEBHOOK_DEV_BASE_URL
if ! wrangler secret list 2>/dev/null | grep -q "FLOW_WEBHOOK_DEV_BASE_URL"; then
    echo "⚠️  FLOW_WEBHOOK_DEV_BASE_URL is not set"
    echo "   (You can set this after deploying your flow app)"
    MISSING_WEBHOOK_URLS=1
fi

# Check DAILY_API_KEY (optional for deployment, but needed for webhook setup)
if ! wrangler secret list 2>/dev/null | grep -q "DAILY_API_KEY"; then
    echo "⚠️  DAILY_API_KEY is not set"
    echo "   (Required for webhook setup script, but not for deployment)"
    MISSING_API_KEY=1
fi

if [ $MISSING_WEBHOOK_URLS -eq 1 ]; then
    echo ""
    echo "ℹ️  Note: Webhook URLs are not set yet."
    echo "   This is OK - you can deploy the worker now and set URLs later."
    echo ""
    echo "   After you deploy your flow app, set the URLs with:"
    echo "     wrangler secret put FLOW_WEBHOOK_BASE_URL"
    echo "     wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL"
    echo ""
    read -p "   Continue with deployment? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   Deployment cancelled."
        exit 0
    fi
    echo ""
fi

if [ $MISSING_API_KEY -eq 1 ]; then
    echo ""
    echo "ℹ️  Note: DAILY_API_KEY is not set."
    echo "   You'll need this to run the webhook setup script later."
    echo ""
fi

if [ $MISSING_WEBHOOK_URLS -eq 0 ] && [ $MISSING_API_KEY -eq 0 ]; then
    echo "✅ All secrets are set"
    echo ""
fi

# Deploy the worker
echo "📦 Deploying worker to Cloudflare..."
echo ""

if wrangler deploy; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "📋 Next steps:"
    echo ""

    STEP_NUM=1

    if [ "$MISSING_WEBHOOK_URLS" = "1" ]; then
        echo "   $STEP_NUM. Deploy your flow application"
        STEP_NUM=$((STEP_NUM + 1))
        echo "   $STEP_NUM. Set webhook URLs:"
        echo "      wrangler secret put FLOW_WEBHOOK_BASE_URL"
        echo "      wrangler secret put FLOW_WEBHOOK_DEV_BASE_URL"
        echo ""
        STEP_NUM=$((STEP_NUM + 1))
    fi

    if [ "$MISSING_API_KEY" = "1" ]; then
        echo "   $STEP_NUM. Set Daily.co API key:"
        echo "      wrangler secret put DAILY_API_KEY"
        echo ""
        STEP_NUM=$((STEP_NUM + 1))
    fi

    echo "   $STEP_NUM. Get your worker URL from the output above"
    STEP_NUM=$((STEP_NUM + 1))
    echo "   $STEP_NUM. Run the webhook setup script:"
    echo "      DAILY_API_KEY=your-key WEBHOOK_URL=https://your-worker.workers.dev python scripts/setup_daily_webhooks.py"
    STEP_NUM=$((STEP_NUM + 1))
    echo "   $STEP_NUM. Or manually configure in Daily.co dashboard:"
    echo "      https://dashboard.daily.co/settings/webhooks"
    echo ""
    echo "🔍 To monitor logs:"
    echo "   wrangler tail"
else
    echo ""
    echo "❌ Deployment failed"
    exit 1
fi
