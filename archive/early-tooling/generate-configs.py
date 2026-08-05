#!/usr/bin/env python3
"""
Generate AmneziaWG client configs and add peers to server.
Run locally, connects to server via SSH.
"""
import subprocess
import os

# --- Server settings ---
SERVER_PUBLIC_KEY = "BeaOUxJPWwtFTimRt9Xx7wDGvYENT4742r7n9SLN/gs="
SERVER_ENDPOINT = "45.140.146.95:443"
SERVER_SSH = "vpnadmin@45.140.146.95"
AWG_CONF = "/etc/amnezia/amneziawg/awg0.conf"

# --- AWG obfuscation params ---
AWG_PARAMS = {
    "Jc": 4, "Jmin": 50, "Jmax": 1000,
    "S1": 113, "S2": 129,
    "H1": 2084167604, "H2": 496352973,
    "H3": 523868278, "H4": 1364490158,
}

# --- Clients ---
CLIENTS = [
    "alex", "kris", "vano", "mac", "artem",
    "vika", "client1", "myphone", "kiga", "kolga",
    "vz", "dm", "workstation", "client2", "client3",
    "spare",
]

OUTPUT_DIR = "configs/clients"


def run(cmd: list) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def generate_keys() -> tuple[str, str, str]:
    priv = run(["awg", "genkey"])
    pub = subprocess.run(
        ["awg", "pubkey"], input=priv,
        capture_output=True, text=True, check=True
    ).stdout.strip()
    psk = run(["awg", "genpsk"])
    return priv, pub, psk


def add_peer_to_server(pub: str, psk: str, ip: str, name: str) -> None:
    peer_block = (
        f"\n### Client {name}\n"
        f"[Peer]\n"
        f"PublicKey = {pub}\n"
        f"PresharedKey = {psk}\n"
        f"AllowedIPs = {ip}/32,fd42:42:42::{ip.split('.')[-1]}/128\n"
    )
    subprocess.run(
        ["ssh", SERVER_SSH, f"echo '{peer_block}' | sudo tee -a {AWG_CONF}"],
        check=True
    )


def build_client_config(priv: str, psk: str, ip: str) -> str:
    last = ip.split(".")[-1]
    params = "\n".join(f"{k} = {v}" for k, v in AWG_PARAMS.items())
    return f"""[Interface]
PrivateKey = {priv}
Address = {ip}/32,fd42:42:42::{last}/128
DNS = 1.1.1.1,1.0.0.1
{params}

[Peer]
PublicKey = {SERVER_PUBLIC_KEY}
PresharedKey = {psk}
Endpoint = {SERVER_ENDPOINT}
AllowedIPs = 0.0.0.0/0,::/0
PersistentKeepalive = 25
"""


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for i, name in enumerate(CLIENTS, 2):
        ip = f"10.66.66.{i}"
        print(f"[{i-1:02d}/{len(CLIENTS)}] Generating {name} ({ip})...", end=" ")

        priv, pub, psk = generate_keys()
        add_peer_to_server(pub, psk, ip, name)

        conf = build_client_config(priv, psk, ip)
        path = os.path.join(OUTPUT_DIR, f"awg0-{name}.conf")
        with open(path, "w") as f:
            f.write(conf)

        print(f"done → {path}")

    # Restart AWG on server
    print("\nRestarting AmneziaWG on server...")
    subprocess.run(
        ["ssh", SERVER_SSH, "sudo systemctl restart awg-quick@awg0"],
        check=True
    )
    print("Done. All configs saved to:", OUTPUT_DIR)


if __name__ == "__main__":
    main()