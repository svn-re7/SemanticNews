from __future__ import annotations

from flask import Blueprint, abort, render_template, request, url_for

from app.services.news_service import NewsService


news_bp = Blueprint("news", __name__, url_prefix="/news")


@news_bp.get("/")
def news_list():
    """Показать список сохраненных новостей."""
    # Контроллер читает только параметры HTTP-запроса, а подготовку данных делегирует сервису.
    page = max(request.args.get("page", default=1, type=int), 1)
    per_page = 20

    news_page = NewsService().get_news_page(page=page, per_page=per_page)

    return render_template(
        "news/list.html",
        news_page=news_page,
    )


@news_bp.get("/<int:article_id>")
def news_detail(article_id: int):
    """Показать карточку одной новости."""
    news_item = NewsService().get_news_detail(article_id)
    if news_item is None:
        abort(404)

    # В desktop-окне нет привычной браузерной стрелки назад, поэтому явно строим ссылку возврата.
    return_url = url_for("news.news_list")
    return_label = "К списку новостей"
    if request.args.get("return_to") == "search":
        request_id = request.args.get("request_id", default=None, type=int)
        return_url = (
            url_for("search.saved_search_results", request_id=request_id)
            if request_id is not None
            else url_for("search.search_page")
        )
        return_label = "К результатам поиска"

    return render_template(
        "news/detail.html",
        news_item=news_item,
        return_url=return_url,
        return_label=return_label,
    )
