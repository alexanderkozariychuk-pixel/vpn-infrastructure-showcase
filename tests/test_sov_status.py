"""
infrastructure/monitoring/sov_status.py: when a location counts as down or
back, what the channel reads, and how the tunnel is built — against a fake
runner, so nothing here touches a real network.
"""

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent / "infrastructure" / "monitoring"
_spec = importlib.util.spec_from_file_location("sov_status", ROOT / "sov_status.py")
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)

LOCS = [{"key": "nl", "name": "Нидерланды", "flag": "🇳🇱", "conf": "/x"},
        {"key": "de", "name": "Германия", "flag": "🇩🇪", "conf": "/y"}]
T0 = 1_793_000_000.0


def _run(state, results, down_after=3, up_after=2, t=T0):
    events = []
    for i, passed in enumerate(results):
        state, ev = st.step_location(state, passed, t + i * 120, down_after, up_after)
        state = st.record(state, passed, t + i * 120)
        events.append(ev)
    return state, events


def test_short_blips_post_nothing():
    s, ev = _run({}, [True, False, False, True, False, True])
    assert ev == [None] * 6 and s["status"] == "up"


def test_three_failures_make_it_down_once():
    s, ev = _run({}, [True, False, False, False, False, False])
    assert ev == [None, None, None, "down", None, None]
    assert s["status"] == "down"
    # Down since the first of the failures, not the third.
    assert s["down_since"] == T0 + 120


def test_back_after_two_good_runs_with_the_duration():
    s, ev = _run({}, [False, False, False, True, False, True, True])
    assert ev == [None, None, "down", None, None, None, "up"]
    assert s["status"] == "up"
    assert s["last_down_s"] == 6 * 120
    assert "Перебой длился 12 мин" in st.post_text("up", LOCS[0], [], s)


def test_maintenance_changes_nothing_and_is_left_out_of_uptime():
    s, ev = _run({}, [True, None, None, True])
    assert ev == [None] * 4 and s["maint"] is False
    assert st.uptime(s, T0 + 600) == 100.0
    s2, _ = _run({}, [None])
    assert s2["maint"] is True and st.uptime(s2, T0) is None


def test_uptime_over_thirty_days():
    s = {"days": {"2026-10-01": [700, 720], "2026-10-25": [720, 720], "2025-01-01": [0, 720]}}
    now = 1_793_000_000.0  # 2026-10-26
    v = st.uptime(s, now)
    assert round(v, 2) == round(100 * 1420 / 1440, 2)
    assert st.pct(v) == "98,61%"
    assert st.pct(100.0) == "100%" and st.pct(None) == "—"


def test_old_days_are_forgotten():
    s = st.record({"days": {"2025-01-01": [1, 1]}}, True, T0)
    assert "2025-01-01" not in s["days"]


def test_the_board_names_locations_only():
    states = {"nl": {"status": "up", "days": {}}, "de": {"status": "down", "days": {}}}
    text = st.board(LOCS, states, T0)
    assert "🟢 🇳🇱 Нидерланды — работает" in text
    assert "🔴 🇩🇪 Германия — перебои" in text
    assert "МСК" in text
    for word in ("exit", "entry", "awg", "10.", "am1", "сервер"):
        assert word not in text, word
    states["nl"]["maint"] = True
    assert "🔧 🇳🇱 Нидерланды — плановые работы" in st.board(LOCS, states, T0)


def test_a_down_post_points_to_the_other_location():
    text = st.post_text("down", LOCS[1], [LOCS[0]], {})
    assert text.startswith("🔴 🇩🇪 Германия") and "Нидерланды" in text


def test_parse_interface_reads_ipv4_and_mtu():
    addrs, mtu = st.parse_interface(
        "[Interface]\nPrivateKey = K\nAddress = 10.88.88.70/32, fd00::1/128\nMTU = 1280\n"
        "[Peer]\nAddress = 9.9.9.9/32\n")
    assert addrs == ["10.88.88.70/32"] and mtu == 1280


class FakeRunner:
    def __init__(self, fail=None, trace="ip=203.0.113.9\nloc=NL\n"):
        self.calls, self.fail, self.trace, self.ns = [], fail or set(), trace, set()

    def __call__(self, cmd, timeout=20, input_text=None):
        self.calls.append(cmd)
        out, rc = "", 0
        if cmd[:3] == ["ip", "netns", "list"]:
            out = "\n".join(self.ns)
        elif cmd[:3] == ["ip", "netns", "add"]:
            self.ns.add(cmd[3])
        elif cmd[:3] == ["ip", "netns", "del"]:
            self.ns.discard(cmd[3])
        elif cmd[:2] == ["awg-quick", "strip"]:
            out = "[Interface]\nPrivateKey = K\n[Peer]\nPublicKey = P\n"
        elif "curl" in cmd:
            out = self.trace
        if any(f in " ".join(cmd) for f in self.fail):
            rc = 1
        return subprocess.CompletedProcess(cmd, rc, out, "")


