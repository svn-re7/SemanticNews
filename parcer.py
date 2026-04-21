import requests
import xml.etree.ElementTree as ET
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
import json
import re
from bs4 import BeautifulSoup
from typing import Optional

# User-Agent для запросов
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

def _build_session() -> requests.Session:
    """Создает session с повторными попытками для временных сетевых сбоев."""
    session = requests.Session()
    retries = Retry(
        total=3, # Максимальное количество попыток
        connect=3, # Максимальное количество попыток соединения
        read=3, # Максимальное количество попыток чтения
        backoff_factor=1.0, # Паузы между попытками
        status_forcelist=(429, 500, 502, 503, 504), # Статусы, при которых будет повторяться попытка
        allowed_methods=("GET",), # Методы, при которых будет повторяться попытка
    )
    adapter = HTTPAdapter(max_retries=retries) # Создаем адаптер для сессии
    session.mount("http://", adapter) # Монтируем адаптер для HTTP
    session.mount("https://", adapter) # Монтируем адаптер для HTTPS
    session.headers.update(
        {
            "User-Agent": USER_AGENT
        }
    )
    return session

def extract_sitemap_urls(sitemap_index_url: str, limit: int = 10) -> list[dict]:
    """Извлекает URL-адреса sitemap-файлов из файла sitemap.xml."""
    # Получаем файл sitemap-индекса
    session = _build_session()
    try:
        response = session.get(sitemap_index_url, timeout=20)
    except requests.RequestException as e:
        print(f"Сетевая ошибка при получении sitemap.xml: {e}")
        return []

    # Проверяем, успешно ли получен файл sitemap.xml
    if response.status_code != 200:
        print(f'Ошибка при получении sitemap.xml: {response.status_code}')
        return []
    
    # Парсим XML-документ
    root = ET.fromstring(response.text)

    # Определяем пространство имен для тега <loc>
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

    sitemap_urls = []

    for loc_element in root.findall('.//ns:loc', ns):
        url = loc_element.text

        date_start = None
        date_end = None

        # Извлекаем дату начала
        if 'date_start' in url:
            date_start_index = url.find('date_start=') + len('date_start=')
            date_start_end = url.find('&', date_start_index) if '&' in url[date_start_index:] else len(url)
            date_start = datetime.strptime(url[date_start_index:date_start_end], '%Y%m%d')

        # Извлекаем дату конца
        if 'date_end' in url:
            date_end_index = url.find('date_end=') + len('date_end=')
            date_end_end = url.find('&', date_end_index) if '&' in url[date_end_index:] else len(url)
            date_end = datetime.strptime(url[date_end_index:date_end_end], '%Y%m%d')

        # Добавляем URL в список
        sitemap_urls.append({'url': url, 'date_start': date_start, 'date_end': date_end})
       
        if len(sitemap_urls) >= limit: # Если достигли лимита, то выходим из цикла
            break

    return sitemap_urls # Возвращаем список URL-адресов

def _parse_iso_date(date_str):
    """Преобразует ISO 8601 дату в datetime (без часового пояса)"""
    # Удаляем часовой пояс (всё после + или Z) для простоты
    if '+' in date_str:
        date_str = date_str.split('+')[0]
    elif date_str.endswith('Z'):
        date_str = date_str[:-1]
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")

def extract_article_urls_from_sitemap(sitemap_url: str) -> list[dict]:
    """Извлекает URL-адреса статей из sitemap-файла."""
    # Получаем файл sitemap-файла
    session = _build_session()
    try:
        response = session.get(sitemap_url, timeout=20)
    except requests.RequestException as e:
        print(f"Сетевая ошибка при получении sitemap.xml: {e}")
        return []

    # Проверяем, успешно ли получен файл sitemap.xml
    if response.status_code != 200:
        print(f'Ошибка при получении sitemap.xml: {response.status_code}')
        return []
    
    # Парсим XML-документ
    root = ET.fromstring(response.text)

    # Определяем пространство имен для тега <url>
    ns = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

    article_urls = []

    # Внутри каждого <url> ищем <loc> и <lastmod>
    for url_element in root.findall('.//ns:url', ns):
        loc_element = url_element.find('ns:loc', ns)
        lastmod_element = url_element.find('ns:lastmod', ns)
        
        if loc_element is None:
            continue  # нет ссылки — пропускаем
        
        article_url = loc_element.text
        
        # Преобразуем дату, если она есть
        lastmod = None
        if lastmod_element is not None and lastmod_element.text:
            lastmod = _parse_iso_date(lastmod_element.text)
        
        article_urls.append({
            'url': article_url,
            'lastmod': lastmod
        })

    return article_urls # Возвращаем список URL-адресов статей

