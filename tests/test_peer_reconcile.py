"""
tools/peer_reconcile.py: the sections, the key beginnings peer-remove.sh needs,
labels left without a peer, and the candidates file.
"""
import subprocess
import sys
import time
from pathlib import Path

TOOL = Path(__file__).parent.parent / "tools" / "peer_reconcile.py"

K_OK = "A" * 43 + "="          # portal, active, on the node
K_MISS = "B" * 43 + "="        # portal, active, not on the node
K_STALE = "C" * 43 + "="       # portal, ended, still on the node
K_HAND = "D" * 43 + "="        # hand-made, labelled
K_UNK = "E" * 43 + "="         # nobody's
K_GONE = "F" * 43 + "="        # labelled, no longer on the node
K_QUOTE = "G" * 43 + "="       # labelled, gone, a quote in the label


def _run(tmp_path, candidates=False):
    now = int(time.time())
    (tmp_path / "node.txt").write_text(
        f"{K_OK} 10.88.88.42/32 {now - 60}\n"
        f"{K_STALE} 10.88.88.43/32 {now - 3 * 86400}\n"
        f"{K_HAND} 10.88.88.20/32 0\n"
        f"{K_UNK} 10.88.88.201/32 {now - 40 * 86400}\n")
    (tmp_path / "db.txt").write_text(
        f"{K_OK}|10.88.88.42|t|paid|alice|phone\n"
        f"{K_MISS}|10.88.88.44|t|paid|bob|laptop\n"
        f"{K_STALE}|10.88.88.43|f|paid|carol|tablet\n")
    (tmp_path / "labels.txt").write_text(
        f"{K_HAND}|Мама, телефон\n{K_GONE}|старый роутер\n{K_QUOTE}|Dan's phone\n")
    args = [sys.executable, str(TOOL)] + [str(tmp_path / n) for n in ("node.txt", "db.txt", "labels.txt")]
    if candidates:
        args.append(str(tmp_path / "cand.txt"))
    p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _section(out, title):
    block = out.split("== " + title, 1)[1]
    return block.split("\n\n", 1)[0]


def test_every_peer_line_starts_with_address_and_key(tmp_path):
    out = _run(tmp_path)

    def row(ip, k8, rest):
        return f"   {ip:<15} {k8}  {rest}"
    assert row("10.88.88.44", "BBBBBBBB", "bob · laptop (paid)") in _section(out, "В базе активны")
    assert row("10.88.88.43", "CCCCCCCC", "carol · tablet  связь: 3 дн назад") in _section(out, "Закончились в базе")
    assert row("10.88.88.20", "DDDDDDDD", "Мама, телефон  связь: никогда") in _section(out, "Ручные")
    assert row("10.88.88.201", "EEEEEEEE", "связь: 40 дн назад") in _section(out, "Неизвестные")


def test_whole_keys_appear_only_in_the_delete_statement(tmp_path):
    out = _run(tmp_path)
    for k in (K_OK, K_MISS, K_STALE, K_HAND, K_UNK):
        assert k not in out


def test_labels_without_a_peer_and_how_to_remove_them(tmp_path):
    sec = _section(_run(tmp_path), "Подписи без пира на сервере")
    assert sec.startswith(": 2")
    assert "FFFFFFFF  старый роутер" in sec and "GGGGGGGG  Dan's phone" in sec
    assert "DDDDDDDD" not in sec
    assert f"DELETE FROM peer_labels WHERE public_key IN ('{K_GONE}', '{K_QUOTE}');" in sec


def test_no_orphan_labels_no_statement(tmp_path):
    _run(tmp_path)
    (tmp_path / "labels.txt").write_text(f"{K_HAND}|Мама\n")
    p = subprocess.run([sys.executable, str(TOOL)] + [str(tmp_path / n) for n in ("node.txt", "db.txt", "labels.txt")],
                       capture_output=True, text=True, timeout=30)
    assert "Подписи без пира на сервере: 0" in p.stdout and "DELETE" not in p.stdout


def test_candidates_are_the_three_groups_all_commented_out(tmp_path):
    out = _run(tmp_path, candidates=True)
    assert "Кандидаты записаны" in out and ": 3" in out.split("Кандидаты записаны", 1)[1]
    lines = (tmp_path / "cand.txt").read_text().splitlines()
    assert all(not ln or ln.startswith("#") for ln in lines)
    peers = [ln[2:] for ln in lines if ln.startswith("# 10.")]
    assert peers == [
        "10.88.88.43 CCCCCCCC закончились в базе | carol · tablet | связь: 3 дн назад",
        "10.88.88.20 DDDDDDDD ручные | Мама, телефон | связь: никогда",
        "10.88.88.201 EEEEEEEE неизвестные | | связь: 40 дн назад",
    ]
    # Neither the active peer nor the missing one is ever a candidate.
    assert "AAAAAAAA" not in "\n".join(lines) and "BBBBBBBB" not in "\n".join(lines)


def test_without_a_candidates_file_nothing_is_written(tmp_path):
    out = _run(tmp_path)
    assert "Кандидаты" not in out and not (tmp_path / "cand.txt").exists()