def test_the_tunnel_is_built_in_its_own_namespace(tmp_path, monkeypatch):
    monkeypatch.setattr(st.time, "sleep", lambda s: None)
    conf = tmp_path / "nl.conf"
    conf.write_text("[Interface]\nPrivateKey = K\nAddress = 10.88.88.70/32\nMTU = 1280\n[Peer]\nPublicKey = P\n")
    r = FakeRunner()
    ok, why = st.check_location("nl", str(conf), "https://1.1.1.1/cdn-cgi/trace", 5, "198.51.100.1", r)
    assert ok, why
    flat = [" ".join(c) for c in r.calls]
    # Made in the main namespace, then moved: its UDP socket stays outside.
    assert flat.index("ip link add dev sovst-nl type amneziawg") < flat.index("ip link set sovst-nl netns sovst-nl")
    assert "ip -n sovst-nl route add default dev sovst-nl" in flat
    assert "ip -n sovst-nl link set sovst-nl mtu 1280 up" in flat
    assert any(c[:4] == ["ip", "netns", "exec", "sovst-nl"] and "curl" in c for c in r.calls)


def test_an_answer_from_am1s_own_address_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(st.time, "sleep", lambda s: None)
    conf = tmp_path / "nl.conf"
    conf.write_text("[Interface]\nAddress = 10.88.88.70/32\n")
    r = FakeRunner(trace="ip=198.51.100.1\n")
    ok, why = st.check_location("nl", str(conf), "u", 5, "198.51.100.1", r)
    assert not ok and "own address" in why


def test_a_dead_tunnel_fails_after_one_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(st.time, "sleep", lambda s: None)
    conf = tmp_path / "nl.conf"
    conf.write_text("[Interface]\nAddress = 10.88.88.70/32\n")
    r = FakeRunner(fail={"curl"})
    ok, _ = st.check_location("nl", str(conf), "u", 5, None, r)
    assert not ok
    assert sum(1 for c in r.calls if c[:3] == ["ip", "netns", "add"]) == 2


class FakeTG:
    def __init__(self, send_ok=True, edit="ok"):
        self.sent, self.edited, self.pinned = [], [], []
        self.send_ok, self.edit_result, self.next = send_ok, edit, 100

    def send(self, text, silent=False):
        if not self.send_ok:
            return None
        self.next += 1
        self.sent.append((self.next, text, silent))
        return self.next

    def edit(self, mid, text):
        self.edited.append((mid, text))
        return self.edit_result

    def pin(self, mid):
        self.pinned.append(mid)
        return True


def test_the_first_run_posts_and_pins_the_board_silently():
    tg = FakeTG()
    s = st.publish(tg, {}, "board", [])
    assert s["board_id"] == 101 and tg.pinned == [101] and tg.sent[0][2] is True


def test_later_runs_edit_it_in_place():
    tg = FakeTG()
    s = st.publish(tg, {"board_id": 55}, "board", [])
    assert tg.edited == [(55, "board")] and tg.sent == [] and s["board_id"] == 55


def test_a_deleted_board_is_posted_again():
    tg = FakeTG(edit="gone")
    s = st.publish(tg, {"board_id": 55}, "board", [])
    assert s["board_id"] == 101 and tg.pinned == [101]


def test_posts_that_could_not_be_sent_wait_for_the_next_run():
    tg = FakeTG(send_ok=False)
    s = st.publish(tg, {"board_id": 55}, "board", ["🔴 a", "🟢 b"])
    assert s["pending"] == ["🔴 a", "🟢 b"]
    tg2 = FakeTG()
    s = st.publish(tg2, s, "board", [])
    assert [t for _, t, _ in tg2.sent] == ["🔴 a", "🟢 b"] and s["pending"] == []


def test_a_board_the_bot_cannot_edit_is_not_posted_again_and_again():
    """2026-10-26: "can't be edited" was taken for "deleted" — a new pinned board every run."""
    tg = FakeTG(edit="error")
    s = {"board_id": 55}
    for i in range(10):
        s = st.publish(tg, s, "board", [], now=T0 + i * 120)
    assert tg.sent == [] and tg.pinned == [] and s["board_id"] == 55


def test_even_a_deleted_board_is_reposted_at_most_every_six_hours():
    tg = FakeTG(edit="gone")
    s = {"board_id": 55}
    for i in range(10):
        s = st.publish(tg, s, "board", [], now=T0 + i * 120)
    assert len(tg.sent) == 1
    s = st.publish(tg, s, "board", [], now=T0 + 7 * 3600)
    assert len(tg.sent) == 2


def test_cant_be_edited_is_an_error_not_gone(monkeypatch):
    t = st.Telegram("x", "@c")
    monkeypatch.setattr(t, "call", lambda *a, **k: {"ok": False, "description": "Bad Request: message can't be edited"})
    assert t.edit(1, "x") == "error"
    monkeypatch.setattr(t, "call", lambda *a, **k: {"ok": False, "description": "Bad Request: message to edit not found"})
    assert t.edit(1, "x") == "gone"