def collect_all_articles(sitemap_urls_list: list[dict], max_articles=100) -> list[dict]:
    """Собирает все статьи из списка sitemap-файлов."""
    all_articles = []
    for sitemap_url in sitemap_urls_list:
        article_urls = extract_article_urls_from_sitemap(sitemap_url['url'])
        all_articles.extend(article_urls) # Добавляем статьи из текущего sitemap-файла в общий список
        if len(all_articles) >= max_articles: # Если достигли лимита, то выходим из цикла
            break
    return all_articles[:max_articles] # Возвращаем список статей

def _extract_date_from_html(soup: BeautifulSoup) -> Optional[datetime]:
    """Пытается извлечь дату публикации из HTML (meta, time, JSON-LD)."""
    candidate_values = []

    # Часто используемые meta-поля для даты публикации
    meta_selectors = [
        ("property", "article:published_time"),
        ("property", "article:modified_time"),
        ("name", "pubdate"),
        ("name", "publish_date"),
        ("name", "date"),
        ("name", "datePublished"),
        ("itemprop", "datePublished"),
        ("itemprop", "dateModified"),
    ]

    # Перебираем заранее отобранные meta-selectors, чтобы попытаться найти дату публикации в мета-тегах HTML
    for attr_name, attr_value in meta_selectors:
        # Ищем тег <meta> с нужным атрибутом (например, property="article:published_time")
        tag = soup.find("meta", attrs={attr_name: attr_value})
        # Если нашли нужный тег и в нем присутствует атрибут content — добавляем его значение в кандидаты на дату
        if tag and tag.get("content"):
            candidate_values.append(tag["content"])

    # Ищем тег <time>, который может содержать дату публикации
    time_tag = soup.find("time")
    # Сначала пытаемся извлечь значение из атрибута datetime, если он есть
    if time_tag and time_tag.get("datetime"):
        candidate_values.append(time_tag["datetime"])
    # Если datetime нет, добавляем содержимое тега <time> как потенциальную дату
    elif time_tag and time_tag.get_text(strip=True):
        candidate_values.append(time_tag.get_text(strip=True))

    # Перебираем все <script type="application/ld+json">
    for script_tag in soup.find_all("script", type="application/ld+json"):
        # Получаем исходный JSON-текст; .string вернет None если содержимое не строка, тогда берем get_text(strip=True)
        raw_json = script_tag.string or script_tag.get_text(strip=True)
        if not raw_json:
            continue 
        try:
            # Пытаемся распарсить JSON
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            # Если блок невалидный, пропускаем
            continue

        # Если JSON — список объектов, разбираем все; иначе упаковываем в список
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            # Проходимся по известным ключам, где обычно хранятся даты публикации или модификации
            for key in ("datePublished", "dateModified", "uploadDate"):
                value = node.get(key)
                if isinstance(value, str):
                    # Если нашли строковое значение ключа — добавляем его в кандидаты
                    candidate_values.append(value)
   

    for value in candidate_values:
        try:
            return _parse_iso_date(value)
        except (ValueError, TypeError):
            continue
    return None

def _extract_text_from_html(soup: BeautifulSoup) -> str:
    """Извлекает основной текст статьи через <article>, затем через <p>."""
    # Удаляем шумные элементы, чтобы меньше мусора попало в текст
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Пытаемся найти тег <article>
    article_tag = soup.find("article")
    if article_tag:
        # Извлекаем текст из <article>, разделяя блоки пробелами и удаляя лишние пробелы
        article_text = article_tag.get_text(" ", strip=True)
        article_text = re.sub(r"\s+", " ", article_text).strip()
        if article_text:
            return article_text

    # Собираем все абзацы <p> длиной больше 40 символов
    paragraphs = []
    for p_tag in soup.find_all("p"):
        # Извлекаем текст абзаца, убираем лишние пробелы
        text = p_tag.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        # Добавляем только достаточно длинные абзацы
        if len(text) > 40:
            paragraphs.append(text)
    # Склеиваем все собранные абзацы в одну строку через перевод строки
    return "\n".join(paragraphs)

def _extract_text_from_article_blocks(soup: BeautifulSoup) -> str:
    """
    Дополнительный извлекатель для страниц формата:
    <div class="article__block" data-type="text"><div class="article__text">...</div></div>
    """
    # Создаем список для хранения фрагментов текста статьи
    chunks = []
    # Находим все блоки формата <div class="article__block" data-type="text">
    for block in soup.find_all("div", class_="article__block", attrs={"data-type": "text"}):
        # Внутри блока ищем элемент с текстом статьи <div class="article__text">
        text_node = block.find("div", class_="article__text")
        if not text_node:
            continue  # если текстовый блок не найден, пропускаем
        # Получаем текст внутри блока, нормализуем пробелы
        chunk = text_node.get_text(" ", strip=True)
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if chunk:
            chunks.append(chunk)  # добавляем непустой фрагмент текста
    # Склеиваем все найденные фрагменты через перевод строки
    return "\n".join(chunks)

