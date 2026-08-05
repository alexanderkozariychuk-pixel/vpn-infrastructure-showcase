#!/bin/bash
# Deploys pwa/ to the app server (Aeza-RU) — the PWA has lived here since
# 2026-07-19, not on Beget. Do not point this back at Beget/entry — that
# node only ever ran the code before the app-server split.
set -e

rsync -av \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.env' \
  ~/Projects/vpn-infrastructure-showcase/pwa/ \
  -e "ssh" \
  ru-aeza:/opt/pwa/vpn-infrastructure-showcase/pwa/

ssh ru-aeza \
  "cd /opt/pwa/vpn-infrastructure-showcase/pwa && sudo docker compose build pwa && sudo docker compose up -d --force-recreate pwa"
