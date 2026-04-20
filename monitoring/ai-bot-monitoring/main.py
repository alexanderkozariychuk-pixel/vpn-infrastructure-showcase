#!/usr/bin/env python3
"""
Telegram bot with Google Gemini integration for DevOps assistance.
Supports inline menu, /status, /logs, /restart, /clients, /addclient, /delclient, /analyze.
"""

import logging
import subprocess
import re
import os
import tempfile
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import google.generativeai as genai

# --- Configuration ---
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
ALLOWED_USER_ID = 123456789  # Your Telegram user ID
# --------------------

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-3-flash-preview')

ANALYSIS_PROMPT = (
    "You are an expert DevOps and SRE Engineer. "
    "Analyze the provided AmneziaWG logs and system metrics. "
    "1. Identify critical errors, handshake issues, or resource bottlenecks. "
    "2. Evaluate system health and stability. "
    "3. Provide technical recommendations for fixes or optimizations. "
    "IMPORTANT: Provide your response in TWO sections: "
    "First, write the full analysis in English. "
    "Second, provide a Russian translation of that analysis below it."
)
SYSTEM_PROMPT = "You are a helpful DevOps assistant. Answer technical questions concisely."

# Store pending restart confirmation
pending_restart = {}

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def parse_awg_show():
    try:
        result = subprocess.run(["sudo", "/usr/bin/awg", "show"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return None, result.stderr
        output = result.stdout
    except Exception as e:
        return None, str(e)

    peers = []
    current_peer = {}
    for line in output.splitlines():
        if line.startswith('peer:'):
            if current_peer:
                peers.append(current_peer)
            current_peer = {'public_key': line.split()[1]}
        elif ': ' in line:
            key, value = line.split(': ', 1)
            key = key.strip()
            value = value.strip()
            if key == 'endpoint':
                current_peer['endpoint'] = value
            elif key == 'allowed ips':
                current_peer['allowed_ips'] = value
            elif key == 'latest handshake':
                current_peer['handshake'] = value
            elif key == 'transfer':
                current_peer['transfer'] = value
            elif key == 'persistent keepalive':
                current_peer['keepalive'] = value
    if current_peer:
        peers.append(current_peer)
    return peers, None

def get_server_public_key():
    try:
        result = subprocess.run(
            "sudo cat /etc/amnezia/amneziawg/awg0.conf | grep PrivateKey | awk '{print $3}'",
            shell=True, capture_output=True, text=True
        )
        priv_key = result.stdout.strip()
        if priv_key:
            pub_result = subprocess.run(
                ["wg", "pubkey"], input=priv_key, capture_output=True, text=True
            )
            return pub_result.stdout.strip()
        return None
    except Exception as e:
        logger.error(f"Error extracting key: {e}")
        return None

def get_server_public_ip():
    try:
        result = subprocess.run(["curl", "-s", "ifconfig.me"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except:
        return None

def get_next_client_ip():
    peers, _ = parse_awg_show()
    used_ips = set()
    if peers:
        for peer in peers:
            allowed = peer.get('allowed_ips', '')
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)/32', allowed)
            if match:
                used_ips.add(match.group(1))
    for i in range(2, 255):
        ip = f"10.66.66.{i}"
        if ip not in used_ips:
            return ip
    return None

def generate_keys():
    try:
        priv_proc = subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True)
        priv = priv_proc.stdout.strip()
        pub_proc = subprocess.run(["wg", "pubkey"], input=priv, capture_output=True, text=True, check=True)
        pub = pub_proc.stdout.strip()
        psk_proc = subprocess.run(["wg", "genpsk"], capture_output=True, text=True, check=True)
        psk = psk_proc.stdout.strip()
        return priv, pub, psk
    except Exception as e:
        logger.error(f"Error generating keys: {e}")
        return None, None, None

def get_awg_params():
    conf_path = '/etc/amnezia/amneziawg/awg0.conf'
    params = {}
    try:
        result = subprocess.run(['sudo', 'cat', conf_path], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                if key in ['Jc', 'Jmin', 'Jmax', 'S1', 'S2', 'H1', 'H2', 'H3', 'H4']:
                    params[key] = value.strip()
        return params
    except Exception as e:
        logger.error(f"Error reading AWG params: {e}")
        return None

def add_peer_to_server(public_key, psk, allowed_ip):
    peer_block = f"\n[Peer]\nPublicKey = {public_key}\nPresharedKey = {psk}\nAllowedIPs = {allowed_ip}/32,fd42:42:42::{allowed_ip.split('.')[-1]}/128\n"
    try:
        process = subprocess.run(
            ['sudo', 'tee', '-a', '/etc/amnezia/amneziawg/awg0.conf'],
            input=peer_block,
            text=True,
            capture_output=True,
            check=True
        )
        return True
    except Exception as e:
        logger.error(f"Error writing to server config: {e}")
        return False

def remove_peer_from_server(public_key):
    conf_path = '/etc/amnezia/amneziawg/awg0.conf'
    try:
        result = subprocess.run(['sudo', 'cat', conf_path], capture_output=True, text=True, check=True)
        # Remove extra blank lines at start/end when reading
        lines = result.stdout.strip().splitlines()

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            current_block = []
            interface_section = True  # Flag indicating we are still in [Interface] section

            for line in lines:
                strip_line = line.strip()

                if strip_line == '[Peer]':
                    interface_section = False
                    # If we have accumulated a peer block, check it and write it
                    if current_block:
                        block_str = "\n".join(current_block).strip()
                        if public_key not in block_str:
                            tmp.write("\n" + block_str + "\n")
                    current_block = [line]
                elif not interface_section:
                    current_block.append(line)
                else:
                    # Write lines from [Interface] section as is
                    tmp.write(line + "\n")

            # Write the last block
            if current_block:
                block_str = "\n".join(current_block).strip()
                if public_key not in block_str:
                    tmp.write("\n" + block_str + "\n")
            tmp_path = tmp.name

        subprocess.run(f"sudo dd if={tmp_path} of={conf_path}", shell=True, check=True)
        os.unlink(tmp_path)
        return True
    except Exception as e:
        logger.error(f"Error removing peer: {e}")
        return False

def restart_wireguard():
    try:
        subprocess.run(["sudo", "systemctl", "restart", "awg-quick@awg0"], check=True, timeout=30)
        return True
    except:
        return False

# ----------------------------------------------------------------------
# Text generators for menu
# ----------------------------------------------------------------------
async def auth_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.id == ALLOWED_USER_ID:
        return True
    logger.warning(f"Unauthorized access: {user.first_name} (ID: {user.id})")
    if update.message:
        await update.message.reply_text("⛔ Access restricted. This is a private bot.")
    elif update.callback_query:
        await update.callback_query.answer("Access denied!", show_alert=True)
    return False

async def get_status_text():
    try:
        result = subprocess.run(["sudo", "/usr/bin/awg", "show"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            output = result.stdout
            peers = output.count("peer:")
            handshake = "yes" if "latest handshake" in output else "no"
            return f"🟢 AmneziaWG is running\nPeers: {peers}\nHandshake: {handshake}\n\n```\n{output[:1500]}\n```"
        else:
            return "🔴 AmneziaWG is not running or `awg` command failed."
    except Exception as e:
        return f"Error: {e}"

async def get_clients_text():
    peers, err = parse_awg_show()
    if err or peers is None:
        return f"❌ Failed to get clients: {err or 'unknown error'}"
    if not peers:
        return "No clients connected."
    msg = "📋 **Connected clients:**\n\n"
    for i, peer in enumerate(peers, 1):
        pubkey = peer.get('public_key', '?')[:16] + "..."
        handshake = peer.get('handshake', 'never')
        transfer = peer.get('transfer', '0 B')
        endpoint = peer.get('endpoint', 'N/A')
        msg += f"**{i}.** `{pubkey}`\n"
        msg += f"   Endpoint: {endpoint}\n"
        msg += f"   Handshake: {handshake}\n"
        msg += f"   Transfer: {transfer}\n\n"
        if len(msg) > 3500:
            msg += "... (truncated)"
            break
    return msg

async def get_logs_text(lines=20):
    try:
        result = subprocess.run(
            ["sudo", "dmesg", "-T"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            all_lines = result.stdout.splitlines()
            relevant = [l for l in all_lines if "amneziawg" in l.lower() or "wg0" in l.lower()]
            if not relevant:
                return "ℹ️ No new logs."
            log_text = "\n".join(relevant[-lines:])
            return f"📜 **Real-time Kernel Logs:**\n```\n{log_text}\n```"
        else:
            return "❌ Access error (check sudo)."
    except Exception as e:
        return f"⚠️ Error: {e}"

# ----------------------------------------------------------------------
# Inline keyboard menu
# ----------------------------------------------------------------------
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Status", callback_data="menu_status")],
        [InlineKeyboardButton("👥 Clients", callback_data="menu_clients")],
        [InlineKeyboardButton("📜 Logs (20)", callback_data="menu_logs")],
        [InlineKeyboardButton("🔄 Restart", callback_data="menu_restart")],
        [InlineKeyboardButton("❓ Help", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_status":
        text = await get_status_text()
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data == "menu_clients":
        text = await get_clients_text()
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data == "menu_logs":
        text = await get_logs_text(20)
        await query.edit_message_text(text, parse_mode='Markdown')
    elif data == "menu_restart":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, restart", callback_data="restart_confirm")],
            [InlineKeyboardButton("❌ No", callback_data="restart_cancel")]
        ])
        await query.edit_message_text("⚠️ Are you sure you want to restart AmneziaWG? This will briefly interrupt the VPN.", reply_markup=keyboard)
    elif data == "menu_help":
        text = "🤖 *AI DevOps Assistant*\nChoose an option from the menu."
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=main_menu_keyboard())

# ----------------------------------------------------------------------
# Command handlers
# ----------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context):
        return

    keyboard = [[InlineKeyboardButton("🔓 Enter Control Panel", callback_data="menu_help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Bot is active. Press the button to enter:", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    await start(update, context)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    await start(update, context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    text = await get_status_text()
    await update.message.reply_text(text, parse_mode='Markdown')

async def clients_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    text = await get_clients_text()
    await update.message.reply_text(text, parse_mode='Markdown')

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    args = context.args
    lines = 30
    if args and args[0].isdigit():
        lines = int(args[0])
    text = await get_logs_text(lines)
    await update.message.reply_text(text, parse_mode='Markdown')

async def analyze_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Determine message to reply to (support both buttons and text commands)
    msg = update.callback_query.message if update.callback_query else update.message
    status_msg = await msg.reply_text("📡 Step 1: Collecting system data...")

    try:
        loop = asyncio.get_event_loop()

        # Function to run system commands in a separate thread
        def get_system_info():
            l = subprocess.run("sudo journalctl -u awg-quick@awg0 -n 10 --no-pager",
                               shell=True, capture_output=True, text=True, timeout=5).stdout
            m = subprocess.run("uptime && free -m",
                               shell=True, capture_output=True, text=True, timeout=3).stdout
            return l, m

        # Run data collection
        logs, metrics = await loop.run_in_executor(None, get_system_info)

        await status_msg.edit_text("🧠 Step 2: Analyzing with Gemini 3 Flash...")

        # Fast prompt for preview model
        prompt = (
            "You are a DevOps assistant. Analyze these VPN logs and metrics. "
            "List 3 bullet points: Status, Critical Errors (if any), and Recommendation. "
            "Be extremely brief. Use English.\n\n"
            f"DATA:\n{metrics}\n{logs}"
        )

        try:
            # Use 3-flash since others may be unavailable
            model_3 = genai.GenerativeModel('models/gemini-3-flash-preview')

            # Wait up to 30 seconds for response
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: model_3.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": 300, "temperature": 0.2}
                )),
                timeout=30.0
            )
            answer = response.text
        except asyncio.TimeoutError:
            # If AI hangs, just output collected logs
            answer = "⚠️ AI did not respond (Timeout). Last logs:\n\n" + f"```\n{logs}\n```"
        except Exception as api_err:
            answer = f"⚠️ API Error (3-flash): {str(api_err)[:100]}"

        # Step 3: Output result
        header = "🤖 **VPN Health Report**\n" + "—" * 20 + "\n"

        try:
            await status_msg.edit_text(header + answer, parse_mode='Markdown')
        except:
            # If Markdown breaks due to special characters in logs
            await status_msg.edit_text(header + answer, parse_mode=None)

    except Exception as e:
        logger.error(f"Critical error in analyze: {e}")
        await msg.reply_text(f"❌ System failure: {str(e)[:100]}")

# Helper function to safely send long messages
async def send_long_message(update, text):
    # Remove possible problematic blocks at the end if text gets truncated
    if len(text) > 4090:
        parts = [text[i:i+4090] for i in range(0, len(text), 4090)]
    else:
        parts = [text]

    for part in parts:
        try:
            # Attempt to send with Markdown
            await update.message.reply_text(part, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
            # If failed, send as plain text without formatting
            await update.message.reply_text(part)

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    user_id = update.effective_user.id
    pending_restart[user_id] = True
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, restart", callback_data="restart_confirm")],
        [InlineKeyboardButton("❌ No", callback_data="restart_cancel")]
    ])
    await update.message.reply_text("⚠️ Are you sure you want to restart AmneziaWG? This will briefly interrupt the VPN.", reply_markup=keyboard)

async def restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if query.data == "restart_confirm":
        if pending_restart.get(user_id):
            try:
                subprocess.run(["sudo", "systemctl", "restart", "awg-quick@awg0"], check=True, timeout=30)
                await query.edit_message_text("🔄 AmneziaWG restarted successfully.")
            except Exception as e:
                await query.edit_message_text(f"❌ Failed to restart: {e}")
            finally:
                pending_restart.pop(user_id, None)
        else:
            await query.edit_message_text("No pending restart request.")
    else:
        await query.edit_message_text("Restart cancelled.")
        pending_restart.pop(user_id, None)

async def addclient_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Usage: /addclient <name>")
        return
    name = context.args[0]
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        await update.message.reply_text("Invalid name. Use only letters, numbers, underscores and hyphens.")
        return

    # 1. Collect server data
    server_pub = get_server_public_key()
    server_ip = get_server_public_ip()
    awg = get_awg_params()

    if not server_pub or not server_ip or not awg:
        await update.message.reply_text("Failed to retrieve server settings (keys, IP or AWG params).")
        return

    # 2. GENERATE KEYS ONCE (3 keys)
    priv, pub, psk = generate_keys()
    if not priv or not pub or not psk:
        await update.message.reply_text("Failed to generate keys.")
        return

    client_ip = get_next_client_ip()
    if not client_ip:
        await update.message.reply_text("No free IP addresses.")
        return

    # 3. Write to SERVER (use same variables)
    if not add_peer_to_server(pub, psk, client_ip):
        await update.message.reply_text("Failed to add client to server.")
        return

    # 4. Restart
    if not restart_wireguard():
        await update.message.reply_text("Client added but failed to restart WireGuard.")
        return

    # 5. Generate CLIENT config
    client_conf = f"""[Interface]
PrivateKey = {priv}
Address = {client_ip}/32,fd42:42:42::{client_ip.split('.')[-1]}/128
DNS = 1.1.1.1,1.0.0.1
Jc = {awg.get('Jc', '4')}
Jmin = {awg.get('Jmin', '50')}
Jmax = {awg.get('Jmax', '1000')}
S1 = {awg.get('S1', '113')}
S2 = {awg.get('S2', '129')}
H1 = {awg.get('H1', '2084167604')}
H2 = {awg.get('H2', '496352973')}
H3 = {awg.get('H3', '523868278')}
H4 = {awg.get('H4', '1364490158')}

[Peer]
PublicKey = {server_pub}
PresharedKey = {psk}
Endpoint = {server_ip}:443
AllowedIPs = 0.0.0.0/0,::/0
PersistentKeepalive = 25
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
        tmp.write(client_conf)
        tmp_path = tmp.name

    try:
        with open(tmp_path, 'rb') as f:
            await update.message.reply_document(
                document=InputFile(f, filename=f"awg0-{name}.conf"),
                caption=f"✅ Client '{name}' created.\nIP: {client_ip}\nEndpoint: {server_ip}:443"
            )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

async def delclient_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: `/delclient <public_key>`", parse_mode='Markdown')
        return

    pub_key = context.args[0]
    await update.message.reply_text(f"⏳ Removing client with key `{pub_key}`...", parse_mode='Markdown')

    if remove_peer_from_server(pub_key):
        if restart_wireguard():
            await update.message.reply_text("✅ Client successfully removed, configuration updated.")
        else:
            await update.message.reply_text("⚠️ Client removed from file, but failed to restart service.")
    else:
        await update.message.reply_text("❌ Error removing client. Check logs.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_filter(update, context): return
    user_text = update.message.text
    full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_text}\n\nAssistant answer:"
    try:
        response = model.generate_content(full_prompt)
        answer = response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        answer = "Sorry, AI service error. Please try again later."
    await update.message.reply_text(answer)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("clients", clients_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("addclient", addclient_command))
    app.add_handler(CommandHandler("delclient", delclient_command))
    app.add_handler(CommandHandler("analyze", analyze_logs_command))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(restart_callback, pattern="^restart_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    logger.info("Bot started with AI Analysis feature")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()