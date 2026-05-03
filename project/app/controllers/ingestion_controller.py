from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock, Thread

from flask import Blueprint, jsonify, render_template

from app.repositories.source_repository import SourceRepository
from app.services.ingestion_service import IngestionResult, IngestionService


ingestion_bp = Blueprint("ingestion", __name__, url_prefix="/ingestion")
INGESTION_MAX_WORKERS = 4


@dataclass
class IngestionTaskState:
    """In-memory статус фонового ingestion для локального desktop-приложения."""

    is_running: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str = "Сбор новостей еще не запускался."
    results: list[IngestionResult] = field(default_factory=list)
    error: str | None = None
    mode: str | None = None
    article_count_before: int | None = None
    should_stop: bool = False
    stopped: bool = False
    run_kind: str = "scheduled"


_task_state = IngestionTaskState()
_task_lock = Lock()


@ingestion_bp.get("")
@ingestion_bp.get("/")
def ingestion_page():
    """Показать страницу ручного запуска ingestion."""
    return render_template("ingestion/index.html")


@ingestion_bp.post("/start")
def start_ingestion():
    """Запустить ingestion в фоне и сразу вернуть управление UI."""
    started = _start_background_ingestion("Сбор новостей запущен.", run_kind="scheduled")
    if not started:
        return jsonify(_serialize_state(started=False))

    return jsonify(_serialize_state(started=True)), 202


@ingestion_bp.post("/start-full")
def start_full_ingestion():
    """Запустить полный initial-сбор с игнорированием checkpoint источников."""
    started = _start_background_ingestion(
        "Полный сбор новостей запущен. Checkpoint источников будет проигнорирован.",
        run_kind="full",
    )
    if not started:
        return jsonify(_serialize_state(started=False))

    return jsonify(_serialize_state(started=True)), 202


def start_auto_ingestion_if_needed() -> bool:
    """Запустить автоматический ingestion при старте приложения, если данные устарели."""
    service = IngestionService()
    if not service.should_run_auto_ingestion():
        return False

    return _start_background_ingestion("Автообновление новостей запущено.", run_kind="scheduled")


def _start_background_ingestion(start_message: str, *, run_kind: str) -> bool:
    """Запустить общий фоновый ingestion, если другая задача еще не выполняется."""
    with _task_lock:
        if _task_state.is_running:
            return False

        _task_state.is_running = True
        _task_state.started_at = datetime.now()
        _task_state.finished_at = None
        _task_state.message = start_message
        _task_state.results = []
        _task_state.error = None
        _task_state.mode = None
        _task_state.article_count_before = None
        _task_state.should_stop = False
        _task_state.stopped = False
        _task_state.run_kind = run_kind

    # Сбор и построение embeddings могут занять время, поэтому не блокируем HTTP-запрос.
    thread = Thread(target=_run_ingestion_task, daemon=True)
    thread.start()
    return True


@ingestion_bp.post("/stop")
def stop_ingestion():
    """Запросить мягкую остановку текущего фонового ingestion."""
    with _task_lock:
        if _task_state.is_running:
            _task_state.should_stop = True
            _task_state.message = "Запрошена остановка сбора. Текущая пачка будет завершена."

    return jsonify(_serialize_state())


@ingestion_bp.get("/status")
def ingestion_status():
    """Вернуть текущий статус ingestion для polling из интерфейса."""
    return jsonify(_serialize_state())


