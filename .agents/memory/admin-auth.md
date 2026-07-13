---
name: Admin auth model
description: How the /admin login/session/password-change works and its testing pitfalls
---

Admin authentication is `admin_users` table based (email/password, werkzeug hashes), NOT the old single ADMIN_ACCESS_KEY (that path was removed).

- Session keys: `session["admin"]=True` gates `require_admin`; `session["admin_user_id"]` identifies the row (used by password change). Rest of /api/admin/* only checks `session["admin"]`.
- Login: POST /api/admin/login {email,password} → check_password_hash → sets both session keys + updates last_login_at. Failure returns a UNIFIED 401 ("이메일 또는 비밀번호가 올바르지 않습니다") to avoid leaking whether an email exists.
- Password change: PUT /api/admin/password (require_admin) confirms current pw + requires new pw ≥8 chars; on success client logs out and forces re-login.

**Seed (db.py `_seed_admin_user`, called from init_db):** inserts one row email='ADMIN'/pw 'ADMIN'/role super_admin ONLY when admin_users is completely empty. Uses `INSERT ... SELECT ... WHERE NOT EXISTS (SELECT 1 FROM admin_users)` — atomic, never overwrites an existing account, never seeds per-missing-email.
**Why:** requirement is "if any admin row exists, do nothing"; ON CONFLICT(email) would wrongly insert ADMIN into a non-empty table.

**Testing pitfall:** login is rate-limited "5 per minute; 30 per hour" (flask-limiter memory:// per-process). Rapid curl re-login tests hit 429. To reset, restart the app workflow (new process). To restore a password without spending login attempts, update password_hash directly in DB via generate_password_hash.
