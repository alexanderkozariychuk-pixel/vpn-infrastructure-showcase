"""
infrastructure/monitoring: what the probe prints, how the monitor judges it,
and when it speaks (first sight, reminder, all clear) — and when it stays quiet.
"""

import configparser
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent / "infrastructure" / "monitoring"
_spec = importlib.util.spec_from_file_location("sov_monitor", ROOT / "sov_monitor.py")
mon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mon)

LIMITS = dict(mon.DEFAULT_LIMITS)


def _section(**kw):
    cfg = configparser.ConfigParser()
    cfg["host:x"] = kw
    return cfg["host:x"]


HEALTHY = {"host": "entry", "load1": 0.3, "ncpu": 2, "mem_avail_pct": 60, "disk_root_pct": 40,
           "uptime_s": 86400, "failed_units": 0, "awg.awg0.peers": 18, "awg.awg0.fresh": 5,
           "awg.awg1.peers": 1, "awg.awg1.fresh": 40}


def test_parse_probe_types_and_junk():
    v = mon.parse_probe("host=entry\nload1=0.25\ndisk_root_pct=40\nnoise\n=x\nfailed_unit_names=a,b\n")
    assert v == {"host": "entry", "load1": 0.25, "disk_root_pct": 40, "failed_unit_names": "a,b"}


def test_a_healthy_host_has_no_problems():
    assert mon.host_problems("entry", _section(links="awg1", clients="awg0"), LIMITS, HEALTHY, "") == {}


def test_an_unreachable_host_is_one_problem():
    assert list(mon.host_problems("exit", _section(), LIMITS, None, "timeout")) == ["exit:down"]


@pytest.mark.parametrize("change,key", [
    ({"disk_root_pct": 91}, "entry:disk"),
    ({"mem_avail_pct": 4}, "entry:mem"),
    ({"load1": 4.5}, "entry:load"),
    ({"failed_units": 1, "failed_unit_names": "awg-quick@awg1.service"}, "entry:units"),
    ({"awg.awg1.fresh": 900}, "entry:link:awg1"),
    ({"awg.awg1.fresh": -1}, "entry:link:awg1"),
])
def test_each_limit(change, key):
    p = mon.host_problems("entry", _section(links="awg1"), LIMITS, {**HEALTHY, **change}, "")
    assert list(p) == [key]


def test_a_missing_link_interface_is_reported():
    probe = {k: v for k, v in HEALTHY.items() if not k.startswith("awg.awg1")}
    assert "entry:link:awg1" in mon.host_problems("entry", _section(links="awg1"), LIMITS, probe, "")


def test_portal_jobs():
    sec = _section(backup_max_h="26", expiry_max_h="2")
    ok = {**HEALTHY, "backup_age": 3600, "expiry_age": 600, "expiry_failures": 0,
          "containers_expected": 2, "containers_up": 2}
    assert mon.host_problems("portal", sec, LIMITS, ok, "") == {}
    bad = {**ok, "backup_age": 30 * 3600, "expiry_failures": 3, "containers_up": 1}
    assert set(mon.host_problems("portal", sec, LIMITS, bad, "")) == {
        "portal:backup", "portal:expiry_fail", "portal:containers"}
    # The probe printed nothing about the dump at all: that is a problem too.
    gone = {k: v for k, v in ok.items() if k != "backup_age"}
    assert "portal:backup" in mon.host_problems("portal", sec, LIMITS, gone, "")
    late = {**ok, "expiry_age": 3 * 3600}
    assert "portal:expiry" in mon.host_problems("portal", sec, LIMITS, late, "")


# ── when it speaks ──────────────────────────────────────────────────────

P = {"exit:down": "exit: не отвечает"}


def test_one_bad_run_stays_quiet_the_second_alerts():
    msgs, st = mon.step({}, P, 0, confirm=2, remind_s=6 * 3600)
    assert msgs == []
    msgs, st = mon.step(st, P, 120, 2, 6 * 3600)
    assert msgs == ["🔴 exit: не отвечает"]


