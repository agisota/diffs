from __future__ import annotations

from celery import Celery

from .pipeline import run_batch, rerender_compare, rerender_full
from .settings import REDIS_URL

celery_app = Celery("docdiffops", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_track_started = True
celery_app.conf.result_expires = 60 * 60 * 24

# Priority queues: high = short tasks (rerender-compare), low = long tasks
# (run_batch, rerender-full). Workers listen to both; routing happens here.
celery_app.conf.task_default_queue = "low"
celery_app.conf.task_routes = {
    "docdiffops.run_batch": {"queue": "low"},
    "docdiffops.rerender_full": {"queue": "low"},
    "docdiffops.rerender_compare": {"queue": "high"},
}


@celery_app.task(name="docdiffops.run_batch", bind=True)
def run_batch_task(self, batch_id: str, profile: str = "fast"):
    from .batch_lock import release
    try:
        return run_batch(batch_id, profile=profile, task=self)
    finally:
        release(batch_id)


@celery_app.task(name="docdiffops.rerender_compare", bind=True)
def rerender_compare_task(self, batch_id: str):
    from .batch_lock import release
    try:
        return rerender_compare(batch_id, task=self)
    finally:
        release(batch_id)


@celery_app.task(name="docdiffops.rerender_full", bind=True)
def rerender_full_task(self, batch_id: str):
    from .batch_lock import release
    try:
        return rerender_full(batch_id, task=self)
    finally:
        release(batch_id)
