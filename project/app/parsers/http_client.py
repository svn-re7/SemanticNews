from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import ParserHttpStatusError, ParserNetworkError

# User-Agent для сетевых запросов к внешним источникам.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


# Эта модель отделяет сетевой слой от логики парсинга HTML/XML:
# парсер получает уже загруженный документ, а не сырой response.
@dataclass
class FetchedDocument:
    """Результат загрузки внешнего документа по HTTP."""

    # Итоговый URL после возможных редиректов.
    url: str
    # Текстовый ответ сервера.
    text: str
    # HTTP-статус ответа.
    status_code: int
    # Content-Type ответа, если он указан сервером.
    content_type: str | None


def create_retry_session() -> requests.Session:
    """Создать HTTP-сессию с повторными попытками для временных сетевых сбоев."""
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_document(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> FetchedDocument:
    """Загрузить внешний документ и вернуть его содержимое с базовыми метаданными."""
    # Если внешняя сессия не передана, создаем ее локально
    # и закрываем в конце этой функции.
    own_session = session is None
    session = session or create_retry_session()

    try:
        # На этом уровне нормализуем только сетевые и HTTP-ошибки,
        # чтобы верхние слои работали уже с понятными parser-исключениями.
        try:
            response = session.get(url, timeout=timeout)
        except requests.RequestException as error:
            raise ParserNetworkError(f"Сетевая ошибка при загрузке ресурса: {error}", url=url) from error

        if response.status_code != 200:
            raise ParserHttpStatusError(
                f"Ресурс вернул неподходящий HTTP-статус: {response.status_code}",
                url=url,
                status_code=response.status_code,
            )

        return FetchedDocument(
            url=response.url,
            text=response.text,
            status_code=response.status_code,
            content_type=response.headers.get("Content-Type"),
        )
    finally:
        if own_session:
            session.close()
