"""可替换的本地任务队列。生产部署可替换为外部队列而不影响编排层。"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Callable


class InProcessTaskQueue:
    """持久化状态由 repository 保存，线程池只负责本进程调度。"""

    def __init__(self, handler: Callable[[str], object], *, max_workers: int = 2) -> None:
        self._handler = handler
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="document-parser")
        self._futures: dict[str, Future[object]] = {}
        self._lock = Lock()

    def submit(self, parse_id: str) -> Future[object]:
        with self._lock:
            existing = self._futures.get(parse_id)
            if existing is not None and not existing.done():
                return existing
            future = self._executor.submit(self._handler, parse_id)
            self._futures[parse_id] = future
            return future

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)
