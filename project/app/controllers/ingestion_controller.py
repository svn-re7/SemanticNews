from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock, Thread

from flask import Blueprint, jsonify, render_template

from app.services.ingestion_service import IngestionResult, IngestionService


ingestion_bp = Blueprint("ingestion", __name__, url_prefix="/ingestion")


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
    with _task_lock:
        if _task_state.is_running:
            should_start = False
        else:
            should_start = True
            _task_state.is_running = True
            _task_state.started_at = datetime.now()
            _task_state.finished_at = None
            _task_state.message = "Сбор новостей запущен."
            _task_state.results = []
            _task_state.error = None
            _task_state.mode = None
            _task_state.article_count_before = None

    if not should_start:
        return jsonify(_serialize_state(started=False))

    # Сбор и построение embeddings могут занять время, поэтому не блокируем HTTP-запрос.
    thread = Thread(target=_run_ingestion_task, daemon=True)
    thread.start()
    return jsonify(_serialize_state(started=True)), 202


@ingestion_bp.get("/status")
def ingestion_status():
    """Вернуть текущий статус ingestion для polling из интерфейса."""
    return jsonify(_serialize_state())


def _run_ingestion_task() -> None:
    """Выполнить ingestion всех активных источников и обновить in-memory статус."""
    try:
        scheduled_result = IngestionService().run_scheduled_ingestion()
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
        _task_state.message = (
            f"Сбор завершен в режиме {scheduled_result.mode}: "
            f"сохранено={saved_total}, проиндексировано={indexed_total}."
        )
        _task_state.error = None


def _serialize_state(*, started: bool | None = None) -> dict:
    """Подготовить статус ingestion к JSON-ответу."""
    with _task_lock:
        payload = {
            "is_running": _task_state.is_running,
            "started_at": _format_datetime(_task_state.started_at),
            "finished_at": _format_datetime(_task_state.finished_at),
            "message": _task_state.message,
            "error": _task_state.error,
            "mode": _task_state.mode,
            "article_count_before": _task_state.article_count_before,
            "results": [
                {
                    "source_id": result.source_id,
                    "found": result.found,
                    "saved": result.saved,
                    "indexed": result.indexed,
                    "skipped_duplicates": result.skipped_duplicates,
                    "skipped_empty_text": result.skipped_empty_text,
                    "skipped_missing_type": result.skipped_missing_type,
                }
                for result in _task_state.results
            ],
        }

    if started is not None:
        payload["started"] = started
    return payload


def _format_datetime(value: datetime | None) -> str | None:
    """Отформатировать datetime для JSON-статуса."""
    return value.strftime("%d.%m.%Y %H:%M:%S") if value is not None else None