def test_a_blip_that_clears_says_nothing():
    _, st = mon.step({}, P, 0, 2, 3600)
    msgs, st = mon.step(st, {}, 120, 2, 3600)
    assert msgs == [] and st["problems"] == {}


def test_no_repeat_until_the_reminder_then_all_clear():
    st = {}
    for t in (0, 120):
        _, st = mon.step(st, P, t, 2, 3600)
    msgs, st = mon.step(st, P, 240, 2, 3600)
    assert msgs == []
    msgs, st = mon.step(st, P, 120 + 3600, 2, 3600)
    assert msgs == ["🔴 exit: не отвечает (всё ещё, 1 ч 2 мин)"]
    msgs, st = mon.step(st, {}, 120 + 3720, 2, 3600)
    assert msgs == ["✅ exit: не отвечает — прошло (1 ч 4 мин)"]


def test_a_reboot_is_told_once():
    probes = {"entry": {"uptime_s": 86400}}
    msgs, st = mon.reboots({}, probes, 100000)
    assert msgs == []
    msgs, st = mon.reboots(st, {"entry": {"uptime_s": 86520}}, 100120)
    assert msgs == []
    msgs, st = mon.reboots(st, {"entry": {"uptime_s": 60}}, 100240)
    assert msgs == ["ℹ️ entry: перезагрузился 1 мин назад"]


def test_digest_mentions_every_host():
    text = mon.digest({"entry": HEALTHY, "exit": None}, {}, 0)
    assert "entry: диск 40%" in text and "пиров 19" in text and "exit: не отвечает" in text


# ── the probe itself ────────────────────────────────────────────────────

@pytest.mark.skipif(not shutil.which("bash"), reason="no bash")
def test_the_probe_runs_anywhere_and_prints_the_basics():
    out = subprocess.run(["bash", str(ROOT / "sov-probe")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    v = mon.parse_probe(out.stdout)
    for key in ("host", "load1", "ncpu", "mem_avail_pct", "disk_root_pct", "uptime_s", "failed_units"):
        assert key in v, key


# ── the report for the admin panel ──────────────────────────────────────

@pytest.mark.parametrize("key,lvl", [("entry:disk", "warn"), ("entry:units", "warn"), ("cert:x", "warn"),
                                     ("exit:down", "bad"), ("entry:link:awg1", "bad"), ("web:u", "bad"),
                                     ("portal:backup", "bad")])
def test_levels(key, lvl):
    assert mon.level(key) == lvl


def test_the_report_carries_only_confirmed_problems_and_the_layout():
    cfg = configparser.ConfigParser()
    cfg.read_string("[host:entry]\nssh = x\nlinks = awg1\nclients = awg0\n[host:am1]\nssh = local\n")
    st = {}
    _, st = mon.step(st, {"exit:down": "exit: не отвечает"}, 0, 2, 3600)
    r = mon.build_report(cfg, {"entry": HEALTHY, "am1": None}, {"am1": "x"}, {}, st, 0, 2)
    assert r["problems"] == [] and r["links"] == {"entry": ["awg1"]} and r["clients"] == {"entry": ["awg0"]}
    _, st = mon.step(st, {"exit:down": "exit: не отвечает"}, 120, 2, 3600)
    r = mon.build_report(cfg, {}, {}, {}, st, 120, 2)
    assert r["problems"] == [{"key": "exit:down", "text": "exit: не отвечает", "level": "bad", "since": 0}]


def test_the_report_matches_what_the_portal_accepts():
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "pwa"))
    from api.monitor import Report
    cfg = configparser.ConfigParser()
    cfg.read_string("[host:entry]\nssh = x\nlinks = awg1\n")
    _, st = mon.reboots({"boots": {"entry": 0}}, {"entry": {"uptime_s": 60}}, 100000)
    for t in (0, 120):
        _, st = mon.step(st, {"entry:disk": "entry: диск"}, t, 2, 3600)
    Report(**mon.build_report(cfg, {"entry": HEALTHY}, {}, {"urls": {}, "certs": {}}, st, 120, 2))


