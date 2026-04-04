#!/bin/bash
# generate-config.sh <client_name>
# Creates a new client configuration for AmneziaWG.

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <client_name>"
    exit 1
fi

CLIENT_NAME="$1"
INSTALL_SCRIPT="/root/amneziawg-install.sh"

if [ ! -f "$INSTALL_SCRIPT" ]; then
    echo "Install script not found. Please download it first:"
    echo "curl -O https://raw.githubusercontent.com/Varckin/amneziawg-install/main/amneziawg-install.sh"
    exit 1
fi

echo "Run the install script and choose to add a new client:"
echo "sudo $INSTALL_SCRIPT"
echo "When prompted, enter client name: $CLIENT_NAME"
echo "After creation, client config will be at /root/awg0-client-$CLIENT_NAME.conf"
