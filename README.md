# email-code-finder

[![PyPI](https://img.shields.io/pypi/v/email-code-finder.svg)](https://pypi.org/project/email-code-finder/)
[![Python](https://img.shields.io/pypi/pyversions/email-code-finder.svg)](https://pypi.org/project/email-code-finder/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Wait for an email to arrive in an IMAP mailbox and extract **any value you can
describe with a regular expression** — a 2FA/OTP code, a confirmation link, a
tracking number, an order ID, a token, or any piece of text. The library
connects over IMAP, waits for the message whose subject you specify, runs your
regex against the body, and returns the captured value — **without ever deleting
your messages.**

> **Not just 2FA.** One-time codes are the most common use case, but the engine
> is generic: if the value is somewhere in the email body and a regex can
> capture it, this library can fetch it. The `regex_pattern` you provide is the
> only thing that decides *what* gets extracted.

Examples of what you can extract:

| Goal | Example `subject_to_find` | Example `regex_pattern` |
| --- | --- | --- |
| 2FA / OTP code | `Your verification code` | `\b(\d{6})\b` |
| Confirmation link | `Confirm your email` | `href="(https://[^"]*/confirm[^"]*)"` |
| Order / tracking ID | `Your order shipped` | `Tracking:\s*([A-Z0-9]{10,})` |
| Arbitrary text | `Your invoice` | `Invoice No\.\s*(\S+)` |

- **No third-party dependencies** — standard library only.
- **Non-destructive** — emails are flagged as read, never deleted.
- **Provider-aware** — Gmail, Outlook/Office 365, Yahoo, iCloud, or any custom
  IMAP host.
- **Pluggable notifications** — pass a callback to surface progress in your UI.

---

## Installation

```bash
pip install email-code-finder
```

Requires Python 3.8+.

## Quick start

```python
from email_code_finder import EmailCodeFinder

config = {
    "provider": "gmail",
    "user_email": "user@example.com",
    "password": "your-app-specific-password",
    "subject_to_find": "Your verification code",
    "regex_pattern": r"(?s)token-2fa-text\"?>.*?<b>(.*?)</b>.*?</div>",
    "max_wait_time_seconds": 180,
    "check_interval_seconds": 6,
}

finder = EmailCodeFinder(config=config, notify_callback=print)
code = finder.wait_for_code()

if code:
    print(f"Got the code: {code}")
else:
    print("Timed out without receiving a code.")
```

Or load the configuration from a JSON file:

```python
finder = EmailCodeFinder(config_path="config.json")
code = finder.wait_for_code()
```

A runnable example lives in [`examples/basic_usage.py`](examples/basic_usage.py).

## Configuration

Configuration can be passed as a `dict` or stored in a JSON file (see
[`examples/config.example.json`](examples/config.example.json)).

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `user_email` | str | ✅ | Full email address used to authenticate. |
| `password` | str | ✅ | Account or **app-specific** password (see Security). |
| `subject_to_find` | str | ✅ | Subject line of the email carrying the code. A `Fwd:` variant is matched too. |
| `regex_pattern` | str | ✅ | Regex whose **first capture group** is the code. |
| `provider` | str | ➖ | `gmail`, `outlook`, `office365`, `yahoo`, `icloud`, `kinghost`. If omitted, the host is derived from your email domain (`imap.<domain>`). |
| `imap_server` | str | ➖ | Explicit IMAP host; overrides `provider` detection. |
| `max_wait_time_seconds` | int | ➖ | How long to wait before giving up. Default `180`. |
| `check_interval_seconds` | int | ➖ | Delay between inbox polls. Default `6`. |

### Writing the regex

`regex_pattern` is matched with `re.DOTALL`; the value returned is **capture
group 1**. For a code wrapped in `<b>123456</b>` you might use:

```text
<b>(\d{6})</b>
```

Test your pattern against a real email body before relying on it.

## API

### `EmailCodeFinder(config=None, config_path="config.json", notify_callback=None)`

- `config` — configuration dict. When `None`, it is loaded from `config_path`.
- `config_path` — path to a JSON config file (used only when `config` is `None`).
- `notify_callback` — optional `Callable(message: str)` invoked for user-facing
  events (waiting, code found, timeout, error). Must be thread-safe.

Missing required keys raise `ValueError`.

#### `wait_for_code() -> Optional[str]`

Connects, polls the inbox until the code arrives or the timeout elapses, and
returns the code (or `None`). On success the matching email is flagged as read.
The connection is always closed when the call returns.

### `ImapEmailClient`

Lower-level IMAP wrapper exposed for advanced use (`connect`, `get_max_uid`,
`search_unread_by_subject`, `fetch_body`, `extract_code`, `mark_as_read`,
`logout`). It performs **no destructive operations**.

## How matching works: timing & the UID baseline

Understanding the sequence is important to use the library correctly.

1. **Baseline.** The moment `wait_for_code()` connects, it reads the highest
   existing message UID in the inbox and stores it as a *baseline*. IMAP UIDs
   only ever increase, so this is a precise "everything up to here is old" mark.
2. **Polling.** Every `check_interval_seconds` it searches the inbox for
   **unread** messages whose subject matches `subject_to_find` (a `Fwd:`
   variant is matched too).
3. **New-only filter.** Any match with a UID **less than or equal to** the
   baseline is skipped — it was already there before you started waiting, so it
   is treated as stale. Only genuinely new messages are inspected.
4. **Extraction.** The regex runs against the body of each new match. The first
   message that yields a capture group wins: that value is returned and the
   message is flagged as read.
5. **Timeout.** If nothing matches within `max_wait_time_seconds`, the call
   returns `None`.

This UID baseline replaces the old, dangerous behaviour of *deleting* the inbox
to "clean up" previous codes. Your existing emails are never touched.

### ⏱️ Critical: start waiting *before* the email is sent

Because the baseline is taken at the start, an email that arrives **before** you
call `wait_for_code()` will be at or below the baseline and therefore ignored.
Trigger the action that generates the email **after** (or concurrently with)
starting the wait:

```python
import threading
from email_code_finder import EmailCodeFinder

finder = EmailCodeFinder(config=config)

# Run wait_for_code() first (in a thread), THEN trigger the email.
result = {}
waiter = threading.Thread(target=lambda: result.update(code=finder.wait_for_code()))
waiter.start()

trigger_login()   # the action that makes the provider send the email
waiter.join()
print(result["code"])
```

### Tuning the delays

| Setting | What it controls | Guidance |
| --- | --- | --- |
| `max_wait_time_seconds` | Total time to wait before giving up. | Set it above the worst-case email delivery time. Mail can take anywhere from a few seconds to a couple of minutes; `180` (3 min) is a safe default. |
| `check_interval_seconds` | Pause between inbox polls. | Lower = the code is picked up sooner, but more IMAP requests. `6` is a good balance. Avoid going below `2–3` so you don't hit provider rate limits or get your IP throttled. |

The call returns **as soon as** a matching code is found — the interval is only
the upper bound on how long after arrival you notice it, not a fixed wait.

## Security

> ⚠️ **This library handles mailbox credentials. Read this section.**

- **Use app-specific passwords**, not your main account password. Gmail,
  Outlook, Yahoo and iCloud all support them and most require them when 2FA is
  enabled on the account.
- **Never commit `config.json`.** It is listed in `.gitignore`. Prefer loading
  secrets from environment variables or a secret manager in production, e.g.:

  ```python
  import os
  config["password"] = os.environ["EMAIL_PASSWORD"]
  ```

- **Connections use TLS** (`IMAP4_SSL` on port 993) with certificate
  verification via `ssl.create_default_context()`. Do not disable verification.
- **Least privilege.** If your provider supports it, use a dedicated mailbox or
  an account scoped only to receiving these codes.
- **Logging.** Extracted codes are written to logs at `DEBUG`/`INFO` level for
  troubleshooting. Keep your log level and log storage appropriately restricted,
  and avoid `DEBUG` in production if logs are shared.
- **Regex from untrusted input.** If `regex_pattern` ever comes from an
  untrusted source, beware of catastrophic backtracking (ReDoS). Prefer simple,
  anchored patterns.

## Limitations

- IMAP only; POP3 and provider-specific APIs are not supported.
- Reads from `INBOX` only.
- The code must be extractable from the email body via a single regex group.

## Development

```bash
git clone https://github.com/erikmelias/email-code-finder.git
cd email-code-finder
pip install -e ".[dev]"
pytest
```

Tests use a mocked IMAP client and make no network connections.

## License

[MIT](LICENSE) © Erik Melias
