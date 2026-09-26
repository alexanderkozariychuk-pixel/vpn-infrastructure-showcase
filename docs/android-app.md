# Android client — plan

Status: **stage 0 done (2026-09-26); stage 1 not started.** The plan below
was written before any code, so the first decisions were made deliberately
rather than by whatever the first tutorial happens to do. What the spike
measured is recorded under [Stage 0](#0-spike--one-weekend-before-committing-to-anything).

## Why

Today a customer pays, then installs a third-party app, then imports a file
into it. Three steps, two of which involve software we do not control and
cannot support. Every one of them loses people, and the cheapest plan is
350 ₽ — nobody perseveres through a setup that costs more attention than the
product costs money.

An app where the customer signs in and presses one switch removes both steps.
That is the whole case for building it. Not "everyone has an app".

## What already exists

The server needs **no changes** for the first version. The portal's own API
covers everything the app does:

| endpoint | what the app uses it for |
|---|---|
| `POST /api/auth/token` | sign in, returns a JWT |
| `GET /api/client/me` | subscription state, plan, expiry date |
| `GET /api/client/configs` | the customer's devices |
| `GET /api/client/configs/{id}/raw` | the `.conf` text for one device |
| `POST /api/client/configs` | add a device, within the plan's limit |
| `DELETE /api/client/configs/{id}` | remove one |

`_build_conf` emits an ordinary AmneziaWG configuration with the obfuscation
parameters inline (`Jc`, `Jmin`, `Jmax`, `S1`, `S2`, `H1`–`H4` — first
generation AWG, the widely supported one). So the app parses a file that
already exists rather than reimplementing anything.

This matters for scope: the work is an HTTP client, a tunnel library and
three screens. It is not a protocol project.

## What has to be settled before writing code

**The tunnel library, and its licence.** The candidates are Amnezia's own
`amneziawg-android` and the Maven artifact `com.zaneschepke:amneziawg-android`.
The core (`amneziawg-go`, a fork of wireguard-go) is permissively licensed,
but the *client* is not necessarily — and if the library is GPL, this app has
to be open source too.

That may well be fine: the repository is already public. But it is a decision
about the product, and it costs nothing to make now and a rewrite to discover
later. **Check the licence file in whatever is actually depended on, not the
project's README.**

**Whether the UI is native or a WebView.** Recommendation: native. The two
things the app exists for — the switch and the device list — are native
anyway, and a WebView adds a second place where a session lives. Payment
stays in the browser: it is a once-a-month action, the portal already does it
well, and keeping money out of the app avoids a category of store policy
questions if this ever reaches a store.

**Where the code lives.** Recommendation: this repository, under `android/`.
Existing CI lints `pwa/` and `monitoring/` and is unaffected. Keeping it here
means the portfolio shows a service and its client rather than two unrelated
things.

## Stages

### 0. Spike — one weekend, before committing to anything

Get a tunnel up on one phone, using a config pasted into the source. No
login, no UI beyond a button, no design, nothing to be proud of.

This answers the only question that matters at the start: can this be built
at all with these libraries, and how long does the real thing take? The
estimate that follows is then the builder's, measured, rather than a guess.

Done when: the phone's traffic goes through the node, verified by checking
the visible address, and the tunnel survives the screen locking.

If it does not come up in a weekend, stop and reconsider — that is what the
spike is for, and a lost weekend is the whole cost.

**Result (2026-09-25 → 26, Galaxy A71, Android 13): both criteria met.**
The phone's public address was the exit node's; handshake response arrived
65 ms after initiation. Unplugged and locked for 25 minutes, the tunnel was
alive on unlock — last handshake 32 s old, pages loading, nothing pressed.
One run, on Wi-Fi; overnight, mobile data and Wi-Fi ↔ LTE switching are
stage 1's to test.

What it settled, and what it found on the way:

- **Licence.** `tunnel/` Java is Apache-2.0 and the Go core (`amneziawg-go`)
  MIT, but the AAR also carries `libwg.so` and `libwg-quick.so`, built from
  GPL-2.0 `amneziawg-tools` — and only visible once submodules are cloned; the
  first count, without them, showed no GPL at all. They serve the root backend
  only. The app uses `GoBackend`, excludes both in `packaging.jniLibs`, and the
  built APK was checked to contain `libwg-go.so` alone. The app's own source
  can stay closed.
- **Distribution.** Amnezia publishes no Maven artifact, so the library is
  built from source (branch `sovrn-build` on top of upstream `ff15093b`) and
  the AAR is kept out of git; `app/libs/README.md` has the hash.
- **The upstream build shipped without its sleep fix.** `go.mod` requires Go
  1.25 while the Makefile fetched 1.24.2; with `GOTOOLCHAIN=auto`, Go silently
  downloaded 1.25 and compiled with that, so the boottime patch landed on a
  toolchain that compiled nothing. Found by reading the version string out of
  the built `.so`, not the build log — native build output never reaches it.
  Fixed in `sovrn-build` (`fba8e09c`), with `GOTOOLCHAIN=local` so it cannot
  recur quietly. Worth reporting upstream.
- **`INTERNET` must be declared by the app.** The library's manifest declares
  the VPN service only; without the permission the tunnel comes up and carries
  nothing, without an error.
- **`getLastHandshake()` is Unix time in seconds** — the docs say "seconds"
  and no more. It matched the handshake log line to the second.
- **Known, harmless:** `UAPIOpen: mkdir /var: read-only file system`. The UAPI
  socket is for the `wg` tool; `GoBackend` talks to the core over JNI. The
  Makefile's `-X …/amneziawg-go/ipc.socketDirectory` probably no longer
  matches the `/v3` module path, so the override is dropped silently.
- **Ten-minute setup traps, for the next machine:** Gradle's silent NDK
  download failed after 27 minutes with a corrupt archive (install NDK and
  CMake with `sdkmanager`, which shows progress); the repository must be cloned
  with `--recurse-submodules`; the distribution `adb` and the SDK's must not
  both be on `PATH` in the wrong order.

Time taken: about six hours on the first day, most of it toolchain and the
library build, and two and a half on the second for the app and the tests.

### 1. The minimum real app

Sign in → the app fetches the device list → picks one → fetches its `.conf`
→ starts the tunnel. One switch, one status line, sign out.

Done when: a person who has never seen it can install the APK, sign in with
their portal account and be connected, without being told anything.

### 2. What a subscriber actually needs

- Subscription state and expiry, read from `/api/client/me`, shown before it
  runs out rather than after.
- Devices: add and remove, within the plan's limit, using the endpoints that
  already exist.
- A useful failure message. "Не удалось подключиться" is not one — the
  journal's incidents are mostly mobile networks dropping handshakes, and the
  app knows things the customer does not.

### 3. Distribution

APK from the site, linked in the portal. No Google Play for the first
release: it adds review, a developer account and a policy surface, for an
audience that is not searching Play for this anyway.

Signing key: generated once, backed up somewhere it survives losing the
laptop. An Android app signed with a lost key cannot be updated — it can only
be replaced by a different app that every user must install by hand.

## Deliberately not in this plan

**iOS.** Apple's guideline 5.4 allows VPN apps only from accounts registered
as an organization; an individual developer account is refused at submission,
whatever the app does. That is a legal-entity problem, not a code problem,
and it does not become one until there is a legal entity.

**In-app payment.** See above.

**Anything requiring server changes.** Not because they are hard, but because
the point of starting now is that the site is frozen for payment moderation
and this work does not touch it.

## Honest estimate

Unknown, deliberately. The builder has not shipped Android before, and a
first project in an unfamiliar stack normally takes two to three times the
guess. An earlier estimate of "weeks of evenings" was made about the size of
the task rather than the size of the learning, and should not be trusted.

Stage 0 is scheduled in wall-clock time — one weekend — precisely because it
is the thing that replaces the guess with a measurement.

It did, partly. The spike fit inside the weekend, but it measured the part of
the work that is now finished: the toolchain, the library and its build.
Stage 1 is a different kind of work — sign-in, an HTTP client, storing a
config per customer instead of bundling one, the service's lifecycle — and
the spike says little about its pace beyond this: the library's API held no
surprises, and the first build of app code compiled unchanged.

## The risk worth naming

This is a fourth open front. The monitoring stack is still gone with
fra-aeza, five peers are still outside billing, and the payment rail is being
rebuilt. None of those are blocked by this, but none of them finish
themselves either.

The counter-argument is that the site cannot be touched for three to four
days anyway, and this is the one piece of work that needs nothing from the
server. That argument expires when moderation comes back.
