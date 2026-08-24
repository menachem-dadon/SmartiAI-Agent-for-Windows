"""Qt-free email connectivity checks shared by every Smarti frontend."""
from __future__ import annotations

import copy
import imaplib
import smtplib

from .ssl_compat import create_ssl_context


def test_email_connection(config, ssl_settings=None):
    """Test IMAP and SMTP login without reading, changing, or sending mail."""
    mail = None
    smtp = None
    try:
        cfg = copy.deepcopy(config or {})
        if not cfg.get("user") or not cfg.get("password"):
            raise ValueError("חסרים כתובת אימייל או סיסמת אפליקציה.")
        ssl_settings = copy.deepcopy(ssl_settings or {})
        imap_context = create_ssl_context(
            ssl_settings,
            url=f"https://{cfg['imap_host']}:{cfg['imap_port']}",
        )
        smtp_context = create_ssl_context(
            ssl_settings,
            url=f"https://{cfg['smtp_host']}:{cfg['smtp_port']}",
        )
        if cfg.get("imap_ssl", True):
            mail = imaplib.IMAP4_SSL(
                cfg["imap_host"], cfg["imap_port"], timeout=30,
                ssl_context=imap_context,
            )
        else:
            mail = imaplib.IMAP4(cfg["imap_host"], cfg["imap_port"], timeout=30)
        mail.login(cfg["user"], cfg["password"])
        status, data = mail.list()
        if status != "OK":
            raise RuntimeError(f"IMAP list failed: {data}")
        try:
            mail.logout()
        except Exception:
            pass
        mail = None

        if cfg.get("smtp_ssl", False):
            smtp = smtplib.SMTP_SSL(
                cfg["smtp_host"], cfg["smtp_port"], timeout=30,
                context=smtp_context,
            )
        else:
            smtp = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30)
            smtp.ehlo()
            if cfg.get("smtp_starttls", True):
                smtp.starttls(context=smtp_context)
                smtp.ehlo()
        smtp.login(cfg["user"], cfg["password"])
        return True, "חיבור האימייל תקין: IMAP ו־SMTP זמינים."
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            if mail is not None:
                mail.logout()
        except Exception:
            pass
        try:
            if smtp is not None:
                smtp.quit()
        except Exception:
            pass
