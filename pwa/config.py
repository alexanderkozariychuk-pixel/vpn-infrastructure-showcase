import os
from dotenv import load_dotenv

load_dotenv()

# Foreign exit node (Cloud4Box DE) — status/logs/metrics are read from here
EXIT_IP = os.getenv("EXIT_IP", "")
EXIT_USER = os.getenv("EXIT_USER", "sovadmin")
AWG_INTERFACE = os.getenv("AWG_INTERFACE", "awg0")
AWG_SERVICE = f"awg-quick@{AWG_INTERFACE}"
# Backbone peer as seen FROM the exit node (the /30 far end = the RU entry).
# This link is what breaks; pinging it from the exit is the early-warning signal.
BACKBONE_PEER_IP = os.getenv("BACKBONE_PEER_IP", "10.77.77.2")

# Bridge
BRIDGE_IP = os.getenv("BRIDGE_IP", "")
BRIDGE_USER = os.getenv("BRIDGE_USER", "vpnadmin")
BRIDGE_AWG_INTERFACE = os.getenv("BRIDGE_AWG_INTERFACE", "awg0")

# LLM
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemini-2.0-flash-001")
