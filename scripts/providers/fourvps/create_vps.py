#!/usr/bin/env python3
"""
4VPS.SU API Client – Create a Virtual Private Server (VPS) automatically.

This script uses the official 4VPS.SU API to provision a new VPS.
It demonstrates Infrastructure as Code (IaC) principles by automating
server creation for the Russian retranslator node.

Requirements:
    - Python 3.7+
    - aiohttp library (install via `pip install aiohttp`)
    - API token from your 4VPS.SU account (found in the customer portal)

How to use:
    1. Replace `YOUR_API_TOKEN_FROM_4VPS_SU` with your actual API token.
    2. Run the script once to discover the correct IDs for:
        - Data center (Saint Petersburg)
        - Tariff plan (Ryzen, 2GB RAM, 50GB NVMe)
        - Operating system template (Ubuntu 22.04)
    3. Update the configuration constants (DATACENTER_ID, TARIFF_ID, OS_TEMPLATE_ID)
       with the discovered IDs.
    4. Run the script again – it will create the VPS and print the server ID and root password.
"""
import asyncio
import sys
import os

# Add the current directory to the Python path so we can import the API wrapper
sys.path.append(os.path.dirname(__file__))
from api import FourVpsClient

# ==================== CONFIGURATION ====================
# Obtain your API token from: https://4vps.su (Account → API)
API_TOKEN = "N9YpNKU79cfGGdKjXmH9xHnsI"

# Data center where the VPS will be hosted.
# Use the script's discovery mode to find the correct ID for Saint Petersburg.
DATACENTER_ID = 1      # Example – replace after discovery

# Tariff (product) ID.
# Run the script once to see the list of tariffs and pick the one with:
#   - Ryzen CPU, 2 GB RAM, 50 GB NVMe, 1 Gbit/s
TARIFF_ID = 123        # Example – replace after discovery

# Operating system template ID.
# Use the same discovery mechanism to get the ID for Ubuntu 22.04 (or your preferred OS).
OS_TEMPLATE_ID = 42    # Example – replace after discovery

# Hostname for the new VPS (will appear in the control panel)
SERVER_NAME = "ru-retranslator"

# Billing period in hours. 720 hours = 30 days (typical monthly billing)
PERIOD = 720
# =======================================================

async def main():
    """
    Main async routine:
        - Connects to the 4VPS.SU API using the provided token.
        - Discovers and prints available data centers, tariffs, and OS images.
        - Creates a new VPS using the selected configuration.
    """
    # Use the client as an async context manager to automatically handle session cleanup
    async with FourVpsClient(token=API_TOKEN) as client:
        # 1. List all data centers (locations) – useful to find the correct DATACENTER_ID
        print("Fetching available data centers...")
        dcs = await client.get_dc_list()
        print("Data centers:")
        for dc in dcs:
            print(f"  ID: {dc.id}, City: {dc.city}, Name: {dc.name}")
        print("\nSet DATACENTER_ID to the ID of Saint Petersburg (or your preferred location).\n")

        # 2. List all tariff plans (presets) – find the one matching your hardware requirements
        print("Fetching tariff plans...")
        tariffs = await client.get_tariff_list()
        print("Tariffs:")
        for tariff in tariffs:
            print(f"  Cluster: {tariff.cluster_info.name} (Data center ID: {tariff.cluster_info.id})")
            for preset in tariff.presets:
                print(f"    Preset ID: {preset.id}, Name: {preset.name}, "
                      f"CPU cores: {preset.cpu_number}, RAM: {preset.ram_mib} MiB, Disk: {preset.rom} GB")
        print("\nSet TARIFF_ID to the Preset ID matching your desired specs (Ryzen, 2GB RAM, 50GB).\n")

        # 3. List available OS templates for the chosen tariff and data center
        # Note: At this point we use the (still placeholder) IDs to demonstrate.
        # In a real run, you would set them after discovery.
        print(f"Fetching OS images for tariff ID {TARIFF_ID} and data center ID {DATACENTER_ID}...")
        images = await client.get_images(tariff_id=TARIFF_ID, dc_id=DATACENTER_ID)
        if images:
            print("OS images:")
            for img in images:
                print(f"  ID: {img.id}, Name: {img.name}")
        else:
            print("  No images found – check that TARIFF_ID and DATACENTER_ID are correct.")
        print("\nSet OS_TEMPLATE_ID to the ID of Ubuntu 22.04 (or your preferred OS).\n")

        # 4. Create the VPS using the configured parameters
        print(f"Creating VPS with name '{SERVER_NAME}'...")
        result = await client.buy_server(
            tariff_id=TARIFF_ID,
            datacenter_id=DATACENTER_ID,
            ostempl_id=OS_TEMPLATE_ID,
            server_name=SERVER_NAME,
            period=PERIOD
        )
        print(f"\n✅ VPS successfully created!")
        print(f"   Server ID: {result.server_id}")
        print(f"   Root password: {result.password}")
        print(f"\nYou can now use this server ID for further API calls (e.g., get VM link, power on).")

if __name__ == "__main__":
    asyncio.run(main())
