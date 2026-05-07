import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.services.ingestion_scheduler import IngestionScheduler  # noqa: E402


class FakeEvent:
    """Тестовая замена threading.Event с управляемым числом итераций."""

    def __init__(self, stop_after_waits: int) -> None:
        self.stop_after_waits = stop_after_waits
        self.wait_calls: list[float] = []

    def wait(self, timeout: float) -> bool:
        """Запомнить интервал ожидания и остановить цикл после заданного числа вызовов."""
        self.wait_calls.append(timeout)
        return len(self.wait_calls) >= self.stop_after_waits

    def set(self) -> None:
        """Имитировать внешний сигнал остановки."""
        self.stop_after_waits = 0


class ImmediateThread:
    """Тестовый поток, который запускает target синхронно."""

    created_count = 0

    def __init__(self, *, target, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        ImmediateThread.created_count += 1

    def start(self) -> None:
        """Сразу выполнить target, чтобы тест не создавал реальный background thread."""
        self.started = True
        self.target()

    def is_alive(self) -> bool:
        """После синхронного выполнения тестовый поток считается завершенным."""
        return False


class AliveThread:
    """Тестовый поток, который остается 'живым' после старта."""

    created_count = 0

    def __init__(self, *, target, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon
        self.started = False
        AliveThread.created_count += 1

    def start(self) -> None:
        """Не выполнять target, а только отметить старт фонового потока."""
        self.started = True

    def is_alive(self) -> bool:
        """Имитировать уже работающий scheduler-thread."""
        return True


class IngestionSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        ImmediateThread.created_count = 0
        AliveThread.created_count = 0

    def test_loop_runs_ingestion_check_on_each_tick_until_stop(self) -> None:
        """Scheduler должен вызывать умный ingestion-check на каждом периодическом tick."""
        calls: list[str] = []
        event = FakeEvent(stop_after_waits=3)
        scheduler = IngestionScheduler(
            check_interval_seconds=123.0,
            ingestion_check=lambda: calls.append("check") or True,
            stop_event=event,
            thread_factory=ImmediateThread,
        )

        started = scheduler.start()

        self.assertTrue(started)
        self.assertEqual(calls, ["check", "check"])
        self.assertEqual(event.wait_calls, [123.0, 123.0, 123.0])

    def test_start_is_idempotent_while_thread_is_alive(self) -> None:
        """Повторный start не должен создавать второй scheduler-thread."""
        scheduler = IngestionScheduler(
            check_interval_seconds=60.0,
            ingestion_check=lambda: True,
            stop_event=FakeEvent(stop_after_waits=1),
            thread_factory=AliveThread,
        )

        first_started = scheduler.start()
        second_started = scheduler.start()

        self.assertTrue(first_started)
        self.assertFalse(second_started)
        self.assertEqual(AliveThread.created_count, 1)

    def test_stop_sets_event(self) -> None:
        """stop должен передать scheduler-loop сигнал завершения."""
        event = FakeEvent(stop_after_waits=10)
        scheduler = IngestionScheduler(
            check_interval_seconds=60.0,
            ingestion_check=lambda: True,
            stop_event=event,
            thread_factory=AliveThread,
        )

        scheduler.stop()

        self.assertEqual(event.stop_after_waits, 0)


if __name__ == "__main__":
    unittest.main()
