#!/bin/bash
rsync -av \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.env' \
  ~/Projects/vpn-infrastructure-showcase/pwa/ \
  -e "ssh -i ~/.ssh/id_ed25519" \
  vpnadmin@212.67.14.85:/opt/pwa/

ssh -i ~/.ssh/id_ed25519 vpnadmin@212.67.14.85 \
  "cd /opt/pwa && docker compose build pwa && docker compose up -d --force-recreate pwa"
