# Node-side wrappers

The portal never holds a personal SSH key and never runs `awg`, `cat` or
`journalctl` directly. It authenticates to the entry node as the restricted
`pwa-provisioner` user, whose `sudoers` entry permits these wrappers and
nothing else. Each wrapper re-validates its arguments server-side: the caller
is a web application, and its checks are a convenience rather than a boundary.

The wrapper approach was forced by a newer `sudo` on one node rejecting
wildcards in command arguments — which turned out to be closing a real hole
that an older `sudo` on another node had silently accepted.

| Wrapper | Purpose | Validates |
|---|---|---|
| `pwa-add-peer` | add a client peer | key format, `/32` inside the client subnet, duplicate key, duplicate IP |
| `pwa-del-peer` | remove a client peer | key format, peer exists, allowed-ips inside the client subnet |
| `pwa-awg-show` | read tunnel state | read-only |
| `pwa-logs` | read service logs | read-only |

Only `pwa-del-peer` is currently version-controlled here. The other three live
on the nodes and should be brought into this directory — production code that
exists in exactly one place, with no history, is one bad edit from being gone.

## Installing

```bash
sudo install -o root -g root -m 0755 pwa-del-peer /usr/local/bin/pwa-del-peer
```

Then extend the existing sudoers entry — as a drop-in, validated before it is
put in place, because a malformed sudoers file locks out sudo entirely:

```bash
sudo visudo -c -f /etc/sudoers.d/pwa-provisioner   # check before, and again after
```

```
pwa-provisioner ALL=(root) NOPASSWD: /usr/local/bin/pwa-del-peer
```

## Verifying, before the portal depends on it

Both directions, on the node, against a peer you created for the purpose —
never against a live client:

```bash
# a peer that does not exist: must refuse, exit non-zero
sudo pwa-del-peer AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=

# a malformed key: must refuse before touching anything
sudo pwa-del-peer 'not-a-key'

# the real thing: peer count in the config drops by exactly one,
# and the peer is gone from the runtime as well
grep -c '^\[Peer\]' /etc/amnezia/amneziawg/awg0.conf
sudo awg show awg0 peers | wc -l
sudo pwa-del-peer <public-key-of-the-test-peer>
grep -c '^\[Peer\]' /etc/amnezia/amneziawg/awg0.conf
sudo awg show awg0 peers | wc -l
```

The config is edited before the runtime on purpose. A failed edit leaves a
working tunnel and loses nothing; the reverse order would drop a paying
customer and leave the peer in the file to return on the next reboot — the
runtime-only failure mode that cost four incidents in June.

A timestamped backup of the config is written next to it on every successful
removal.
