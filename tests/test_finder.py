"""Unit tests for EmailCodeFinder using a fake IMAP client (no network)."""

import pytest

from email_code_finder.client import ImapEmailClient
from email_code_finder.finder import EmailCodeFinder

BASE_CONFIG = {
    "provider": "gmail",
    "user_email": "user@example.com",
    "password": "pw",
    "subject_to_find": "Your code",
    "regex_pattern": r"<b>(\d+)</b>",
    "max_wait_time_seconds": 5,
    "check_interval_seconds": 0,
}


class FakeClient:
    """Stand-in for ImapEmailClient that records behaviour without networking."""

    def __init__(self, baseline, messages):
        self.baseline = baseline
        self.messages = messages  # dict: uid (bytes) -> body (str)
        self.fetched = []
        self.read_flagged = []

    def connect(self):
        pass

    def logout(self):
        pass

    def get_max_uid(self):
        return self.baseline

    def search_unread_by_subject(self, subject):
        return list(self.messages.keys())

    def fetch_body(self, uid):
        self.fetched.append(uid)
        return self.messages[uid]

    extract_code = staticmethod(ImapEmailClient.extract_code)

    def mark_as_read(self, uid):
        self.read_flagged.append(uid)


def make_finder(fake, config=None):
    finder = EmailCodeFinder(config=config or dict(BASE_CONFIG))
    finder.client = fake
    return finder


def test_missing_required_key_raises():
    bad = dict(BASE_CONFIG)
    del bad["regex_pattern"]
    with pytest.raises(ValueError):
        EmailCodeFinder(config=bad)


def test_finds_code_in_new_message():
    fake = FakeClient(baseline=5, messages={b"7": "code: <b>123456</b>"})
    finder = make_finder(fake)
    assert finder.wait_for_code() == "123456"
    assert fake.read_flagged == [b"7"]  # flagged read, not deleted


def test_ignores_message_at_or_below_baseline():
    # UID 5 == baseline -> stale -> must be skipped and never fetched.
    fake = FakeClient(baseline=5, messages={b"5": "code: <b>999999</b>"})
    finder = make_finder(fake, {**BASE_CONFIG, "max_wait_time_seconds": 0.05})
    assert finder.wait_for_code() is None
    assert fake.fetched == []
    assert fake.read_flagged == []


def test_timeout_returns_none():
    fake = FakeClient(baseline=5, messages={})
    finder = make_finder(fake, {**BASE_CONFIG, "max_wait_time_seconds": 0.05})
    assert finder.wait_for_code() is None


def test_no_match_in_body_returns_none():
    fake = FakeClient(baseline=5, messages={b"9": "no code here"})
    finder = make_finder(fake, {**BASE_CONFIG, "max_wait_time_seconds": 0.05})
    assert finder.wait_for_code() is None
    assert fake.read_flagged == []
