"""Authentication & verification gate for InsightAI.

Implements sign up, login, logout and two-factor identity verification via
**email OTP** and **phone OTP**. New users must verify both their email and
phone before their account is activated.

OTP delivery uses real SMTP / Twilio when configured (see ``utils.security``);
otherwise the app runs in *demo mode* and shows the code on screen so the flow
is fully testable offline.

Public helpers used by ``app.py``:
    * ``is_authenticated()``  – True if a user/guest session is active
    * ``current_user()``      – the active user dict
    * ``logout()``            – end the session
    * ``render_gate()``       – draw the login/signup screen
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from database import get_database
from utils import get_logger
from utils.ui import hero_3d
from utils.security import (
    generate_otp,
    hash_password,
    is_valid_email,
    is_valid_phone,
    otp_expiry,
    otp_valid,
    password_strength,
    send_email_otp,
    send_sms_otp,
    verify_password,
)

logger = get_logger(__name__)


# ── Session helpers ─────────────────────────────────────────────────────
def is_authenticated() -> bool:
    return st.session_state.get("user") is not None


def current_user() -> dict | None:
    return st.session_state.get("user")


def logout() -> None:
    for key in ("user", "auth_stage", "pending", "otp_email", "otp_phone",
                "otp_exp_email", "otp_exp_phone", "otp_demo"):
        st.session_state.pop(key, None)
    st.session_state["auth_stage"] = "login"


def _issue_otp(channel: str, target: str) -> None:
    """Generate, attempt delivery, and store an OTP for email/phone."""
    code = generate_otp()
    st.session_state[f"otp_{channel}"] = code
    st.session_state[f"otp_exp_{channel}"] = otp_expiry()
    sent = (send_email_otp if channel == "email" else send_sms_otp)(target, code)
    st.session_state["otp_demo"] = not sent
    logger.info("Issued %s OTP to %s (delivered=%s)", channel, target, sent)


# ── UI ──────────────────────────────────────────────────────────────────
def render_gate() -> None:
    """Render the full-screen authentication gate."""
    st.session_state.setdefault("auth_stage", "login")

    # Cinematic 3D animated banner on the auth screen.
    hero_3d(
        'Welcome to <span class="grad">InsightAI</span>',
        "Sign in to upload data, build dashboards, train ML models and generate "
        "reports — your AI-powered data analyst.",
        height=340,
    )

    left, mid, right = st.columns([1, 2, 1])
    with mid:
        st.markdown('<div class="ia-card ia-auth-card">', unsafe_allow_html=True)
        stage = st.session_state["auth_stage"]
        if stage == "login":
            _login_form()
        elif stage == "signup":
            _signup_form()
        elif stage == "verify_email":
            _verify_form("email")
        elif stage == "verify_phone":
            _verify_form("phone")
        elif stage == "forgot":
            _forgot_form()
        elif stage == "reset":
            _reset_form()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)
        if st.button("👀 Continue as guest", use_container_width=True):
            st.session_state["user"] = {"name": "Guest", "email": "guest@insightai.app",
                                        "guest": True}
            st.rerun()


def _show_demo_otp(channel: str) -> None:
    """Prominent, copyable code card when running without SMTP/Twilio."""
    if not st.session_state.get("otp_demo"):
        return
    provider = "SMTP (email)" if channel == "email" else "Twilio (SMS)"
    code = st.session_state.get(f"otp_{channel}")
    st.markdown(
        f'<div class="ia-otp-card">'
        f'<div class="ia-otp-label">🧪 Demo mode — no {provider} configured</div>'
        f'<div class="ia-otp-code">{code}</div>'
        f'<div class="ia-otp-hint">Enter this code below. '
        f'To receive real codes by {"email" if channel=="email" else "SMS"}, '
        f'set the {"SMTP_*" if channel=="email" else "TWILIO_*"} environment variables.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _login_form() -> None:
    st.subheader("🔓 Sign in")
    email = st.text_input("Email", key="login_email", placeholder="you@example.com")
    password = st.text_input("Password", type="password", key="login_pw")

    if st.button("Log in", type="primary", use_container_width=True):
        db = get_database()
        user = db.get_user(email)
        if not user or not verify_password(password, user["password_hash"]):
            st.error("Invalid email or password.")
            return
        if not (user["email_verified"] and user["phone_verified"]):
            st.warning("Your account isn't fully verified. Resuming verification…")
            st.session_state["pending"] = user
            channel = "email" if not user["email_verified"] else "phone"
            _issue_otp(channel, user["email"] if channel == "email" else user["phone"])
            st.session_state["auth_stage"] = f"verify_{channel}"
            st.rerun()
        db.touch_login(email)
        st.session_state["user"] = {k: user[k] for k in ("name", "email", "phone")}
        logger.info("User logged in: %s", email)
        st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✨ Create account", use_container_width=True):
            st.session_state["auth_stage"] = "signup"
            st.rerun()
    with c2:
        if st.button("🔑 Forgot password?", use_container_width=True):
            st.session_state["auth_stage"] = "forgot"
            st.rerun()


def _signup_form() -> None:
    st.subheader("Create your account")
    name = st.text_input("Full name", key="su_name")
    email = st.text_input("Email", key="su_email", placeholder="you@example.com")
    phone = st.text_input("Phone (with country code)", key="su_phone",
                          placeholder="+1 555 123 4567")
    password = st.text_input("Password", type="password", key="su_pw")

    if password:
        score, label = password_strength(password)
        colors = ["#F43F5E", "#F43F5E", "#FBBF24", "#34D399", "#34D399"]
        st.markdown(
            f'<div style="height:6px;border-radius:6px;background:#1e293b;overflow:hidden">'
            f'<div style="height:100%;width:{score*25}%;background:{colors[score]};'
            f'transition:width .3s"></div></div>'
            f'<small style="color:{colors[score]}">Password strength: {label}</small>',
            unsafe_allow_html=True,
        )

    if st.button("✨ Create account", type="primary", use_container_width=True):
        if not name.strip():
            st.error("Please enter your name."); return
        if not is_valid_email(email):
            st.error("Please enter a valid email address."); return
        if not is_valid_phone(phone):
            st.error("Please enter a valid phone number (7–15 digits)."); return
        if password_strength(password)[0] < 2:
            st.error("Please choose a stronger password (8+ chars, mixed case, a number)."); return

        db = get_database()
        if db.email_exists(email):
            st.error("An account with this email already exists. Try logging in."); return

        db.create_user(name.strip(), email, phone, hash_password(password))
        st.session_state["pending"] = {"name": name.strip(), "email": email.lower(),
                                       "phone": phone}
        _issue_otp("email", email)
        st.session_state["auth_stage"] = "verify_email"
        logger.info("New signup: %s", email)
        st.rerun()

    if st.button("← Back to login", use_container_width=True):
        st.session_state["auth_stage"] = "login"
        st.rerun()


def _verify_form(channel: str) -> None:
    pending = st.session_state.get("pending", {})
    target = pending.get("email") if channel == "email" else pending.get("phone")
    icon, noun = ("📧", "email") if channel == "email" else ("📱", "phone")
    st.subheader(f"{icon} Verify your {noun}")
    st.caption(f"We sent a 6-digit code to **{target}**. It expires in 5 minutes.")

    _show_demo_otp(channel)

    code = st.text_input("Enter verification code", key=f"otp_input_{channel}",
                         max_chars=6, placeholder="••••••")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Verify", type="primary", use_container_width=True):
            expected = st.session_state.get(f"otp_{channel}")
            expiry = st.session_state.get(f"otp_exp_{channel}")
            if not otp_valid(expiry):
                st.error("Code expired. Please resend a new one."); return
            if code.strip() != expected:
                st.error("Incorrect code. Please try again."); return

            db = get_database()
            db.set_verified(pending["email"], f"{channel}_verified")

            if channel == "email":
                st.success("Email verified! Now let's verify your phone.")
                _issue_otp("phone", pending["phone"])
                st.session_state["auth_stage"] = "verify_phone"
                st.rerun()
            else:
                db.touch_login(pending["email"])
                st.session_state["user"] = {"name": pending["name"],
                                            "email": pending["email"],
                                            "phone": pending["phone"]}
                st.balloons()
                logger.info("Account fully verified: %s", pending["email"])
                st.rerun()
    with c2:
        if st.button("🔁 Resend code", use_container_width=True):
            _issue_otp(channel, target)
            st.toast("A new code has been sent.")
            st.rerun()

    if st.button("← Cancel", use_container_width=True):
        logout()
        st.rerun()


def _forgot_form() -> None:
    st.subheader("🔑 Reset your password")
    st.caption("Enter your account email and we'll send a verification code.")
    email = st.text_input("Email", key="fp_email", placeholder="you@example.com")

    if st.button("📨 Send reset code", type="primary", use_container_width=True):
        if not is_valid_email(email):
            st.error("Please enter a valid email address."); return
        db = get_database()
        if not db.email_exists(email):
            st.error("No account found with that email."); return
        st.session_state["reset_email"] = email.lower()
        _issue_otp("email", email)
        st.session_state["auth_stage"] = "reset"
        logger.info("Password reset requested: %s", email)
        st.rerun()

    if st.button("← Back to login", use_container_width=True):
        st.session_state["auth_stage"] = "login"
        st.rerun()


def _reset_form() -> None:
    email = st.session_state.get("reset_email", "")
    st.subheader("🔐 Set a new password")
    st.caption(f"We sent a 6-digit code to **{email}**. It expires in 5 minutes.")
    _show_demo_otp("email")

    code = st.text_input("Verification code", key="rp_code", max_chars=6,
                         placeholder="••••••")
    new_pw = st.text_input("New password", type="password", key="rp_pw")
    if new_pw:
        score, label = password_strength(new_pw)
        colors = ["#F43F5E", "#F43F5E", "#FBBF24", "#34D399", "#34D399"]
        st.markdown(
            f'<div style="height:6px;border-radius:6px;background:#1e293b;overflow:hidden">'
            f'<div style="height:100%;width:{score*25}%;background:{colors[score]};'
            f'transition:width .3s"></div></div>'
            f'<small style="color:{colors[score]}">Password strength: {label}</small>',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Reset password", type="primary", use_container_width=True):
            if not otp_valid(st.session_state.get("otp_exp_email")):
                st.error("Code expired. Please resend a new one."); return
            if code.strip() != st.session_state.get("otp_email"):
                st.error("Incorrect code. Please try again."); return
            if password_strength(new_pw)[0] < 2:
                st.error("Please choose a stronger password (8+ chars, mixed case, a number)."); return
            get_database().update_password(email, hash_password(new_pw))
            st.session_state["auth_stage"] = "login"
            st.session_state.pop("reset_email", None)
            logger.info("Password reset completed: %s", email)
            st.success("✅ Password updated. Please log in with your new password.")
            st.rerun()
    with c2:
        if st.button("🔁 Resend code", use_container_width=True):
            _issue_otp("email", email)
            st.toast("A new code has been sent.")
            st.rerun()

    if st.button("← Back to login", use_container_width=True):
        st.session_state["auth_stage"] = "login"
        st.rerun()
