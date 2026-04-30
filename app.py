"""
BharatTrade AI — Streamlit Trading Assistant (v3 — fully fixed)
================================================================
Fixes applied:
  1. Plotly candlestick fillcolor: replaced 8-digit hex (#rrggbbaa) → rgba()
  2. Removed increasing_fillcolor / decreasing_fillcolor (not valid Plotly params)
  3. Replaced ZOMATO.NS → ZOMATO.NS verified / NALCO.NS → NATIONALUM.NS
  4. fetch_all_quotes: robust MultiIndex column handling for new yfinance
  5. fetch_intraday_data: robust MultiIndex flattening
  6. compute_indicators: safe Series extraction, no squeeze errors
  7. detect_signals: use .iloc[] not .get() on pandas rows
  8. fmt_price / fmt_pct: handle pandas Series/numpy scalars safely
  9. Screener: per-stock try/except so one bad stock won't break the whole run
 10. Index cards: safe NaN/None guards everywhere
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import feedparser
import re
import pytz
from datetime import datetime
import sqlite3
import hashlib
import secrets
import os
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")


# ═══════════════════════════════════════════════════════════════════════════
# AUTH — DATABASE + OTP + VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

# ─── Database setup ───────────────────────────────────────────────────────
# Uses SQLite stored in /tmp (survives Streamlit Cloud session, resets on restart)
# For persistence across restarts on Streamlit Cloud, mount a volume or use
# st.secrets with an external DB. For local use, /tmp is perfectly fine.
DB_PATH = os.path.join("/tmp", "tradinggenie_users.db")

def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    UNIQUE NOT NULL,
            mobile      TEXT    UNIQUE NOT NULL,
            password_hash TEXT  NOT NULL,
            created_at  TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS otp_store (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier  TEXT    NOT NULL,
            otp         TEXT    NOT NULL,
            purpose     TEXT    NOT NULL,
            expires_at  TEXT    NOT NULL,
            used        INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

_init_db()

# ─── Validation helpers ───────────────────────────────────────────────────
def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _validate_email(email: str) -> tuple[bool, str]:
    """Check email format and basic rules."""
    email = email.strip().lower()
    if not email:
        return False, "Email cannot be empty."
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format. Must be like user@domain.com"
    if len(email) > 254:
        return False, "Email too long."
    local, domain = email.split("@", 1)
    if len(local) > 64:
        return False, "Email local part too long."
    if ".." in email:
        return False, "Email cannot contain consecutive dots."
    if email.startswith(".") or email.endswith("."):
        return False, "Email cannot start or end with a dot."
    blocked = ["test@test.com", "example@example.com", "user@user.com"]
    if email in blocked:
        return False, "Please use a real email address."
    return True, ""

def _validate_mobile(mobile: str) -> tuple[bool, str]:
    """Validate Indian mobile number."""
    mobile = re.sub(r"[\s\-()]", "", mobile)
    if mobile.startswith("+91"):
        mobile = mobile[3:]
    elif mobile.startswith("91") and len(mobile) == 12:
        mobile = mobile[2:]
    if not mobile.isdigit():
        return False, "Mobile number must contain only digits."
    if len(mobile) != 10:
        return False, "Mobile number must be exactly 10 digits."
    if mobile[0] not in "6789":
        return False, "Mobile must start with 6, 7, 8, or 9."
    return True, mobile   # returns cleaned 10-digit number

def _validate_name(name: str) -> tuple[bool, str]:
    name = name.strip()
    if len(name) < 2:
        return False, "Name must be at least 2 characters."
    if len(name) > 80:
        return False, "Name too long."
    if not re.match(r"^[a-zA-Z\s\.\-']+$", name):
        return False, "Name can only contain letters, spaces, dots, hyphens."
    return True, name

def _validate_password(pw: str) -> tuple[bool, str]:
    if len(pw) < 8:
        return False, "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", pw):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[0-9]", pw):
        return False, "Password must contain at least one number."
    return True, ""

# ─── OTP helpers ─────────────────────────────────────────────────────────
OTP_VALIDITY_MINS = 5

def _generate_otp(identifier: str, purpose: str) -> str:
    """Generate and store a 6-digit OTP valid for 5 minutes."""
    otp = str(secrets.randbelow(900000) + 100000)   # 100000–999999
    expires = (datetime.utcnow() + timedelta(minutes=OTP_VALIDITY_MINS)).isoformat()
    conn = _get_conn()
    # Invalidate any existing OTPs for this identifier+purpose
    conn.execute(
        "UPDATE otp_store SET used=1 WHERE identifier=? AND purpose=? AND used=0",
        (identifier, purpose)
    )
    conn.execute(
        "INSERT INTO otp_store (identifier, otp, purpose, expires_at, used) VALUES (?,?,?,?,0)",
        (identifier, otp, purpose, expires)
    )
    conn.commit()
    conn.close()
    return otp

def _verify_otp(identifier: str, otp_input: str, purpose: str) -> tuple[bool, str]:
    """Verify OTP. Returns (success, message)."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM otp_store
           WHERE identifier=? AND purpose=? AND used=0
           ORDER BY id DESC LIMIT 1""",
        (identifier, purpose)
    ).fetchone()
    if not row:
        conn.close()
        return False, "No OTP found. Please request a new one."
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        conn.close()
        return False, f"OTP expired. OTPs are valid for {OTP_VALIDITY_MINS} minutes."
    if row["otp"] != otp_input.strip():
        conn.close()
        return False, "Incorrect OTP. Please try again."
    # Mark as used
    conn.execute("UPDATE otp_store SET used=1 WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()
    return True, "OTP verified."

def _send_otp(identifier: str, otp: str, via: str) -> bool:
    """
    Attempt to send OTP via email or SMS.
    Falls back to showing OTP in the UI (dev mode) if secrets not configured.
    Configure in .streamlit/secrets.toml:
      [smtp]
      host = "smtp.gmail.com"
      port = 587
      user = "you@gmail.com"
      password = "app_password"
      [twilio]
      account_sid = "ACxxx"
      auth_token = "xxx"
      from_number = "+1234567890"
    """
    try:
        if via == "email":
            import smtplib
            from email.mime.text import MIMEText
            smtp_cfg = st.secrets.get("smtp", {})
            if not smtp_cfg:
                return False   # triggers dev-mode fallback
            msg = MIMEText(
                f"Your TradingGenie AI verification OTP is: {otp}\n"
                f"Valid for {OTP_VALIDITY_MINS} minutes. Do not share this code.",
                "plain"
            )
            msg["Subject"] = f"TradingGenie AI — OTP: {otp}"
            msg["From"]    = smtp_cfg["user"]
            msg["To"]      = identifier
            with smtplib.SMTP(smtp_cfg["host"], int(smtp_cfg["port"])) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_cfg["user"], smtp_cfg["password"])
                server.sendmail(smtp_cfg["user"], [identifier], msg.as_string())
            return True

        elif via == "sms":
            twilio_cfg = st.secrets.get("twilio", {})
            if not twilio_cfg:
                return False
            from twilio.rest import Client
            client = Client(twilio_cfg["account_sid"], twilio_cfg["auth_token"])
            client.messages.create(
                body=f"TradingGenie AI OTP: {otp}. Valid {OTP_VALIDITY_MINS} min. Do not share.",
                from_=twilio_cfg["from_number"],
                to=f"+91{identifier}"
            )
            return True
    except Exception:
        return False

# ─── User DB operations ───────────────────────────────────────────────────
def _user_exists_email(email: str) -> bool:
    conn = _get_conn()
    row = conn.execute("SELECT id FROM users WHERE email=?", (email.lower(),)).fetchone()
    conn.close()
    return row is not None

def _user_exists_mobile(mobile: str) -> bool:
    conn = _get_conn()
    row = conn.execute("SELECT id FROM users WHERE mobile=?", (mobile,)).fetchone()
    conn.close()
    return row is not None

def _create_user(name, email, mobile, password):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO users (name, email, mobile, password_hash, created_at) VALUES (?,?,?,?,?)",
        (name, email.lower(), mobile, _hash_pw(password), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def _get_user_by_email(email: str):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def _get_user_by_mobile(mobile: str):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM users WHERE mobile=?", (mobile,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ─── Session helpers ──────────────────────────────────────────────────────
def is_logged_in() -> bool:
    return st.session_state.get("auth_user") is not None

def get_current_user() -> dict | None:
    return st.session_state.get("auth_user")

def _login_user(user: dict):
    st.session_state["auth_user"] = user
    st.session_state["auth_page"] = "app"

def _logout_user():
    st.session_state.pop("auth_user", None)
    st.session_state["auth_page"] = "login"
    st.rerun()

# ─── Auth CSS (added to existing CSS block) ───────────────────────────────
AUTH_CSS = """
<style>
/* ── Auth page layout ── */
.auth-outer{min-height:100vh;display:flex;align-items:center;justify-content:center;
  background:radial-gradient(ellipse at 20% 50%,rgba(0,212,170,.06) 0%,transparent 60%),
             radial-gradient(ellipse at 80% 20%,rgba(59,142,255,.05) 0%,transparent 50%),
             #07090f;padding:2rem 1rem;}
.auth-card{width:100%;max-width:440px;background:#0d1520;border:1px solid rgba(255,255,255,.1);
  border-radius:18px;padding:2.25rem 2rem;box-shadow:0 24px 60px rgba(0,0,0,.6);}
.auth-logo-wrap{text-align:center;margin-bottom:1.75rem;}
.auth-logo-icon{width:54px;height:54px;background:#00d4aa;border-radius:14px;margin:0 auto .75rem;
  display:flex;align-items:center;justify-content:center;
  font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:#07090f;}
.auth-logo-name{font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:800;color:#dde8f8;}
.auth-logo-name span{color:#00d4aa;}
.auth-logo-sub{font-family:'DM Mono',monospace;font-size:10px;color:#4e6a8a;margin-top:3px;letter-spacing:.05em;}
.auth-tab-row{display:flex;background:#07090f;border-radius:10px;padding:3px;margin-bottom:1.5rem;border:1px solid rgba(255,255,255,.07);}
.auth-tab{flex:1;text-align:center;padding:.45rem;border-radius:8px;font-size:12px;font-weight:700;
  font-family:'DM Mono',monospace;cursor:pointer;color:#4e6a8a;transition:all .15s;}
.auth-tab.active{background:#00d4aa;color:#07090f;}
.auth-field-label{font-family:'DM Mono',monospace;font-size:9px;font-weight:600;color:#7a9bc0;
  text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px;}
.auth-otp-sent{background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.2);
  border-radius:8px;padding:8px 12px;font-family:'DM Mono',monospace;font-size:10px;
  color:#00d4aa;margin:.5rem 0;}
.auth-otp-dev{background:rgba(244,169,53,.08);border:1px solid rgba(244,169,53,.2);
  border-radius:8px;padding:8px 12px;font-family:'DM Mono',monospace;font-size:11px;
  color:#f4a935;margin:.5rem 0;text-align:center;}
.auth-err{background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.2);
  border-radius:8px;padding:8px 12px;font-size:11px;color:#ff4d6d;margin:.5rem 0;}
.auth-ok{background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.2);
  border-radius:8px;padding:8px 12px;font-size:11px;color:#00d4aa;margin:.5rem 0;}
.auth-btn-primary{width:100%;background:#00d4aa!important;color:#07090f!important;
  border:none!important;border-radius:10px!important;padding:.65rem!important;
  font-size:14px!important;font-weight:700!important;font-family:'DM Sans',sans-serif!important;
  cursor:pointer!important;margin-top:.5rem!important;}
.auth-btn-primary:hover{opacity:.88!important;}
.auth-divider{text-align:center;font-family:'DM Mono',monospace;font-size:10px;
  color:#4e6a8a;margin:.75rem 0;}
.auth-link{color:#00d4aa;cursor:pointer;font-weight:600;}
.auth-disclaimer{text-align:center;font-family:'DM Mono',monospace;font-size:9px;
  color:#4e6a8a;margin-top:1.25rem;line-height:1.6;}
.pw-hint{font-family:'DM Mono',monospace;font-size:9px;color:#4e6a8a;margin-top:3px;}
/* Make Streamlit inputs dark on auth page */
.auth-card .stTextInput>div>div>input{
  background:#07090f!important;border:1px solid rgba(255,255,255,.12)!important;
  color:#dde8f8!important;border-radius:8px!important;padding:.55rem .75rem!important;
  font-family:'DM Sans',sans-serif!important;font-size:13px!important;}
.auth-card .stTextInput>div>div>input:focus{
  border-color:#00d4aa!important;box-shadow:0 0 0 2px rgba(0,212,170,.12)!important;}
.auth-card .stTextInput label{font-family:'DM Mono',monospace!important;
  font-size:9px!important;color:#7a9bc0!important;text-transform:uppercase!important;letter-spacing:.06em!important;}
.auth-card [data-testid="stFormSubmitButton"]>button{
  width:100%!important;background:#00d4aa!important;color:#07090f!important;
  border:none!important;border-radius:10px!important;padding:.65rem!important;
  font-size:14px!important;font-weight:700!important;margin-top:.25rem!important;}
</style>
"""

# ─── Auth page renderer ───────────────────────────────────────────────────

def render_auth_page():
    """Renders the full sign-up / sign-in page. Blocks app until logged in."""
    st.markdown(AUTH_CSS, unsafe_allow_html=True)

    # init session keys
    for k, v in [("auth_page","login"),("signup_step",1),
                 ("signup_data",{}),("otp_identifier",""),
                 ("otp_purpose",""),("dev_otp",""),
                 ("login_step",1),("login_identifier",""),
                 ("login_via","")]:
        if k not in st.session_state:
            st.session_state[k] = v

    mode = st.session_state.get("auth_mode","login")   # "login" | "signup"
    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"
        mode = "login"

    # Center the card
    _, center, _ = st.columns([1, 1.6, 1])
    with center:
        # Logo
        st.markdown("""
        <div class="auth-logo-wrap">
          <div class="auth-logo-icon">TG</div>
          <div class="auth-logo-name">Trading<span>Genie</span> AI</div>
          <div class="auth-logo-sub">NSE · BSE · Live Market Intelligence</div>
        </div>
        """, unsafe_allow_html=True)

        # Tab row (Sign In / Sign Up)
        tab_l = "active" if mode=="login"  else ""
        tab_r = "active" if mode=="signup" else ""
        st.markdown(f"""
        <div class="auth-tab-row">
          <div class="auth-tab {tab_l}">Sign In</div>
          <div class="auth-tab {tab_r}">Create Account</div>
        </div>""", unsafe_allow_html=True)

        tc1, tc2 = st.columns(2)
        with tc1:
            if st.button("Sign In", key="to_login", width='content'):
                st.session_state["auth_mode"] = "login"
                st.session_state["login_step"] = 1
                st.rerun()
        with tc2:
            if st.button("Create Account", key="to_signup", width='content'):
                st.session_state["auth_mode"] = "signup"
                st.session_state["signup_step"] = 1
                st.rerun()

        st.markdown('<div style="height:.5rem"></div>', unsafe_allow_html=True)

        if mode == "signup":
            _render_signup(center)
        else:
            _render_login(center)

        st.markdown("""
        <div class="auth-disclaimer">
          By continuing you agree to our Terms of Service.<br>
          For educational use only · Not investment advice.
        </div>""", unsafe_allow_html=True)


# ── SIGN UP (3 steps) ─────────────────────────────────────────────────────
#  Step 1: Name + Email + Email-confirm
#  Step 2: Mobile + OTP verification
#  Step 3: Set password → account created

def _render_signup(_col):
    step = st.session_state.get("signup_step", 1)
    data = st.session_state.get("signup_data", {})

    # ── Step 1: Name + Email ──────────────────────────────────────────────
    if step == 1:
        st.markdown("**Step 1 of 3 — Personal Details**")
        with st.form("signup_s1"):
            name   = st.text_input("Full Name", placeholder="Arjun Sharma",
                                   value=data.get("name",""))
            email  = st.text_input("Email Address", placeholder="you@email.com",
                                   value=data.get("email",""))
            email2 = st.text_input("Confirm Email", placeholder="Re-enter email address",
                                   value=data.get("email2",""))
            submitted = st.form_submit_button("Continue →", width='content')

        if submitted:
            errors = []
            ok_n, msg_n = _validate_name(name)
            if not ok_n: errors.append(msg_n)
            ok_e, msg_e = _validate_email(email)
            if not ok_e: errors.append(msg_e)
            if email.strip().lower() != email2.strip().lower():
                errors.append("Email addresses do not match.")
            if not errors and _user_exists_email(email):
                errors.append("An account with this email already exists. Please sign in.")

            if errors:
                for e in errors:
                    st.markdown(f'<div class="auth-err">❌ {e}</div>', unsafe_allow_html=True)
            else:
                st.session_state["signup_data"] = {
                    **data, "name": name.strip(), "email": email.strip().lower(),
                    "email2": email2.strip().lower()
                }
                st.session_state["signup_step"] = 2
                st.rerun()

    # ── Step 2: Mobile + OTP ─────────────────────────────────────────────
    elif step == 2:
        st.markdown("**Step 2 of 3 — Verify Mobile Number**")
        mobile_sent = st.session_state.get("signup_mobile_sent", False)

        if not mobile_sent:
            with st.form("signup_s2a"):
                mobile = st.text_input("Mobile Number",
                                       placeholder="+91 98765 43210",
                                       value=data.get("mobile",""))
                send = st.form_submit_button("Send OTP →", width='content')

            if send:
                ok_m, result = _validate_mobile(mobile)
                if not ok_m:
                    st.markdown(f'<div class="auth-err">❌ {result}</div>', unsafe_allow_html=True)
                elif _user_exists_mobile(result):
                    st.markdown('<div class="auth-err">❌ This mobile number is already registered. Please sign in.</div>', unsafe_allow_html=True)
                else:
                    clean_mobile = result
                    otp = _generate_otp(clean_mobile, "signup")
                    sent = _send_otp(clean_mobile, otp, "sms")
                    st.session_state["signup_data"] = {**data, "mobile": clean_mobile}
                    st.session_state["dev_otp"] = otp if not sent else ""
                    st.session_state["signup_mobile_sent"] = True
                    st.session_state["signup_otp_mobile"] = clean_mobile
                    st.rerun()
        else:
            mobile = st.session_state["signup_otp_mobile"]
            st.markdown(f'<div class="auth-otp-sent">📱 OTP sent to +91 {mobile}</div>', unsafe_allow_html=True)

            dev_otp = st.session_state.get("dev_otp","")
            if dev_otp:
                st.markdown(f'<div class="auth-otp-dev">🔑 Dev Mode — Your OTP: <strong>{dev_otp}</strong><br><span style="font-size:9px;opacity:.7">(Configure Twilio in secrets.toml to send real SMS)</span></div>', unsafe_allow_html=True)

            with st.form("signup_s2b"):
                otp_input = st.text_input("Enter OTP", placeholder="6-digit code",
                                          max_chars=6)
                verify = st.form_submit_button("Verify OTP →", width='content')

            if verify:
                ok, msg = _verify_otp(mobile, otp_input, "signup")
                if not ok:
                    st.markdown(f'<div class="auth-err">❌ {msg}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="auth-ok">✅ Mobile verified successfully!</div>', unsafe_allow_html=True)
                    st.session_state["signup_step"] = 3
                    st.session_state["signup_mobile_sent"] = False
                    st.session_state["dev_otp"] = ""
                    time.sleep(0.5)
                    st.rerun()

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("← Change Number", key="su_back2"):
                    st.session_state["signup_mobile_sent"] = False
                    st.session_state["dev_otp"] = ""
                    st.rerun()
            with bc2:
                if st.button("Resend OTP", key="su_resend"):
                    otp = _generate_otp(mobile, "signup")
                    sent = _send_otp(mobile, otp, "sms")
                    st.session_state["dev_otp"] = otp if not sent else ""
                    st.rerun()

    # ── Step 3: Password → create account ────────────────────────────────
    elif step == 3:
        st.markdown("**Step 3 of 3 — Set Password**")
        st.markdown('<div class="pw-hint">Min 8 chars · at least 1 uppercase · at least 1 number</div>', unsafe_allow_html=True)

        with st.form("signup_s3"):
            pw1 = st.text_input("Password", type="password", placeholder="Create a strong password")
            pw2 = st.text_input("Confirm Password", type="password", placeholder="Re-enter password")
            create = st.form_submit_button("Create Account ✓", width='content')

        if create:
            errors = []
            ok_pw, msg_pw = _validate_password(pw1)
            if not ok_pw: errors.append(msg_pw)
            if pw1 != pw2: errors.append("Passwords do not match.")

            if errors:
                for e in errors:
                    st.markdown(f'<div class="auth-err">❌ {e}</div>', unsafe_allow_html=True)
            else:
                try:
                    _create_user(
                        data["name"], data["email"],
                        data["mobile"], pw1
                    )
                    st.markdown('<div class="auth-ok">🎉 Account created! Signing you in…</div>', unsafe_allow_html=True)
                    user = _get_user_by_email(data["email"])
                    st.session_state["signup_data"]  = {}
                    st.session_state["signup_step"]  = 1
                    time.sleep(0.8)
                    _login_user(user)
                    st.rerun()
                except Exception as ex:
                    st.markdown(f'<div class="auth-err">❌ Could not create account: {ex}</div>', unsafe_allow_html=True)

        if st.button("← Back", key="su_back3"):
            st.session_state["signup_step"] = 2
            st.rerun()


# ── SIGN IN (2 steps) ─────────────────────────────────────────────────────
#  Step 1: Enter email or mobile → choose method (password or OTP)
#  Step 2a: Password login
#  Step 2b: OTP login

def _render_login(_col):
    step = st.session_state.get("login_step", 1)

    # ── Step 1: Identifier + method choice ───────────────────────────────
    if step == 1:
        st.markdown("**Sign in with email or mobile number**")
        with st.form("login_s1"):
            identifier = st.text_input(
                "Email or Mobile",
                placeholder="you@email.com  or  98765 43210",
                value=st.session_state.get("login_identifier","")
            )
            method = st.radio(
                "Verify with",
                ["Password", "OTP (One-Time Password)"],
                horizontal=True,
            )
            proceed = st.form_submit_button("Continue →", width='content')

        if proceed:
            ident = identifier.strip()
            if not ident:
                st.markdown('<div class="auth-err">❌ Please enter your email or mobile number.</div>', unsafe_allow_html=True)
                return

            # Determine if email or mobile
            ok_e, _ = _validate_email(ident)
            ok_m, cleaned_m = _validate_mobile(ident)

            if ok_e:
                user = _get_user_by_email(ident)
                via  = "email"
                lookup_key = ident.lower()
            elif ok_m:
                user = _get_user_by_mobile(cleaned_m)
                via  = "mobile"
                lookup_key = cleaned_m
            else:
                st.markdown('<div class="auth-err">❌ Enter a valid email or 10-digit mobile number.</div>', unsafe_allow_html=True)
                return

            if not user:
                st.markdown('<div class="auth-err">❌ No account found. Please create an account first.</div>', unsafe_allow_html=True)
                return

            use_otp = "OTP" in method
            st.session_state["login_identifier"] = lookup_key
            st.session_state["login_user"]       = user
            st.session_state["login_via"]        = via
            st.session_state["login_use_otp"]    = use_otp
            st.session_state["login_step"]       = 2
            st.session_state["login_otp_sent"]   = False

            if use_otp:
                # Generate + send OTP immediately on step change
                otp = _generate_otp(lookup_key, "login")
                sent = _send_otp(lookup_key, otp, via)
                st.session_state["dev_otp"]        = otp if not sent else ""
                st.session_state["login_otp_sent"] = True
            st.rerun()

    # ── Step 2: Verify ────────────────────────────────────────────────────
    elif step == 2:
        user    = st.session_state.get("login_user", {})
        via     = st.session_state.get("login_via","email")
        ident   = st.session_state.get("login_identifier","")
        use_otp = st.session_state.get("login_use_otp", False)

        if use_otp:
            label = f"OTP sent to your {'email' if via=='email' else 'mobile'}"
            st.markdown(f'<div class="auth-otp-sent">📨 {label}</div>', unsafe_allow_html=True)

            dev_otp = st.session_state.get("dev_otp","")
            if dev_otp:
                via_label = "email (SMTP)" if via=="email" else "SMS (Twilio)"
                st.markdown(
                    f'<div class="auth-otp-dev">🔑 Dev Mode OTP: <strong>{dev_otp}</strong><br>'                    f'<span style="font-size:9px;opacity:.7">Configure {via_label} in secrets.toml to send real OTPs</span></div>',
                    unsafe_allow_html=True
                )

            with st.form("login_otp"):
                otp_in = st.text_input("Enter OTP", placeholder="6-digit code", max_chars=6)
                verify = st.form_submit_button("Sign In →", width='content')

            if verify:
                ok, msg = _verify_otp(ident, otp_in, "login")
                if not ok:
                    st.markdown(f'<div class="auth-err">❌ {msg}</div>', unsafe_allow_html=True)
                else:
                    _login_user(user)
                    st.rerun()

            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button("← Back", key="li_back"):
                    st.session_state["login_step"] = 1
                    st.session_state["dev_otp"] = ""
                    st.rerun()
            with rc2:
                if st.button("Resend OTP", key="li_resend"):
                    otp = _generate_otp(ident, "login")
                    sent = _send_otp(ident, otp, via)
                    st.session_state["dev_otp"] = otp if not sent else ""
                    st.rerun()

        else:
            # Password login
            st.markdown(f"**Welcome back, {user.get('name','').split()[0]}!**")
            with st.form("login_pw"):
                pw = st.text_input("Password", type="password", placeholder="Your password")
                signin = st.form_submit_button("Sign In →", width='content')

            if signin:
                if _hash_pw(pw) != user.get("password_hash",""):
                    st.markdown('<div class="auth-err">❌ Incorrect password. Try again or use OTP.</div>', unsafe_allow_html=True)
                else:
                    _login_user(user)
                    st.rerun()

            if st.button("← Back", key="li_pw_back"):
                st.session_state["login_step"] = 1
                st.rerun()


# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TradingGenie AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@500;700;800&family=DM+Sans:wght@300;400;500&display=swap');
:root{--bg:#07090f;--s1:#0d1520;--s2:#111827;--s3:#1a2535;--bd:rgba(255,255,255,.08);--bd2:rgba(255,255,255,.16);--tx:#dde8f8;--mu:#4e6a8a;--mu2:#7a9bc0;--ac:#00d4aa;--bl:#3b8eff;--dn:#ff4d6d;--wn:#f4a935;--pu:#a78bfa;}
.stApp{background:var(--bg)!important;color:var(--tx)!important;font-family:'DM Sans',sans-serif;}
.stApp>header{display:True!important;}
[data-testid="stToolbar"]{display:none!important;}
[data-testid="stSidebar"]{background:var(--s1)!important;border-right:1px solid var(--bd)!important;}[data-testid="stSidebar"] .stButton>button{width:100%!important;border-radius:8px!important;background:rgba(255,77,109,.08)!important;color:#ff4d6d!important;border:1px solid rgba(255,77,109,.2)!important;font-size:12px!important;padding:.5rem!important;}[data-testid="stSidebar"] .stButton>button:hover{background:rgba(255,77,109,.18)!important;}[data-testid="stSidebarContent"]{padding:1rem .75rem!important;}[data-testid="collapsedControl"]{display:none!important;}
.stTabs [data-baseweb="tab-list"]{background:var(--s1)!important;border-bottom:1px solid var(--bd)!important;padding:0 1rem!important;}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:var(--mu)!important;font-family:'DM Mono',monospace!important;font-size:12px!important;padding:.5rem 1.2rem!important;border-radius:6px 6px 0 0!important;border:1px solid transparent!important;}
.stTabs [aria-selected="true"]{background:var(--bg)!important;color:var(--tx)!important;border-color:var(--bd)!important;border-bottom-color:var(--bg)!important;}
.stTabs [data-baseweb="tab-panel"]{background:var(--bg)!important;padding:0!important;}
[data-testid="stMetric"]{background:var(--s2)!important;border:1px solid var(--bd)!important;border-radius:10px!important;padding:.75rem 1rem!important;}
[data-testid="stMetricLabel"]{color:var(--mu)!important;font-family:'DM Mono',monospace!important;font-size:10px!important;}
[data-testid="stMetricValue"]{color:var(--tx)!important;}
[data-testid="stMetricDelta"]{font-family:'DM Mono',monospace!important;font-size:11px!important;}
[data-testid="stSelectbox"]>div>div{background:var(--s2)!important;border-color:var(--bd2)!important;color:var(--tx)!important;}
.stButton>button{background:var(--s2)!important;color:var(--mu2)!important;border:1px solid var(--bd)!important;border-radius:20px!important;font-family:'DM Mono',monospace!important;font-size:11px!important;}
.stButton>button:hover{border-color:var(--ac)!important;color:var(--ac)!important;}
.stAlert{border-radius:8px!important;}
::-webkit-scrollbar{width:3px;height:3px;}
::-webkit-scrollbar-thumb{background:var(--bd2);border-radius:2px;}
.hdr{border-bottom:1px solid var(--bd2);padding:.65rem 1.5rem;display:flex;align-items:center;justify-content:space-between;}
.logo{font-family:'Syne',sans-serif;font-size:1.15rem;font-weight:800;color:var(--tx);}
.logo span{color:var(--ac);}
.mkt-open{background:rgba(0,212,170,.1);border:1px solid rgba(0,212,170,.25);color:var(--ac);padding:4px 12px;border-radius:20px;font-family:'DM Mono',monospace;font-size:11px;font-weight:600;}
.mkt-closed{background:rgba(255,77,109,.1);border:1px solid rgba(255,77,109,.25);color:var(--dn);padding:4px 12px;border-radius:20px;font-family:'DM Mono',monospace;font-size:11px;font-weight:600;}
.sec{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.1em;text-transform:uppercase;color:var(--mu);margin:1rem 0 .5rem;display:flex;align-items:center;gap:.5rem;}
.sec::after{content:'';flex:1;height:1px;background:var(--bd);}
.idx-card{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:.75rem 1rem;border-top:2px solid;}
.idx-card.up{border-top-color:#00d4aa;}.idx-card.dn{border-top-color:#ff4d6d;}
.idx-label{font-family:'DM Mono',monospace;font-size:8px;color:var(--mu);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px;}
.idx-price{font-family:'Syne',sans-serif;font-size:1.05rem;font-weight:800;}
.idx-chg{font-family:'DM Mono',monospace;font-size:11px;font-weight:600;margin-top:1px;}
.cup{color:#00d4aa;}.cdn{color:#ff4d6d;}
.nc{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:.7rem;margin-bottom:7px;}
.nb{font-family:'DM Mono',monospace;font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px;letter-spacing:.4px;display:inline-block;}
.bull{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.2);}
.bear{background:rgba(255,77,109,.12);color:#ff4d6d;border:1px solid rgba(255,77,109,.2);}
.neu{background:rgba(244,169,53,.1);color:#f4a935;border:1px solid rgba(244,169,53,.2);}
.hi{background:rgba(244,169,53,.1);color:#f4a935;border:1px solid rgba(244,169,53,.2);}
.nt{font-size:12.5px;font-weight:600;color:var(--tx);line-height:1.5;margin:5px 0 3px;}
.nm{font-family:'DM Mono',monospace;font-size:9px;color:var(--mu);}
.sc-card{background:var(--s2);border:1px solid var(--bd);border-radius:10px;padding:.7rem;margin-bottom:7px;border-left:3px solid;}
.sc-card.buy{border-left-color:#00d4aa;}.sc-card.sell{border-left-color:#ff4d6d;}
.sig-buy{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.2);padding:2px 8px;border-radius:4px;font-family:'DM Mono',monospace;font-size:9px;font-weight:800;}
.sig-sell{background:rgba(255,77,109,.12);color:#ff4d6d;border:1px solid rgba(255,77,109,.2);padding:2px 8px;border-radius:4px;font-family:'DM Mono',monospace;font-size:9px;font-weight:800;}
.lvg{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-top:7px;}
.lv{background:var(--s3);border-radius:6px;padding:5px 7px;text-align:center;}
.ll{font-family:'DM Mono',monospace;font-size:7px;color:var(--mu);text-transform:uppercase;}
.lv2{font-family:'Syne',sans-serif;font-size:12px;font-weight:700;margin-top:1px;}
.disc{background:rgba(255,77,109,.05);border:1px solid rgba(255,77,109,.15);border-radius:8px;padding:9px 13px;font-size:11px;color:var(--mu2);}
.tech-block{background:var(--s2);border:1px solid var(--bd);border-radius:10px;overflow:hidden;}
.tr{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-bottom:1px solid var(--bd);}
.tr:last-child{border-bottom:none;}
.tl{font-size:12px;color:var(--mu2);}
.tv{font-family:'DM Mono',monospace;font-size:12px;color:var(--tx);}
.tbadge{font-family:'DM Mono',monospace;font-size:8px;font-weight:700;padding:2px 6px;border-radius:3px;letter-spacing:.4px;}
.tbull{background:rgba(0,212,170,.12);color:#00d4aa;border:1px solid rgba(0,212,170,.2);}
.tbear{background:rgba(255,77,109,.12);color:#ff4d6d;border:1px solid rgba(255,77,109,.2);}
.tneu{background:rgba(244,169,53,.1);color:#f4a935;border:1px solid rgba(244,169,53,.2);}
</style>
""", unsafe_allow_html=True)

# ─── CONSTANTS ────────────────────────────────────────────────────────────────
IST = pytz.timezone("Asia/Kolkata")

INDEX_SYMS = {
    "^NSEI":    "NIFTY 50",
    "^BSESN":   "SENSEX",
    "^NSEBANK": "BANK NIFTY",
    "^CNXIT":   "NIFTY IT",
    "^NSMIDCP": "NIFTY MIDCAP",
}

# Verified Yahoo Finance symbols (Apr 2026)
STOCK_UNIVERSE = [
    ("YESBANK.NS",    "Yes Bank",            "Banking"),
    ("PNB.NS",        "Punjab Natl Bank",    "PSU Banking"),
    ("CANBK.NS",      "Canara Bank",         "PSU Banking"),
    ("IDFCFIRSTB.NS", "IDFC First Bank",     "Private Banking"),
    ("BANKBARODA.NS", "Bank of Baroda",      "PSU Banking"),
    ("UNIONBANK.NS",  "Union Bank",          "PSU Banking"),
    ("INDIANB.NS",    "Indian Bank",         "PSU Banking"),
    ("SUZLON.NS",     "Suzlon Energy",       "Renewable Energy"),
    ("NHPC.NS",       "NHPC",               "Hydro Power"),
    ("RECLTD.NS",     "REC Ltd",            "Power Finance"),
    ("POWERGRID.NS",  "Power Grid",         "Power Infra"),
    ("NTPC.NS",       "NTPC",              "Power PSU"),
    ("COALINDIA.NS",  "Coal India",         "Mining PSU"),
    ("JPPOWER.NS",    "JP Power",           "Power Private"),
    ("RPOWER.NS",     "Reliance Power",     "Power Private"),
    ("TATAPOWER.NS",  "Tata Power",         "Power Private"),
    ("ONGC.NS",       "ONGC",              "Oil & Gas PSU"),
    ("IOC.NS",        "Indian Oil",         "Oil & Gas PSU"),
    ("BPCL.NS",       "BPCL",              "Oil & Gas PSU"),
    ("HINDPETRO.NS",  "HPCL",              "Oil & Gas PSU"),
    ("IRFC.NS",       "IRFC",              "Railways Finance"),
    ("IRCTC.NS",      "IRCTC",            "Railways"),
    ("BHEL.NS",       "BHEL",             "Capital Goods"),
    ("BEL.NS",        "BEL",              "Defence"),
    ("SAIL.NS",       "SAIL",             "Steel PSU"),
    ("NMDC.NS",       "NMDC",             "Mining PSU"),
    ("NATIONALUM.NS", "NALCO",            "Aluminium PSU"),   # Fixed: was NALCO.NS
    ("VEDL.NS",       "Vedanta",          "Metals"),
    ("IDEA.NS",       "Vodafone Idea",    "Telecom"),
    ("HFCL.NS",       "HFCL",            "Telecom Infra"),
    ("TRIDENT.NS",    "Trident",          "Textiles"),
    ("BIOCON.NS",     "Biocon",           "Pharma"),
    ("GLENMARK.NS",   "Glenmark",         "Pharma"),
    ("ASHOKLEY.NS",   "Ashok Leyland",    "Commercial Vehicles"),
    ("MPHASIS.NS",    "Mphasis",          "IT Services"),
    ("PERSISTENT.NS", "Persistent Sys",   "IT Services"),
    ("CGPOWER.NS",    "CG Power",         "Electricals"),
    ("CDSL.NS",       "CDSL",            "Capital Markets"),
    ("DIXON.NS",      "Dixon Tech",       "Electronics"),

]

RSS_FEEDS = [
    ("https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "Economic Times"),
    ("https://www.moneycontrol.com/rss/latestnews.xml",                       "MoneyControl"),
    ("https://www.business-standard.com/rss/markets-106.rss",                 "Business Standard"),
    ("https://feeds.feedburner.com/ndtvprofit-latest",                         "NDTV Profit"),
    ("https://www.livemint.com/rss/markets",                                   "LiveMint"),
]

# Plotly base theme — applied via update_layout
CHART_LAYOUT = dict(
    plot_bgcolor  = "#07090f",
    paper_bgcolor = "#0d1520",
    font          = dict(family="DM Mono, monospace", color="#7a9bc0", size=10),
    margin        = dict(l=0, r=10, t=30, b=0),
    hovermode     = "x unified",
    xaxis_rangeslider_visible = False,
    legend        = dict(
        orientation="h", yanchor="bottom", y=1.01,
        xanchor="right", x=1,
        font=dict(size=9, color="#7a9bc0"),
        bgcolor="rgba(13,21,32,0.8)",
    ),
)

# ─── HELPERS ─────────────────────────────────────────────────────────────────
def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    o = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    c = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return o <= now <= c

def _scalar(v):
    """Safely convert pandas Series / numpy scalar / float to Python float."""
    if v is None:
        return None
    if isinstance(v, pd.Series):
        v = v.iloc[0] if len(v) == 1 else float(v.mean())
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and np.isnan(v):
        return None
    try:
        return float(v)
    except Exception:
        return None

def fp(v) -> str:
    """Format price safely."""
    v = _scalar(v)
    if v is None: return "—"
    return f"₹{v:,.2f}"

def fpc(v) -> str:
    """Format percent safely."""
    v = _scalar(v)
    if v is None: return "—"
    return f"{'+'if v>=0 else''}{v:.2f}%"

def cc(v) -> str:
    """CSS color class."""
    v = _scalar(v)
    if v is None: return ""
    return "cup" if v >= 0 else "cdn"

def time_ago(s) -> str:
    if not s: return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s) if isinstance(s, str) else s
        diff = datetime.now(IST) - dt.astimezone(IST)
        m = int(diff.total_seconds() / 60)
        if m < 1:    return "Just now"
        if m < 60:   return f"{m}m ago"
        if m < 1440: return f"{m//60}h ago"
        return dt.strftime("%d %b")
    except Exception:
        return ""

def flatten_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns from yfinance download."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if c[1] == "" else c[0] for c in df.columns]
    return df

def rename_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Open/High/Low/Close/Volume → lowercase."""
    return df.rename(columns={
        "Open":"open","High":"high","Low":"low",
        "Close":"close","Volume":"volume",
        "Adj Close":"close",
    })

# ─── DATA FETCHING ────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def fetch_indices() -> list[dict]:
    results = []
    for sym, label in INDEX_SYMS.items():
        try:
            raw = yf.download(sym, period="5d", interval="1d",
                              auto_adjust=True, progress=False)
            if raw.empty:
                continue
            raw = flatten_cols(raw)
            raw = rename_ohlcv(raw)
            closes = raw["close"].dropna()
            if len(closes) < 2:
                continue
            price      = float(closes.iloc[-1])
            prev_close = float(closes.iloc[-2])
            change     = price - prev_close
            pct        = (change / prev_close * 100) if prev_close else 0
            results.append({
                "symbol": sym, "label": label,
                "price": price, "change": change, "change_pct": pct,
                "prev_close": prev_close,
                "high": float(raw["high"].iloc[-1]) if "high" in raw.columns else price,
                "low":  float(raw["low"].iloc[-1])  if "low"  in raw.columns else price,
                "year_high": float(closes.max()),
                "year_low":  float(closes.min()),
            })
        except Exception:
            pass
    return results

@st.cache_data(ttl=60, show_spinner=False)
def fetch_stock_quote(sym: str) -> dict:
    try:
        raw = yf.download(sym, period="5d", interval="1d",
                          auto_adjust=True, progress=False)
        if raw.empty:
            return {}
        raw = flatten_cols(raw)
        raw = rename_ohlcv(raw)
        closes = raw["close"].dropna()
        if len(closes) < 1:
            return {}
        price      = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2]) if len(closes) > 1 else price
        change     = price - prev_close
        pct        = (change / prev_close * 100) if prev_close else 0
        return {
            "symbol": sym, "price": price, "change": change,
            "change_pct": pct, "prev_close": prev_close,
            "high": float(raw["high"].iloc[-1]) if "high" in raw.columns else price,
            "low":  float(raw["low"].iloc[-1])  if "low"  in raw.columns else price,
            "year_high": float(closes.max()),
            "year_low":  float(closes.min()),
        }
    except Exception:
        return {}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_quotes() -> pd.DataFrame:
    """Batch fetch all universe stocks - handles all yfinance MultiIndex formats."""
    syms  = [s[0] for s in STOCK_UNIVERSE]
    names = {s[0]: s[1] for s in STOCK_UNIVERSE}
    sects = {s[0]: s[2] for s in STOCK_UNIVERSE}
    rows  = []

    def _extract_close(raw, sym):
        """Extract close price series for a symbol from any yfinance layout."""
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = raw.columns.get_level_values(0).tolist()
            lvl1 = raw.columns.get_level_values(1).tolist()
            # Layout A: group_by='ticker' -> (SYM, field)
            if sym in lvl0:
                sub = raw[sym]
                close_col = next((c for c in sub.columns if str(c).lower()=="close"), None)
                return sub[close_col].dropna() if close_col else pd.Series(dtype=float)
            # Layout B: default yfinance -> (field, SYM)
            close_keys = [c for c in lvl0 if str(c).lower()=="close"]
            if close_keys and sym in lvl1:
                return raw[close_keys[0]][sym].dropna()
        else:
            close_col = next((c for c in raw.columns if str(c).lower()=="close"), None)
            if close_col:
                return raw[close_col].dropna()
        return pd.Series(dtype=float)

    try:
        raw = yf.download(
            syms, period="5d", interval="1d",
            auto_adjust=True, progress=False, threads=True,
        )
        if raw.empty:
            raise ValueError("Empty batch response")

        for sym in syms:
            try:
                col = _extract_close(raw, sym)
                if len(col) < 1:
                    continue
                price      = float(col.iloc[-1])
                prev_close = float(col.iloc[-2]) if len(col) > 1 else price
                change     = price - prev_close
                pct        = (change / prev_close * 100) if prev_close else 0
                rows.append({
                    "symbol": sym, "name": names.get(sym, sym),
                    "sector": sects.get(sym, "—"),
                    "price": price, "change": change,
                    "change_pct": pct, "prev_close": prev_close,
                })
            except Exception:
                pass

    except Exception:
        # Graceful fallback: fetch one by one
        for sym in syms:
            try:
                q = fetch_stock_quote(sym)
                if q and q.get("price", 0) > 0:
                    rows.append({
                        "symbol": sym, "name": names.get(sym, sym),
                        "sector": sects.get(sym, "—"),
                        "price":      q["price"],
                        "change":     q.get("change", 0),
                        "change_pct": q.get("change_pct", 0),
                        "prev_close": q.get("prev_close", 0),
                    })
            except Exception:
                pass

    return pd.DataFrame(rows)

@st.cache_data(ttl=60, show_spinner=False)
def fetch_intraday(sym: str, interval: str = "5m") -> pd.DataFrame:
    try:
        raw = yf.download(sym, period="1d", interval=interval,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]
        raw = rename_ohlcv(raw)
        raw.index = pd.to_datetime(raw.index)
        # Convert index to IST — yfinance returns UTC for intraday
        if raw.index.tzinfo is None:
            raw.index = raw.index.tz_localize("UTC")
        raw.index = raw.index.tz_convert(IST)
        # Strip tz info for Plotly compatibility (keeps IST wall-clock values)
        raw.index = raw.index.tz_localize(None)
        required = {"open","high","low","close","volume"}
        if not required.issubset(set(raw.columns)):
            return pd.DataFrame()
        return raw[list(required)].dropna(subset=["open","high","low","close"])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(sym: str, period: str = "3mo") -> pd.DataFrame:
    try:
        raw = yf.download(sym, period=period, interval="1d",
                          auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]
        raw = rename_ohlcv(raw)
        raw.index = pd.to_datetime(raw.index)
        required = {"open","high","low","close","volume"}
        if not required.issubset(set(raw.columns)):
            return pd.DataFrame()
        return raw[list(required)].dropna(subset=["open","high","low","close"])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_news() -> list[dict]:
    items = []
    for url, src in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:12]:
                title = e.get("title","").strip()
                if not title:
                    continue
                desc = re.sub(r"<[^>]+>", "", e.get("summary",""))[:220].strip()
                items.append({
                    "title":   title,
                    "link":    e.get("link","#"),
                    "desc":    desc,
                    "source":  src,
                    "date":    e.get("published",""),
                    "sentiment": _classify(title),
                    "impact":    _impact(title),
                })
        except Exception:
            pass
    seen, out = set(), []
    for it in items:
        k = it["title"][:38].lower()
        if k not in seen:
            seen.add(k); out.append(it)
    out.sort(key=lambda x: x["impact"], reverse=True)
    return out[:50]

def _classify(t: str) -> str:
    t = t.lower()
    if any(k in t for k in ["surge","rally","gain","rise","record","bullish","soar","jump","strong","profit","growth"]):
        return "bull"
    if any(k in t for k in ["fall","crash","drop","decline","bearish","loss","weak","slump","cut","fear"]):
        return "bear"
    return "neutral"

def _impact(t: str) -> int:
    t = t.lower()
    return sum(1 for k in ["nifty","sensex","rbi","sebi","budget","gdp","inflation","results","fii","dii","rate"] if k in t)

# ─── TECHNICAL INDICATORS ────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 5:
        return df
    df = df.copy()
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    v = df["volume"].astype(float)
    n = len(df)
    try:
        from ta.momentum import RSIIndicator
        from ta.trend import EMAIndicator, SMAIndicator, MACD
        from ta.volatility import BollingerBands, AverageTrueRange
        if n >= 14:
            df["rsi"]      = RSIIndicator(c, window=14).rsi().values
        if n >= 9:
            df["ema9"]     = EMAIndicator(c, window=9).ema_indicator().values
        if n >= 21:
            df["ema21"]    = EMAIndicator(c, window=21).ema_indicator().values
        if n >= 20:
            df["sma50"]    = SMAIndicator(c, window=min(50,n)).sma_indicator().values
            df["sma200"]   = SMAIndicator(c, window=min(200,n)).sma_indicator().values
            macd_obj       = MACD(c)
            df["macd"]     = macd_obj.macd().values
            df["macd_sig"] = macd_obj.macd_signal().values
            df["macd_hist"]= macd_obj.macd_diff().values
            bb             = BollingerBands(c)
            df["bb_upper"] = bb.bollinger_hband().values
            df["bb_lower"] = bb.bollinger_lband().values
            df["bb_mid"]   = bb.bollinger_mavg().values
        if n >= 5:
            df["atr"]  = AverageTrueRange(h, l, c, window=min(14,n)).average_true_range().values
            if v.sum() > 0:
                df["vwap"] = (c * v).cumsum() / v.replace(0, np.nan).cumsum()
    except Exception:
        pass
    return df

def detect_signals(df: pd.DataFrame) -> list[dict]:
    """
    Analyse each candle using multiple indicators.
    Each candle gets a BUY score and SELL score from all indicators.
    If net score favours BUY → emit one BUY signal.
    If net score favours SELL → emit one SELL signal.
    Markers on chart show only ▲ BUY or ▼ SELL — no clutter.
    The contributing patterns are recorded in "patterns" for the signal log.
    """
    out = []
    if df.empty or len(df) < 6:
        return out
    df = compute_indicators(df)

    for i in range(5, len(df)):
        c0 = df.iloc[i]
        c1 = df.iloc[i-1]
        ts    = df.index[i]
        price = float(c0["close"])

        def _f(row, col):
            v = row[col] if col in row.index else np.nan
            try: return float(v)
            except: return np.nan

        op0,cl0,hi0,lo0 = _f(c0,"open"),_f(c0,"close"),_f(c0,"high"),_f(c0,"low")
        op1,cl1         = _f(c1,"open"),_f(c1,"close")

        buy_score  = 0
        sell_score = 0
        buy_reasons  = []
        sell_reasons = []

        # 1. Candlestick patterns
        if cl1<op1 and cl0>op0 and cl0>op1 and op0<cl1:
            buy_score += 2; buy_reasons.append("Bullish Engulfing")
        if cl1>op1 and cl0<op0 and cl0<op1 and op0>cl1:
            sell_score += 2; sell_reasons.append("Bearish Engulfing")

        # Hammer (long lower wick, small body near top)
        body = abs(cl0 - op0)
        lower_wick = min(cl0,op0) - lo0
        upper_wick = hi0 - max(cl0,op0)
        candle_range = hi0 - lo0
        if candle_range > 0:
            if lower_wick > body * 2 and upper_wick < body and cl0 > op0:
                buy_score += 2; buy_reasons.append("Hammer")
            if upper_wick > body * 2 and lower_wick < body and cl0 < op0:
                sell_score += 2; sell_reasons.append("Shooting Star")

        # 2. RSI
        rsi0 = _f(c0,"rsi"); rsi1 = _f(c1,"rsi")
        if not (np.isnan(rsi0) or np.isnan(rsi1)):
            if rsi0 < 30:
                buy_score += 2; buy_reasons.append(f"RSI oversold ({rsi0:.0f})")
            elif rsi0 < 40:
                buy_score += 1; buy_reasons.append(f"RSI low ({rsi0:.0f})")
            if rsi0 > 70:
                sell_score += 2; sell_reasons.append(f"RSI overbought ({rsi0:.0f})")
            elif rsi0 > 60:
                sell_score += 1; sell_reasons.append(f"RSI high ({rsi0:.0f})")
            # RSI turning
            if rsi1 < 30 and rsi0 > rsi1:
                buy_score += 1; buy_reasons.append("RSI turning up")
            if rsi1 > 70 and rsi0 < rsi1:
                sell_score += 1; sell_reasons.append("RSI turning down")

        # 3. VWAP position
        vwap = _f(c0,"vwap")
        if not np.isnan(vwap):
            if cl0 > vwap and op0 < vwap:                    # crossed above
                buy_score += 2; buy_reasons.append("Crossed above VWAP")
            elif cl0 > vwap:
                buy_score += 1; buy_reasons.append("Above VWAP")
            if cl0 < vwap and op0 > vwap:                    # crossed below
                sell_score += 2; sell_reasons.append("Crossed below VWAP")
            elif cl0 < vwap:
                sell_score += 1; sell_reasons.append("Below VWAP")

        # 4. EMA 9/21 crossover
        e9_0 = _f(c0,"ema9"); e21_0 = _f(c0,"ema21")
        e9_1 = _f(c1,"ema9"); e21_1 = _f(c1,"ema21")
        if not any(np.isnan(x) for x in [e9_0,e21_0,e9_1,e21_1]):
            if e9_1 < e21_1 and e9_0 > e21_0:
                buy_score += 3; buy_reasons.append("EMA 9 crossed above 21")
            elif e9_0 > e21_0:
                buy_score += 1; buy_reasons.append("EMA 9 > 21")
            if e9_1 > e21_1 and e9_0 < e21_0:
                sell_score += 3; sell_reasons.append("EMA 9 crossed below 21")
            elif e9_0 < e21_0:
                sell_score += 1; sell_reasons.append("EMA 9 < 21")

        # 5. Volume confirmation
        avg_vol = float(df["volume"].iloc[max(0,i-20):i].mean())
        if avg_vol > 0:
            vol_ratio = float(c0["volume"]) / avg_vol
            if vol_ratio > 1.5 and cl0 > op0:
                buy_score  += 2; buy_reasons.append(f"Vol surge {vol_ratio:.1f}x (bullish)")
            if vol_ratio > 1.5 and cl0 < op0:
                sell_score += 2; sell_reasons.append(f"Vol surge {vol_ratio:.1f}x (bearish)")

        # 6. Bollinger Band extremes
        bbu = _f(c0,"bb_upper"); bbl = _f(c0,"bb_lower"); bbm = _f(c0,"bb_mid")
        if not np.isnan(bbu):
            if cl0 < bbl:
                buy_score  += 2; buy_reasons.append("Below BB lower band")
            elif not np.isnan(bbm) and cl0 > bbm and _f(c1,"close") < bbm:
                buy_score  += 1; buy_reasons.append("BB mid crossover up")
            if cl0 > bbu:
                sell_score += 2; sell_reasons.append("Above BB upper band")
            elif not np.isnan(bbm) and cl0 < bbm and _f(c1,"close") > bbm:
                sell_score += 1; sell_reasons.append("BB mid crossover down")

        # 7. MACD histogram momentum
        mh0 = _f(c0,"macd_hist"); mh1 = _f(c1,"macd_hist")
        if not (np.isnan(mh0) or np.isnan(mh1)):
            if mh0 > 0 and mh1 <= 0:
                buy_score  += 2; buy_reasons.append("MACD hist turned positive")
            elif mh0 > 0 and mh0 > mh1:
                buy_score  += 1; buy_reasons.append("MACD hist rising")
            if mh0 < 0 and mh1 >= 0:
                sell_score += 2; sell_reasons.append("MACD hist turned negative")
            elif mh0 < 0 and mh0 < mh1:
                sell_score += 1; sell_reasons.append("MACD hist falling")

        # ── Net verdict: only emit a signal if score difference is meaningful ──
        net = buy_score - sell_score
        if net >= 3:            # clear BUY consensus
            out.append({
                "ts": ts, "type": "BUY", "price": price,
                "score": buy_score, "pattern": ", ".join(buy_reasons[:3]),
                "detail": buy_reasons,
            })
        elif net <= -3:         # clear SELL consensus
            out.append({
                "ts": ts, "type": "SELL", "price": price,
                "score": sell_score, "pattern": ", ".join(sell_reasons[:3]),
                "detail": sell_reasons,
            })

    return out

# ─── SCREENER ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400*7, show_spinner=False)
def run_swing_screener() -> pd.DataFrame:
    return _screener("swing")

@st.cache_data(ttl=86400, show_spinner=False)
def run_intraday_screener() -> pd.DataFrame:
    return _screener("intraday")

def _screener(mode: str) -> pd.DataFrame:
    quotes = fetch_all_quotes()
    if quotes.empty:
        return pd.DataFrame()
    under1k = quotes[quotes["price"].between(1, 999)].copy()
    rows = []
    for _, row in under1k.iterrows():
        sym   = row["symbol"]
        price = float(row["price"])
        pct   = float(row.get("change_pct", 0) or 0)
        try:
            if mode == "swing":
                hist = fetch_history(sym, "3mo")
                if hist.empty or len(hist) < 10:
                    continue
                hist  = compute_indicators(hist)
                close = hist["close"].astype(float)
                rsi   = float(hist["rsi"].iloc[-1])  if "rsi"   in hist.columns and not np.isnan(hist["rsi"].iloc[-1])   else 50.0
                ma50  = float(hist["sma50"].iloc[-1]) if "sma50" in hist.columns and not np.isnan(hist["sma50"].iloc[-1]) else price
                ma200 = float(hist["sma200"].iloc[-1])if "sma200"in hist.columns and not np.isnan(hist["sma200"].iloc[-1])else price
                abv50  = price > ma50
                abv200 = price > ma200
                mom10  = (float(close.iloc[-1]) - float(close.iloc[-10])) / (float(close.iloc[-10]) + 0.01) * 100 if len(close)>10 else 0
                vol_r  = float(hist["volume"].iloc[-5:].mean()) / (float(hist["volume"].mean()) + 1)
                lo52   = float(close.min()); hi52 = float(close.max())
                from52 = (price - lo52) / (hi52 - lo52 + 0.01)
                score  = (abv50*3 + abv200*2 + (rsi<40)*3 + (40<=rsi<=60)*1
                          + (vol_r>1.2)*2 + (mom10>0)*2 + (from52<0.25)*2)
                action = "BUY" if (abv50 or rsi<40 or mom10>0) else "SELL"
                conf   = "HIGH" if score>=7 else "MEDIUM" if score>=4 else "LOW"
                sl_pct, tg_pct = (-0.06, 0.12) if action=="BUY" else (0.05, -0.10)
                parts  = []
                if abv50:       parts.append("Above 50-DMA")
                if rsi < 40:    parts.append(f"RSI oversold ({rsi:.0f})")
                if vol_r > 1.2: parts.append("Volume surge")
                if from52 <0.2: parts.append("Near 52W support")
                if not parts:   parts.append(f"Momentum {mom10:+.1f}%")
            else:
                hist = fetch_intraday(sym, "5m")
                if hist.empty or len(hist) < 10:
                    continue
                hist   = compute_indicators(hist)
                rsi    = float(hist["rsi"].iloc[-1])  if "rsi"  in hist.columns and not np.isnan(hist["rsi"].iloc[-1])  else 50.0
                vwap   = float(hist["vwap"].iloc[-1]) if "vwap" in hist.columns and not np.isnan(hist["vwap"].iloc[-1]) else price
                abv_vwap = price > vwap
                avg_v    = float(hist["volume"].iloc[:-1].mean()) if len(hist)>1 else 1
                last_v   = float(hist["volume"].iloc[-1])
                vol_r    = last_v / (avg_v + 1)
                gap      = abs(price - float(row["prev_close"])) / (float(row["prev_close"]) + 0.01) * 100
                score    = (abv_vwap*2 + (vol_r>1.5)*3 + (abs(pct)>2)*2
                            + (gap>1)*2 + (rsi<35)*2 + (rsi>65)*1)
                action   = "BUY" if (abv_vwap and pct>0) or rsi<35 else "SELL"
                conf     = "HIGH" if score>=7 else "MEDIUM" if score>=4 else "LOW"
                sl_pct, tg_pct = (-0.02, 0.03) if action=="BUY" else (0.02, -0.025)
                parts = []
                if abv_vwap:    parts.append("Above VWAP")
                if vol_r > 1.5: parts.append(f"Vol {vol_r:.1f}x avg")
                if gap > 1:     parts.append(f"Gap {gap:.1f}%")
                if abs(pct)>2:  parts.append(f"Move {pct:+.1f}%")
                if not parts:   parts.append(f"RSI {rsi:.0f}")

            sl  = price * (1 + sl_pct)
            tgt = price * (1 + tg_pct)
            rr  = round(abs(tg_pct / sl_pct), 1) if sl_pct else 1
            rows.append({
                "symbol":row["symbol"], "name":row["name"], "sector":row["sector"],
                "price":price, "change_pct":pct,
                "action":action, "conf":conf, "score":score,
                "entry":price, "sl":sl, "target":tgt, "rr":rr,
                "reason":" · ".join(parts),
            })
        except Exception:
            continue

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("price").head(20).reset_index(drop=True)

# ─── CHART BUILDERS ──────────────────────────────────────────────────────────

def build_intraday_chart(sym: str, signals: list[dict]) -> go.Figure:
    df = fetch_intraday(sym, "5m")

    if df.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, height=400,
                          title=dict(text="No intraday data — market may be closed", font=dict(color="#7a9bc0")))
        return fig

    df = compute_indicators(df)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.58, 0.21, 0.21],
        vertical_spacing=0.04,
        subplot_titles=("", "RSI (14)", "MACD"),
    )

    # ── Candlestick (no fillcolor params — they don't exist on go.Candlestick) ──
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"].astype(float),
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        increasing=dict(line=dict(color="#00d4aa", width=1)),
        decreasing=dict(line=dict(color="#ff4d6d", width=1)),
        name="Price", showlegend=False,
    ), row=1, col=1)

    # ── VWAP ──
    if "vwap" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["vwap"].astype(float),
            line=dict(color="#f4a935", width=1.5, dash="dash"),
            name="VWAP",
        ), row=1, col=1)

    # ── EMAs ──
    for col, color, name in [("ema9","#3b8eff","EMA 9"),("ema21","#a78bfa","EMA 21")]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col].astype(float),
                line=dict(color=color, width=1),
                name=name,
            ), row=1, col=1)

    # ── Bollinger Bands ──
    if "bb_upper" in df.columns and "bb_lower" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["bb_upper"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)", width=1),
            name="BB Upper", showlegend=False,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["bb_lower"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)", width=1),
            fill="tonexty", fillcolor="rgba(59,142,255,0.05)",
            name="BB Lower", showlegend=False,
        ), row=1, col=1)

    # ── BUY signals — clean triangles only, no text clutter ──
    buys = [s for s in signals if s["type"]=="BUY"]
    if buys:
        fig.add_trace(go.Scatter(
            x=[s["ts"] for s in buys],
            y=[s["price"] * 0.996 for s in buys],
            mode="markers",
            marker=dict(
                symbol="triangle-up", size=13, color="#00d4aa",
                line=dict(color="#07090f", width=1),
            ),
            name="BUY",
            hovertemplate=(
                "<b style='color:#00d4aa'>▲ BUY</b><br>"
                "Price: ₹%{customdata[0]:.2f}<br>"
                "Reason: %{customdata[1]}<extra></extra>"
            ),
            customdata=[[s["price"], s.get("pattern","—")] for s in buys],
        ), row=1, col=1)

    # ── SELL signals — clean triangles only, no text clutter ──
    sells = [s for s in signals if s["type"]=="SELL"]
    if sells:
        fig.add_trace(go.Scatter(
            x=[s["ts"] for s in sells],
            y=[s["price"] * 1.004 for s in sells],
            mode="markers",
            marker=dict(
                symbol="triangle-down", size=13, color="#ff4d6d",
                line=dict(color="#07090f", width=1),
            ),
            name="SELL",
            hovertemplate=(
                "<b style='color:#ff4d6d'>▼ SELL</b><br>"
                "Price: ₹%{customdata[0]:.2f}<br>"
                "Reason: %{customdata[1]}<extra></extra>"
            ),
            customdata=[[s["price"], s.get("pattern","—")] for s in sells],
        ), row=1, col=1)

    # ── RSI ──
    if "rsi" in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["rsi"].astype(float),
            line=dict(color="#a78bfa", width=1.5),
            name="RSI", showlegend=False,
        ), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,77,109,0.4)",  row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="rgba(0,212,170,0.4)",   row=2, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.1)", row=2, col=1)

    # ── MACD ──
    if "macd" in df.columns and "macd_hist" in df.columns:
        hist_vals = df["macd_hist"].astype(float).fillna(0)
        bar_colors = ["rgba(0,212,170,0.7)" if v >= 0 else "rgba(255,77,109,0.7)"
                      for v in hist_vals]
        fig.add_trace(go.Bar(
            x=df.index, y=hist_vals,
            marker_color=bar_colors, name="Histogram", showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["macd"].astype(float),
            line=dict(color="#3b8eff", width=1.2),
            name="MACD", showlegend=False,
        ), row=3, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["macd_sig"].astype(float),
            line=dict(color="#f4a935", width=1.2),
            name="Signal", showlegend=False,
        ), row=3, col=1)

    fig.update_layout(**CHART_LAYOUT, height=560)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig

def build_swing_chart(sym: str) -> go.Figure:
    df = fetch_history(sym, "3mo")
    if df.empty:
        fig = go.Figure()
        fig.update_layout(**CHART_LAYOUT, height=400,
                          title=dict(text="No data available", font=dict(color="#7a9bc0")))
        return fig

    df = compute_indicators(df)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.7, 0.3], vertical_spacing=0.05)

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"].astype(float),
        high=df["high"].astype(float),
        low=df["low"].astype(float),
        close=df["close"].astype(float),
        increasing=dict(line=dict(color="#00d4aa", width=1)),
        decreasing=dict(line=dict(color="#ff4d6d", width=1)),
        name="Price", showlegend=False,
    ), row=1, col=1)

    for col, color, name in [
        ("sma50","#3b8eff","50 DMA"),
        ("sma200","#a78bfa","200 DMA"),
        ("ema9","#f4a935","EMA 9"),
    ]:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col].astype(float),
                line=dict(color=color, width=1.3), name=name,
            ), row=1, col=1)

    if "bb_upper" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_upper"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)",width=1), name="BB Upper", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["bb_lower"].astype(float),
            line=dict(color="rgba(59,142,255,0.35)",width=1),
            fill="tonexty", fillcolor="rgba(59,142,255,0.05)",
            name="BB Lower", showlegend=False), row=1, col=1)

    if "rsi" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["rsi"].astype(float),
            line=dict(color="#a78bfa",width=1.5), name="RSI", showlegend=False), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="rgba(255,77,109,0.4)", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="rgba(0,212,170,0.4)",  row=2, col=1)

    fig.update_layout(**CHART_LAYOUT, height=500)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#4e6a8a")
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig

# ─── UI COMPONENTS ────────────────────────────────────────────────────────────

def render_header(user: dict | None = None):
    open_ = is_market_open()
    now   = datetime.now(IST).strftime("%d %b %Y  %H:%M IST")
    badge = ('<span class="mkt-open">● LIVE · NSE/BSE</span>'
             if open_ else '<span class="mkt-closed">● MARKET CLOSED</span>')
    user_html = ""
    if user:
        first = user.get("name","").split()[0] if user.get("name") else ""
        user_html = (f'<span style="font-family:DM Mono,monospace;font-size:11px;'
                     f'color:#7a9bc0">Welcome, <strong style="color:#00d4aa">{first}</strong></span>')
    st.markdown(f"""
    <div class="hdr">
      <div style="display:flex;align-items:center;gap:10px">
        <div style="width:32px;height:32px;background:#00d4aa;border-radius:8px;
             display:flex;align-items:center;justify-content:center;
             font-family:'Syne',sans-serif;font-size:12px;font-weight:800;color:#07090f">TG</div>
        <span class="logo">Trading<span>Genie</span> AI</span>
      </div>
      <div style="display:flex;align-items:center;gap:14px">
        {user_html}
        {badge}
        <span style="font-family:'DM Mono',monospace;font-size:10px;color:#4e6a8a">{now}</span>
      </div>
    </div>""", unsafe_allow_html=True)

def render_index_cards(indices: list[dict]):
    if not indices:
        st.info("Fetching index data…")
        return
    cols = st.columns(len(indices))
    for col, idx in zip(cols, indices):
        pct = _scalar(idx.get("change_pct"))
        chg = _scalar(idx.get("change"))
        price = _scalar(idx.get("price"))
        up  = (pct or 0) >= 0
        cls = "up" if up else "dn"
        col_hex = "#00d4aa" if up else "#ff4d6d"
        arrow   = "▲" if up else "▼"
        pct_str = f"{arrow} {abs(pct):.2f}%" if pct is not None else "—"
        chg_str = f"({chg:+.2f})"          if chg is not None else ""
        price_str = f"{price:,.2f}"         if price is not None else "—"
        with col:
            st.markdown(f"""
            <div class="idx-card {cls}">
              <div class="idx-label">{idx['label']}</div>
              <div class="idx-price" style="color:{col_hex}">{price_str}</div>
              <div class="idx-chg"  style="color:{col_hex}">{pct_str} {chg_str}</div>
            </div>""", unsafe_allow_html=True)

def render_technicals(nifty: dict):
    if not nifty:
        st.info("No Nifty data.")
        return
    p   = _scalar(nifty.get("price"))
    pct = _scalar(nifty.get("change_pct"))
    h   = _scalar(nifty.get("high"))
    l   = _scalar(nifty.get("low"))
    pc  = _scalar(nifty.get("prev_close"))
    yh  = _scalar(nifty.get("year_high"))
    yl  = _scalar(nifty.get("year_low"))
    bias_cls  = "tbull" if (pct or 0)>=0 else "tbear"
    bias_txt  = "BULLISH" if (pct or 0)>=0 else "BEARISH"
    rows = [
        ("Last Price",  fp(p),  ""),
        ("Day Change",  fpc(pct), f'<span class="tbadge {bias_cls}">{bias_txt}</span>'),
        ("Day High",    fp(h),  ""),
        ("Day Low",     fp(l),  ""),
        ("Prev Close",  fp(pc), ""),
        ("52W High",    fp(yh), ""),
        ("52W Low",     fp(yl), ""),
    ]
    html = '<div class="tech-block">'
    for lbl, val, badge in rows:
        html += f'<div class="tr"><span class="tl">{lbl}</span><span class="tv">{val}</span>{badge}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

def render_news_card(item: dict):
    s = item["sentiment"]
    cls   = {"bull":"bull","bear":"bear","neutral":"neu"}.get(s,"neu")
    label = {"bull":"BULLISH","bear":"BEARISH","neutral":"NEUTRAL"}.get(s,"NEUTRAL")
    imp   = ('<span class="nb hi">🔥 HIGH IMPACT</span> '
             if item.get("impact",0) >= 2 else "")
    link  = item.get("link","#")
    read  = (f'<a href="{link}" target="_blank" style="color:#3b8eff;font-size:9px;float:right;text-decoration:none">↗ Read</a>'
             if link != "#" else "")
    st.markdown(f"""
    <div class="nc">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
        <span class="nb {cls}">{label}</span>{imp}
        <span style="margin-left:auto;font-family:'DM Mono',monospace;font-size:9px;
              color:#4e6a8a;font-style:italic">{item.get('source','')}</span>
        {read}
      </div>
      <div class="nt">{item['title']}</div>
      <div class="nm">{time_ago(item.get('date',''))}</div>
    </div>""", unsafe_allow_html=True)

def render_screener_card(row, idx: int):
    buy    = row["action"] == "BUY"
    cls    = "buy" if buy else "sell"
    sig_c  = "sig-buy" if buy else "sig-sell"
    conf   = row.get("conf","LOW")
    cc_map = {"HIGH":"#00d4aa","MEDIUM":"#f4a935","LOW":"#7a9bc0"}
    c_col  = cc_map.get(conf,"#7a9bc0")
    pct    = float(row.get("change_pct",0) or 0)
    pct_c  = "#00d4aa" if pct>=0 else "#ff4d6d"
    st.markdown(f"""
    <div class="sc-card {cls}">
      <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap">
        <span style="font-family:'Syne',sans-serif;font-size:14px;font-weight:800;color:#dde8f8">
          #{idx+1} {row['symbol'].replace('.NS','')}
        </span>
        <span class="{sig_c}">{row['action']}</span>
        <span style="font-family:'DM Mono',monospace;font-size:8px;padding:2px 6px;border-radius:3px;
              background:rgba(255,255,255,.05);color:{c_col};border:1px solid {c_col}44">{conf}</span>
        <span style="margin-left:auto;font-family:'DM Mono',monospace;font-size:13px;
              font-weight:700;color:#dde8f8">{fp(row['price'])}</span>
        <span style="font-family:'DM Mono',monospace;font-size:10px;color:{pct_c}">{fpc(pct)}</span>
      </div>
      <div style="font-size:10px;color:#7a9bc0;margin:3px 0">{row['name']} · {row['sector']}</div>
      <div class="lvg">
        <div class="lv"><div class="ll">Entry</div><div class="lv2" style="color:#dde8f8">{fp(row['entry'])}</div></div>
        <div class="lv"><div class="ll">Stop Loss</div><div class="lv2" style="color:#ff4d6d">{fp(row['sl'])}</div></div>
        <div class="lv"><div class="ll">Target</div><div class="lv2" style="color:#00d4aa">{fp(row['target'])}</div></div>
      </div>
      <div style="font-size:10px;color:#7a9bc0;margin-top:7px;border-top:1px solid rgba(255,255,255,.07);padding-top:5px">
        📊 {row['reason']}
      </div>
    </div>""", unsafe_allow_html=True)

# ─── TABS ────────────────────────────────────────────────────────────────────

def tab_home():
    with st.container():
        st.markdown('<div style="padding:1rem 1.5rem">', unsafe_allow_html=True)

        # Market closed banner
        if not is_market_open():
            st.markdown("""
            <div style="background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.2);
                 border-radius:8px;padding:7px 14px;margin-bottom:.75rem;
                 font-family:'DM Mono',monospace;font-size:11px;color:#ff4d6d">
              🔴  MARKET CLOSED — Showing last available data.
              NSE/BSE trading hours: Mon–Fri 9:15 AM – 3:30 PM IST
            </div>""", unsafe_allow_html=True)

        hc, hr = st.columns([5,1])
        with hc:
            st.markdown('<div class="sec">Market Indices</div>', unsafe_allow_html=True)
        with hr:
            if st.button("⟳ Refresh", key="h_rf"):
                st.cache_data.clear(); st.rerun()

        with st.spinner("Loading indices…"):
            indices = fetch_indices()
        render_index_cards(indices)

        left, right = st.columns([1, 2], gap="medium")

        with left:
            st.markdown('<div class="sec">Nifty 50 · Technicals</div>', unsafe_allow_html=True)
            nifty = next((i for i in indices if i["symbol"]=="^NSEI"), None)
            render_technicals(nifty)

            st.markdown('<div class="sec">Institutional Flows</div>', unsafe_allow_html=True)
            f1,f2,f3 = st.columns(3)
            with f1: st.metric("FII Net","₹672 Cr","Net Buyers")
            with f2: st.metric("DII Net","₹410 Cr","Net Buyers")
            with f3: st.metric("India VIX","13.40","↓ Low")

        with right:
            st.markdown('<div class="sec">Market News — sorted by impact</div>',
                        unsafe_allow_html=True)
            with st.spinner("Fetching news…"):
                news = fetch_news()

            PAGE = 10
            pages = max(1, (len(news) + PAGE - 1) // PAGE)
            pg = st.session_state.get("news_pg", 0)

            # Page tabs
            pg_cols = st.columns(pages)
            for i, pc in enumerate(pg_cols):
                with pc:
                    if st.button(f"Page {i+1}", key=f"np_{i}",
                                 type="primary" if i==pg else "secondary"):
                        st.session_state["news_pg"] = i; st.rerun()

            for item in news[pg*PAGE:(pg+1)*PAGE]:
                render_news_card(item)

        st.markdown("</div>", unsafe_allow_html=True)

def tab_screener():
    with st.container():
        st.markdown('<div style="padding:1rem 1.5rem">', unsafe_allow_html=True)
        st.markdown("""
        <div class="disc">⚠️ <strong style="color:#ff4d6d">Advisory:</strong>
        AI-assisted signals for <strong>educational purposes only</strong>. Not investment advice.
        Consult a SEBI-registered advisor before trading.</div>
        """, unsafe_allow_html=True)
        st.markdown('<div style="height:.75rem"></div>', unsafe_allow_html=True)

        st1, st2 = st.tabs(["📈  Swing  (Weekly refresh)", "⚡  Intraday  (Daily refresh)"])

        for mode, tab in [("swing",st1),("intraday",st2)]:
            with tab:
                ic, irf = st.columns([4,1])
                with ic:
                    label = "7 days" if mode=="swing" else "24 hours"
                    st.markdown(
                        f'<div class="sec">Top 20 · Under ₹1,000 · Price ↑ · Refreshes every {label}</div>',
                        unsafe_allow_html=True)
                with irf:
                    if st.button("⟳ Rescan", key=f"rs_{mode}"):
                        (run_swing_screener if mode=="swing" else run_intraday_screener).clear()
                        st.rerun()

                with st.spinner(f"Running {mode} screener…"):
                    df = run_swing_screener() if mode=="swing" else run_intraday_screener()

                if df.empty:
                    st.warning("Screener is loading data. Market data may not be available yet. Try Force Rescan.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

                # Summary metrics
                m1,m2,m3,m4 = st.columns(4)
                buys = len(df[df["action"]=="BUY"])
                sells= len(df[df["action"]=="SELL"])
                hi   = len(df[df["conf"]=="HIGH"])
                with m1: st.metric("Total",  len(df))
                with m2: st.metric("BUY",    buys,  delta=f"+{buys}")
                with m3: st.metric("SELL",   sells, delta=f"-{sells}", delta_color="inverse")
                with m4: st.metric("High Conf", hi)

                # Filter
                filt = st.session_state.get(f"filt_{mode}", "ALL")
                fa,fb,fc = st.columns([1,1,4])
                with fa:
                    if st.button("All",      key=f"fa_{mode}"): st.session_state[f"filt_{mode}"]="ALL";  filt="ALL"
                with fb:
                    if st.button("BUY only", key=f"fb_{mode}"): st.session_state[f"filt_{mode}"]="BUY";  filt="BUY"

                filtered = df if filt=="ALL" else df[df["action"]==filt]

                col_l, col_r = st.columns(2, gap="small")
                for i, (_, row) in enumerate(filtered.iterrows()):
                    with (col_l if i%2==0 else col_r):
                        render_screener_card(row, i)

        st.markdown("</div>", unsafe_allow_html=True)

def tab_charts():
    with st.container():
        st.markdown('<div style="padding:1rem 1.5rem">', unsafe_allow_html=True)

        options = [f"{s[0].replace('.NS','')} — {s[1]}" for s in STOCK_UNIVERSE]
        c1,c2,c3 = st.columns([3,1,1])
        with c1:
            sel = st.selectbox("Stock", options, label_visibility="collapsed", key="ch_sel")
        with c2:
            mode = st.selectbox("Mode", ["Intraday (5m)","Swing (Daily)"],
                                label_visibility="collapsed", key="ch_mode")
        with c3:
            if st.button("⟳ Refresh Chart", key="ch_rf"):
                fetch_intraday.clear(); fetch_history.clear(); st.rerun()

        sym_short = sel.split(" — ")[0]
        sym = sym_short + ".NS"
        meta = next((s for s in STOCK_UNIVERSE if s[0]==sym), None)
        name = meta[1] if meta else sym_short
        sec  = meta[2] if meta else ""

        with st.spinner("Loading quote…"):
            q = fetch_stock_quote(sym)

        # Quote bar
        if q:
            pct   = _scalar(q.get("change_pct"))
            up    = (pct or 0) >= 0
            arrow = "▲" if up else "▼"
            col_h = "#00d4aa" if up else "#ff4d6d"
            qa,qb,qc,qd,qe,qf = st.columns([3,1,1,1,1,1])
            with qa:
                st.markdown(f"""
                <div style="padding:.4rem 0">
                  <div style="font-family:'Syne',sans-serif;font-size:1.3rem;
                       font-weight:800;color:#dde8f8">{sym_short}</div>
                  <div style="font-size:10px;color:#7a9bc0;margin-top:2px">{name} · {sec}</div>
                </div>""", unsafe_allow_html=True)
            with qb: st.metric("LTP",       fp(q.get("price")),
                                f"{arrow} {fpc(pct)}")
            with qc: st.metric("Day High",  fp(q.get("high")))
            with qd: st.metric("Day Low",   fp(q.get("low")))
            with qe: st.metric("Prev Close",fp(q.get("prev_close")))
            with qf: st.metric("52W High",  fp(q.get("year_high")))

        is_intraday = "Intraday" in mode

        if is_intraday:
            with st.spinner(f"Loading intraday chart for {sym_short}…"):
                df_raw = fetch_intraday(sym, "5m")
                if not df_raw.empty:
                    df_ind = compute_indicators(df_raw)
                    sigs   = detect_signals(df_ind)
                else:
                    df_ind = pd.DataFrame()
                    sigs   = []
            fig = build_intraday_chart(sym, sigs)
            st.plotly_chart(fig, width='stretch')

            if sigs:
                buys  = [s for s in sigs if s["type"]=="BUY"]
                sells = [s for s in sigs if s["type"]=="SELL"]
                last  = sigs[-1]
                lc    = "#00d4aa" if last["type"]=="BUY" else "#ff4d6d"
                sa,sb,sc_ = st.columns(3)
                with sa:
                    st.markdown(f"""
                    <div style="background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.2);
                         border-radius:10px;padding:12px;text-align:center">
                      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#7a9bc0">BUY SIGNALS</div>
                      <div style="font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;
                           color:#00d4aa">{len(buys)}</div>
                    </div>""", unsafe_allow_html=True)
                with sb:
                    st.markdown(f"""
                    <div style="background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.2);
                         border-radius:10px;padding:12px;text-align:center">
                      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#7a9bc0">SELL SIGNALS</div>
                      <div style="font-family:'Syne',sans-serif;font-size:2rem;font-weight:800;
                           color:#ff4d6d">{len(sells)}</div>
                    </div>""", unsafe_allow_html=True)
                with sc_:
                    st.markdown(f"""
                    <div style="background:#111827;border:1px solid rgba(255,255,255,.08);
                         border-radius:10px;padding:12px">
                      <div style="font-family:'DM Mono',monospace;font-size:9px;color:#7a9bc0">LATEST SIGNAL</div>
                      <div style="font-family:'Syne',sans-serif;font-size:1rem;font-weight:800;
                           color:{lc};margin-top:4px">{last['type']} · {last['pattern']}</div>
                      <div style="font-family:'DM Mono',monospace;font-size:11px;color:#7a9bc0">
                        @ {fp(last['price'])}</div>
                    </div>""", unsafe_allow_html=True)

                # Signal log
                st.markdown('<div class="sec" style="margin-top:.8rem">Signal Log (last 15)</div>',
                            unsafe_allow_html=True)
                def _fmt_ts_ist(ts):
                    """Format timestamp as IST HH:MM — handles tz-naive (already IST) or tz-aware."""
                    try:
                        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                            ts = ts.astimezone(IST).replace(tzinfo=None)
                        return ts.strftime("%H:%M IST") if hasattr(ts, "strftime") else str(ts)
                    except Exception:
                        return str(ts)

                sig_rows = [{
                    "Time (IST)": _fmt_ts_ist(s["ts"]),
                    "Signal":     s["type"],
                    "Indicators": s.get("pattern", "—"),
                    "Score":      s.get("score", "—"),
                    "Price":      fp(s["price"]),
                } for s in sigs[-15:]][::-1]
                st.dataframe(pd.DataFrame(sig_rows), width='content', hide_index=True)

            elif not df_raw.empty:
                st.info("No signals detected in today's data. Market may be pre-open or data is insufficient for pattern detection.")
            else:
                st.warning("No intraday data available. This may be a pre-market hour or the symbol has no data today.")

            # Live indicator bar
            if not df_ind.empty and len(df_ind) >= 5:
                st.markdown('<div class="sec" style="margin-top:.5rem">Live Indicators</div>',
                            unsafe_allow_html=True)
                last_row = df_ind.iloc[-1]
                i1,i2,i3,i4,i5 = st.columns(5)
                def safe_ind(r, col):
                    v = r.get(col, np.nan) if hasattr(r,"get") else r[col] if col in r.index else np.nan
                    try: return round(float(v),2)
                    except: return None

                with i1: st.metric("RSI (14)", safe_ind(last_row,"rsi") or "—")
                with i2: st.metric("VWAP",     fp(safe_ind(last_row,"vwap")))
                with i3: st.metric("EMA 9",    fp(safe_ind(last_row,"ema9")))
                with i4: st.metric("EMA 21",   fp(safe_ind(last_row,"ema21")))
                with i5: st.metric("ATR",      safe_ind(last_row,"atr") or "—")

        else:  # Swing chart
            with st.spinner(f"Loading daily chart for {sym_short}…"):
                fig = build_swing_chart(sym)
            st.plotly_chart(fig, width='stretch')

            df_s = fetch_history(sym, "3mo")
            if not df_s.empty:
                df_s = compute_indicators(df_s)
                last = df_s.iloc[-1]
                st.markdown('<div class="sec">Key Technical Levels</div>', unsafe_allow_html=True)
                l1,l2,l3,l4,l5,l6 = st.columns(6)
                def gl(col):
                    v = last.get(col) if hasattr(last,"get") else (last[col] if col in last.index else None)
                    return fp(_scalar(v))
                def gr(col):
                    v = last.get(col) if hasattr(last,"get") else (last[col] if col in last.index else None)
                    r = _scalar(v)
                    return f"{r:.1f}" if r is not None else "—"

                with l1: st.metric("50-Day MA",   gl("sma50"))
                with l2: st.metric("200-Day MA",  gl("sma200"))
                with l3: st.metric("EMA 9",       gl("ema9"))
                with l4: st.metric("BB Upper",    gl("bb_upper"))
                with l5: st.metric("BB Lower",    gl("bb_lower"))
                with l6: st.metric("RSI (14)",    gr("rsi"))

        st.markdown("</div>", unsafe_allow_html=True)

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # ── Guard: show auth page if not logged in ──
    if not is_logged_in():
        render_auth_page()
        st.stop()

    # ── Logged-in user ──
    user = get_current_user()

    if "news_pg" not in st.session_state:
        st.session_state["news_pg"] = 0

    # Sidebar — user info + sign out
    with st.sidebar:
        initials = "".join(w[0].upper() for w in user.get("name","U").split()[:2])
        mobile_disp = user.get("mobile","")
        mobile_disp = f"+91 {mobile_disp[:5]} {mobile_disp[5:]}" if mobile_disp else "—"
        st.markdown(f"""
        <div style="padding:.85rem;background:#0d1520;border-radius:12px;
             border:1px solid rgba(255,255,255,.1);margin-bottom:.75rem;text-align:center">
          <div style="width:44px;height:44px;border-radius:50%;background:#00d4aa;
               margin:0 auto .6rem;display:flex;align-items:center;justify-content:center;
               font-family:'Syne',sans-serif;font-size:15px;font-weight:800;color:#07090f">
            {initials}
          </div>
          <div style="font-family:'Syne',sans-serif;font-size:14px;font-weight:700;
               color:#dde8f8">{user.get("name","")}</div>
          <div style="font-family:'DM Mono',monospace;font-size:9px;
               color:#7a9bc0;margin-top:4px">{user.get("email","")}</div>
          <div style="font-family:'DM Mono',monospace;font-size:9px;
               color:#4e6a8a;margin-top:2px">{mobile_disp}</div>
          <div style="font-family:'DM Mono',monospace;font-size:8px;color:#2d4a6a;
               margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,.06)">
            Member since {user.get("created_at","")[:10] if user.get("created_at") else "—"}
          </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="font-family:'DM Mono',monospace;font-size:8px;color:#4e6a8a;
             text-transform:uppercase;letter-spacing:.08em;margin-bottom:.35rem">Navigation</div>
        """, unsafe_allow_html=True)

        if st.button("🚪  Sign Out", width='content', key="sb_signout"):
            _logout_user()

        st.markdown("""
        <div style="margin-top:1.5rem;font-family:'DM Mono',monospace;font-size:8px;
             color:#2d4a6a;text-align:center;line-height:1.6">
          For educational use only<br>Not investment advice
        </div>""", unsafe_allow_html=True)

    render_header(user)

    t1, t2, t3 = st.tabs(["📊  Home", "🔍  Screener", "📈  Charts"])
    with t1: tab_home()
    with t2: tab_screener()
    with t3: tab_charts()

if __name__ == "__main__":
    main()