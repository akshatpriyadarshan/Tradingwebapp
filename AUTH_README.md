# TradingGenie AI — Auth System Documentation

## What was added to app.py

### Architecture
- **Database**: SQLite via Python's built-in `sqlite3` — zero extra packages, works on
  Streamlit Community Cloud. DB file lives at `/tmp/tradinggenie_users.db`.
- **No new pip packages required** for core auth. Twilio is optional for real SMS.
- **OTP validity**: 6-digit code, expires in 5 minutes, single-use.
- **Password storage**: SHA-256 hashed — never stored in plain text.

---

## User Flow

### Sign Up (3 steps)
```
Step 1 → Name + Email + Confirm Email
         ↓ (validations pass)
Step 2 → Mobile number → OTP sent → Verify OTP
         ↓ (OTP verified)
Step 3 → Set Password + Confirm Password → Account created → Auto login
```

### Sign In (2 steps)
```
Step 1 → Email OR Mobile → Choose: Password  or  OTP
         ↓
Step 2a → Enter password → Login
Step 2b → OTP sent → Enter OTP → Login
```

---

## Validations Applied

### Email
- Regex format check: `user@domain.tld`
- Max length: 254 chars total, 64 chars local part
- No consecutive dots (`..`)
- Cannot start or end with dot
- Both fields must match (confirm email)
- Checked against existing accounts

### Mobile
- Accepts: `9876543210`, `+91 98765 43210`, `091-98765-43210`
- Auto-stripped to 10 digits
- Must start with 6, 7, 8, or 9
- Checked against existing accounts

### Password
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 number

### Name
- 2–80 characters
- Letters, spaces, dots, hyphens only

---

## OTP Delivery

### Default (Dev Mode — no config needed)
When no secrets are configured, the OTP is displayed **directly on screen** in
an amber box labelled "Dev Mode OTP". This is intentional for local development
and testing.

### Production — Real SMS via Twilio
1. Install Twilio: add `twilio>=8.0.0` to `requirements.txt`
2. Create `.streamlit/secrets.toml`:

```toml
[twilio]
account_sid  = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
auth_token   = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
from_number  = "+1xxxxxxxxxx"   # your Twilio number
```

3. On Streamlit Cloud: Settings → Secrets → paste the same content.

### Production — Real Email OTP via Gmail SMTP
```toml
[smtp]
host     = "smtp.gmail.com"
port     = 587
user     = "yourapp@gmail.com"
password = "xxxx xxxx xxxx xxxx"   # Gmail App Password (not your Gmail password)
```

> To generate a Gmail App Password:
> Google Account → Security → 2-Step Verification → App passwords → Create

When SMTP is configured, OTP login via email will send a real email.
When Twilio is configured, OTP login via mobile will send a real SMS.
Both can be configured simultaneously.

---

## Database Schema

### `users` table
| Column        | Type    | Notes                          |
|---------------|---------|--------------------------------|
| id            | INTEGER | Auto-increment primary key     |
| name          | TEXT    | Full name                      |
| email         | TEXT    | Unique, stored lowercase       |
| mobile        | TEXT    | Unique, 10-digit cleaned       |
| password_hash | TEXT    | SHA-256 hash                   |
| created_at    | TEXT    | UTC ISO timestamp              |

### `otp_store` table
| Column      | Type    | Notes                              |
|-------------|---------|-------------------------------------|
| id          | INTEGER | Auto-increment                      |
| identifier  | TEXT    | Email or mobile number              |
| otp         | TEXT    | 6-digit code                        |
| purpose     | TEXT    | "signup" or "login"                |
| expires_at  | TEXT    | UTC ISO, 5 min after generation    |
| used        | INTEGER | 0 = active, 1 = consumed/expired  |

---

## Session State Keys Used

| Key                  | Value                                      |
|----------------------|--------------------------------------------|
| `auth_user`          | `dict` of logged-in user row (or `None`)  |
| `auth_mode`          | `"login"` or `"signup"`                   |
| `auth_page`          | `"login"` or `"app"`                      |
| `signup_step`        | `1`, `2`, or `3`                          |
| `signup_data`        | Partial form data across steps             |
| `signup_mobile_sent` | `bool` — OTP sent state                   |
| `login_step`         | `1` or `2`                                |
| `login_user`         | User dict found in DB                     |
| `login_via`          | `"email"` or `"mobile"`                   |
| `login_use_otp`      | `bool`                                    |
| `dev_otp`            | OTP shown on screen when no SMS/email cfg |

---

## Streamlit Cloud — Data Persistence Note

SQLite at `/tmp/tradinggenie_users.db` **resets** when Streamlit Cloud restarts
the app (typically after ~1 hour of inactivity or on redeployment).

For persistent user storage across restarts, replace the SQLite functions with
one of these free-tier options:

| Option              | Free Tier | Setup                              |
|---------------------|-----------|------------------------------------|
| **Supabase**        | 500 MB    | PostgreSQL, REST API, Python SDK   |
| **PlanetScale**     | 5 GB      | MySQL-compatible                   |
| **MongoDB Atlas**   | 512 MB    | Document DB, `pymongo`             |
| **Streamlit KV**    | Built-in  | `st.session_state` only (no persist)|

For a quick Supabase drop-in replacement, the only functions to update are:
`_get_conn()`, `_init_db()`, `_create_user()`, `_get_user_by_email()`,
`_get_user_by_mobile()`, `_user_exists_email()`, `_user_exists_mobile()`,
`_generate_otp()`, `_verify_otp()`.

---

## requirements.txt additions needed

```
# Already in your requirements.txt — no changes needed for core auth
# Optional: add this only if using Twilio SMS
twilio>=8.0.0
```
