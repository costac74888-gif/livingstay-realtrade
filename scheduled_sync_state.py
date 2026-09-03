"""Shared advisory-lock identity and dashboard reconciliation helpers."""

STAGE_ACTIVITY_LOCK_BASE = 9_282_990


def stage_activity_lock_id(stage_keys, stage_key):
    """Return the unique liveness lock for one scheduled-sync stage."""
    return STAGE_ACTIVITY_LOCK_BASE + tuple(stage_keys).index(stage_key)


def stage_displayed_running(
    *,
    reports_running,
    active_locks,
    stage_keys,
    stage_key,
):
    """Require this exact stage's liveness lock before displaying running."""
    if active_locks is None:
        return bool(reports_running)
    return bool(
        reports_running
        and stage_activity_lock_id(stage_keys, stage_key) in active_locks
    )


def reconcile_stage_state(*, state, age_seconds, stale_seconds, lock_active):
    """Turn persisted running into stale when heartbeat or liveness is gone."""
    if state != "running":
        return state
    if lock_active is False:
        return "stale"
    if age_seconds is not None and float(age_seconds) > stale_seconds:
        return "stale"
    return state