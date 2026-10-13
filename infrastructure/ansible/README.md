# Ansible — entry nodes

Builds an entry node from `docs/entry-spec.md` and checks a running one
against it. Written in October 2026 for entry B; the July roles it replaces
are in `archive/ansible-2026-07/` with the reasons.

```
ansible.cfg                  run from this directory
playbooks/entry.yml          common + entry, then read-only checks
roles/common/                admin user, sshd, ufw, fail2ban, updates, swap, sov-probe
roles/entry/                 AmneziaWG, awg0, link, split tunnel, trial subnet, wrappers
inventory/hosts.yml.example  copy to hosts.yml (git-ignored)
inventory/group_vars/entry/  what every entry shares (port, obfuscation, subnets)
vault.yml.example            what the vault holds; the vault itself lives outside the repo
```

## Two rules the roles are built around

**awg0.conf is written once and never again.** Its peers belong to the
portal (`pwa-add-peer`/`pwa-del-peer`). The role creates the file only when it
does not exist and only ever *starts* `awg-quick@awg0`, never restarts it. The
interface is then compared with what clients were issued — public key, port,
every obfuscation parameter — by reading the running interface
(`roles/entry/tasks/verify.yml`). A template that owned the file erased 35
peers in July.

**Entry A is checked, never changed.** It is in the `live` group, and the
playbook refuses any run against a `live` host without `--check`. Changes on A
are made by hand, one at a time, as before.

## Setup on the workstation

```bash
pipx install --include-deps ansible        # collections ansible.posix, community.general included
cd infrastructure/ansible
cp inventory/hosts.yml.example inventory/hosts.yml   # fill in
ansible-vault create ~/.sovereign/vault-b.yml        # keys as in vault.yml.example
```

The awg0 private key goes from A into the vault without passing through a
terminal or the chat:

```bash
ssh sov-entry 'sudo awk -F" = " "/^PrivateKey/{print \$2; exit}" /etc/amnezia/amneziawg/awg0.conf' \
  | { read -r k; printf 'entry_awg0_private_key: "%s"\n' "$k"; } \
  | ansible-vault encrypt --output ~/.sovereign/vault-b.yml   # then add the link keys with ansible-vault edit
```

## Checking entry A

```bash
ansible-playbook playbooks/entry.yml --limit entry-a --check --diff --skip-tags keyfiles
```

Nothing on A changes. `--skip-tags keyfiles` leaves out the two files that
carry private keys, so no vault is needed. The commands that do run are
read-only: `modinfo`, `awg show` (cut before the first peer), `ip rule/route
show`, `ipset list -t`, `iptables -S`, `sysctl -n`, `systemctl is-active`,
`sshd -T`, `ufw status`.

What the diff and the findings should contain is listed in
`docs/entry-spec.md` ("Expected on a check run against A"). Anything else is
a defect in the roles or in the specification.

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

## Tests

`tests/infrastructure/test_entry_verify.sh` runs the read-only checks against
stubbed commands: a correct entry must give no findings, and each of 23
single breakages must give exactly its own. `ansible-lint` passes at the
`production` profile (`.ansible-lint` says which two rules are skipped and why).
