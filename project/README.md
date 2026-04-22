# SemanticNews

`SemanticNews` — локальное десктопное приложение для накопления, хранения и последующего семантического поиска новостей.

Текущий стек проекта:

- backend: `Flask`
- интерфейс: `HTML + Jinja2 + Bootstrap`
- desktop-оболочка: `pywebview`
- хранилище данных: `SQLite`
- ORM: `SQLAlchemy`
- парсинг статей: `requests`, `BeautifulSoup`, `trafilatura`, `htmldate`
- будущий семантический поиск: `sentence-transformers` + `FAISS`

## Что уже есть

- Flask application factory в `app/__init__.py`
- запуск web-версии через `run.py`
- запуск desktop-версии через `webview_app.py`
- ORM-сущности и базовые репозитории для работы с `SQLite`
- внутренняя структура `controller -> service -> repository -> model`
- parser package в `app/parsers` для sitemap/html-сценария
- базовые шаблоны и static-файлы интерфейса

## Что пока не доведено

- интегрированный `ingestion_service`
- сохранение новостей из parser pipeline в `SQLite` по полному рабочему сценарию
- пользовательский интерфейс просмотра новостей
- рабочий `FAISS`-индекс
- пользовательский семантический поиск
- адаптация embedding-модели под новостной домен
- финальная сборка desktop-приложения

## Структура проекта

```text
project/
  app/
    controllers/
    services/
    repositories/
    models/
    parsers/
    ml/
    templates/
    static/
  instance/
  run.py
  webview_app.py
```

Коротко по слоям:

- `controllers` — HTTP-маршруты Flask
- `services` — прикладные сценарии
- `repositories` — доступ к `SQLite` через ORM
- `models` — ORM-сущности, DTO и интерфейсы
- `parsers` — получение и извлечение внешнего контента
- `ml` — embedding-модели, их адаптация и связанная логика

## Запуск

Используй проектное виртуальное окружение:

```powershell
.\.venv\Scripts\python.exe run.py
```

После этого приложение будет доступно по адресу:

```text
http://127.0.0.1:5000
```

Для запуска desktop-версии:

```powershell
.\.venv\Scripts\python.exe webview_app.py
```

## Замечание по текущему статусу

Сейчас проект находится между этапами стабилизации data layer и интеграции ingestion pipeline.

Это означает:

- parser и слой данных уже развиты заметно сильнее, чем UI и сервисы верхнего уровня;
- часть контроллеров и сервисов пока остаются каркасными заглушками;
- README описывает текущее состояние, а не финальную целевую версию.
