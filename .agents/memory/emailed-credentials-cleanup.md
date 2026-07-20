---
name: emailed credentials vs test-data cleanup
description: Why deleting test accounts after sending real credential emails breaks user logins
---

Rule: If a verification test sends real credentials (temp password SMS/email) to the user's actual address, do NOT delete the created account afterward — the user will try to log in with those credentials and fail, looking like a bug (e.g. suspected "duplicate email" that was actually a deleted account).

**Why:** 2026-07-20 loan-consultant login failure report: two test approvals emailed temp passwords to the user, then the accounts were cleaned up as test data → emailed passwords became invalid.

**How to apply:** Either use a throwaway email for disposable test rows, or keep the final approved account and tell the user which email/password is the live one. loan_consultants now has UNIQUE(email) + LOWER(email) pre-approval check + login ORDER BY approved_at DESC safety net.
