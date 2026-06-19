"""Security & verification helpers for InsightAI.

Provides password hashing (PBKDF2-HMAC-SHA256, no external deps), OTP generation
and OTP delivery for email and phone. Delivery degrades gracefully:

* **Email** — sent via SMTP when ``SMTP_HOST`` / ``SMTP_USER`` / ``SMTP_PASS``
  environment variables are configured; otherwise returns ``False`` so the UI
  can fall back to "demo mode" (showing the code on screen).
* **Phone** — sent via Twilio when ``TWILIO_*`` variables are configured and the
  ``twilio`` package is installed; otherwise falls back to demo mode.

This keeps the app fully runnable offline while supporting real delivery in
production with zero code changes — just set the env vars.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import random
import secrets
import time

from utils.logger import get_logger

logger = get_logger(__name__)

_PBKDF2_ROUNDS = 200_000
_OTP_TTL_SECONDS = 300  # 5 minutes


# ── Password hashing ────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """Hash a password with a random salt. Returns ``salt$hash`` (hex)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS
    ).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    try:
        salt, digest = stored.split("$", 1)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:  # noqa: BLE001
        return False


# ── OTP ─────────────────────────────────────────────────────────────────
def generate_otp() -> str:
    """Return a 6-digit numeric one-time password."""
    return f"{random.randint(0, 999999):06d}"


def otp_expiry() -> float:
    """Return an absolute expiry timestamp for a freshly issued OTP."""
    return time.time() + _OTP_TTL_SECONDS


def otp_valid(expiry: float | None) -> bool:
    """True if ``expiry`` is in the future."""
    return bool(expiry) and time.time() < expiry


# ── Validation ──────────────────────────────────────────────────────────
def is_valid_email(email: str) -> bool:
    import re

    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email or ""))


def is_valid_phone(phone: str) -> bool:
    import re

    digits = re.sub(r"\D", "", phone or "")
    return 7 <= len(digits) <= 15


def password_strength(password: str) -> tuple[int, str]:
    """Return a (score 0-4, label) tuple for a password."""
    import re

    score = 0
    if len(password) >= 8:
        score += 1
    if re.search(r"[A-Z]", password) and re.search(r"[a-z]", password):
        score += 1
    if re.search(r"\d", password):
        score += 1
    if re.search(r"[^A-Za-z0-9]", password):
        score += 1
    return score, ["Very weak", "Weak", "Fair", "Good", "Strong"][score]


# ── Delivery ────────────────────────────────────────────────────────────
def send_email_otp(email: str, otp: str) -> bool:
    """Send an OTP email via SMTP. Returns True if actually sent.

    Configure with env vars: ``SMTP_HOST``, ``SMTP_PORT`` (default 587),
    ``SMTP_USER``, ``SMTP_PASS``, ``SMTP_FROM`` (default = SMTP_USER).
    """
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    if not (host and user and password):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        sender = os.getenv("SMTP_FROM", user)
        body = (
            f"Your InsightAI verification code is: {otp}\n\n"
            "It expires in 5 minutes. If you did not request this, ignore this email."
        )
        msg = MIMEText(body)
        msg["Subject"] = "InsightAI – Email Verification Code"
        msg["From"] = sender
        msg["To"] = email

        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, [email], msg.as_string())
        logger.info("Sent email OTP to %s", email)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("Email OTP delivery failed; falling back to demo mode", exc_info=True)
        return False


def send_sms_otp(phone: str, otp: str) -> bool:
    """Send an OTP SMS via Twilio. Returns True if actually sent.

    Configure with env vars: ``TWILIO_ACCOUNT_SID``, ``TWILIO_AUTH_TOKEN``,
    ``TWILIO_FROM`` (a Twilio phone number). Requires the ``twilio`` package.
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_num = os.getenv("TWILIO_FROM")
    if not (sid and token and from_num):
        return False
    try:
        from twilio.rest import Client  # type: ignore

        Client(sid, token).messages.create(
            body=f"Your InsightAI verification code is {otp} (valid 5 min).",
            from_=from_num,
            to=phone,
        )
        logger.info("Sent SMS OTP to %s", phone)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("SMS OTP delivery failed; falling back to demo mode", exc_info=True)
        return False
