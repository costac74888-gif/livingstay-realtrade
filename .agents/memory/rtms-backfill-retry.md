---
name: RTMS backfill 429 & retry strategy
description: Why the 5yr RTMS backfill stalls on older years and the strategy chosen to fill it slowly.
---

# RTMS backfill rate-limit (429) & retry strategy

The public data.go.kr RTMS API returns HTTP 429 in bursts once the **daily call quota
is exhausted**. A full 60-month backfill across all sgg burns the quota, so the older
months never insert — symptom: transactions only reach back ~2 years despite `--months 60`.

**Key decision — back off BETWEEN rounds, not per-item.**
When the daily quota is dead, every request 429s. Per-item exponential backoff would
spend ~a day hammering a dead quota for zero rows. Strategy instead: a retry *round*
aborts after N consecutive 429s (quota-exhausted signal) and the driver backs off
between rounds (minutes → hours cap), so it resumes naturally when the quota resets the
next day. This is the "천천히 채워지면 됨" (fill slowly) behavior the user wanted.

**Where the failure queue lives:** a `sync_failures` table created lazily by `sync_batch.py`
itself (deliberately NOT in db.py, to keep db.py untouched). Normal sync records 429s
there and clears an entry on success; `--retry-failures` consumes only that queue.

**Why no row-level locking:** run as a *single* detached low-priority worker, so no
claim/lock is needed; `transactions.raw_key` ON CONFLICT makes re-processing idempotent.
If you ever run multiple workers or overlap with scheduled sync, add
`FOR UPDATE SKIP LOCKED` claiming to avoid duplicate API calls worsening 429.

**Operational:** deal_date is TEXT 'YYYY-MM-DD' (year = LEFT(deal_date,4)). `--sleep`
(0.5–1.0s) spaces requests to avoid tripping 429 in the first place.
