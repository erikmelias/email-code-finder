# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-26

First public release, repackaged from the original single-file script.

### Added
- Installable package layout (`src/email_code_finder`) with `pyproject.toml`.
- English API, type hints, and a `py.typed` marker.
- `EmailCodeFinder.wait_for_code()` non-destructive value retrieval.
- Generic extraction: any regex-matchable value (codes, links, IDs, text),
  not only 2FA/OTP codes.
- Test suite (`pytest`, mocked IMAP) and GitHub Actions CI/publish workflows.

### Changed
- Renamed `EmailTokenFinder` to `EmailCodeFinder` and `UniversalEmailClient`
  to `ImapEmailClient`.
- Configuration is now validated; missing required keys raise `ValueError`.

### Fixed
- **Mailbox no longer wiped.** Removed the destructive `cleanup()` that deleted
  every inbox message, and the automatic call to it on construction.
- `mark_as_read()` now actually flags messages `\Seen` instead of deleting them.
- Avoid returning a stale code: only messages received after the wait starts
  (UID greater than the inbox baseline) are considered.
- `extract_code()` raises a clear error when the regex pattern is missing.

### Security
- `config.json` and `.env` are git-ignored to prevent committing credentials.
- README documents app-password and least-privilege recommendations.
