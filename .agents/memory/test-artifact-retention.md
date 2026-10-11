---
name: Test artifact retention safety
description: Evidence retention must not guess whether historical or interrupted runs are disposable.
---

Cleanup is explicitly opt-in for deletion and must keep evidence when run
completion or writer ownership is unknown. A later successful check does not
replace the most recent failure evidence. Keep the latest failure for each
individual check, not just one failure for an aggregate runner. Do not weaken
these protections to meet a disk budget.

**Why:** Historical capture folders lack reliable completion/owner information;
logs and screenshots alone cannot distinguish finished evidence from an active
or interrupted run. Losing the last failure would prevent investigating it.
A newer failure in a different check cannot replace the older check's evidence,
even when both checks were launched by the same aggregate runner.

**How to apply:** Retention changes should preserve unknown historical runs and
report unmet budgets plainly. Any scheduler should retain the same exclusions
and require an explicit operational choice before enabling actual deletion.

The operator approved a 30-day / 2048-MiB / 24-hour periodic policy. This is
policy approval, not blanket permission to apply deletions or change limits.
Require an inspected, successful dry-run and explicit apply opt-in. Audit logs
remain outside evidence cleanup; their automatic pruning needs separate consent.

**Why:** The operator selected these exact limits and cadence after being told
that size pressure may remove eligible results still within the age window,
but protected evidence remains even if the budget cannot be met.

**How to apply:** Keep future defaults consistent with these choices unless
the operator changes them; a changed policy requires a fresh dry-run review.
