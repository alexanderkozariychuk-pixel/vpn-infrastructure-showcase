"""
services/trial.py — the free trial: who may have one, and what it is.

A trial is one device for TRIAL_DAYS, in the trial subnet (10.88.89.0/24),
which the entry node runs under a shared bandwidth ceiling and a kill switch
(infrastructure/trial). It is a sample of the product, not a second, free
product, so the rules below are about making it hard to take more than once:

  * a confirmed mailbox — the same gate as a purchase;
  * one trial per mailbox, for good: normalised, so "Ivan.Petrov+x@gmail.com"
    and "ivanpetrov@gmail.com" are one inbox, and recorded in trial_grants,
    which outlives the account;
  * no trial for anyone who has already paid;
  * no throwaway-mailbox domains;
  * per-address and per-day ceilings, so a burst of new accounts cannot take
    the whole trial pool;
  * TRIAL_ENABLED, so it can be switched off without a deploy — together with
    the node's own kill switch (sovrn-trial-net off) that stops new trials
    and cuts existing ones.
"""

import os
from datetime import datetime, timedelta, timezone

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "3"))
# Trials granted per rolling 24 hours, across everyone. The trial pool has
# ~240 addresses and the subnet one shared ceiling; this keeps a sudden wave
# (or a script that got past the other checks) from filling either.
TRIAL_DAILY_CAP = int(os.getenv("TRIAL_DAILY_CAP", "30"))


def trial_enabled() -> bool:
    return os.getenv("TRIAL_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")


# Providers that ignore dots in the local part. Only these: elsewhere a dot
# can be significant, and stripping it would merge two real people.
_DOTLESS = {"gmail.com", "googlemail.com"}
_ALIASES = {"googlemail.com": "gmail.com", "ya.ru": "yandex.ru"}

# Throwaway-mailbox services. A starting list, not a complete one — the
# per-mailbox, per-address and per-day limits are what carry the weight; this
# only takes away the cheapest way round them. Extend from the trial_grants
# table when a domain shows up there more than it should.
DISPOSABLE_DOMAINS = {
    "10minutemail.com", "10minutemail.net", "20minutemail.com", "byom.de",
    "discard.email", "dispostable.com", "dropmail.me", "emailondeck.com",
    "fakeinbox.com", "getairmail.com", "getnada.com", "guerrillamail.com",
    "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com",
    "inboxkitten.com", "mail.tm", "mailcatch.com", "maildrop.cc",
    "mailinator.com", "mailnesia.com", "mintemail.com", "mohmal.com",
    "mytemp.email", "nada.email", "sharklasers.com", "spamgourmet.com",
    "temp-mail.io", "temp-mail.org", "tempail.com", "tempmail.com",
    "tempmail.net", "tempmailo.com", "tempr.email", "throwawaymail.com",
    "trashmail.com", "trashmail.de", "yopmail.com", "yopmail.fr",
    "yopmail.net", "crazymailing.com", "emailfake.com", "1secmail.com",
    "1secmail.net", "1secmail.org", "internxt.com", "tmpmail.org",
}


def normalise_email(email: str) -> str:
    """
    One string per inbox, as far as can be told from the address.

    Lower-cased; "+tag" dropped (Gmail, Yandex, Mail.ru, Outlook and most
    others deliver it to the same box); dots dropped for Gmail only.
    """
    local, _, domain = email.strip().lower().rpartition("@")
    domain = _ALIASES.get(domain, domain)
    local = local.split("+", 1)[0]
    if domain in _DOTLESS:
        local = local.replace(".", "")
    return f"{local}@{domain}"


def is_disposable(email: str) -> bool:
    domain = email.strip().lower().rpartition("@")[2]
    return any(domain == d or domain.endswith("." + d) for d in DISPOSABLE_DOMAINS)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def trial_active(user, now: datetime | None = None) -> bool:
    until = _aware(user.trial_until)
    return until is not None and until > (now or datetime.now(timezone.utc))


def trial_state(user, *, has_paid: bool, now: datetime | None = None) -> str:
    """
    What the portal should offer, from the account alone:

      active        — a trial is running
      used          — had one, or has already paid
      needs_verify  — would be offered once the address is confirmed
      available     — can be started now
      off           — trials are switched off

    The checks that need the database or the request (the mailbox already
    used by another account, the daily ceiling, the source address) run when
    the trial is actually requested; a refusal there says why.
    """
    if trial_active(user, now):
        return "active"
    if user.trial_until is not None or has_paid:
        return "used"
    if not trial_enabled():
        return "off"
    if user.email_verified_at is None:
        return "needs_verify"
    return "available"


def trial_end(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) + timedelta(days=TRIAL_DAYS)
