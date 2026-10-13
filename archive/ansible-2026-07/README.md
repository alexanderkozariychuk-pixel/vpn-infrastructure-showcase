# Ansible, July 2026 — retired

The first configuration-as-code for the nodes, written for the Moldova and
Bulgaria relays and adapted to the RU entry in July. Replaced in October 2026
by `infrastructure/ansible/`, rewritten from `docs/entry-spec.md` rather than
patched, for these reasons:

- **It fought the firewall the nodes actually run.** `common` installed
  `iptables-persistent`, which removes `ufw` at the apt level, and the role
  said so in a comment and went without a firewall. Every production node
  runs ufw.
- **Key generation was not idempotent.** With no key in the inventory,
  `amneziawg` ran `awg genkey` on every play and printed the key into the
  log via `set_fact`. A run against a live entry with the variable unset
  would have replaced the server key and cut off every client.
- **It owned `awg0.conf` whole, peers included.** Peers added outside the
  inventory were erased by the template: 35 production peers were lost this
  way after a port change (journal, July). The portal now writes peers
  through `pwa-add-peer`, so a template that owns the peer list cannot exist.
- **SSH hardening was opt-in** (`-e ssh_hardening=true`); a plain run left
  root login and passwords as they were.
- **`host_key_checking = False`** in both `ansible.cfg` files: the first
  connection to a host trusted whatever answered.

Kept as a record, not as working code. Do not run it.
