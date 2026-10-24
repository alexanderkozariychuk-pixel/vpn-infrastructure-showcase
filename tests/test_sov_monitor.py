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


def test_a_hostname_of_digits_stays_a_name():
    # The exit node's hostname is all digits; it is a name, not a number.
    v = mon.parse_probe("host=833352\nfailed_unit_names=12\nuptime_s=60\n")
    assert v == {"host": "833352", "failed_unit_names": "12", "uptime_s": 60}


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


# ── clocks ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("now,skew", [(100.0, 0.0), (103.0, 0.0), (101.5, 0.0),   # inside the window
                                      (95.0, -5.0), (99.5, -0.5), (110.0, 7.0), ("x", None), (None, None)])
def test_clock_skew_counts_only_what_lies_outside_the_call(now, skew):
    assert mon.clock_skew(now, 100.0, 103.0) == skew


def test_a_slow_call_widens_the_window_and_never_alarms():
    # The probe read its clock 9 s after am1 started the call, the call took 12 s.
    assert mon.clock_skew(1009.0, 1000.0, 1012.0) == 0.0


def test_skews_go_into_remote_probes_only():
    probes = {"entry": {"clock_now": 110.0}, "exit": {"clock_now": 100.5}, "am1": {"clock_now": 500.0},
              "portal": None}
    windows = {n: (100.0, 101.0) for n in probes}
    mon.apply_clock_skews(probes, windows, {"am1"})
    assert probes["entry"]["clock_skew_s"] == 9.0 and probes["exit"]["clock_skew_s"] == 0.0
    assert "clock_skew_s" not in probes["am1"] and probes["portal"] is None


def test_am1_unsynchronised_is_no_reference():
    probes = {"entry": {"clock_now": 110.0}, "am1": {"clock_synced": 0}}
    mon.apply_clock_skews(probes, {"entry": (100.0, 101.0), "am1": (0, 0)}, {"am1"})
    assert "clock_skew_s" not in probes["entry"]


@pytest.mark.parametrize("change,text", [
    ({"clock_synced": 0}, "entry: часы не синхронизированы (NTP)"),
    ({"clock_synced": 1, "clock_skew_s": 7.4}, "entry: часы спешат на 7 с относительно am1"),
    ({"clock_skew_s": -3.0}, "entry: часы отстают на 3 с относительно am1"),
    ({"clock_skew_s": 2.0}, "entry: часы спешат на 2 с относительно am1"),
])
def test_clock_problems(change, text):
    p = mon.host_problems("entry", _section(), LIMITS, {**HEALTHY, **change}, "")
    assert p == {"entry:clock": text}
    assert mon.level("entry:clock") == "warn"


@pytest.mark.parametrize("change", [{}, {"clock_synced": 1}, {"clock_synced": 1, "clock_skew_s": 1.9},
                                    {"clock_skew_s": -1.9}, {"clock_skew_s": 0.0}])
def test_a_good_clock_or_an_old_probe_is_quiet(change):
    assert mon.host_problems("entry", _section(), LIMITS, {**HEALTHY, **change}, "") == {}


def _probe_with(tmp_path, tool, body):
    fake = tmp_path / tool
    fake.write_text("#!/bin/sh\n" + body)
    fake.chmod(0o755)
    src = (ROOT / "sov-probe").read_text().replace(
        "export LC_ALL=C PATH=/usr/local/sbin", f"export LC_ALL=C PATH={tmp_path}:/usr/local/sbin")
    script = tmp_path / "probe"
    script.write_text(src)
    out = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30)
    return out.stdout


@pytest.mark.skipif(not shutil.which("bash"), reason="no bash")
@pytest.mark.parametrize("answer,synced", [("yes", 1), ("no", 0), ("", None)])
def test_the_probe_reads_the_sync_flag(tmp_path, answer, synced):
    out = _probe_with(tmp_path, "timedatectl",
                      f'[ "$*" = "show -p NTPSynchronized --value" ] && echo "{answer}"\n')
    v = mon.parse_probe(out)
    assert v.get("clock_synced") == synced


@pytest.mark.skipif(not shutil.which("bash"), reason="no bash")
def test_the_probe_prints_its_clock_first(tmp_path):
    import time
    before = time.time()
    out = _probe_with(tmp_path, "timedatectl", "exit 1\n")
    after = time.time()
    assert out.splitlines()[0].startswith("clock_now=")
    v = mon.parse_probe(out)
    assert isinstance(v["clock_now"], float) and mon.clock_skew(v["clock_now"], before, after) == 0.0
    assert "clock_synced" not in v


def test_main_measures_the_clock_around_each_call(tmp_path, monkeypatch, capsys):
    import json
    import time
    ini = tmp_path / "monitor.ini"
    ini.write_text("[host:entry]\nssh = sovmon@entry\n[host:exit]\nssh = sovmon@exit\n"
                   "[host:am1]\nssh = local\n")
    monkeypatch.setattr(mon, "CONFIG", str(ini))
    monkeypatch.setattr(mon, "STATE", str(tmp_path / "state.json"))

    def fake(target, key, timeout=40):
        base = {**HEALTHY, "clock_synced": 1}
        if target == "local":
            return {**base, "clock_now": time.time()}, ""
        if target == "sovmon@exit":   # a slow call, a correct clock read at its very end
            time.sleep(0.3)
            return {**base, "clock_now": time.time()}, ""
        return {**base, "clock_now": time.time() + 30}, ""   # entry is 30 s ahead
    monkeypatch.setattr(mon, "run_probe", fake)
    monkeypatch.setattr("sys.argv", ["sov-monitor", "--dry-run"])
    assert mon.main() == 0
    report, _ = json.JSONDecoder().raw_decode(capsys.readouterr().out)
    assert 29 <= report["hosts"]["entry"]["clock_skew_s"] <= 30
    assert report["hosts"]["exit"]["clock_skew_s"] == 0.0
    assert "clock_skew_s" not in report["hosts"]["am1"]


