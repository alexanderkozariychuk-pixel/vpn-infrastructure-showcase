"""
Signature verification for incoming payment notifications.

This is the boundary where an unauthenticated request becomes a paid
subscription, so the tests are written around what must be *rejected* rather
than around the happy path. Every case here is a way someone could try to
provision themselves for free.
"""

import hashlib

import pytest

from conftest import TEST_MERCHANT, TEST_SECRET_2


def test_valid_notification_is_accepted(fk, signed_notification):
    assert fk.verify_notification(signed_notification()) is True


def test_tampered_amount_is_rejected(fk, signed_notification):
    """Raising the amount after signing must invalidate the signature."""
    params = signed_notification(amount="300.00")
    params["AMOUNT"] = "1.00"
    assert fk.verify_notification(params) is False


def test_tampered_order_id_is_rejected(fk, signed_notification):
    """Pointing a valid signature at somebody else's order must fail."""
    params = signed_notification(order_id="order-1")
    params["MERCHANT_ORDER_ID"] = "order-2"
    assert fk.verify_notification(params) is False


def test_signature_from_a_different_secret_is_rejected(fk, signed_notification):
    """A correctly shaped signature made with the wrong key is still wrong."""
    params = signed_notification(secret="guessed-secret")
    assert fk.verify_notification(params) is False


def test_foreign_merchant_is_rejected(fk, signed_notification):
    """
    A notification signed correctly for another shop must not be honoured.
    The merchant check runs before the signature comparison, so this also
    covers the case where an attacker holds valid credentials of their own.
    """
    params = signed_notification(merchant="9999")
    assert fk.verify_notification(params) is False


@pytest.mark.parametrize("sign", ["", None])
def test_missing_signature_is_rejected(fk, signed_notification, sign):
    params = signed_notification()
    params["SIGN"] = sign
    assert fk.verify_notification(params) is False


def test_empty_payload_is_rejected(fk):
    assert fk.verify_notification({}) is False


def test_signature_comparison_is_case_insensitive(fk, signed_notification):
    """
    The gateway has sent uppercase hex in the past. Lowercasing before
    comparison is deliberate, not incidental — this pins that behaviour.
    """
    params = signed_notification()
    params["SIGN"] = params["SIGN"].upper()
    assert fk.verify_notification(params) is True


def test_amount_is_not_normalised_before_verifying(fk, signed_notification):
    """
    AMOUNT must be used exactly as received. If the implementation reformatted
    "300.0" to "300.00" before hashing, a genuine notification would fail.
    """
    params = signed_notification(amount="300.0")
    assert fk.verify_notification(params) is True


class TestPaymentUrl:
    def test_signature_matches_the_documented_formula(self, fk):
        """
        md5(merchant_id:amount:secret_word_1:currency:order_id), computed here
        rather than taken from the implementation.
        """
        from urllib.parse import parse_qs, urlparse

        url = fk.build_payment_url(order_id="abc", amount="300")
        query = parse_qs(urlparse(url).query)

        raw = f"{TEST_MERCHANT}:300:{fk.SECRET_1}:RUB:abc"
        expected = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()

        assert query["s"] == [expected]

    def test_amount_appears_verbatim(self, fk):
        """
        The amount in the URL and the amount in the signature must be the same
        string. Sending "300" while signing "300.00" fails at the gateway with
        no useful error, which is expensive to diagnose in production.
        """
        from urllib.parse import parse_qs, urlparse

        url = fk.build_payment_url(order_id="abc", amount="300.00")
        query = parse_qs(urlparse(url).query)
        assert query["oa"] == ["300.00"]

    def test_secret_never_appears_in_the_url(self, fk):
        url = fk.build_payment_url(order_id="abc", amount="300")
        assert fk.SECRET_1 not in url
        assert fk.SECRET_2 not in url
