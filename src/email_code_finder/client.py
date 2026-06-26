"""IMAP client used to search and read one-time authentication codes.

This module intentionally avoids any destructive mailbox operation. Messages
are never deleted; once a code is extracted the message is only flagged as
``\\Seen`` (read), so the user keeps a record of the email.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import ssl
from email.message import Message
from typing import List, Optional

log = logging.getLogger(__name__)

# Default IMAP host/port for the most common providers. Any provider not listed
# here falls back to ``imap.<domain>`` derived from the user's email address.
DEFAULT_IMAP_PORT = 993
KNOWN_IMAP_SERVERS = {
    "gmail": "imap.gmail.com",
    "outlook": "outlook.office365.com",
    "office365": "outlook.office365.com",
    "yahoo": "imap.mail.yahoo.com",
    "icloud": "imap.mail.me.com",
    "kinghost": "imap.kinghost.net",
}


class ImapEmailClient:
    """Thin wrapper around :mod:`imaplib` for reading authentication codes.

    Args:
        user_email: Full email address used to authenticate.
        password: Account or app-specific password. Prefer app passwords; see
            the security notes in the project README.
        provider: Optional provider key (``gmail``, ``outlook``, ``yahoo``,
            ``icloud``, ...). When omitted or unknown, the IMAP host is derived
            from the email domain as ``imap.<domain>``.
        imap_server: Explicit IMAP host. Overrides ``provider`` detection.
        port: IMAP-over-SSL port. Defaults to 993.
    """

    def __init__(
        self,
        user_email: str,
        password: str,
        provider: Optional[str] = None,
        imap_server: Optional[str] = None,
        port: int = DEFAULT_IMAP_PORT,
    ) -> None:
        self.user_email = user_email
        self.password = password
        self.provider = provider.lower() if provider else None
        self.port = port
        self.imap_server = imap_server or self._resolve_imap_server()
        self.mail: Optional[imaplib.IMAP4_SSL] = None

    def _resolve_imap_server(self) -> str:
        """Return the IMAP host for the configured provider/email domain."""
        if self.provider and self.provider in KNOWN_IMAP_SERVERS:
            return KNOWN_IMAP_SERVERS[self.provider]
        try:
            domain = self.user_email.split("@", 1)[1].lower()
        except IndexError as exc:
            raise ValueError(
                f"Invalid email address, missing domain: {self.user_email!r}"
            ) from exc
        return f"imap.{domain}"

    def connect(self) -> None:
        """Open an authenticated IMAP-over-SSL session and select the inbox."""
        context = ssl.create_default_context()
        self.mail = imaplib.IMAP4_SSL(self.imap_server, self.port, ssl_context=context)
        self.mail.login(self.user_email, self.password)
        # readonly=False is required so processed messages can be flagged \Seen.
        self.mail.select("INBOX", readonly=False)

    def get_max_uid(self) -> int:
        """Return the highest UID currently in the inbox (0 if empty).

        Used as a baseline: only messages with a UID greater than this value are
        considered "new", so codes received before the wait started are ignored.
        """
        self._require_connection()
        status, data = self.mail.uid("SEARCH", None, "ALL")
        if status != "OK":
            raise RuntimeError(f"Failed to read inbox baseline: {status}")
        uids = data[0].split()
        return max((int(uid) for uid in uids), default=0)

    def search_unread_by_subject(self, subject: str) -> List[bytes]:
        """Return UIDs of unread messages whose subject matches ``subject``.

        Both the exact subject and a ``Fwd:`` forwarded variant are matched.
        """
        self._require_connection()
        subject_fwd = f"Fwd: {subject}"
        criteria = '(OR (SUBJECT "{}") (SUBJECT "{}"))'.format(
            subject, subject_fwd
        ).encode("utf-8")
        status, messages = self.mail.uid(
            "SEARCH", "CHARSET", "UTF-8", "UNSEEN", criteria
        )
        if status != "OK":
            raise RuntimeError(f"Failed to search emails: {status}")
        return messages[0].split()

    def fetch_body(self, message_uid: bytes) -> str:
        """Fetch and decode the textual body (HTML preferred) of a message."""
        self._require_connection()
        status, data = self.mail.uid("FETCH", message_uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            raise RuntimeError(
                f"Failed to fetch email UID {message_uid.decode(errors='ignore')}"
            )
        email_message = email.message_from_bytes(data[0][1])
        return self._extract_text(email_message)

    @staticmethod
    def _extract_text(email_message: Message) -> str:
        """Return the best textual representation of the email body."""
        html_body = ""
        plain_body = ""
        for part in email_message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="ignore")
            if content_type == "text/html":
                html_body = text
            elif content_type == "text/plain":
                plain_body = text
        # Prefer HTML (codes are usually inside markup); fall back to plain text.
        return html_body or plain_body

    @staticmethod
    def extract_code(body: str, pattern: str) -> Optional[str]:
        """Return the first capture group matched by ``pattern`` in ``body``."""
        if not pattern:
            raise ValueError("A non-empty regex pattern is required to extract the code.")
        match = re.search(pattern, body, re.DOTALL)
        return match.group(1) if match else None

    def mark_as_read(self, message_uid: bytes) -> None:
        """Flag a message as read (``\\Seen``). The message is NOT deleted."""
        self._require_connection()
        self.mail.uid("STORE", message_uid, "+FLAGS", "(\\Seen)")

    def logout(self) -> None:
        """Close the IMAP session if one is open."""
        if self.mail is not None:
            try:
                self.mail.logout()
            finally:
                self.mail = None

    def _require_connection(self) -> None:
        if self.mail is None:
            raise RuntimeError("Not connected. Call connect() first.")
