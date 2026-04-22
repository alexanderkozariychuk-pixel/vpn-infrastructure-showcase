"""
Client management handlers: /clients, /addclient, /delclient.
"""
import asyncio
import logging
import os
import re
import tempfile

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from services.wireguard import (
    add_peer_to_server,
    generate_keys,
    get_awg_params,
    get_next_client_ip,
    get_server_public_ip,
    get_server_public_key,
    parse_awg_show,
    remove_peer_from_server,
    restart_wireguard,
)
from utils.telegram import auth_filter, send_long_message

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Text builder — from system.py (menu_callback)
# ----------------------------------------------------------------------

async def get_clients_text() -> str:
    """
    Build connected clients list from parse_awg_show().
    """
    loop = asyncio.get_event_loop()
    peers, err = await loop.run_in_executor(None, parse_awg_show)

    if err:
        return f"❌ Failed to get clients:\n```\n{err}\n```"

    if not peers:
        return "ℹ️ No peers configured."

    lines = [f"📋 *Clients: {len(peers)}*\n"]

    for i, peer in enumerate(peers, 1):
        pk_short = peer.public_key[:16] + "..."
        active = peer.handshake != "never"
        status = "🟢" if active else "⚪"
        lines += [
            f"{status} *{i}.* `{pk_short}`",
            f"   Endpoint: {peer.endpoint}",
            f"   Handshake: {peer.handshake}",
            f"   Transfer: {peer.transfer}",
            "",
        ]

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Client config builder
# ----------------------------------------------------------------------

def _build_client_config(
    priv: str,
    client_ip: str,
    server_pub: str,
    server_ip: str,
    psk: str,
    awg: dict,
) -> str:
    last_octet = client_ip.split(".")[-1]
    return (
        f"[Interface]\n"
        f"PrivateKey = {priv}\n"
        f"Address = {client_ip}/32,fd42:42:42::{last_octet}/128\n"
        f"DNS = 1.1.1.1,1.0.0.1\n"
        f"Jc = {awg.get('Jc', '4')}\n"
        f"Jmin = {awg.get('Jmin', '50')}\n"
        f"Jmax = {awg.get('Jmax', '1000')}\n"
        f"S1 = {awg.get('S1', '113')}\n"
        f"S2 = {awg.get('S2', '129')}\n"
        f"H1 = {awg.get('H1', '2084167604')}\n"
        f"H2 = {awg.get('H2', '496352973')}\n"
        f"H3 = {awg.get('H3', '523868278')}\n"
        f"H4 = {awg.get('H4', '1364490158')}\n"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {server_pub}\n"
        f"PresharedKey = {psk}\n"
        f"Endpoint = {server_ip}:443\n"
        f"AllowedIPs = 0.0.0.0/0,::/0\n"
        f"PersistentKeepalive = 25\n"
    )


# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------

async def clients_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return
    text = await get_clients_text()
    await send_long_message(update, text)


async def addclient_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return

    # Validate name
    if not context.args:
        await update.message.reply_text("Usage: /addclient <name>")
        return

    name = context.args[0]
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        await update.message.reply_text(
            "❌ Invalid name. Use only letters, numbers, underscores, hyphens."
        )
        return

    status_msg = await update.message.reply_text("⏳ Step 1/4: Collecting server info...")

    # Step 1 — server info (parallel)
    loop = asyncio.get_event_loop()
    server_pub, server_ip, awg = await asyncio.gather(
        loop.run_in_executor(None, get_server_public_key),
        get_server_public_ip(),                            # уже async
        loop.run_in_executor(None, get_awg_params),
    )

    if not all([server_pub, server_ip, awg]):
        await status_msg.edit_text("❌ Failed to retrieve server settings.")
        return

    await status_msg.edit_text("⏳ Step 2/4: Generating keys...")

    # Step 2 — keys + IP
    priv, pub, psk = await loop.run_in_executor(None, generate_keys)
    if not all([priv, pub, psk]):
        await status_msg.edit_text("❌ Failed to generate keys.")
        return

    client_ip = await loop.run_in_executor(None, get_next_client_ip)
    if not client_ip:
        await status_msg.edit_text("❌ No free IP addresses in subnet.")
        return

    await status_msg.edit_text("⏳ Step 3/4: Adding peer to server...")

    # Step 3 — add peer + restart
    ok = await loop.run_in_executor(None, add_peer_to_server, pub, psk, client_ip)
    if not ok:
        await status_msg.edit_text("❌ Failed to add peer to server config.")
        return

    restarted = await loop.run_in_executor(None, restart_wireguard)
    if not restarted:
        await status_msg.edit_text(
            "⚠️ Peer added but failed to restart WireGuard."
        )
        return

    await status_msg.edit_text("⏳ Step 4/4: Generating client config...")

    # Step 4 — build and send config
    conf = _build_client_config(priv, client_ip, server_pub, server_ip, psk, awg)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as tmp:
            tmp.write(conf)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=f"awg0-{name}.conf"),
                caption=(
                    f"✅ Client *{name}* created.\n"
                    f"IP: `{client_ip}`\n"
                    f"Endpoint: `{server_ip}:443`"
                ),
                parse_mode="Markdown",
            )
        await status_msg.delete()

    except Exception as e:
        logger.error("Failed to send client config: %s", e)
        await status_msg.edit_text(f"❌ Failed to send config: {e}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def delclient_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/delclient <public_key>`", parse_mode="Markdown"
        )
        return

    pub_key = context.args[0]
    status_msg = await update.message.reply_text(
        f"⏳ Removing peer `{pub_key[:16]}...`", parse_mode="Markdown"
    )

    loop = asyncio.get_event_loop()

    removed = await loop.run_in_executor(None, remove_peer_from_server, pub_key)
    if not removed:
        await status_msg.edit_text("❌ Failed to remove peer. Check logs.")
        return

    restarted = await loop.run_in_executor(None, restart_wireguard)
    if restarted:
        await status_msg.edit_text("✅ Client removed and service restarted.")
    else:
        await status_msg.edit_text(
            "⚠️ Client removed from config but failed to restart service."
        )