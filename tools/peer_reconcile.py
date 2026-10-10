#!/usr/bin/env python3
"""
peer_reconcile.py — the entry node's peers against the portal's database.

Read-only: it compares two text files and prints what does not match. It
changes nothing on either side; what to remove is decided by a person.

Inputs (made by the commands in docs/runbook.md, "Peers and the database"):

  node.txt    one line per peer on awg0:  <public key> <allowed ips> <latest handshake epoch>
              (from `awg show awg0 dump`, keys only — the PSK column is dropped
              before the file leaves the node)
  db.txt      <public key>|<peer ip>|<is_active t/f>|<kind>|<username>|<device name>
  labels.txt  <public key>|<label>      (the admin panel's names for hand-made peers)

Usage: peer_reconcile.py node.txt db.txt labels.txt
"""
import ipaddress
import sys
import time
from collections import Counter

PAID_POOL = ("10.88.88", 42, 199)    # pwa/services/provisioner.py CLIENT_POOL
TRIAL_POOL = ("10.88.89", 10, 250)   # pwa/services/provisioner.py TRIAL_POOL


def read_node(path):
    peers = {}
    for line in open(path, encoding="utf-8"):
        parts = line.replace("\r", "").split()
        if len(parts) < 3:
            continue
        key, ips, hs = parts[0], parts[1], parts[2]
        ip = ips.split(",")[0].split("/")[0]
        peers[key] = {"ip": ip, "hs": int(hs) if hs.isdigit() else 0}
    return peers


def read_db(path):
    rows = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("|")
        if len(p) < 6:
            continue
        rows[p[0]] = {"ip": p[1], "active": p[2] == "t", "kind": p[3], "user": p[4], "name": p[5]}
    return rows


def read_labels(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("|", 1)
        if len(p) == 2:
            out[p[0]] = p[1]
    return out


def ago(epoch, now):
    if not epoch:
        return "никогда"
    s = now - epoch
    if s < 3600:
        return f"{s // 60} мин назад"
    if s < 86400 * 2:
        return f"{s // 3600} ч назад"
    return f"{s // 86400} дн назад"


def in_pool(ip, pool):
    prefix, lo, hi = pool
    head, _, last = ip.rpartition(".")
    return head == prefix and last.isdigit() and lo <= int(last) <= hi


def sort_ip(ip):
    try:
        return int(ipaddress.ip_address(ip))
    except ValueError:
        return 0


def main(node_path, db_path, labels_path):
    now = int(time.time())
    node, db, labels = read_node(node_path), read_db(db_path), read_labels(labels_path)
    active = {k: v for k, v in db.items() if v["active"]}

    ok = [k for k in node if k in active]
    missing = [k for k in active if k not in node]          # customer has a config that cannot work
    stale = [k for k in node if k in db and not db[k]["active"]]   # ended, still on the node
    manual = [k for k in node if k not in db and k in labels]
    unknown = [k for k in node if k not in db and k not in labels]

    print(f"На сервере peers: {len(node)}   активных конфигов в базе: {len(active)}   совпадают: {len(ok)}\n")

    def section(title, keys, line):
        print(f"== {title}: {len(keys)}")
        for k in sorted(keys, key=lambda k: sort_ip((node.get(k) or db.get(k))["ip"])):
            print("   " + line(k))
        print()

    section("В базе активны, на сервере НЕТ (у клиента конфиг не работает)", missing,
            lambda k: f"{active[k]['ip']:<15} {active[k]['user']} · {active[k]['name']} ({active[k]['kind']})")
    section("Закончились в базе, но всё ещё на сервере (пользуются бесплатно)", stale,
            lambda k: f"{node[k]['ip']:<15} {db[k]['user']} · {db[k]['name']}  связь: {ago(node[k]['hs'], now)}")
    section("Ручные, с подписью в админке", manual,
            lambda k: f"{node[k]['ip']:<15} {labels[k]}  связь: {ago(node[k]['hs'], now)}")
    section("Неизвестные (нет в базе и без подписи)", unknown,
            lambda k: f"{node[k]['ip']:<15} {k[:8]}…  связь: {ago(node[k]['hs'], now)}")

    dup = [ip for ip, n in Counter(p["ip"] for p in node.values()).items() if n > 1]
    if dup:
        print(f"== Один адрес у нескольких peers: {', '.join(sorted(dup, key=sort_ip))}\n")

    for title, pool in (("Платный пул", PAID_POOL), ("Пробный пул", TRIAL_POOL)):
        size = pool[2] - pool[1] + 1
        taken = {p["ip"] for p in node.values() if in_pool(p["ip"], pool)}
        taken |= {v["ip"] for v in active.values() if in_pool(v["ip"], pool)}
        print(f"{title} {pool[0]}.{pool[1]}–{pool[2]}: занято {len(taken)} из {size}, свободно {size - len(taken)} "
              f"({len(taken) * 100 // size}%)")
    below = [p for p in node.values() if p["ip"].startswith(PAID_POOL[0] + ".") and not in_pool(p["ip"], PAID_POOL)]
    print(f"Ручные адреса {PAID_POOL[0]}.x вне пула: {len(below)}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
