#!/bin/bash
# backup-configs.sh
# Creates a timestamped archive of all important configuration files.

BACKUP_DIR="/root/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/configs_$TIMESTAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

tar -czf "$BACKUP_FILE" \
    /etc/amneziawg \
    /usr/local/etc/xray \
    /etc/3x-ui \
    /opt/monitoring \
    /usr/local/bin/check_awg.sh \
    2>/dev/null || true

echo "Backup created: $BACKUP_FILE"
