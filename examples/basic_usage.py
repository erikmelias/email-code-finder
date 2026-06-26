"""Minimal example: wait for a 2FA code using a JSON config file.

Run from the repository root after creating your own ``config.json``::

    python examples/basic_usage.py
"""

import logging

from email_code_finder import EmailCodeFinder


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s — %(message)s",
    )

    # ``notify_callback`` receives user-facing progress messages; here we just
    # print them. Pass any thread-safe callable (e.g. a GUI status updater).
    finder = EmailCodeFinder(
        config_path="examples/config.example.json",
        notify_callback=print,
    )
    code = finder.wait_for_code()

    if code:
        print(f"Code received: {code}")
    else:
        print("No code was received within the time limit.")


if __name__ == "__main__":
    main()
