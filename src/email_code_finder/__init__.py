"""email-code-finder: read one-time 2FA/OTP codes from an IMAP mailbox.

Public API::

    from email_code_finder import EmailCodeFinder

    finder = EmailCodeFinder(config_path="config.json", notify_callback=print)
    code = finder.wait_for_code()
"""

from __future__ import annotations

from .client import ImapEmailClient
from .finder import EmailCodeFinder

__all__ = ["EmailCodeFinder", "ImapEmailClient"]
__version__ = "0.1.0"
