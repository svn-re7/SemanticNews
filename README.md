# SemanticNews

SemanticNews — локальное десктопное приложение для сбора новостей из подключенных источников и семантического поиска по сохраненным материалам.

Приложение хранит новости локально, позволяет управлять источниками, запускать сбор, искать материалы обычным текстовым запросом и открывать найденные статьи в интерфейсе.

## Стек

- Python
- Flask
- HTML + Jinja2 + Bootstrap
- pywebview
- SQLite
- SQLAlchemy
- FAISS
- sentence-transformers
- Telethon
- PyInstaller

## Запуск из исходников

Установите зависимости в виртуальное окружение и запускайте команды из корня проекта.

```powershell
.\.venv\Scripts\python.exe project\run.py
```

После запуска web-версия будет доступна в браузере:

```text
http://127.0.0.1:5000
```

Для запуска desktop-версии:

```powershell
.\.venv\Scripts\python.exe project\webview_app.py
```

## Сборка desktop-приложения

Установите PyInstaller:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

Запустите сборку:

```powershell
.\scripts\build_desktop.ps1
```

Готовое приложение появится здесь:

```text
dist\SemanticNews\SemanticNews.exe
```

## Локальные данные

В режиме разработки база данных, индекс поиска и локальная модель хранятся в:

```text
project\instance
```

В собранном приложении эти файлы копируются в:

```text
dist\SemanticNews\instance
```
