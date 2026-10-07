#!/usr/bin/env python3
"""
sov-monitor — checks the whole service from am1 (outside Russia), shows it on
the admin panel's "Состояние" card, and writes to Telegram when something
breaks, when it is fixed, and once a day with a summary.

Runs every 2 minutes from a systemd timer (sov-monitor.timer). Python standard
library only: nothing to install on am1, nothing listening there.

What it looks at:
  - the portal from outside: the page answers, and the certificate is not near
    its end;
  - every host's sov-probe (over SSH as `sovmon`, pinned to that one command):
    disk, memory, load, failed systemd units, reboots;
  - the links between nodes: the newest AmneziaWG handshake on the interfaces
    named as links in the config;
  - the portal's own jobs: tonight's dump, the hourly expiry sweep and its
    failures, the containers; and the copy pulled to am1.

After every run the report (numbers + confirmed problems) is posted to the
portal, /api/monitor/report, with MONITOR_TOKEN; the portal says it in words
(pwa/services/monitor_view.py). Telegram is optional: without it the panel is
the only view.

A problem is reported after it has been seen on `confirm_runs` runs in a row,
so a single dropped SSH connection stays quiet; then every `remind_h` hours
while it lasts, and once more when it clears. State lives in
/var/lib/sov-monitor/state.json and is saved only after Telegram took the
message, so an alert that could not be sent is sent on the next run.

If am1 itself goes quiet nobody would know, so the last step of every run pings
a dead man's switch (healthchecks.io, `[deadman] url`), which mails when the
pings stop — or straight away when a run reports that Telegram refused.

Install on am1:
  sudo install -m 755 infrastructure/monitoring/sov_monitor.py /usr/local/sbin/sov-monitor
  sudo install -m 755 infrastructure/monitoring/sov-probe /usr/local/sbin/
  sudo install -d -m 700 /etc/sov-monitor /var/lib/sov-monitor
  sudo install -m 600 infrastructure/monitoring/monitor.ini.example /etc/sov-monitor/monitor.ini
  (the tokens: sudo sh -c 'umask 077; cat > /etc/sov-monitor/portal.token', paste, Ctrl-D)
  sudo install -m 644 infrastructure/monitoring/sov-monitor.service infrastructure/monitoring/sov-monitor.timer /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl enable --now sov-monitor.timer

  sov-monitor --dry-run    prints what it would send, sends nothing, saves nothing
  sov-monitor --test       sends one test message
"""

import argparse
import configparser
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CONFIG = os.environ.get("SOV_MONITOR_CONFIG", "/etc/sov-monitor/monitor.ini")
STATE = os.environ.get("SOV_MONITOR_STATE", "/var/lib/sov-monitor/state.json")
MSK = timezone(timedelta(hours=3))

DEFAULT_LIMITS = {
    "disk_pct": "85",
    "mem_avail_pct": "10",
    "load_per_cpu": "2.0",
    "link_stale_s": "300",
    "cert_min_days": "14",
    "confirm_runs": "2",
    "remind_h": "6",
    "backup_max_h": "26",
    "pulled_backup_max_h": "27",
    "expiry_max_h": "2",
}


# ── collecting ──────────────────────────────────────────────────────────

def parse_probe(text: str) -> dict:
    """key=value lines from sov-probe; numbers become numbers."""
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            continue
        value = value.strip()
        try:
            out[key.strip()] = int(value)
        except ValueError:
            try:
                out[key.strip()] = float(value)
            except ValueError:
                out[key.strip()] = value
    return out


def run_probe(target: str, key: str, timeout: int = 40) -> tuple[dict | None, str]:
    """(probe values, "") or (None, why it failed)."""
    if target == "local":
        cmd = ["/usr/local/sbin/sov-probe"]
    else:
        cmd = ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
               "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=yes", target]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "нет ответа за %d с" % timeout
    if p.returncode != 0:
        err = (p.stderr.strip().splitlines() or ["код %d" % p.returncode])[-1]
        return None, err[:200]
    values = parse_probe(p.stdout)
    if "host" not in values:
        return None, "пустой ответ"
    return values, ""


