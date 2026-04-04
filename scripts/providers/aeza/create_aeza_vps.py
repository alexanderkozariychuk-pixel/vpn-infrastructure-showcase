#!/usr/bin/env python3
"""
Script to create a VPS on Aeza using their official API.
Requires library installation: pip install aeza
"""
import os
from aeza import AezaClient

# --- CONFIGURATION (replace with your data) ---
# API key: https://my.aeza.net/account/api
API_KEY = "YOUR_API_KEY_FROM_PERSONAL_ACCOUNT"
# Product ID (e.g., for France with 2GB RAM)
# Full list can be obtained via client.products.list()
PRODUCT_ID = 220  # Example ID, verify in documentation or via code
# OS ID (e.g., Ubuntu 22.04)
OS_ID = 135       # Example ID, verify in documentation or via code
# Desired hostname for your server
HOSTNAME = "my-france-exit-node"
# ----------------------------------------------

def main():
    print("Initializing Aeza client...")
    client = AezaClient(API_KEY)

    try:
        print(f"Creating VPS with product ID {PRODUCT_ID} and OS ID {OS_ID}...")
        new_vps = client.vps.create(
            product_id=PRODUCT_ID,
            os_id=OS_ID,
            hostname=HOSTNAME
        )

        print("\n✅ VPS successfully created!")
        print(f"Server ID: {new_vps['id']}")
        print(f"IP address: {new_vps['ip']}")
        print(f"Status: {new_vps['status']}")

        # Here you can add code to save IP and ID to a file (inventory.json)
        # for later use with Ansible.

    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        print("Please check your API key, product ID, and OS ID.")

if __name__ == "__main__":
    main()
