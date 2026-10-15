# Working on Sovereign

Rules for Claude sessions in this repository. They come from incidents and
decisions recorded in `PROJECT-JOURNAL.md`; the journal says why.

## Language and order of work
- Talk to Alexander in **Russian**, plainly, without needless jargon.
  `PROJECT-JOURNAL.md`, commit messages and code comments are in **English**.
- A session goes **analysis of the current state → plan → implementation**.
  Rebuild the state from `git log`, the journal and real command output, never
  from memory: work may have happened in sessions you were not part of.
- When Alexander reports a situation, answer or explain it and ask before
  building anything around it.

## Live nodes
- Entry A and the exit carry paying clients. **They are changed by hand only.
  Ansible never touches them, not even `--check`.** Ansible builds entry B only
  (`infrastructure/ansible/`, inventory with B alone, `live` group refused).
- Before any change on A or the exit: show the command, explain the way back,
  and measure before and after (handshake age, traffic counters over 10 s,
  count of the rules involved). Ask before running it.
- Changes on live nodes happen at night with minimal online unless Alexander
  decides otherwise for a specific, purely additive change.
- Never `git pull` on the portal. The portal is deployed **only with
  `./deploy.sh` from the workstation and only from `main`** (it rsyncs the
  working copy). No hot patches inside containers.
- Any firewall change voids a reboot-readiness check: run it again. "Works now"
  is not "survives a reboot".

## Secrets
- Keys, PSKs, tokens, `.env`, the Ansible vault: **never print them**. Cut them
  on the node itself (see `tools/node-inventory.sh`), move them server-to-server
  or through a pipe straight into `ansible-vault`, or read them with `read -s`.
- The vault lives outside the repository (`~/.sovereign/`). Backups of
  inventory files also go there, never next to the originals.

## The repository is public
- No IP addresses, hostnames of the nodes or secrets in tracked files. Name
  hosts by role: `<entry-A>`, `<entry-B>`, `<exit>`, `<portal>`, `<am1>`.
- On `main`, `infrastructure/ansible/inventory/hosts.yml` is **not** ignored:
  `git add` by file name only, never `git add -A` there.

## Git
- Commits carry Alexander as author:
  `--author="Alexander Kozariychuk <alexanderkozariychuk@gmail.com>"`,
  with a `Co-Authored-By:` trailer for Claude.
- Branch `cluster-b` holds the standby-cluster work (stage 4 next: the portal
  writes peers to both entries, `tools/peer_reconcile.py` against both). Merge
  `main` into it before stage 4. The journal is written in `cluster-b`.
- Do not commit half-done work. Push only after tests pass.
- Anything that depends on the branch must stop on the wrong branch, not just
  print it.

## Checks before a commit
- Shell: `shellcheck` with **both** 0.9.0 (what CI installs) and a current
  version — 0.9.0 is stricter on SC2015.
- Python: the tests under `tests/`; infrastructure checks:
  `tests/infrastructure/test_entry_verify.sh`.

## Pitfalls already paid for
- `sudo cmd < file`: the redirect runs without sudo. Pass the path as an
  argument or use `sudo tee`.
- Ubuntu's `awk` is mawk (no `asort`).
- Base64 keys contain `/` and `+`: never put them into `sed s///` or awk
  regexes, compare them as strings.
- `sudo -v` asks for a password even with NOPASSWD when the user is also in
  group `sudo`; check with `sudo -n true`.
- No `!` inside double quotes in commands typed into an interactive shell:
  `!!` expands to the previous command.
- `ssh.service` disabled on newer Ubuntu is normal: `ssh.socket` starts sshd.
- `journalctl` as the admin user shows nothing without `sudo`.
- sshd: check with `sshd -T`; whether root is really refused, only by trying.
- A script used as a check must end with `true`, or its last false test
  reads as a failure.

## Where things are
- `docs/entry-spec.md` — what an entry is, layer by layer; how B differs from A.
- `docs/runbook.md` — operations; §9 peers and the database, order of peer removal.
- `infrastructure/` — `ansible/` (roles for B), `wrappers/` (`pwa-*`),
  `trial/` (`sovrn-trial-net`, its kill switch is set by hand to match A),
  `monitoring/` (`sov-probe`, `sov_monitor.py`).
- `tools/` — `node-inventory.sh`, `awg-conf-check.sh`, `peer_reconcile.py`,
  `peer-remove.sh`, `dpi-test-node.sh`.
- `pwa/services/provisioner.py` — client config, address pools, how the portal
  talks to the entry.

## Permissions
`.claude/settings.json` starts sessions in Manual mode and makes every command
that reaches a node or publishes something ask first — even in auto mode:
`ssh`, `scp`, `rsync`, `sudo`, Ansible, `deploy.sh`, `git push`. It also keeps
Claude's file tools out of `~/.sovereign/` (vault, inventory backups), SSH
private keys and `.env` files. These rules match commands as written; they are
a fence, not a guarantee — still read every command that touches a node.
Commands that wait for a password (`--ask-vault-pass`, `sudo` on the
workstation, a key passphrase) cannot be answered by Claude: Alexander runs
those in his own terminal.
