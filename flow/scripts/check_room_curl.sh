#!/bin/bash
# Quick curl command to check Daily.co room status
#
# Usage:
#   source flow/scripts/check_room_curl.sh
#   check_room <room_name>

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

check_room() {
    local room_name=$1
    if [ -z "$room_name" ]; then
        echo "Usage: check_room <room_name>"
        echo "Example: check_room g6c2GYUhQojQ69UiqG8b"
        return 1
    fi

    echo "📹 Checking Daily.co Room: $room_name"
    echo "=========================================="

    curl -X GET "https://api.daily.co/v1/rooms/$room_name" \
        -H "Authorization: Bearer $DAILY_API_KEY" \
        -H "Content-Type: application/json" \
        | jq '.'
}

# If script is run directly (not sourced), run the function
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    if [ -n "$1" ]; then
        check_room "$1"
    else
        echo "Usage:"
        echo "  source flow/scripts/check_room_curl.sh"
        echo "  check_room <room_name>"
        echo ""
        echo "Or run directly:"
        echo "  bash flow/scripts/check_room_curl.sh <room_name>"
    fi
fi
