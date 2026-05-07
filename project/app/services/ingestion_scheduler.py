from __future__ import annotations

import logging
from threading import Event, Lock, Thread
from typing import Callable, Protocol


logger = logging.getLogger(__name__)

DEFAULT_CHECK_INTERVAL_SECONDS = 60 * 5


class SchedulerThread(Protocol):
    """Минимальный интерфейс thread-объекта, который нужен scheduler-у."""

    def start(self) -> None:
        """Запустить поток."""

    def is_alive(self) -> bool:
        """Проверить, продолжает ли поток работать."""


ThreadFactory = Callable[..., SchedulerThread]
IngestionCheck = Callable[[], bool]


class IngestionScheduler:
    """Периодически запускать умный авто-scheduling ingestion, пока живо приложение."""

    def __init__(
        self,
        *,
        check_interval_seconds: float = DEFAULT_CHECK_INTERVAL_SECONDS,
        ingestion_check: IngestionCheck,
        stop_event: Event | None = None,
        thread_factory: ThreadFactory = Thread,
    ) -> None:
        self.check_interval_seconds = check_interval_seconds
        self.ingestion_check = ingestion_check
        self.stop_event = stop_event or Event()
        self.thread_factory = thread_factory
        self._lock = Lock()
        self._thread: SchedulerThread | None = None

    def start(self) -> bool:
        """Запустить scheduler-thread один раз за процесс."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            self._thread = self.thread_factory(target=self._run_loop, daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        """Попросить scheduler-loop завершиться."""
        self.stop_event.set()

    def _run_loop(self) -> None:
        """Периодически дергать существующий умный запуск ingestion."""
        while not self.stop_event.wait(self.check_interval_seconds):
            try:
                # Сам scheduler не решает, какие источники собирать: это делает IngestionService.
                self.ingestion_check()
            except Exception:
                # Ошибка scheduler-а не должна ронять desktop-приложение.
                logger.exception("Ошибка периодического автообновления новостей.")


_default_scheduler: IngestionScheduler | None = None
_default_scheduler_lock = Lock()


def start_ingestion_scheduler(ingestion_check: IngestionCheck) -> bool:
    """Запустить общий scheduler периодического автообновления новостей."""
    global _default_scheduler

    with _default_scheduler_lock:
        if _default_scheduler is None:
            _default_scheduler = IngestionScheduler(ingestion_check=ingestion_check)

    return _default_scheduler.start()


def stop_ingestion_scheduler() -> None:
    """Остановить общий scheduler периодического автообновления новостей."""
    if _default_scheduler is not None:
        _default_scheduler.stop()
