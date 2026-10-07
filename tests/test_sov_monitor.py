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
