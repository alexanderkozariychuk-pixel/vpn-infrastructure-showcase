#!/bin/bash
# Deploys pwa/ to the app server, wherever `sov-app` currently points.
#
# The app server is a host of its own and never a VPN node: Docker rewrites
# FORWARD, which is what broke traffic the one time the two were co-located.
# The portal moved Beget → Aeza (2026-07-19) → Beget again (2026-09-06), so
# the alias is the source of truth and naming a provider here only goes stale.
#
# This syncs pwa/ and nothing else. The node-side wrappers under
# infrastructure/wrappers/ are installed on the ENTRY node by hand — different
# machine, different trust boundary; see that directory's README.
#
# rsync overwrites the server copy with the local one. Edits made directly on
# the server are lost, which has happened before — dry-run first when the last
# deploy was a while ago:
#
#   rsync -avn --delete ~/Projects/vpn-infrastructure-showcase/pwa/ sov-app:/opt/pwa/vpn-infrastructure-showcase/pwa/
set -e

rsync -av \
  --exclude='venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  --exclude='.ruff_cache' \
  --exclude='.env' \
  ~/Projects/vpn-infrastructure-showcase/pwa/ \
  -e "ssh" \
  sov-app:/opt/pwa/vpn-infrastructure-showcase/pwa/

ssh sov-app \
  "cd /opt/pwa/vpn-infrastructure-showcase/pwa && sudo docker compose build pwa && sudo docker compose up -d --force-recreate pwa"
