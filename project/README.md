# SemanticNews Starter Scaffold

SemanticNews is a clean starter scaffold for a desktop-oriented semantic news search app.
It includes a Flask backend, Jinja2 templates, Bootstrap UI base, and a pywebview desktop launcher.

## What is included

- Flask application factory structure
- Controller, service, repository, and model placeholders
- One working health endpoint: `GET /health` -> `{"status": "ok"}`
- Starter HTML templates and static assets
- Desktop launcher via pywebview

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run Flask app

```bash
python run.py
```

Then open `http://127.0.0.1:5000` in your browser.

## Launch desktop version (pywebview)

```bash
python webview_app.py
```

## Note

Search, scraping, ML inference/classification, and FAISS indexing are intentionally not implemented yet.
This scaffold is prepared for future expansion with semantic search, ingestion pipelines, and SQLite-backed storage.
