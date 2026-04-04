#!/bin/bash
# setup-new-vps.sh
# Basic hardening and user setup for a new VPS.

set -e

NEW_USER="vpnadmin"
SSH_PUB_KEY="ssh-ed25519 AAAAC3... your-key"

sudo apt update && sudo apt upgrade -y

sudo adduser --disabled-password --gecos "" "$NEW_USER"
sudo usermod -aG sudo "$NEW_USER"

sudo mkdir -p /home/$NEW_USER/.ssh
echo "$SSH_PUB_KEY" | sudo tee /home/$NEW_USER/.ssh/authorized_keys > /dev/null
sudo chown -R $NEW_USER:$NEW_USER /home/$NEW_USER/.ssh
sudo chmod 700 /home/$NEW_USER/.ssh
sudo chmod 600 /home/$NEW_USER/.ssh/authorized_keys

sudo sed -i 's/^#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

sudo ufw allow 22/tcp
sudo ufw allow 443/udp
sudo ufw allow 443/tcp
sudo ufw enable

echo "Base setup complete. Now you can log in as $NEW_USER and continue with AmneziaWG installation."
