#!/bin/bash
# check_awg.sh
# Sends AmneziaWG health status to Uptime Kuma push monitor.

PUSH_URL="http://localhost:3001/api/push/<TOKEN>?status=up&msg=OK"

if sudo awg show awg0 > /dev/null 2>&1; then
    if sudo awg show awg0 | grep -q "latest handshake"; then
        curl -s -o /dev/null "$PUSH_URL"
        echo "$(date): AWG OK"
    else
        curl -s -o /dev/null "http://localhost:3001/api/push/<TOKEN>?status=down&msg=NO_HANDSHAKE"
        echo "$(date): AWG NO HANDSHAKE"
    fi
else
    curl -s -o /dev/null "http://localhost:3001/api/push/<TOKEN>?status=down&msg=INTERFACE_DOWN"
    echo "$(date): AWG INTERFACE DOWN"
fi
