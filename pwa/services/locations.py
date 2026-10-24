"""
services/locations.py — where a device connects: one entry node per location.

Since 2026-10-24 the service runs two independent chains, each with its own
entry and its own exit:

  de  "Germany"      clients → entry A → the first exit; AmneziaWG 1.0
  nl  "Netherlands"  clients → entry B → exit-2;        AmneziaWG 3.x

A device belongs to one location for life (Config.location): its peer lives on
that location's entry, its file carries that entry's key, address and
obfuscation. Nothing moves between them; a customer who wants both holds a
device in each.

Germany is the portal's original setup and reads the settings it always did
(BRIDGE_*). The Netherlands is configured only through the environment, its
obfuscation included: the repository is public, and a 3.x header range and
I1 signature published next to the code would hand a censor the pattern to
match. Until every NL_* setting is present the location does not exist —
not listed, not accepted — so a portal deployed before its .env is filled in
behaves exactly as it did.

Order matters: it is the order the portal shows them in, and the first one
is the one recommended.
"""
import json
import os
from dataclasses import dataclass, field

DEFAULT = "de"


@dataclass(frozen=True)
class Location:
    key: str
    host: str                 # entry node address, reached over SSH by the wrappers
    public_key: str           # entry awg0 public key, in every client file
    endpoint: str             # host:port in the client file (a DNS name, so the IP can change)
    params: dict = field(default_factory=dict)   # obfuscation lines for the client file, in order
    mtu: int = 1300


# Obfuscation of entry A's awg0 (AmneziaWG 1.0). Public since the portal's
# first version (and in infrastructure/ansible/inventory/group_vars/entry).
DE_PARAMS = {
    "Jc": "3", "Jmin": "50", "Jmax": "1000",
    "S1": "72", "S2": "146",
    "H1": "1163059398", "H2": "1787455160",
    "H3": "970047041",  "H4": "133143559",
}

# What a client file may carry, in the order it is written.
_PARAM_ORDER = ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4",
                "H1", "H2", "H3", "H4", "I1", "I2", "I3", "I4", "I5"]


def _parse_params(raw: str) -> dict | None:
    """NL_AWG_PARAMS: a JSON object, {"Jc": "5", ..., "I1": "<b 0x...>"}."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not data:
        return None
    unknown = set(data) - set(_PARAM_ORDER)
    if unknown:
        return None
    return {k: str(data[k]) for k in _PARAM_ORDER if k in data}


def _germany() -> Location:
    return Location(
        key="de",
        host=os.getenv("BRIDGE_IP", ""),
        public_key=os.getenv("BRIDGE_PUBLIC_KEY", "kCq1FK/tYvvB68h9luTRX5PAV0a2pIn2klbyNUKRMm0="),
        endpoint=os.getenv("BRIDGE_ENDPOINT", ""),
        params=dict(DE_PARAMS),
        mtu=1300,
    )


def _netherlands() -> Location | None:
    host = os.getenv("NL_ENTRY_IP", "").strip()
    pub = os.getenv("NL_PUBLIC_KEY", "").strip()
    endpoint = os.getenv("NL_ENDPOINT", "").strip()
    params = _parse_params(os.getenv("NL_AWG_PARAMS", ""))
    if not (host and pub and endpoint and params):
        return None
    try:
        mtu = int(os.getenv("NL_MTU", "1280"))
    except ValueError:
        mtu = 1280
    return Location(key="nl", host=host, public_key=pub, endpoint=endpoint, params=params, mtu=mtu)


def all_locations() -> list[Location]:
    """Every configured location, recommended first. Read at call time."""
    nl = _netherlands()
    return ([nl] if nl else []) + [_germany()]


def get(key: str | None) -> Location | None:
    """The location by key; None for an unknown or unconfigured one."""
    key = key or DEFAULT
    for loc in all_locations():
        if loc.key == key:
            return loc
    return None


def keys() -> list[str]:
    return [loc.key for loc in all_locations()]


def recommended() -> str:
    return all_locations()[0].key
