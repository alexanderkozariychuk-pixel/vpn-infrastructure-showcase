#!/bin/bash
# healthcheck.sh
# Checks the status of key services and reports.

STATUS=0

echo "=== Health check at $(date) ==="

# AmneziaWG
if sudo awg show awg0 > /dev/null 2>&1; then
    PEERS=$(sudo awg show awg0 | grep -c "peer:")
    echo "AmneziaWG: OK (peers: $PEERS)"
else
    echo "AmneziaWG: FAILED"
    STATUS=1
fi

# Xray (3X-UI)
if sudo systemctl is-active x-ui > /dev/null 2>&1; then
    echo "Xray/3X-UI: OK"
else
    echo "Xray/3X-UI: FAILED"
    STATUS=1
fi

# Docker containers
if command -v docker > /dev/null 2>&1; then
    RUNNING=$(docker ps -q | wc -l)
    echo "Docker containers running: $RUNNING"
else
    echo "Docker not installed"
fi

# Port checks
if ss -ulpn | grep -q ':443'; then
    echo "UDP/443 (AmneziaWG): listening"
else
    echo "UDP/443 (AmneziaWG): NOT listening"
    STATUS=1
fi

if ss -tulpn | grep -q ':443.*xray'; then
    echo "TCP/443 (Xray): listening"
else
    echo "TCP/443 (Xray): NOT listening"
    STATUS=1
fi

exit $STATUS