def _run_ingestion_task() -> None:
    """Выполнить ingestion всех активных источников и обновить in-memory статус."""
    with _task_lock:
        run_kind = _task_state.run_kind

    try:
        if run_kind == "full":
            # Полный ручной сбор использует initial-параметры независимо от размера текущей базы.
            scheduled_result = IngestionService().run_scheduled_ingestion(
                initial_article_threshold=10**12,
                initial_articles_per_source=1000,
                max_workers=INGESTION_MAX_WORKERS,
                should_stop=_should_stop_requested,
            )
        else:
            scheduled_result = IngestionService().run_scheduled_ingestion(
                max_workers=INGESTION_MAX_WORKERS,
                should_stop=_should_stop_requested,
            )
    except Exception as error:
        # В фоне нельзя отдавать traceback пользователю, поэтому сохраняем краткую причину в статус.
        with _task_lock:
            _task_state.is_running = False
            _task_state.finished_at = datetime.now()
            _task_state.error = str(error)
            _task_state.message = "Сбор новостей завершился с ошибкой."
        return

    results = scheduled_result.results
    saved_total = sum(result.saved for result in results)
    indexed_total = sum(result.indexed for result in results)
    with _task_lock:
        _task_state.is_running = False
        _task_state.finished_at = datetime.now()
        _task_state.results = results
        _task_state.mode = scheduled_result.mode
        _task_state.article_count_before = scheduled_result.article_count_before
        _task_state.stopped = scheduled_result.stopped
        if scheduled_result.stopped:
            _task_state.message = (
                f"Сбор остановлен пользователем в режиме {scheduled_result.mode}: "
                f"сохранено={saved_total}, проиндексировано={indexed_total}."
            )
        else:
            _task_state.message = (
                f"Сбор завершен в режиме {scheduled_result.mode}: "
                f"сохранено={saved_total}, проиндексировано={indexed_total}."
            )
        _task_state.error = None


def _should_stop_requested() -> bool:
    """Проверить, запросил ли пользователь мягкую остановку фоновой задачи."""
    with _task_lock:
        return _task_state.should_stop


def _serialize_state(*, started: bool | None = None) -> dict:
    """Подготовить статус ingestion к JSON-ответу."""
    with _task_lock:
        # Под lock только копируем in-memory статус, чтобы не держать его во время чтения SQLite.
        results = list(_task_state.results)
        is_running = _task_state.is_running
        started_at = _task_state.started_at
        finished_at = _task_state.finished_at
        message = _task_state.message
        error = _task_state.error
        mode = _task_state.mode
        article_count_before = _task_state.article_count_before
        should_stop = _task_state.should_stop
        stopped = _task_state.stopped
        run_kind = _task_state.run_kind

    source_names = _source_names_by_id(results)
    payload = {
        "is_running": is_running,
        "started_at": _format_datetime(started_at),
        "finished_at": _format_datetime(finished_at),
        "message": message,
        "error": error,
        "mode": mode,
        "article_count_before": article_count_before,
        "should_stop": should_stop,
        "stopped": stopped,
        "run_kind": run_kind,
        "results": [
            _serialize_result(result, source_names)
            for result in results
        ],
    }

    if started is not None:
        payload["started"] = started
    return payload


def _source_names_by_id(results: list[IngestionResult]) -> dict[int, str]:
    """Прочитать имена источников из БД для отображения итогов сбора."""
    source_ids = {result.source_id for result in results}
    if not source_ids:
        return {}

    # Контроллер не ходит в ORM напрямую: имена берутся через repository-слой.
    return {
        source.id: source.name
        for source in SourceRepository().list_sources()
        if source.id in source_ids
    }


def _serialize_result(result: IngestionResult, source_names: dict[int, str]) -> dict:
    """Подготовить один результат ingestion к JSON-ответу."""
    return {
        "source_id": result.source_id,
        "source_name": (
            source_names.get(result.source_id)
            or result.source_name
            or result.source_base_url
        ),
        "source_base_url": result.source_base_url,
        "found": result.found,
        "saved": result.saved,
        "indexed": result.indexed,
        "skipped_duplicates": result.skipped_duplicates,
        "skipped_empty_text": result.skipped_empty_text,
        "skipped_low_quality_text": result.skipped_low_quality_text,
        "skipped_missing_type": result.skipped_missing_type,
    }


def _format_datetime(value: datetime | None) -> str | None:
    """Отформатировать datetime для JSON-статуса."""
    return value.strftime("%d.%m.%Y %H:%M:%S") if value is not None else None
