from __future__ import annotations

from celery import Celery

from .pipeline import run_batch
from .settings import REDIS_URL

celery_app = Celery("docdiffops", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_track_started = True
celery_app.conf.result_expires = 60 * 60 * 24


@celery_app.task(name="docdiffops.run_batch")
def run_batch_task(batch_id: str, profile: str = "fast"):
    return run_batch(batch_id, profile=profile)