def check_url(url: str, timeout: int = 15) -> str:
    """"" when the page answers 200, otherwise what went wrong."""
    req = urllib.request.Request(url, headers={"User-Agent": "sov-monitor"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "" if r.status == 200 else "HTTP %d" % r.status
    except urllib.error.HTTPError as e:
        return "HTTP %d" % e.code
    except Exception as e:  # noqa: BLE001 — any failure is the answer
        return type(e).__name__ + (": %s" % e.reason if hasattr(e, "reason") else "")


def cert_days_left(host: str, port: int = 443, timeout: int = 15) -> float:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            not_after = tls.getpeercert()["notAfter"]
    return (ssl.cert_time_to_seconds(not_after) - time.time()) / 86400


# ── judging ─────────────────────────────────────────────────────────────

def _list(value: str) -> list[str]:
    return [v.strip() for v in value.replace(",", " ").split() if v.strip()]


def host_problems(name: str, section, limits, probe: dict | None, why: str) -> dict:
    """{problem key: message} for one host's probe."""
    if probe is None:
        return {f"{name}:down": f"{name}: не отвечает ({why})"}
    p = {}
    disk = probe.get("disk_root_pct")
    if isinstance(disk, int) and disk >= int(limits["disk_pct"]):
        p[f"{name}:disk"] = f"{name}: диск занят на {disk}%"
    mem = probe.get("mem_avail_pct")
    if isinstance(mem, int) and mem < int(limits["mem_avail_pct"]):
        p[f"{name}:mem"] = f"{name}: свободной памяти {mem}%"
    load, ncpu = probe.get("load1"), probe.get("ncpu") or 1
    if isinstance(load, (int, float)) and load / ncpu >= float(limits["load_per_cpu"]):
        p[f"{name}:load"] = f"{name}: нагрузка {load} на {ncpu} CPU"
    if probe.get("failed_units", 0):
        p[f"{name}:units"] = f"{name}: упали сервисы: {probe.get('failed_unit_names', '?')}"

    for ifname in _list(section.get("links", "")):
        fresh = probe.get(f"awg.{ifname}.fresh")
        if fresh is None:
            p[f"{name}:link:{ifname}"] = f"{name}: интерфейса {ifname} нет"
        elif fresh < 0 or fresh > int(limits["link_stale_s"]):
            ago = "ни разу" if fresh < 0 else f"{fresh // 60} мин назад"
            p[f"{name}:link:{ifname}"] = f"{name}: связка {ifname} молчит, последний handshake {ago}"
    for ifname in _list(section.get("clients", "")):
        if f"awg.{ifname}.peers" not in probe:
            p[f"{name}:iface:{ifname}"] = f"{name}: клиентского интерфейса {ifname} нет"

    if "backup_max_h" in section or "backup_age" in probe:
        age = probe.get("backup_age")
        limit = float(section.get("backup_max_h", limits["backup_max_h"])) * 3600
        if age is None or age > limit:
            p[f"{name}:backup"] = f"{name}: свежего дампа базы нет" + (
                f" ({age / 3600:.0f} ч)" if age is not None else "")
    if "pulled_backup_max_h" in section or "pulled_backup_age" in probe:
        age = probe.get("pulled_backup_age")
        limit = float(section.get("pulled_backup_max_h", limits["pulled_backup_max_h"])) * 3600
        if age is None or age > limit:
            p[f"{name}:pulled"] = f"{name}: копия бэкапа не обновлялась" + (
                f" ({age / 3600:.0f} ч)" if age is not None else "")
    if "expiry_max_h" in section or "expiry_age" in probe:
        age = probe.get("expiry_age")
        limit = float(section.get("expiry_max_h", limits["expiry_max_h"])) * 3600
        if age is None or age > limit:
            p[f"{name}:expiry"] = f"{name}: почасовая проверка подписок не запускалась"
        elif probe.get("expiry_failures", 0):
            p[f"{name}:expiry_fail"] = (f"{name}: проверка подписок — {probe['expiry_failures']} "
                                        "ошибок (смотри /var/log/pwa/expiry.log)")
    want, up = probe.get("containers_expected"), probe.get("containers_up")
    if isinstance(want, int) and isinstance(up, int) and up < want:
        p[f"{name}:containers"] = f"{name}: контейнеров запущено {up} из {want}"
    return p


def web_checks(cfg, limits) -> tuple[dict, dict]:
    """(problems, facts) for the site seen from outside."""
    p, facts = {}, {"urls": {}, "certs": {}}
    if not cfg.has_section("web"):
        return p, facts
    for url in _list(cfg["web"].get("urls", "")):
        why = check_url(url)
        facts["urls"][url] = why
        if why:
            p[f"web:{url}"] = f"сайт {url} не открывается: {why}"
    for host in _list(cfg["web"].get("cert_hosts", "")):
        try:
            days = cert_days_left(host)
        except Exception as e:  # noqa: BLE001
            facts["certs"][host] = None
            p[f"cert:{host}"] = f"сертификат {host} не проверить: {type(e).__name__}"
            continue
        facts["certs"][host] = round(days, 1)
        if days < float(limits["cert_min_days"]):
            p[f"cert:{host}"] = f"сертификат {host} истекает через {days:.0f} дн"
    return p, facts


WARN_KINDS = ("disk", "mem", "load", "units")


def level(key: str) -> str:
    """'warn' = something to do soon, 'bad' = broken now."""
    if key.startswith("cert:"):
        return "warn"
    _, _, kind = key.partition(":")
    return "warn" if kind in WARN_KINDS else "bad"


# ── remembering and telling ─────────────────────────────────────────────

def _dur(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m // 60} ч {m % 60} мин" if m >= 60 else f"{m} мин"


def step(state: dict, problems: dict, now: float, confirm: int, remind_s: float) -> tuple[list[str], dict]:
    """What to send now, and the state to keep if it was sent."""
    old = state.get("problems", {})
    new, msgs = {}, []
    for key, text in problems.items():
        s = dict(old.get(key, {"since": now, "count": 0, "sent": 0}))
        s["count"] += 1
        s["text"] = text
        if s["count"] >= confirm and (not s["sent"] or now - s["sent"] >= remind_s):
            again = " (всё ещё, %s)" % _dur(now - s["since"]) if s["sent"] else ""
            msgs.append("🔴 " + text + again)
            s["sent"] = now
        new[key] = s
    for key, s in old.items():
        if key not in problems and s.get("sent"):
            msgs.append("✅ " + s["text"] + " — прошло (%s)" % _dur(now - s["since"]))
    out = dict(state)
    out["problems"] = new
    return msgs, out


def reboots(state: dict, probes: dict, now: float) -> tuple[list[str], dict]:
    """A host whose boot time moved has rebooted: one message, no 'resolved'."""
    boots = dict(state.get("boots", {}))
    msgs, notices = [], []
    for name, probe in probes.items():
        if not probe or "uptime_s" not in probe:
            continue
        boot = now - probe["uptime_s"]
        last = boots.get(name)
        if last is not None and abs(boot - last) > 300:
            msgs.append(f"ℹ️ {name}: перезагрузился {_dur(probe['uptime_s'])} назад")
            notices.append({"key": f"{name}:reboot", "text": f"{name}: перезагрузился", "at": boot})
        boots[name] = boot
    out = dict(state)
    out["boots"] = boots
    out["notices"] = notices
    return msgs, out


def digest(probes: dict, problems: dict, now: float) -> str:
    lines = ["📋 Sovereign, сводка на " + datetime.fromtimestamp(now, MSK).strftime("%d.%m %H:%M МСК")]
    for name, probe in probes.items():
        if not probe:
            lines.append(f"• {name}: не отвечает")
            continue
        peers = sum(v for k, v in probe.items() if k.endswith(".peers") and isinstance(v, int))
        bits = [f"диск {probe.get('disk_root_pct', '?')}%", f"память своб. {probe.get('mem_avail_pct', '?')}%",
                f"load {probe.get('load1', '?')}"]
        if peers:
            bits.append(f"пиров {peers}")
        lines.append(f"• {name}: " + ", ".join(bits))
    lines.append("Проблем сейчас: %d" % len(problems) if problems else "Проблем нет")
    return "\n".join(lines)


def send_telegram(cfg, text: str) -> bool:
    """True when sent — or when Telegram is not set up, so alerts do not pile up."""
    if not cfg.has_section("telegram"):
        return True
    tg = cfg["telegram"]
    try:
        with open(tg["token_file"]) as f:
            token = f.read().strip()
    except OSError:
        return True
    data = urllib.parse.urlencode({"chat_id": tg["chat_id"], "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        print(f"telegram: {type(e).__name__}", file=sys.stderr)
        return False


def build_report(cfg, probes: dict, errors: dict, web: dict, state: dict, now: float, confirm: int) -> dict:
    """What the admin panel gets: the numbers and the problems confirmed so far."""
    hosts = [s for s in cfg.sections() if s.startswith("host:")]
    return {
        "sent_at": now,
        "hosts": probes,
        "errors": errors,
        "links": {s[5:]: _list(cfg[s].get("links", "")) for s in hosts if _list(cfg[s].get("links", ""))},
        "clients": {s[5:]: _list(cfg[s].get("clients", "")) for s in hosts if _list(cfg[s].get("clients", ""))},
        "web": web,
        "problems": [{"key": k, "text": v["text"], "level": level(k), "since": v["since"]}
                     for k, v in state.get("problems", {}).items() if v["count"] >= confirm],
        "notices": state.get("notices", []),
    }


def send_report(cfg, report: dict) -> bool:
    if not cfg.has_section("portal"):
        return True
    url = cfg["portal"].get("report_url", "").strip()
    if not url:
        return True
    try:
        with open(cfg["portal"]["token_file"]) as f:
            token = f.read().strip()
        req = urllib.request.Request(url, json.dumps(report, ensure_ascii=False).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {token}",
                                              "User-Agent": "sov-monitor"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        print(f"portal report: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def ping_deadman(cfg, ok: bool) -> None:
    url = cfg.get("deadman", "url", fallback="").strip()
    if not url:
        return
    try:
        urllib.request.urlopen(url if ok else url.rstrip("/") + "/fail", timeout=10).close()
    except Exception as e:  # noqa: BLE001
        print(f"deadman: {type(e).__name__}", file=sys.stderr)


def load_state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    cfg = configparser.ConfigParser()
    if not cfg.read(CONFIG):
        print(f"no config at {CONFIG}", file=sys.stderr)
        return 2
    limits = dict(DEFAULT_LIMITS)
    if cfg.has_section("limits"):
        limits.update(cfg["limits"])

    if args.test:
        return 0 if send_telegram(cfg, "🧪 sov-monitor: тестовое сообщение, связь есть") else 1

    now = time.time()
    key = cfg.get("ssh", "key", fallback="/root/.ssh/sov-monitor")
    probes, problems, errors = {}, {}, {}
    for section in cfg.sections():
        if not section.startswith("host:"):
            continue
        name = section[5:]
        probe, why = run_probe(cfg[section].get("ssh", "local"), key)
        probes[name] = probe
        if why:
            errors[name] = why
        problems.update(host_problems(name, cfg[section], limits, probe, why))
    web_p, web = web_checks(cfg, limits)
    problems.update(web_p)

    state = load_state()
    # A host that does not answer tells nothing about its disk or links: keep
    # what was open for it rather than announce it all as fixed.
    for name, probe in probes.items():
        if probe is None:
            for k, s in state.get("problems", {}).items():
                if k.startswith(name + ":") and k != name + ":down":
                    problems.setdefault(k, s["text"])
    msgs, state = step(state, problems, now, int(limits["confirm_runs"]), float(limits["remind_h"]) * 3600)
    boot_msgs, state = reboots(state, probes, now)
    msgs += boot_msgs

    hour = cfg.getint("digest", "hour_msk", fallback=-1)
    today = datetime.fromtimestamp(now, MSK)
    if hour >= 0 and today.hour == hour and state.get("digest_day") != today.strftime("%F"):
        msgs.append(digest(probes, problems, now))
        state["digest_day"] = today.strftime("%F")

    report = build_report(cfg, probes, errors, web, state, now, int(limits["confirm_runs"]))
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        print("\n".join(msgs) or "(nothing to send)")
        return 0

    sent = not msgs or send_telegram(cfg, "\n".join(msgs))
    if sent:
        save_state(state)
    # The panel is a second view of the same state; a failed post does not
    # hold back Telegram, and the next run posts a fresh report anyway.
    send_report(cfg, report)
    ping_deadman(cfg, sent)
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
