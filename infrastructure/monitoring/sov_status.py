#!/usr/bin/env python3
"""
sov-status — the public status of each location, checked the way a customer
uses it, shown in the Telegram channel.

Every 2 minutes (sov-status.timer) on am1, for every location in the config:
a real client device of that location (a service account's device, issued by
the portal like any other) is brought up in a network namespace of its own,
and a page is fetched through it. The namespace keeps am1's own traffic out of
the tunnel; the tunnel's UDP socket stays in the main namespace, so it leaves
am1 the normal way. A run passes when the page comes back through a different
address than am1's own — proof the request went through the whole chain.

What the channel sees:
  * one pinned message, edited in place every run (no notifications):
    every location 🟢 / 🔴 / 🔧, uptime over 30 days, time of the check;
  * a post when a location stops working (`down_after` failed runs in a row,
    ~6 minutes) and one when it is back (`up_after` good runs), with how long
    it lasted. Short blips post nothing.

Planned work: `touch /etc/sov-status/maintenance.<key>` shows 🔧 for that
location, posts nothing, and leaves those runs out of the uptime. Remove the
file when done.

Only locations are named — never hosts, addresses or providers.

Install on am1 (Python standard library; needs AmneziaWG with `awg`,
`awg-quick` and the kernel module, plus curl):
  sudo install -m 755 infrastructure/monitoring/sov_status.py /usr/local/sbin/sov-status
  sudo install -d -m 700 /etc/sov-status /var/lib/sov-status
  sudo install -m 600 infrastructure/monitoring/status.ini.example /etc/sov-status/status.ini
  (device files: /etc/sov-status/<key>.conf, mode 600)
  sudo install -m 644 infrastructure/monitoring/sov-status.service infrastructure/monitoring/sov-status.timer /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now sov-status.timer

  sov-status --dry-run     checks, prints the board and any posts; sends and saves nothing
  sov-status --teardown    removes the namespaces (they are rebuilt on the next run)
"""

import argparse
import configparser
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CONFIG = os.environ.get("SOV_STATUS_CONFIG", "/etc/sov-status/status.ini")
STATE = os.environ.get("SOV_STATUS_STATE", "/var/lib/sov-status/state.json")
MAINT_DIR = os.environ.get("SOV_STATUS_MAINT_DIR", "/etc/sov-status")
MSK = timezone(timedelta(hours=3))
KEEP_DAYS = 31
UPTIME_DAYS = 30


# ── the tunnel ──────────────────────────────────────────────────────────────

def run(cmd: list[str], timeout: int = 20, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)


def parse_interface(conf_text: str) -> tuple[list[str], int | None]:
    """Addresses and MTU from the [Interface] section of a device file."""
    addrs, mtu, section = [], None, ""
    for line in conf_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("["):
            section = line.lower()
            continue
        if section != "[interface]" or "=" not in line:
            continue
        k, v = (p.strip() for p in line.split("=", 1))
        if k.lower() == "address":
            addrs += [a.strip() for a in v.split(",") if a.strip() and ":" not in a]
        elif k.lower() == "mtu" and v.isdigit():
            mtu = int(v)
    return addrs, mtu


def ns_name(key: str) -> str:
    return f"sovst-{key}"[:15]


def ns_exists(ns: str, runner=run) -> bool:
    out = runner(["ip", "netns", "list"]).stdout
    return any(line.split()[0] == ns for line in out.splitlines() if line.strip())


def teardown(key: str, runner=run) -> None:
    ns = ns_name(key)
    if ns_exists(ns, runner):
        runner(["ip", "netns", "del", ns])
    runner(["ip", "link", "del", ns])  # a half-built one left in the main namespace