def test_without_telegram_set_up_the_monitor_still_runs():
    cfg = configparser.ConfigParser()
    assert mon.send_telegram(cfg, "x") is True and mon.send_report(cfg, {}) is True


# ── address pools ───────────────────────────────────────────────────────

POOLS = "paid:10.88.88.42-199, trial:10.88.89.10-250"


def _entry(ips):
    return {**HEALTHY, "awg.awg0.ips": ",".join(ips)}


def test_parse_pools_skips_junk():
    assert mon.parse_pools(POOLS + ", nonsense, x:1.2.3-4") == [
        ("paid", "10.88.88", 42, 199), ("trial", "10.88.89", 10, 250)]


def test_pool_usage_counts_only_addresses_inside_the_pool():
    ips = ["10.88.88.2", "10.88.88.41", "10.88.88.42", "10.88.88.199", "10.88.88.200", "10.88.89.12"]
    use = mon.pool_usage(_section(clients="awg0", pools=POOLS), _entry(ips))
    assert use == [{"label": "paid", "range": "10.88.88.42-199", "used": 2, "size": 158, "pct": 1},
                   {"label": "trial", "range": "10.88.89.10-250", "used": 1, "size": 241, "pct": 0}]


def test_a_filling_pool_warns_then_alarms():
    sec = _section(clients="awg0", pools="paid:10.88.88.42-199")
    ips = lambda n: [f"10.88.88.{42 + i}" for i in range(n)]  # noqa: E731
    assert mon.host_problems("entry", sec, LIMITS, _entry(ips(110)), "") == {}          # 69%
    p = mon.host_problems("entry", sec, LIMITS, _entry(ips(111)), "")                   # 70%
    assert list(p) == ["entry:pool:paid"] and "111 из 158" in p["entry:pool:paid"]
    assert mon.level("entry:pool:paid") == "warn"
    p = mon.host_problems("entry", sec, LIMITS, _entry(ips(151)), "")                   # 95%
    assert list(p) == ["entry:poolfull:paid"] and mon.level("entry:poolfull:paid") == "bad"


def test_the_report_carries_pool_usage():
    cfg = configparser.ConfigParser()
    cfg.read_string(f"[host:entry]\nssh = x\nclients = awg0\npools = {POOLS}\n[host:exit]\nssh = y\n")
    r = mon.build_report(cfg, {"entry": _entry(["10.88.88.50"]), "exit": HEALTHY}, {}, {}, {}, 0, 2)
    assert list(r["pools"]) == ["entry"] and r["pools"]["entry"][0]["used"] == 1


@pytest.mark.skipif(not shutil.which("bash"), reason="no bash")
def test_the_probe_lists_peer_addresses(tmp_path):
    fake = tmp_path / "awg"
    fake.write_text("#!/bin/sh\ncase \"$*\" in\n"
                    "  'show interfaces') echo awg0 ;;\n"
                    "  'show all latest-handshakes') printf 'awg0\\tK1\\t0\\nawg0\\tK2\\t0\\n' ;;\n"
                    "  'show all allowed-ips') printf 'awg0\\tK1\\t10.88.88.42/32\\nawg0\\tK2\\t10.88.88.7/32 10.9.9.9/32\\n' ;;\n"
                    "esac\n")
    fake.chmod(0o755)
    src = (ROOT / "sov-probe").read_text().replace(
        "export LC_ALL=C PATH=/usr/local/sbin", f"export LC_ALL=C PATH={tmp_path}:/usr/local/sbin")
    script = tmp_path / "probe"
    script.write_text(src)
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30)
    v = mon.parse_probe(out.stdout)
    assert v["awg.awg0.ips"] == "10.88.88.42,10.88.88.7" and v["awg.awg0.peers"] == 2
