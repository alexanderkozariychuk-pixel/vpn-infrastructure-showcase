"""
services/monitor_view.py — the monitor's report, in words.

sov-monitor on the backup host sends its numbers every two minutes
(api/monitor.py stores them). This module is what turns "disk_root_pct=87,
awg.awg1.fresh=34" into "Диск занят на 87%" and "на связи, обмен ключами 34 с
назад", and colours each server: ok, warn (something to do soon), bad
(broken now), unknown (the monitor has said nothing).

Nothing here decides what is a problem — sov-monitor does, with its limits and
its two-runs-in-a-row rule, and sends the problems it has confirmed. This
only describes the state and places those problems on the right card.
"""
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))
STALE_AFTER_S = 600

TITLES = {
    "portal": "Портал",
    "entry": "Вход (entry)",
    "exit": "Выход (exit)",
    "am1": "Бэкап-сервер (am1)",
}
RANK = {"ok": 0, "unknown": 1, "warn": 2, "bad": 3}


def aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; everything stored here is UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def ago(seconds: float | int | None) -> str:
    if seconds is None:
        return "неизвестно когда"
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} с назад"
    m = s // 60
    if m < 60:
        return f"{m} мин назад"
    h = m // 60
    if h < 48:
        return f"{h} ч {m % 60} мин назад" if h < 6 and m % 60 else f"{h} ч назад"
    return f"{h // 24} дн назад"


def when(at: datetime, now: datetime) -> str:
    """'сегодня в 03:17', 'вчера в 03:17', '05.10 в 03:17' — Moscow time."""
    local, today = at.astimezone(MSK), now.astimezone(MSK).date()
    day = local.date()
    if day == today:
        prefix = "сегодня"
    elif day == today - timedelta(days=1):
        prefix = "вчера"
    else:
        prefix = local.strftime("%d.%m")
    return f"{prefix} в {local:%H:%M}"


