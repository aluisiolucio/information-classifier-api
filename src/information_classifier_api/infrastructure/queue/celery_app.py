from celery import Celery

from ..config.settings import get_settings

_settings = get_settings()

celery_app = Celery(
    "information_classifier_api",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["information_classifier_api.infrastructure.queue.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
)
