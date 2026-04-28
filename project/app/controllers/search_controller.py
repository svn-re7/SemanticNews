from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from app.models.dto import SearchResponseDTO
from app.services.search_service import SearchService


search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.get("")
@search_bp.get("/")
def search_page():
    """Показать форму семантического поиска и результаты по запросу."""
    # Контроллер работает только с HTTP-параметрами и шаблоном, а сам поиск делегирует сервису.
    query_text = request.args.get("q", default="", type=str).strip()
    search_result: SearchResponseDTO | None = None
    error_message: str | None = None

    if query_text:
        try:
            # top_k фиксируем на уровне UI, чтобы пользовательский ввод пока не усложнял сценарий.
            search_result = SearchService().search(query_text, top_k=10)
        except (FileNotFoundError, ValueError) as error:
            # Пользователю показываем понятную причину, а не технический traceback Flask.
            error_message = str(error)

    return render_template(
        "search/index.html",
        query_text=query_text,
        search_result=search_result,
        error_message=error_message,
    )


@search_bp.get("/results/<int:request_id>")
def saved_search_results(request_id: int):
    """Показать ранее сохраненную выдачу без повторного семантического поиска."""
    try:
        search_result = SearchService().get_saved_results(request_id)
    except ValueError:
        abort(404)

    return render_template(
        "search/index.html",
        query_text=search_result.query_text,
        search_result=search_result,
        error_message=None,
    )


@search_bp.get("/history")
def search_history():
    """Показать историю поисковых запросов с переходом к сохраненным результатам."""
    # История не запускает embedding и FAISS: она читает только таблицу Request.
    page = request.args.get("page", default=1, type=int)
    if page < 1:
        page = 1

    history_page = SearchService().get_search_history(page=page, per_page=20)
    return render_template("search/history.html", history_page=history_page)
