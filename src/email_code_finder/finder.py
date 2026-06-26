"""High-level API to wait for and extract a regex-matched value from email.

The most common use case is a one-time authentication code (2FA/OTP), but the
extraction is fully generic: whatever ``regex_pattern`` captures is returned,
be it a code, a confirmation link, a tracking number, or any other text.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Callable, Optional

from .client import ImapEmailClient

log = logging.getLogger(__name__)

# Configuration keys that must be present for the finder to operate.
REQUIRED_CONFIG_KEYS = (
    "user_email",
    "password",
    "subject_to_find",
    "regex_pattern",
)

# Defaults applied when the corresponding key is absent from the config.
DEFAULT_MAX_WAIT_SECONDS = 180
DEFAULT_CHECK_INTERVAL_SECONDS = 6


class EmailCodeFinder:
    """Poll an IMAP inbox until an email matching your regex arrives.

    Returns whatever ``regex_pattern`` captures (group 1) — typically a 2FA/OTP
    code, but any regex-matchable value works.

    The finder is non-destructive: it never deletes emails. To avoid returning a
    value from an older email, it records the highest inbox UID when the wait
    starts and only considers messages received afterwards. The matched message
    is flagged as read (``\\Seen``) once its value is extracted.

    Timing note: the UID baseline is taken when the wait starts, so trigger the
    action that sends the email *after* (or while) calling ``wait_for_code()`` —
    an email already in the inbox is treated as stale and ignored.

    Configuration (dict or JSON file)::

        {
            "provider": "gmail",
            "user_email": "user@gmail.com",
            "password": "app-password",
            "subject_to_find": "Your verification code",
            "regex_pattern": "(?s)token-2fa-text\\"?>.*?<b>(.*?)</b>.*?</div>",
            "max_wait_time_seconds": 180,
            "check_interval_seconds": 6
        }

    Args:
        config: Configuration dict. If ``None``, it is loaded from ``config_path``.
        config_path: Path to a JSON config file. Used only when ``config`` is None.
        notify_callback: Optional ``Callable(message: str)`` invoked for
            user-facing events (waiting, code found, timeout, error). Must be
            thread-safe. When ``None``, events are only logged.
    """

    def __init__(
        self,
        config: Optional[dict] = None,
        config_path: str = "config.json",
        notify_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.notify_callback = notify_callback
        self.config = config if config is not None else self._load_config(config_path)
        self._validate_config(self.config)

        self.client = ImapEmailClient(
            user_email=self.config["user_email"],
            password=self.config["password"],
            provider=self.config.get("provider"),
            imap_server=self.config.get("imap_server"),
        )

    @staticmethod
    def _load_config(path: str) -> dict:
        """Load configuration from a JSON file."""
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _validate_config(config: dict) -> None:
        """Raise ``ValueError`` if any required configuration key is missing."""
        missing = [key for key in REQUIRED_CONFIG_KEYS if not config.get(key)]
        if missing:
            raise ValueError(
                "Missing required configuration key(s): " + ", ".join(missing)
            )

    def _notify(self, message: str) -> None:
        """Log a message and forward it to ``notify_callback`` when present."""
        log.info(message)
        if self.notify_callback is not None:
            try:
                self.notify_callback(message)
            except Exception as exc:  # never let a UI callback break the flow
                log.debug("notify_callback raised an exception: %s", exc)

    def wait_for_code(self) -> Optional[str]:
        """Wait for and return the authentication code received by email.

        Returns:
            The extracted code, or ``None`` if the timeout elapses first.
        """
        max_wait = self.config.get("max_wait_time_seconds", DEFAULT_MAX_WAIT_SECONDS)
        interval = self.config.get(
            "check_interval_seconds", DEFAULT_CHECK_INTERVAL_SECONDS
        )
        subject = self.config["subject_to_find"]
        regex_pattern = self.config["regex_pattern"]

        code: Optional[str] = None
        start_time = datetime.now()

        try:
            self.client.connect()
            # Baseline: ignore every code that already exists in the inbox.
            baseline_uid = self.client.get_max_uid()
            self._notify("Connected to the mail server. Waiting for the email...")

            while (datetime.now() - start_time).total_seconds() < max_wait:
                for msg_uid in self.client.search_unread_by_subject(subject):
                    if int(msg_uid) <= baseline_uid:
                        continue  # message predates this wait; skip it
                    body = self.client.fetch_body(msg_uid)
                    if not body:
                        continue
                    code = self.client.extract_code(body, regex_pattern)
                    if code:
                        self.client.mark_as_read(msg_uid)
                        log.debug("Email UID %s processed.", msg_uid.decode())
                        break
                if code:
                    break

                elapsed = (datetime.now() - start_time).total_seconds()
                progress = int((elapsed / max_wait) * 100)
                self._notify(
                    f"Waiting for the email... {progress}% ({elapsed:.0f}s)"
                )
                time.sleep(interval)

            if code:
                self._notify("Matching email received; value extracted.")
                log.info("Value found.")
            else:
                self._notify(
                    f"Timed out. No matching email found within {max_wait}s."
                )
                log.warning("Timed out (%ss). No value found.", max_wait)

            return code

        except Exception as exc:
            self._notify(f"Error while waiting for the email: {exc}")
            log.error("Error in wait_for_code: %s", exc, exc_info=True)
            return None
        finally:
            self.client.logout()
            log.info("Disconnected from the mail server.")