def duration(seconds: float) -> str:
    m = max(0, int(seconds // 60))
    if m < 1:
        return "меньше минуты"
    if m < 60:
        return f"{m} мин"
    h = m // 60
    if h < 48:
        return f"{h} ч {m % 60} мин" if m % 60 else f"{h} ч"
    return f"{h // 24} дн {h % 24} ч"


def _load_word(load, ncpu) -> str:
    if not isinstance(load, (int, float)):
        return "?"
    per = load / (ncpu or 1)
    return "низкая" if per < 0.7 else "средняя" if per < 1.5 else "высокая"


def _resources(p: dict) -> str:
    return (f"Диск занят на {p.get('disk_root_pct', '?')}% · свободно памяти "
            f"{p.get('mem_avail_pct', '?')}% · нагрузка {_load_word(p.get('load1'), p.get('ncpu'))}")


def _stamp(age, base: datetime, now: datetime) -> str:
    if not isinstance(age, (int, float)):
        return "нет данных"
    return f"{when(base - timedelta(seconds=age), now)} ({ago(age)})"


def _host_lines(name: str, p: dict, clients: list[str], base: datetime, now: datetime) -> list[str]:
    lines = []
    for ifname in clients:
        peers, active = p.get(f"awg.{ifname}.peers"), p.get(f"awg.{ifname}.active")
        if peers is not None:
            line = f"Устройств на сервере: {peers}"
            if active is not None:
                line += f", активны сейчас: {active}"
            lines.append(line)
    if "backup_age" in p:
        lines.append("Бэкап базы: " + _stamp(p["backup_age"], base, now))
    if "pulled_backup_age" in p:
        lines.append("Копия бэкапа здесь: " + _stamp(p["pulled_backup_age"], base, now))
    if "expiry_age" in p:
        line = "Подписки проверены " + ago(p["expiry_age"])
        if p.get("expiry_failures"):
            line += f", ошибок: {p['expiry_failures']}"
        lines.append(line)
    if "containers_expected" in p:
        lines.append(f"Контейнеры: работают {p.get('containers_up', '?')} из {p['containers_expected']}")
    if p.get("failed_units"):
        lines.append("Упавшие службы: " + str(p.get("failed_unit_names", "?")))
    lines.append(_resources(p))
    if isinstance(p.get("uptime_s"), int):
        lines.append(f"Без перезагрузки {duration(p['uptime_s'])}")
    return lines


def _card(cid: str, title: str, lines: list[str], problems: list[dict], status: str | None = None,
          raw: dict | None = None) -> dict:
    if status is None:
        status = max((pr["level"] for pr in problems), key=RANK.get, default="ok")
    return {"id": cid, "title": title, "status": status, "lines": lines,
            "problems": [pr["text"] for pr in problems], "raw": raw or {}}


def build(payload: dict | None, received_at: datetime | None, now: datetime) -> dict:
    """The admin page's state block: banner, cards, overall colour."""
    received_at = aware(received_at)
    if not payload or received_at is None:
        return {"received_at": None, "age_s": None, "stale": True, "status": "unknown",
                "summary": "Мониторинг ещё не присылал отчётов", "cards": []}

    age = (now - received_at).total_seconds()
    # Ages in the report were measured when it was sent, not now.
    base = datetime.fromtimestamp(payload.get("sent_at") or received_at.timestamp(), timezone.utc)
    hosts = payload.get("hosts") or {}
    errors = payload.get("errors") or {}
    links = payload.get("links") or {}
    clients = payload.get("clients") or {}
    web = payload.get("web") or {}
    problems = payload.get("problems") or []

    def mine(prefix: str, *, only: str | None = None, skip: str | None = None) -> list[dict]:
        out = []
        for pr in problems:
            key = pr.get("key", "")
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            if only is not None and not rest.startswith(only):
                continue
            if skip is not None and rest.startswith(skip):
                continue
            out.append(pr)
        return out

    cards = []

    # The site, from outside.
    site_lines = []
    for url, err in (web.get("urls") or {}).items():
        site_lines.append(f"{url} — открывается" if not err else f"{url} — не открывается ({err})")
    for host, days in (web.get("certs") or {}).items():
        site_lines.append(f"Сертификат {host}: ещё {int(days)} дн" if isinstance(days, (int, float))
                          else f"Сертификат {host}: не удалось проверить")
    site_problems = [pr for pr in problems if pr.get("key", "").startswith(("web:", "cert:"))]
    cards.append(_card("site", "Сайт", site_lines or ["нет данных"], site_problems,
                       raw=web, status=None if site_lines or site_problems else "unknown"))

    for name, probe in hosts.items():
        title = TITLES.get(name, name)
        host_problems = mine(f"{name}:", skip="link:")
        if probe is None:
            cards.append(_card(name, title, [f"Не отвечает: {errors.get(name, 'причина неизвестна')}"],
                               host_problems, status="bad"))
            continue
        cards.append(_card(name, title, _host_lines(name, probe, clients.get(name) or [], base, now),
                           host_problems, raw=probe))

    # Links between nodes get a card of their own: the thing customers feel.
    link_lines, link_problems, link_raw = [], [], {}
    for name, ifaces in links.items():
        probe = hosts.get(name)
        for ifname in ifaces:
            label = f"{TITLES.get(name, name)}, {ifname}"
            fresh = (probe or {}).get(f"awg.{ifname}.fresh")
            link_raw[f"{name}.{ifname}"] = fresh
            if probe is None:
                link_lines.append(f"{label}: сервер не отвечает, не проверить")
            elif fresh is None:
                link_lines.append(f"{label}: интерфейса нет")
            elif fresh < 0:
                link_lines.append(f"{label}: связи не было ни разу")
            else:
                link_lines.append(f"{label}: обмен ключами {ago(fresh)}")
        link_problems += mine(f"{name}:", only="link:")
    if link_lines:
        unknown = all(hosts.get(n) is None for n in links)
        cards.insert(1, _card("links", "Связка вход ↔ выход", link_lines, link_problems, raw=link_raw,
                              status="unknown" if unknown and not link_problems else None))

    if age > STALE_AFTER_S:
        status = "unknown"
        summary = (f"Мониторинг молчит с {when(received_at, now)} — проверь am1. "
                   "Ниже последнее, что он видел")
    else:
        status = max((c["status"] for c in cards), key=RANK.get, default="ok")
        bad = sum(1 for c in cards if c["status"] == "bad")
        warn = sum(1 for c in cards if c["status"] == "warn")
        summary = ("Всё работает" if not bad and not warn else
                   ", ".join(x for x in (f"сломано: {bad}" if bad else "",
                                         f"требует внимания: {warn}" if warn else "") if x).capitalize())
    return {"received_at": received_at.isoformat(), "age_s": int(age), "stale": age > STALE_AFTER_S,
            "status": status, "summary": summary, "checked": ago(age), "cards": cards}


def describe_event(e, now: datetime) -> dict:
    start, end = aware(e.started_at), aware(e.ended_at)
    return {
        "text": e.text,
        "level": e.level,
        "at": when(start, now),
        "open": end is None,
        "duration": duration(((end or now) - start).total_seconds()) if e.level != "info" else "",
    }
