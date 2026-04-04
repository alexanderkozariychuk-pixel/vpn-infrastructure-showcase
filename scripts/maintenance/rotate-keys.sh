#!/bin/bash
# rotate-keys.sh <client_name>
# Generates new keys for a client and updates the server config.

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <client_name>"
    exit 1
fi

CLIENT_NAME="$1"
AWG_DIR="/etc/amneziawg"
CONFIG_FILE="$AWG_DIR/awg0.conf"

cd "$AWG_DIR"
sudo umask 077
NEW_PRIVATE=$(sudo wg genkey)
NEW_PUBLIC=$(echo "$NEW_PRIVATE" | sudo wg pubkey)

sudo cp "$CONFIG_FILE" "$CONFIG_FILE.bak.$(date +%Y%m%d%H%M%S)"

# Find the client's current public key based on comment line "# Client: <client_name>"
OLD_PUBLIC=$(sudo awk -v name="$CLIENT_NAME" '/^# Client: /{flag=0} /^# Client: '"$CLIENT_NAME"'/{flag=1} flag && /^PublicKey = /{print $3; exit}' "$CONFIG_FILE")

if [ -z "$OLD_PUBLIC" ]; then
    echo "Client $CLIENT_NAME not found in config. Please add a comment line: # Client: $CLIENT_NAME before the [Peer] section."
    exit 1
fi

# Replace the old public key with the new one
sudo sed -i.bak "/^# Client: $CLIENT_NAME/,/^AllowedIPs/s/^PublicKey = .*/PublicKey = $NEW_PUBLIC/" "$CONFIG_FILE"

sudo systemctl restart awg-quick@awg0

echo "$NEW_PRIVATE" | sudo tee "$AWG_DIR/client_${CLIENT_NAME}_private.key" > /dev/null
echo "New keys generated for $CLIENT_NAME. Private key saved to $AWG_DIR/client_${CLIENT_NAME}_private.key"
echo "Please update the client configuration with the new private key."
