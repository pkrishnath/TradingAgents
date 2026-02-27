#!/bin/bash
# Restart script for TradingView Webhook + Cloudflare Tunnel
#
# Usage:
#   ./scripts/restart_webhook.sh          # Docker mode (default)
#   ./scripts/restart_webhook.sh --local   # Local mode (no Docker)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.webhook.yml"
TUNNEL_LOG="$PROJECT_DIR/tunnel.log"

echo "==============================================="
echo "   TradingAgents - Webhook Restart"
echo "==============================================="
echo ""

# ── Local mode (no Docker) ────────────────────────────────────────────────────
if [ "$1" = "--local" ]; then
    echo "[1/3] Starting webhook server locally..."

    # Kill existing webhook process
    pkill -f "tradingview_webhook" 2>/dev/null || true
    sleep 1

    cd "$PROJECT_DIR"
    nohup python -m tradingagents.dataflows.tradingview_webhook > "$PROJECT_DIR/webhook.log" 2>&1 &
    WEBHOOK_PID=$!
    echo "      Webhook PID: $WEBHOOK_PID (port 8089)"
    sleep 2

    # Verify it started
    if ! kill -0 $WEBHOOK_PID 2>/dev/null; then
        echo "      Failed to start webhook. Check webhook.log"
        exit 1
    fi

    echo ""
    echo "[2/3] Starting Cloudflare Tunnel..."

    if ! command -v cloudflared &> /dev/null; then
        echo "      cloudflared not installed!"
        echo "      Run: brew install cloudflare/cloudflare/cloudflared"
        exit 1
    fi

    pkill cloudflared 2>/dev/null || true
    sleep 2

    nohup cloudflared tunnel --url http://localhost:8089 > "$TUNNEL_LOG" 2>&1 &
    echo "      Waiting for tunnel..."
    sleep 3

    # Extract tunnel URL
    echo ""
    echo "[3/3] Retrieving Webhook URL..."
    TUNNEL_URL=""
    for i in $(seq 1 15); do
        TUNNEL_URL=$(grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | tail -1)
        if [ -n "$TUNNEL_URL" ]; then break; fi
        sleep 2
        echo -n "."
    done
    echo ""

    if [ -z "$TUNNEL_URL" ]; then
        echo "      Could not find tunnel URL. Check: cat $TUNNEL_LOG"
        echo "      Webhook is still running at http://localhost:8089"
    else
        echo ""
        echo "==============================================="
        echo "   WEBHOOK IS LIVE!"
        echo "   ─────────────────────────────────────────"
        echo "   Local:   http://localhost:8089/webhook"
        echo "   Public:  $TUNNEL_URL/webhook"
        echo "   Status:  $TUNNEL_URL/status"
        echo "   Health:  $TUNNEL_URL/health"
        echo "==============================================="
        echo ""
        echo "   TradingView Alert Webhook URL:"
        echo "   $TUNNEL_URL/webhook"
        echo ""
        echo "==============================================="
    fi
    exit 0
fi

# ── Docker mode (default) ─────────────────────────────────────────────────────

echo "[1/2] Building and starting containers..."

cd "$PROJECT_DIR"
docker compose -f "$COMPOSE_FILE" down 2>/dev/null || true
docker compose -f "$COMPOSE_FILE" up -d --build

echo "      Waiting for services..."
sleep 5

# Verify webhook is healthy
echo ""
echo "[2/2] Checking health..."

MAX_RETRIES=10
for i in $(seq 1 $MAX_RETRIES); do
    if curl -s http://localhost:8089/health > /dev/null 2>&1; then
        echo "      Webhook: healthy"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "      Webhook not responding. Check: docker compose -f $COMPOSE_FILE logs webhook"
    fi
    sleep 2
done

# Extract cloudflared tunnel URL from container logs
echo ""
echo "      Retrieving tunnel URL..."
TUNNEL_URL=""
for i in $(seq 1 15); do
    TUNNEL_URL=$(docker compose -f "$COMPOSE_FILE" logs cloudflared 2>/dev/null | grep -o 'https://[-a-zA-Z0-9]*\.trycloudflare\.com' | tail -1)
    if [ -n "$TUNNEL_URL" ]; then break; fi
    sleep 2
    echo -n "."
done
echo ""

if [ -z "$TUNNEL_URL" ]; then
    echo "      Could not find tunnel URL."
    echo "      Check: docker compose -f $COMPOSE_FILE logs cloudflared"
    echo "      Webhook is running at http://localhost:8089"
else
    echo ""
    echo "==============================================="
    echo "   WEBHOOK IS LIVE!"
    echo "   ─────────────────────────────────────────"
    echo "   Local:   http://localhost:8089/webhook"
    echo "   Public:  $TUNNEL_URL/webhook"
    echo "   Status:  $TUNNEL_URL/status"
    echo "   Health:  $TUNNEL_URL/health"
    echo "==============================================="
    echo ""
    echo "   TradingView Alert Webhook URL:"
    echo "   $TUNNEL_URL/webhook"
    echo ""
    echo "==============================================="
fi
