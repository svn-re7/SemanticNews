from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from app.services.source_service import SourceService


source_bp = Blueprint("sources", __name__, url_prefix="/sources")


@source_bp.get("")
@source_bp.get("/")
def sources_page():
    """Показать страницу управления источниками."""
    return render_template(
        "sources/index.html",
        sources_page=SourceService().get_sources_page(),
        error_message=None,
    )


@source_bp.post("")
@source_bp.post("/")
def create_source():
    """Создать новый источник из формы UI."""
    service = SourceService()
    try:
        service.create_source(
            name=request.form.get("name", ""),
            base_url=request.form.get("base_url", ""),
            source_type_id=int(request.form.get("source_type_id", "0")),
        )
    except ValueError as error:
        # При ошибке валидации остаемся на странице и показываем понятное сообщение.
        return (
            render_template(
                "sources/index.html",
                sources_page=service.get_sources_page(),
                error_message=str(error),
            ),
            400,
        )

    return redirect(url_for("sources.sources_page"))


@source_bp.post("/<int:source_id>/active")
def update_source_activity(source_id: int):
    """Переключить активность источника."""
    # В форме передается строка true/false, чтобы кнопка явно задавала следующее состояние.
    is_active = request.form.get("is_active") == "true"
    SourceService().update_source_activity(source_id=source_id, is_active=is_active)
    return redirect(url_for("sources.sources_page"))


@source_bp.post("/<int:source_id>/delete")
def delete_source(source_id: int):
    """Удалить источник вместе со статьями и связанными результатами поиска."""
    SourceService().delete_source(source_id=source_id)
    return redirect(url_for("sources.sources_page"))