def extract_article_content(article_url: str) -> Optional[dict]:
    """
    Получает HTML-страницу статьи и возвращает: url, title, text, published_at
    """
    
    # Создаем сессию для HTTP-запроса с повторными попытками
    session = _build_session()
    try:
        # Пытаемся загрузить HTML страницы статьи
        response = session.get(article_url, timeout=20)
    except requests.RequestException as e:
        # Обрабатываем ошибку сети
        print(f"Сетевая ошибка при получении статьи: {e}")
        return None

    # Проверяем успешность получения страницы
    if response.status_code != 200:
        print(f"Ошибка при получении статьи: {response.status_code}")
        return None

    # Парсим HTML с помощью BeautifulSoup
    soup = BeautifulSoup(response.text, "html.parser")

    # Пытаемся определить заголовок статьи
    title = None
    og_title = soup.find("meta", attrs={"property": "og:title"})
    if og_title and og_title.get("content"):
        # Если есть <meta property="og:title"> — берем его
        title = og_title["content"].strip()
    elif soup.title and soup.title.string:
        # Если есть <title> — берем его
        title = soup.title.string.strip()
    elif soup.find("h1"):
        # В крайнем случае берем текст из первого <h1>
        title = soup.find("h1").get_text(" ", strip=True)

    # Извлекаем текст статьи: основной извлекатель
    text = _extract_text_from_html(soup)
    if not text:
        # альтернативный
        text = _extract_text_from_article_blocks(soup)
    # Извлекаем дату публикации
    published_at = _extract_date_from_html(soup)

    # Если не удалось извлечь заголовок и текст — возвращаем None
    if not title and not text:
        return None

    # Возвращаем словарь с результатами извлечения
    return {
        "url": article_url,
        "title": title,
        "text": text,
        "published_at": published_at,
    }

def collect_article_contents_from_sitemap_index(
    sitemap_index_url: str,
    sitemap_limit: int = 5,
    max_articles: int = 10) -> list[dict]:
    """
    1) Получить sitemap-URL из sitemap-индекса
    2) Получить URL статей из sitemap-файлов
    3) Скачать HTML каждой статьи и извлечь контент
    """
    # Получаем список sitemap-ов из sitemap-индекса
    sitemap_urls = extract_sitemap_urls(sitemap_index_url, limit=sitemap_limit)
    if not sitemap_urls:
        # Если не удалось получить sitemap — возвращаем пустой список
        return []

    # Собираем ссылки на статьи из всех найденных sitemap-ов
    article_refs = collect_all_articles(sitemap_urls, max_articles=max_articles)
    if not article_refs:
        # Если не смогли собрать ссылки на статьи — возвращаем пустой список
        return []

    articles_content = []
    # Проходим по каждой найденной статье
    for article_ref in article_refs:
        article_url = article_ref.get("url")
        if not article_url:
            # Если в словаре нет ключа url — пропускаем запись
            continue

        # Извлекаем контент статьи по ее URL
        article_content = extract_article_content(article_url)
        if article_content is None:
            # Если не удалось извлечь — пропускаем статью
            continue

        # Если дата публикации не извлечена из HTML,
        # подставляем lastmod из sitemap-а
        if article_content.get("published_at") is None:
            article_content["published_at"] = article_ref.get("lastmod")

        # Добавляем результат в общий список
        articles_content.append(article_content)

        # Если достигнуто максимальное число статей — останавливаем сбор
        if len(articles_content) >= max_articles:
            break

    # Возвращаем результаты
    return articles_content

if __name__ == "__main__":
    sitemap_index_url = "https://ria.ru/sitemap_article_index.xml"
    articles = collect_article_contents_from_sitemap_index(
        sitemap_index_url=sitemap_index_url,
        sitemap_limit=1,
        max_articles=10
    )

    print(f"\nНайдено статей: {len(articles)}")
    print("=" * 80)

    for i, article in enumerate(articles, 1):
        print(f"{i}. URL: {article.get('url')}")
        print(f"   TITLE: {article.get('title')}")
        print(f"   PUBLISHED_AT: {article.get('published_at')}")
        text = article.get("text") or ""
        preview = text[:350] + ("..." if len(text) > 350 else "")
        print(f"   TEXT: {preview}")
        print("-" * 80)
