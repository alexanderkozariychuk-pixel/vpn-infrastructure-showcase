"""
api/support.py — support ticket submission.

Receives a structured support request from the portal form and emails it
to the support inbox. No auth required (users may be logged out / pre-sub).
"""
import os
import logging

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from services.mailer import send_email, support_ticket_email

logger = logging.getLogger(__name__)
router = APIRouter()

SUPPORT_INBOX = os.getenv("SUPPORT_INBOX", "sovrn.support@gmail.com")

# human-readable category labels
CATEGORY_LABELS = {
    "no_connect": "VPN won't connect in AmneziaWG",
    "slow": "App or resource not loading / slow",
    "conf_file": "Can't import .conf file in AmneziaWG",
    "other": "Other issue",
}


class SupportTicket(BaseModel):
    issue_type: str
    os: str | None = None
    service: str | None = None
    details: str | None = None
    email: EmailStr


@router.post("/api/support/ticket")
async def submit_ticket(ticket: SupportTicket):
    """
    Accept a support ticket and email it to the support inbox.
    Always returns ok — the user's success screen shouldn't depend on
    mail delivery, and we don't want to leak internal failures.
    """
    category = CATEGORY_LABELS.get(ticket.issue_type, ticket.issue_type)

    details = {
        "Operating system": ticket.os,
        "Service": ticket.service,
        "Description": ticket.details,
    }
    # drop empty fields
    details = {k: v for k, v in details.items() if v}

    try:
        subject, html, text = support_ticket_email(category, details, ticket.email)
        await send_email(SUPPORT_INBOX, subject, html, text)
    except Exception as e:
        logger.error("Support ticket email failed (from %s): %s", ticket.email, e)

    return {"ok": True, "message": "Ticket received"}
