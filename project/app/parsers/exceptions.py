from __future__ import annotations


# Исключения выделены отдельно, чтобы сервисы могли различать
# сетевые ошибки, проблемы XML и ошибки извлечения контента.
class ParserError(Exception):
    """Базовое исключение парсера."""

    # Короткий машинный код ошибки парсера.
    code = "parser_error"

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class ParserNetworkError(ParserError):
    """Сетевая ошибка при загрузке внешнего ресурса."""

    code = "network_error"


class ParserHttpStatusError(ParserError):
    """Ошибка HTTP-статуса при загрузке внешнего ресурса."""

    code = "http_status_error"

    def __init__(self, message: str, *, url: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message, url=url)
        self.status_code = status_code


class ParserXmlError(ParserError):
    """Ошибка разбора XML-документа sitemap."""

    code = "xml_parse_error"


class ParserContentError(ParserError):
    """Ошибка извлечения содержимого статьи из HTML."""

    code = "content_error"