def setup(key: str, conf_path: str, runner=run) -> None:
    """Bring the location's device up inside its own namespace."""
    ns = ns_name(key)
    with open(conf_path) as f:
        addrs, mtu = parse_interface(f.read())
    if not addrs:
        raise RuntimeError(f"{key}: no IPv4 Address in the device file")
    strip = runner(["awg-quick", "strip", conf_path])
    if strip.returncode != 0:
        raise RuntimeError(f"{key}: awg-quick strip failed")
    teardown(key, runner)
    steps = [
        ["ip", "netns", "add", ns],
        ["ip", "link", "add", "dev", ns, "type", "amneziawg"],
    ]
    for cmd in steps:
        r = runner(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"{key}: {' '.join(cmd[:3])} failed: {r.stderr.strip()[:120]}")
    fd, tmp = tempfile.mkstemp(prefix="sovst-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(strip.stdout)
        r = runner(["awg", "setconf", ns, tmp])
        if r.returncode != 0:
            raise RuntimeError(f"{key}: awg setconf failed: {r.stderr.strip()[:120]}")
    finally:
        os.unlink(tmp)
    steps = [["ip", "link", "set", ns, "netns", ns]]
    steps += [["ip", "-n", ns, "addr", "add", a, "dev", ns] for a in addrs]
    steps += [
        ["ip", "-n", ns, "link", "set", "lo", "up"],
        ["ip", "-n", ns, "link", "set", ns] + (["mtu", str(mtu)] if mtu else []) + ["up"],
        ["ip", "-n", ns, "route", "add", "default", "dev", ns],
    ]
    for cmd in steps:
        r = runner(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"{key}: {' '.join(cmd[:4])} failed: {r.stderr.strip()[:120]}")


def parse_trace(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def fetch(url: str, timeout: int, ns: str | None = None, runner=run) -> dict | None:
    cmd = ["curl", "-sS", "-m", str(timeout), url]
    if ns:
        cmd = ["ip", "netns", "exec", ns] + cmd
    try:
        r = runner(cmd, timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0:
        return None
    t = parse_trace(r.stdout)
    return t if t.get("ip") else None


def check_location(key: str, conf_path: str, url: str, timeout: int, own_ip: str | None, runner=run) -> tuple[bool, str]:
    """(passed, why). One rebuild and retry before calling it a failure."""
    ns = ns_name(key)
    for attempt in (1, 2):
        try:
            if attempt == 2 or not ns_exists(ns, runner):
                setup(key, conf_path, runner)
                time.sleep(2)  # the first handshake
        except Exception as e:  # noqa: BLE001
            why = str(e)
            continue
        t = fetch(url, timeout, ns, runner)
        if t is None:
            why = "no answer through the tunnel"
            continue
        if own_ip and t["ip"] == own_ip:
            why = "the answer came from am1's own address"
            continue
        return True, f"via exit, loc={t.get('loc', '?')}"
    return False, why


# ── judging and remembering ─────────────────────────────────────────────────

def in_maintenance(key: str) -> bool:
    return os.path.exists(os.path.join(MAINT_DIR, f"maintenance.{key}"))


def step_location(st: dict, passed: bool | None, now: float, down_after: int, up_after: int) -> tuple[dict, str | None]:
    """
    New state of one location after a run, and the event to post: "down",
    "up" or None. `passed` is None in maintenance: nothing changes but the flag.
    """
    st = dict(st)
    st.setdefault("status", "up")
    st.setdefault("fails", 0)
    st.setdefault("oks", 0)
    if passed is None:
        st["maint"] = True
        return st, None
    st["maint"] = False
    event = None
    if passed:
        st["oks"] += 1
        st["fails"] = 0
        if st["status"] == "down" and st["oks"] >= up_after:
            st["status"] = "up"
            event = "up"
            st["last_down_s"] = now - st.get("down_since", now)
    else:
        st["fails"] += 1
        st["oks"] = 0
        if st["status"] == "up" and st["fails"] >= down_after:
            st["status"] = "down"
            # It went down when the first of these failures was seen.
            st["down_since"] = st.get("first_fail", now)
            event = "down"
        if st["fails"] == 1:
            st["first_fail"] = now
    return st, event


def record(st: dict, passed: bool | None, now: float) -> dict:
    """Per-day counts of good and checked runs, for the uptime figure."""
    if passed is None:
        return st
    st = dict(st)
    days = dict(st.get("days", {}))
    day = datetime.fromtimestamp(now, MSK).strftime("%Y-%m-%d")
    ok, total = days.get(day, [0, 0])
    days[day] = [ok + (1 if passed else 0), total + 1]
    cutoff = (datetime.fromtimestamp(now, MSK) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    st["days"] = {d: v for d, v in days.items() if d >= cutoff}
    return st


def uptime(st: dict, now: float) -> float | None:
    cutoff = (datetime.fromtimestamp(now, MSK) - timedelta(days=UPTIME_DAYS)).strftime("%Y-%m-%d")
    ok = total = 0
    for d, (o, t) in st.get("days", {}).items():
        if d > cutoff:
            ok += o
            total += t
    return None if total == 0 else 100.0 * ok / total


def pct(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 99.995:
        return "100%"
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def minutes(seconds: float) -> str:
    m = max(1, round(seconds / 60))
    if m < 60:
        return f"{m} мин"
    h, m = divmod(m, 60)
    return f"{h} ч {m} мин" if m else f"{h} ч"


# ── what the channel reads ──────────────────────────────────────────────────

def board(locs: list[dict], states: dict, now: float) -> str:
    lines = ["📡 Статус Sovereign", ""]
    for loc in locs:
        st = states.get(loc["key"], {})
        if st.get("maint"):
            mark, word = "🔧", "плановые работы"
        elif st.get("status") == "down":
            mark, word = "🔴", "перебои"
        else:
            mark, word = "🟢", "работает"
        lines.append(f"{mark} {loc['flag']} {loc['name']} — {word}")
    lines += ["", "Доступность за 30 дней:",
              " · ".join(f"{loc['flag']} {pct(uptime(states.get(loc['key'], {}), now))}" for loc in locs), ""]
    when = datetime.fromtimestamp(now, MSK).strftime("%d.%m в %H:%M")
    lines.append(f"Обновлено {when} МСК · проверка каждые 2 минуты")
    lines.append("Проверка идёт с нашей стороны. Если у вас не работает — переключитесь "
                 "на другую локацию и напишите в поддержку.")
    return "\n".join(lines)


def post_text(event: str, loc: dict, others: list[dict], st: dict) -> str:
    if event == "down":
        if others:
            alt = ", ".join(o["name"] for o in others)
            tip = (f"Пока используйте {alt}: в личном кабинете можно добавить устройство "
                   "во второй локации.")
        else:
            tip = "Новости — здесь же."
        return f"🔴 {loc['flag']} {loc['name']}: перебои в работе. Уже разбираемся.\n{tip}"
    return (f"🟢 {loc['flag']} {loc['name']} снова работает. "
            f"Перебой длился {minutes(st.get('last_down_s', 0))}.")


# ── Telegram ────────────────────────────────────────────────────────────────

class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    def call(self, method: str, **params) -> dict:
        data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        try:
            with urllib.request.urlopen(url, data, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return json.load(e)
            except Exception:  # noqa: BLE001
                return {"ok": False, "description": f"HTTP {e.code}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "description": type(e).__name__}

    def send(self, text: str, silent: bool = False) -> int | None:
        r = self.call("sendMessage", chat_id=self.chat_id, text=text,
                      disable_web_page_preview="true", disable_notification="true" if silent else None)
        return r["result"]["message_id"] if r.get("ok") else None

    def edit(self, message_id: int, text: str) -> str:
        """"ok", "same" (nothing changed), "gone" (the message is not there), or "error"."""
        r = self.call("editMessageText", chat_id=self.chat_id, message_id=message_id, text=text,
                      disable_web_page_preview="true")
        if r.get("ok"):
            return "ok"
        d = r.get("description", "")
        if "not modified" in d:
            return "same"
        if "not found" in d or "can't be edited" in d:
            return "gone"
        return "error"

    def pin(self, message_id: int) -> bool:
        return bool(self.call("pinChatMessage", chat_id=self.chat_id, message_id=message_id,
                              disable_notification="true").get("ok"))


def publish(tg, state: dict, board_text: str, posts: list[str]) -> dict:
    """Posts first (oldest first), then the board. Unsent posts wait for the next run."""
    state = dict(state)
    pending = list(state.get("pending", [])) + posts
    left = []
    for text in pending:
        if left or tg.send(text) is None:
            left.append(text)
    state["pending"] = left
    mid = state.get("board_id")
    if mid:
        r = tg.edit(mid, board_text)
        if r == "gone":
            mid = None
    if not mid:
        mid = tg.send(board_text, silent=True)
        if mid:
            tg.pin(mid)
    state["board_id"] = mid
    return state


# ── a run ───────────────────────────────────────────────────────────────────

def load_config(path: str) -> tuple[configparser.ConfigParser, list[dict]]:
    cfg = configparser.ConfigParser()
    if not cfg.read(path):
        raise SystemExit(f"no config at {path}")
    locs = []
    for sec in cfg.sections():
        if sec.startswith("location:"):
            s = cfg[sec]
            locs.append({"key": sec.split(":", 1)[1], "name": s.get("name", sec), "flag": s.get("flag", ""),
                         "conf": s["conf"]})
    if not locs:
        raise SystemExit("no [location:*] sections")
    return cfg, locs


def load_state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    args = ap.parse_args()

    cfg, locs = load_config(CONFIG)
    if args.teardown:
        for loc in locs:
            teardown(loc["key"])
        print("namespaces removed")
        return 0

    chk = cfg["check"] if cfg.has_section("check") else {}
    url = chk.get("url", "https://1.1.1.1/cdn-cgi/trace")
    timeout = int(chk.get("timeout", 12))
    down_after = int(chk.get("down_after", 3))
    up_after = int(chk.get("up_after", 2))

    own = fetch(url, timeout)
    own_ip = own["ip"] if own else None

    state = load_state()
    states = dict(state.get("locations", {}))
    now = time.time()
    events = []
    for loc in locs:
        key = loc["key"]
        if in_maintenance(key):
            passed, why = None, "maintenance"
        else:
            passed, why = check_location(key, loc["conf"], url, timeout, own_ip)
        st, ev = step_location(states.get(key, {}), passed, now, down_after, up_after)
        states[key] = record(st, passed, now)
        print(f"{key}: {'maintenance' if passed is None else ('ok' if passed else 'FAIL')} — {why}")
        if ev:
            events.append((ev, loc))
    state["locations"] = states

    posts = []
    for ev, loc in events:
        others = [o for o in locs if o["key"] != loc["key"]
                  and states[o["key"]].get("status") == "up" and not states[o["key"]].get("maint")]
        posts.append(post_text(ev, loc, others, states[loc["key"]]))
    text = board(locs, states, now)

    if args.dry_run:
        print("\n--- board ---\n" + text)
        for p in posts:
            print("\n--- post ---\n" + p)
        return 0

    if cfg.has_section("channel"):
        ch = cfg["channel"]
        with open(ch["token_file"]) as f:
            tg = Telegram(f.read().strip(), ch["chat_id"])
        state = publish(tg, state, text, posts)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
