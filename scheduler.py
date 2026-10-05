"""Dispatch scheduled in-app notices. SQLite transactions prevent duplicate delivery."""

import logging
import threading

from flask import Flask

from admin_service import dispatch_announcements


def start_announcements_worker(app: Flask) -> threading.Event:
    stop = threading.Event()

    def work() -> None:
        while not stop.is_set():
            try:
                with app.app_context():
                    dispatch_announcements()
            except Exception:
                # Contains no codes, emails, passwords, or payload content.
                logging.getLogger(__name__).error(
                    "Announcement dispatcher failed; retrying on next tick."
                )
            stop.wait(20)

    threading.Thread(target=work, name="announcement-dispatcher", daemon=True).start()
    return stop
