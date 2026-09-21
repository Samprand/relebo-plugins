"""Lifecycle of an Inbox entry, as the engine names it (src/shared/enums/inbox/status.py)."""

from enum import Enum


class InboxStatusE(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    # The permission dialog was dismissed: closed without a decision, never a rejection.
    CANCELLED = "cancelled"
    ANSWERED = "answered"
    EXPIRED = "expired"
