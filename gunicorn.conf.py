"""Gunicorn lifecycle hooks for the preloaded application."""


timeout = 120
workers = 2
preload_app = True


def post_fork(server, worker):
    """Start each fork's private cache worker without blocking worker readiness."""
    from app import start_master_stats_worker

    try:
        start_master_stats_worker()
        server.log.info("worker %s started master stats warmup", worker.pid)
    except Exception:
        # Starting the best-effort worker must not prevent the web worker from
        # serving the cold-start COUNT summary.
        server.log.exception(
            "worker %s could not start master stats warmup; continuing",
            worker.pid,
        )