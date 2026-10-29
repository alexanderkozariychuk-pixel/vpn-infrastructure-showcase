# Ansible — entry and exit nodes

Builds an entry node from `docs/entry-spec.md` and checks a running one
against it. Written in October 2026 for entry B; the July roles it replaces
are in `archive/ansible-2026-07/` with the reasons. Since 2026-10-24 it also
builds the exit of cluster 2 (exit-2: entry B's own exit, AmneziaWG 3.x).

```
ansible.cfg                  run from this directory
playbooks/entry.yml          common + entry, then read-only checks
playbooks/exit.yml           common + exit, then read-only checks
roles/common/                admin user, sshd, ufw, fail2ban, updates, swap, sov-probe
roles/amneziawg/             the Amnezia PPA (by fingerprint) and packages; used by both
roles/entry/                 awg0, link, split tunnel, trial subnet, wrappers
roles/exit/                  forwarding, one link interface per entry, NAT, BitTorrent block
inventory/hosts.yml.example  copy to hosts.yml (git-ignored)
inventory/group_vars/entry/  what every entry shares (port, obfuscation, subnets)
inventory/group_vars/exit/   ufw forward policy DROP
vault.yml.example            what an entry's vault holds; the vault itself lives outside the repo
vault-exit.yml.example       the same for an exit
```

## Two rules the roles are built around

**awg0.conf is written once and never again.** Its peers belong to the
portal (`pwa-add-peer`/`pwa-del-peer`). The role creates the file only when it
does not exist and only ever *starts* `awg-quick@awg0`, never restarts it. The
interface is then compared with what clients were issued — public key, port,
every obfuscation parameter — by reading the running interface
(`roles/entry/tasks/verify.yml`). A template that owned the file erased 35
peers in July.

**Entry A is not managed by Ansible at all.** It carries paying clients;
every change there is made by hand, one at a time, with a rollback ready. It
is not in the inventory, not even for `--check`: a check run still executes
read-only commands on the node and is one forgotten flag away from a real
one. B is compared with A by `tools/node-inventory.sh` (a diff of the two
reports), and what B does differently on purpose is listed in
`docs/entry-spec.md`. As a second fence the playbook refuses any non-check
run against a host in the `live` group, which is kept empty. The same holds
for the exit of cluster 1 (the one A uses).

**An exit's link files are the role's.** Unlike awg0 on an entry, a link
interface on an exit has a single peer, the entry, so `roles/exit` owns the
whole file and restarts a link whose file changed (only that one; a restart
drops that entry's clients for a second). The obfuscation is the same on both
ends of a link; the entry's end is in that entry's `entry_link`.

## Setup on the workstation

```bash
pipx install --include-deps ansible        # collections ansible.posix, community.general included
cd infrastructure/ansible
cp inventory/hosts.yml.example inventory/hosts.yml   # fill in; the play refuses example values
ansible-vault create ~/.sovereign/vault-b.yml        # keys as in vault.yml.example
```

The awg0 private key goes from A into the vault without passing through a
terminal or the chat (this reads one line on A; nothing on A changes):

```bash
ssh sov-entry 'sudo awk -F" = " "/^PrivateKey/{print \$2; exit}" /etc/amnezia/amneziawg/awg0.conf' \
  | { read -r k; printf 'entry_awg0_private_key: "%s"\n' "$k"; } \
  | ansible-vault encrypt --output ~/.sovereign/vault-b.yml   # then add the link keys with ansible-vault edit
```

## Building entry B

First run, as root (sovadmin does not exist yet), with the host key checked
against the provider's console beforehand:

```bash
ansible-playbook playbooks/entry.yml --limit entry-b -e ansible_user=root \
  -e @~/.sovereign/vault-b.yml --ask-vault-pass
```

Root login is switched off at the end of that run (after the role has
confirmed sovadmin's key is in place). Every run after it is as sovadmin. The
play ends with the findings; a real run with findings fails.

After the run that adds `entry_link`, the trial subnet comes up with its kill
switch **off**: the role does not manage `/etc/sovereign/trial.state`, and a
missing file means every trial packet is dropped (a handshake, no traffic).
Set it by hand to what entry A has:

```bash
S=$(ssh sov-entry 'cat /etc/sovereign/trial.state 2>/dev/null || echo off')
ssh sov-entry-b "sudo sovrn-trial-net $S && sudo sovrn-trial-net check"
```

## Building exit-2

exit-2 was first built by hand (2026-10-24); the role reproduces it. Its
host entry can sit in `inventory/hosts.yml` (as in the example) or in a file
of its own outside the repository, given as a second inventory:
`-i inventory/hosts.yml -i ~/.sovereign/inventory-exit2.yml` (shared vars
come from the first, `group_vars/exit` still applies). Its private key and PSK go from the node into the vault without passing through
a terminal or the chat:

```bash
ssh sov-exit2 'sudo awk -F" = " "/^PrivateKey/{k=\$2} /^PresharedKey/{p=\$2} END{print k; print p}" /etc/amnezia/amneziawg/awg0.conf' \
  | { read -r k; read -r p; printf 'exit_link_keys:\n  awg0:\n    private_key: "%s"\n    psk: "%s"\n' "$k" "$p"; } \
  | ansible-vault encrypt --output ~/.sovereign/vault-exit2.yml
```

Then a check run, read through before the real one:

```bash
ansible-playbook playbooks/exit.yml --limit exit-2 -e @~/.sovereign/vault-exit2.yml --ask-vault-pass --check --diff
ansible-playbook playbooks/exit.yml --limit exit-2 -e @~/.sovereign/vault-exit2.yml --ask-vault-pass
```

A second real run must report `changed=0`.

On entry B the end of this link (`awg3`) is still the hand-made file: B's
clients go out through `awg1` until awg0 on B is rebuilt for AmneziaWG 3.x.
At that switch `entry_link` moves to `awg3` and `awg1` is removed; until then
the role must not template `awg3`, because `link.conf.j2` also routes the
clients into the link.

## Link port hopping

The path between an entry and its exit has twice dropped one flow — one pair
of ports — while both ends were healthy (2026-10-23 and -24, two different
exits); another source port on the entry cured it each time. With
`entry_link.hop_ports` set, `sovrn-link-hop.timer` checks the link every
minute and, after `entry_link_hop_stale` seconds (180) without a handshake,
moves it to the next port in the list (`infrastructure/link/sovrn-link-hop`).
Only the running interface changes; the file keeps the inventory's port and
the link's PostUp restores the port in use from `/var/lib/sovrn/link-hop.state`,
so the role still owns the file and a reboot does not fall back to a blocked
port. The exit needs nothing: it accepts the entry from any port. sov-probe
reports the hops and sov-monitor sends one message per hop.

**Slow, not silent (2026-10-29).** The link kept its handshakes and lost no
pings, yet inside it answered in 88 ± 24 ms while the same path outside the
tunnel answered in 48 ± 4: a filter on the way was slowing down that one
long-lived UDP flow. On another source port it answered in 50 ± 3 at once.
So every check also pings the exit's end of the link and the exit's public
address together; inside worse by `entry_link_hop_slow_ms` (20) or losing
`entry_link_hop_slow_loss` % (5) more, `entry_link_hop_slow_runs` (3) checks in
a row, moves the link too — at most once per `entry_link_hop_slow_cooldown`
(30 min), so a path where every port is slow is not churned. If the exit's
public address does not answer ping, there is no comparison and only the
silence check works. `journalctl -t sovrn-link-hop` shows both numbers every
minute; the state file records why each hop happened (`why=silent|slow`).

## Tests

`tests/infrastructure/test_entry_verify.sh` runs the read-only checks against
stubbed commands: a correct entry must give no findings, and each of 28
single breakages must give exactly its own. `test_exit_verify.sh` does the
same for the exit (19 breakages), `test_sovrn_bt.sh` runs `sovrn-bt` against
a fake iptables. `ansible-lint` passes at the
`production` profile (`.ansible-lint` says which two rules are skipped and why).
