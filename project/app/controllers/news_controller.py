from __future__ import annotations

from flask import Blueprint, abort, render_template, request

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

    return render_template("news/detail.html", news_item=news_item)
