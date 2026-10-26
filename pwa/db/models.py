import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Boolean, DateTime, Integer, Text, UniqueConstraint, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # None for an account created from Telegram (api/telegram.py): there the
    # Telegram account stands where the confirmed mailbox does.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    peer_ip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    subscribed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Mailbox ownership. Set once a link from a letter sent to `email` has been
    # opened (or a password reset through it completed). Purchases need it.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SHA-256 of the current confirmation token; the letter carries the token.
    email_verify_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_verify_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Language the account was created in, so letters sent later — a payment
    # receipt from a gateway callback, with no browser behind it — match it.
    lang: Mapped[str] = mapped_column(String(2), default="ru", server_default="ru")
    # End of the free trial; set once, when the trial is granted, and never
    # cleared — a past date is how "already used" is told from "never had".
    trial_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The code from the referral link this account was registered through
    # (/?ref=CODE). Applied by itself to the first purchase only — see
    # credit.price_order — so a link nobody remembers to type still counts.
    referred_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # The customer's chat with the Telegram bot (services/telegram.py), once
    # they linked it from the account. Messages from the bell go there too.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    # SHA-256 of the one-time token in the t.me/<bot>?start= link, and its end.
    telegram_link_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_link_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    configs: Mapped[list["Config"]] = relationship("Config", back_populates="user")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user")


class Config(Base):
    __tablename__ = "configs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    peer_ip: Mapped[str] = mapped_column(String(20), nullable=False)
    # "paid" or "trial". A trial device lives in its own subnet (10.88.89.0/24)
    # under its own bandwidth ceiling, so it cannot simply become a paid one:
    # a purchase issues a paid device and removes the trial peer.
    kind: Mapped[str] = mapped_column(String(8), default="paid", server_default="paid")
    # Which entry the peer lives on: "de" (entry A) or "nl" (entry B), see
    # services/locations.py. Fixed for the device's life; the same address
    # may be held by one device in each location.
    location: Mapped[str] = mapped_column(String(8), default="de", server_default="de")
    private_key: Mapped[str] = mapped_column(String(255), nullable=False)
    public_key: Mapped[str] = mapped_column(String(255), nullable=False)
    preshared_key: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["User"] = relationship("User", back_populates="configs")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    # What we actually asked the customer for, after any discount and credit.
    # This — not the plan price — is what a gateway notification is verified
    # against: the plan price stops being the requested amount the moment a
    # discount exists, while this stays server-computed and never comes from
    # the request.
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="RUB")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    heleket_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Which gateway this payment belongs to ('platega' | 'heleket'; rows from
    # FreeKassa, removed 2026-09-29, carry none)
    # and that gateway's own transaction id. A callback carrying a transaction
    # id is matched to a payment by provider_ref; provider keeps two gateways'
    # ids from being confused. See migration d4f2a9c81e30.
    provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The promo code used, and how much credit the order intends to consume.
    # The credit is held here rather than deducted up front: an order that is
    # never paid must not spend anything, and a ledger entry written at
    # checkout would have to be chased back.
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credit_spent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="payments")


