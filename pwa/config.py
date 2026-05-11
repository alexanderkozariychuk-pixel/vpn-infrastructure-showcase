import os
from dotenv import load_dotenv

load_dotenv()

MOLDOVA_IP = os.getenv("MOLDOVA_IP", "45.140.146.134")
MOLDOVA_USER = os.getenv("MOLDOVA_USER", "alex")
AWG_INTERFACE = os.getenv("AWG_INTERFACE", "awg0")
AWG_SERVICE = f"awg-quick@{AWG_INTERFACE}"
IPIP_INTERFACE = os.getenv("IPIP_INTERFACE", "ipip0")
API_SECRET = os.getenv("API_SECRET", "changeme")
