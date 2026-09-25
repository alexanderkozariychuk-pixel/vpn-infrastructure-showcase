# Android client — plan

Status: **not started.** This is the plan, written before any code, so the
first decisions are made deliberately rather than by whatever the first
tutorial happens to do.

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

## The risk worth naming

This is a fourth open front. The monitoring stack is still gone with
fra-aeza, five peers are still outside billing, and the payment rail is being
rebuilt. None of those are blocked by this, but none of them finish
themselves either.

The counter-argument is that the site cannot be touched for three to four
days anyway, and this is the one piece of work that needs nothing from the
server. That argument expires when moderation comes back.