class PromoCode(Base):
    """
    A code that discounts a purchase, and optionally earns its owner credit.

    `owner_user_id` is what makes a code a referral rather than a campaign:
    a code with an owner pays that owner when someone else buys with it, and
    is refused when the owner tries to use it themselves.
    """
    __tablename__ = "promo_codes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Stored upper-case; lookups upper-case the input, so the customer can
    # type it however they like.
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    # A cap on how many paid orders may carry this code. Checked against a
    # count of those orders — there is deliberately no `uses` column, because
    # a counter has to be incremented by someone and the one place doing it
    # returned early for exactly the codes the cap was meant for.
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Why this code exists — which blogger, which mailing, which month. A code
    # with no record of its purpose is one nobody dares switch off.
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CreditEntry(Base):
    """
    One movement of account credit. Append-only.

    The balance is the sum of a customer's vested, unexpired entries — never a
    column on `users`. A stored number drifts from the events that produced it
    and cannot answer a customer asking why they have 350 rather than 525;
    a ledger answers that by construction, and at this scale summing costs
    nothing.

    `reason` is one of:
      referral_reward — someone bought with this customer's code
      spend           — consumed by an order
      expiry          — cancelled after six months
      adjustment      — done by hand, with a note saying why

    The unique constraint on (reason, source_payment_id) is what makes the
    reward idempotent. Gateway webhooks retry, and the database — not code
    that has to remember to check — is what guarantees a reward lands once.
    """
    __tablename__ = "credit_entries"
    __table_args__ = (
        UniqueConstraint("reason", "source_payment_id", name="uq_credit_reason_source"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    # Signed: positive earns, negative consumes. Points are whole rubles.
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    # The order this entry paid toward, for a spend.
    payment_id: Mapped[str | None] = mapped_column(String, ForeignKey("payments.id"), nullable=True)
    # The referred purchase that earned it, for a reward. Part of the
    # uniqueness that makes crediting idempotent.
    source_payment_id: Mapped[str | None] = mapped_column(String, ForeignKey("payments.id"), nullable=True)
    # Earned immediately, spendable later: a reward on a purchase that gets
    # refunded never vests, which is what stops a refund from leaving paid-out
    # credit behind.
    vests_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ReferralReward(Base):
    """
    Days of subscription earned by bringing a paying customer (since 2026-10-26;
    before that the reward was points, CreditEntry "referral_reward").

    Written when the referred purchase is paid, added to the referrer's
    subscription once it vests (`vests_at`) — the window a refund has to happen
    in for the reward never to land. `applied_at` is set when the days were
    added; a referrer with no live subscription at that moment keeps the reward
    until their next purchase, which picks it up.

    One per referred payment: the unique `source_payment_id` is what makes a
    retried gateway notification harmless.
    """
    __tablename__ = "referral_rewards"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    referrer_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    source_payment_id: Mapped[str] = mapped_column(String, ForeignKey("payments.id"), nullable=False, unique=True)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    vests_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TelegramSupport(Base):
    """
    A customer's message forwarded to the operator's chat: which chat it came
    from, so the operator's reply (a Telegram reply to that message) finds its
    way back. Nothing of the text is kept here.
    """
    __tablename__ = "telegram_support"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    user_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrialGrant(Base):
    """
    One free trial per mailbox, recorded for good.

    Keyed on the normalised address (services/trial.normalise_email), not the
    account: deleting an account and registering again with the same inbox —
    or the same Gmail with a dot moved — must not buy a second trial. The
    unique constraints are what make that hold under two requests at once.
    """
    __tablename__ = "trial_grants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email_norm: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # The Telegram account a trial went to — one trial per Telegram account,
    # as one per mailbox. Either may be empty, never both.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    # Nulled, not cascaded, when the account is deleted: the grant is about
    # the mailbox and must outlive the account.
    user_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """
    One message in a customer's in-portal feed (the bell).

    Text is stored rendered, in the language of the account at the time, so
    a message reads the same tomorrow as the day it was sent, whatever the
    templates have become since.

    `dedupe_key` makes a reminder idempotent: the hourly sweep may see the
    same subscription several times inside the window, and the unique
    (user_id, dedupe_key) is what keeps it to one message. The key carries
    the period's end date, so a renewed period gets its own reminders.
    Messages with no key (a payment, a broadcast) are never deduplicated.
    """
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    # A portal page to open from the message: "payment", "config", or none.
    link: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Set here, to the microsecond, rather than by the database: messages made
    # in one transaction (or one second, on SQLite) must still sort in order.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PeerLabel(Base):
    """
    The operator's name for a peer the portal did not issue — configs handed
    out by hand before the portal, the operator's own devices. Portal-issued
    peers are named from their configs row and never need one.

    Keyed by the full public key, which is what the node reports. A label
    outlives the peer on purpose: a removed peer's label costs nothing, and
    a re-added one comes back named.
    """
    __tablename__ = "peer_labels"

    public_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), server_default=func.now())


class MonitorReport(Base):
    """
    The latest report from sov-monitor on the backup host: one row, replaced
    every two minutes. The payload is the monitor's own JSON (probes, open
    problems, outside checks); services/monitor_view.py turns it into words.
    """
    __tablename__ = "monitor_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class MonitorEvent(Base):
    """
    What broke and when it was fixed, as the admin page's history. Opened when
    a report first carries a problem, closed by the first report without it.
    A one-off notice (a reboot) is born closed.
    """
    __tablename__ = "monitor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    text: Mapped[str] = mapped_column(String(300), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSession(Base):
    """
    A signed-in app: the long-lived half of the Android client's sign-in.

    The access token (JWT) lasts a day and is never stored server-side. The
    app also gets a random refresh token at sign-in and trades it for a new
    access token when the old one runs out (api/auth.py, /api/auth/refresh).
    Only its SHA-256 is kept here, so a database dump opens nothing.

    The expiry slides: each trade moves it APP_SESSION_DAYS ahead, so an app
    opened now and then is never asked to sign in again. A password reset
    removes every row of the account; signing out of the app removes its own.
    """
    __tablename__ = "app_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
