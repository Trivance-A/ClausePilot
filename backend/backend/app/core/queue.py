"""Redis + RQ 작업 큐. FastAPI 요청 스레드는 여기 job을 enqueue만 하고, 실제 실행은
별도 `rq worker` 프로세스(docker-compose의 worker 서비스)가 담당한다.
Job 함수(app/services/pipeline.py)는 UUID 인자만 받고 자체적으로 새 DB 세션을 여는
형태라 RQ 직렬화(pickle) 요건과 그대로 맞는다."""

from redis import Redis
from rq import Queue

from app.core.config import settings

_redis = Redis.from_url(settings.redis_url)
default_queue = Queue("default", connection=_redis, is_async=settings.queue_async)