# ── link port hops (infrastructure/link/sovrn-link-hop) ─────────────────

def test_a_link_hop_is_told_once_and_the_first_sight_only_records():
    msgs, st = mon.link_hops({}, {"entry-b": {"link_hop.hops": 2, "link_hop.port": 51861}}, 1000)
    assert msgs == [] and st["hops"] == {"entry-b": 2}
    msgs, st = mon.link_hops(st, {"entry-b": {"link_hop.hops": 2, "link_hop.port": 51861}}, 1120)
    assert msgs == []
    msgs, st = mon.link_hops(st, {"entry-b": {"link_hop.hops": 3, "link_hop.port": 51871, "link_hop.last": 1200}}, 1240)
    assert len(msgs) == 1 and "entry-b" in msgs[0] and "51871" in msgs[0]
    assert st["notices"] == [{"key": "entry-b:hop", "text": "entry-b: связка сменила порт на 51871", "at": 1200}]


def test_several_hops_between_runs_say_how_many():
    _, st = mon.link_hops({}, {"entry-b": {"link_hop.hops": 1}}, 0)
    msgs, _ = mon.link_hops(st, {"entry-b": {"link_hop.hops": 3, "link_hop.port": 51871}}, 120)
    assert "2 смены подряд" in msgs[0]


def test_hop_notices_join_reboot_notices_and_hosts_without_hops_are_ignored():
    _, st = mon.reboots({"boots": {"entry": 0}}, {"entry": {"uptime_s": 60}}, 100000)
    st["hops"] = {"entry-b": 1}
    msgs, st = mon.link_hops(st, {"entry": {"uptime_s": 60}, "exit": None,
                                  "entry-b": {"link_hop.hops": 2, "link_hop.port": 51861}}, 100000)
    assert [n["key"] for n in st["notices"]] == ["entry:reboot", "entry-b:hop"]
    assert "entry" not in st["hops"]


def test_the_probe_reads_the_hop_state(tmp_path):
    state = tmp_path / "link-hop.state"
    state.write_text("port=51861\nfrom=51851\nlast_hop=1800000000\nhops=4\n")
    env = {"PATH": "/usr/bin:/bin", "SOV_LINK_HOP_STATE": str(state)}
    out = subprocess.run(["bash", str(ROOT / "sov-probe")], capture_output=True, text=True, timeout=30, env=env)
    v = mon.parse_probe(out.stdout)
    assert (v["link_hop.port"], v["link_hop.hops"], v["link_hop.last"]) == (51861, 4, 1800000000)


# ── traffic ─────────────────────────────────────────────────────────────

def _t(rx, tx):
    return {"net.rx_bytes": rx, "net.tx_bytes": tx}


# 2026-10-24 12:00 MSK and the next day; the month turns on 2026-11-01.
D1 = 1792832400
D2 = D1 + 86400


def test_traffic_counts_from_the_first_sight_and_sums_in_and_out():
    rep, st = mon.traffic({}, {"exit-2": _t(1000, 2000)}, D1)
    assert rep["exit-2"]["day_bytes"] == 0 and rep["exit-2"]["since"] == D1
    rep, st = mon.traffic(st, {"exit-2": _t(1500, 2600)}, D1 + 120)
    assert rep["exit-2"] == {"day_bytes": 1100, "month_bytes": 1100, "since": D1}


def test_a_new_day_starts_the_day_and_keeps_the_month():
    _, st = mon.traffic({}, {"x": _t(0, 0)}, D1)
    _, st = mon.traffic(st, {"x": _t(100, 0)}, D1 + 60)
    rep, st = mon.traffic(st, {"x": _t(150, 0)}, D2)
    assert rep["x"]["day_bytes"] == 50 and rep["x"]["month_bytes"] == 150


def test_a_reboot_counts_everything_since_the_boot():
    _, st = mon.traffic({}, {"x": _t(10_000, 0)}, D1)
    rep, _ = mon.traffic(st, {"x": _t(300, 0)}, D1 + 60)
    assert rep["x"]["day_bytes"] == 300


def test_a_silent_host_keeps_its_numbers_and_an_old_probe_is_ignored():
    _, st = mon.traffic({}, {"x": _t(0, 0)}, D1)
    _, st = mon.traffic(st, {"x": _t(500, 0)}, D1 + 60)
    rep, st = mon.traffic(st, {"x": None, "old": {"uptime_s": 5}}, D1 + 120)
    assert rep == {"x": {"day_bytes": 500, "month_bytes": 500, "since": D1}}


def test_the_month_turns_over():
    nov = 1793480400   # 2026-11-01 00:00 MSK
    _, st = mon.traffic({}, {"x": _t(0, 0)}, nov - 120)
    _, st = mon.traffic(st, {"x": _t(700, 0)}, nov - 60)
    rep, _ = mon.traffic(st, {"x": _t(900, 0)}, nov + 60)
    assert rep["x"]["month_bytes"] == 200


def test_the_probe_prints_the_uplink_counters():
    out = subprocess.run(["bash", str(ROOT / "sov-probe")], capture_output=True, text=True, timeout=30)
    v = mon.parse_probe(out.stdout)
    if "net.if" in v:   # a sandbox may have no default route
        assert isinstance(v["net.rx_bytes"], int) and isinstance(v["net.tx_bytes"], int)
