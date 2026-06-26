"""Unit tests for ImapEmailClient (no network; imaplib is mocked)."""

from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest

from email_code_finder.client import ImapEmailClient


def make_client():
    return ImapEmailClient(user_email="user@example.com", password="pw", provider="gmail")


def test_resolve_known_provider():
    client = ImapEmailClient("user@whatever.com", "pw", provider="gmail")
    assert client.imap_server == "imap.gmail.com"


def test_resolve_domain_fallback():
    client = ImapEmailClient("user@acme.co", "pw")
    assert client.imap_server == "imap.acme.co"


def test_explicit_server_overrides_provider():
    client = ImapEmailClient("user@acme.co", "pw", provider="gmail", imap_server="mail.acme.co")
    assert client.imap_server == "mail.acme.co"


def test_invalid_email_raises():
    with pytest.raises(ValueError):
        ImapEmailClient("not-an-email", "pw")


def test_extract_code_returns_first_group():
    assert ImapEmailClient.extract_code("Your code is <b>123456</b>.", r"<b>(\d+)</b>") == "123456"


def test_extract_code_no_match_returns_none():
    assert ImapEmailClient.extract_code("nothing here", r"<b>(\d+)</b>") is None


def test_extract_code_empty_pattern_raises():
    with pytest.raises(ValueError):
        ImapEmailClient.extract_code("body", "")


def test_extract_text_prefers_html():
    msg = EmailMessage()
    msg.set_content("plain body")
    msg.add_alternative("<p>html body</p>", subtype="html")
    assert "html body" in ImapEmailClient._extract_text(msg)


def test_get_max_uid_returns_highest():
    client = make_client()
    client.mail = MagicMock()
    client.mail.uid.return_value = ("OK", [b"3 7 5"])
    assert client.get_max_uid() == 7


def test_get_max_uid_empty_inbox():
    client = make_client()
    client.mail = MagicMock()
    client.mail.uid.return_value = ("OK", [b""])
    assert client.get_max_uid() == 0


def test_mark_as_read_uses_seen_flag_not_delete():
    client = make_client()
    client.mail = MagicMock()
    client.mail.uid.return_value = ("OK", [b""])
    client.mark_as_read(b"42")
    # Must flag \Seen and must never issue a \Deleted store or expunge.
    client.mail.uid.assert_called_once_with("STORE", b"42", "+FLAGS", "(\\Seen)")
    client.mail.expunge.assert_not_called()


def test_operations_require_connection():
    client = make_client()
    with pytest.raises(RuntimeError):
        client.get_max_uid()
