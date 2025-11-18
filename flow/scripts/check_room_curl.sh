#!/bin/bash
# Quick curl commands to check room and VAPI status
#
# Usage:
#   source flow/scripts/check_room_curl.sh
#   check_room <room_name>
#   check_vapi_call <call_id>

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

check_vapi_call() {
    local call_id=$1
    if [ -z "$call_id" ]; then
        echo "Usage: check_vapi_call <call_id>"
        echo "Example: check_vapi_call 019a9299-96f7-7770-a5c7-c5bcc38a4fea"
        return 1
    fi

    echo "📞 Checking VAPI Call: $call_id"
    echo "=========================================="

    curl -X GET "https://api.vapi.ai/call/$call_id" \
        -H "Authorization: Bearer $VAPI_API_KEY" \
        -H "Content-Type: application/json" \
        | jq '.'
}

# If script is run directly (not sourced), run the function
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    if [ "$1" = "room" ] && [ -n "$2" ]; then
        check_room "$2"
    elif [ "$1" = "vapi" ] && [ -n "$2" ]; then
        check_vapi_call "$2"
    else
        echo "Usage:"
        echo "  source flow/scripts/check_room_curl.sh"
        echo "  check_room <room_name>"
        echo "  check_vapi_call <call_id>"
        echo ""
        echo "Or run directly:"
        echo "  bash flow/scripts/check_room_curl.sh room <room_name>"
        echo "  bash flow/scripts/check_room_curl.sh vapi <call_id>"
    fi
fi
