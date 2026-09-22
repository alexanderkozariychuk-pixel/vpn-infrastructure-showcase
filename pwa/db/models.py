import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, UniqueConstraint, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db.base import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    peer_ip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    subscribed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    configs: Mapped[list["Config"]] = relationship("Config", back_populates="user")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user")


class Config(Base):
    __tablename__ = "configs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    peer_ip: Mapped[str] = mapped_column(String(20), nullable=False)
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
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
