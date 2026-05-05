# ML-этап SemanticNews

Документ фиксирует, что именно сделано в ML-части проекта SemanticNews, как устроен pipeline и какие результаты получены.

## Цель ML-части

ML-часть нужна для семантического поиска новостей.

Пользователь вводит не точное ключевое слово, а смысловой запрос:

```text
курс рубля и финансовые рынки
```

Система должна найти статьи, близкие по смыслу, даже если в статье используются другие формулировки.

## Зафиксированная архитектура

ML-часть встроена в уже выбранную архитектуру проекта без смены стека:

- `sentence-transformers` строит embedding-векторы;
- `FAISS` хранит и ищет векторы статей;
- `SQLite` остается основным хранилищем статей и метаданных;
- `Flask/Jinja2` остаются UI-слоем;
- ML-логика вынесена в отдельные модули и не смешана с контроллерами.

Основной поток:

```text
Article из SQLite
-> EmbeddingService
-> SentenceTransformerEmbeddingProvider
-> FAISS index
-> SearchService
-> результаты поиска из SQLite
```

## Абстракция embedding-модели

Добавлена абстракция `EmbeddingProvider`.

Зачем она нужна:

- приложение не зависит напрямую от конкретной модели;
- базовую модель можно заменить на дообученную без переписывания поиска;
- тесты могут подставлять fake-provider без загрузки реальной ML-модели.

Основная реализация:

```text
SentenceTransformerEmbeddingProvider
```

Она умеет:

- строить embedding одного текста;
- строить batch embeddings;
- нормализовать векторы для cosine similarity;
- автоматически подхватывать локально дообученную модель из `project/instance/models/news-embeddings`, если она существует.

## FAISS-индекс

Реализован `IndexingService`.

Он отвечает за:

- полную пересборку FAISS-индекса по статьям из SQLite;
- добавление новых статей в существующий индекс;
- синхронизацию FAISS-позиций с `article_id` через JSON-карту.

FAISS хранит только векторы и их позиции. Поэтому отдельно хранится файл:

```text
project/instance/news_index_ids.json
```

Он связывает:

```text
позиция в FAISS -> article_id в SQLite
```

Это нужно, чтобы после поиска по вектору вернуться к полноценной статье в базе.

## Семантический поиск

Реализован `SearchService`.

Поток поиска:

```text
query пользователя
-> embedding query
-> FAISS top-k search
-> article_id из JSON-карты
-> статьи из SQLite
-> фильтрация по активным источникам
-> порог релевантности
-> сохранение Request/SearchResult
-> UI-выдача
```

Поиск уже интегрирован в пользовательский интерфейс.

История поиска сохраняется, а переход из карточки новости обратно к результатам идет через `request_id`, а не через повторный запуск поиска.

## Базовая модель

Сначала использовалась модель:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Она легкая, но хуже подходит для русскоязычных новостей, потому что в первую очередь ориентирована на английский язык.

После сравнения модель заменена на:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Причины выбора:

- multilingual-модель лучше работает с русским языком;
- размерность embedding осталась `384`;
- модель достаточно легкая для локального desktop-приложения;
- архитектура приложения не изменилась.

## Ручной evaluation baseline

Добавлен ручной eval-набор:

```text
project/app/ml/evaluation/queries.json
```

В нем 24 смысловых запроса и ожидаемые маркеры релевантности.

Пример:

```json
{
  "query": "курс рубля и финансовые рынки",
  "expected_terms": ["рубл", "рын", "бирж", "акци"]
}
```

Добавлен evaluator:

```text
project/app/ml/evaluation/search_baseline.py
```

Он выполняет read-only проверку поиска:

```text
query
-> embedding
-> FAISS
-> top-k статьи
-> проверка expected_terms
-> hit@1 / hit@3 / hit@5 / MRR
```

Важно: baseline evaluator не пишет данные в историю поиска и не создает `Request/SearchResult`.

## Метрики

Используются базовые retrieval-метрики:

- `hit@1` — релевантный результат есть на первом месте;
- `hit@3` — релевантный результат есть в первых 3;
- `hit@5` — релевантный результат есть в первых 5;
- `MRR` — среднее обратное значение ранга первого релевантного результата.

Пример:

```text
first_hit_rank = 2
MRR для запроса = 1 / 2 = 0.5
```

## Сравнение базовых моделей

Добавлен инструмент:

```text
project/app/ml/evaluation/model_comparison.py
project/scripts/compare_embedding_models.py
```

Он строит временный FAISS-индекс для каждой модели в `project/instance/evaluation`, не трогая рабочий индекс приложения.

Результаты сравнения:

```text
sentence-transformers/all-MiniLM-L6-v2:
hit@1 = 0.333
hit@3 = 0.583
hit@5 = 0.750
MRR   = 0.473

sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2:
hit@1 = 0.875
hit@3 = 0.958
hit@5 = 1.000
MRR   = 0.925
```

На основе этого базовая модель проекта заменена на multilingual-вариант.

## Подготовка train/validation/test датасета

Добавлен сборщик датасета:

```text
project/app/ml/training/dataset_builder.py
project/scripts/build_training_dataset.py
```

Он берет статьи из SQLite и строит пары:

```text
title -> text
```

Формат выходных файлов:

```text
project/instance/ml_datasets/train.jsonl
project/instance/ml_datasets/validation.jsonl
project/instance/ml_datasets/test.jsonl
project/instance/ml_datasets/stats.json
```

Каждая строка JSONL:

```json
{
  "article_id": 123,
  "query": "Заголовок статьи",
  "positive": "Текст этой же статьи",
  "source_id": 1,
  "source_name": "РИА Новости",
  "direct_url": "https://...",
  "published_at": "2026-05-04T12:00:00"
}
```

Для обучения главные поля:

```text
query
positive
```

Остальные поля нужны для анализа и отладки.

Датасет разделен так:

```text
80% train
10% validation
10% test
```

Split воспроизводимый за счет `random_seed = 42`.

Реальный результат сборки:

```text
Всего статей в БД: 10089
Попало в датасет: 10071
Train: 8056
Validation: 1007
Test: 1008
Отброшено: short_title=17, short_text=1
```

Тексты ограничиваются по длине:

```text
max_text_chars = 2000
```

Это сделано потому, что для новостей основной смысл обычно находится в первых абзацах, а слишком длинные тексты замедляют обучение.

## Fine-tuning модели

Добавлен training-модуль:

```text
project/app/ml/training/model_trainer.py
project/scripts/train_embedding_model.py
```

Обучение выполняется на парах:

```text
query = title
positive = text этой же статьи
```

Используется:

```text
MultipleNegativesRankingLoss
```

Принцип:

```text
В batch есть пары:
A1 -> B1
A2 -> B2
A3 -> B3

Для A1 правильный ответ B1.
B2 и B3 считаются негативами.
```

Модель учится располагать заголовок ближе к тексту своей статьи, чем к текстам других статей в batch.

Реальный запуск:

```text
Train examples: 8056
Validation examples: 1007
Epochs: 1
Batch size: 16
Warmup steps: 51
```

Модель сохранена в:

```text
project/instance/models/news-embeddings
```

Этот каталог не коммитится в Git, потому что это runtime-артефакт.

## Подключение дообученной модели

`SentenceTransformerEmbeddingProvider` устроен так:

```text
если project/instance/models/news-embeddings существует
-> использовать локальную adapted-модель

иначе
-> использовать Config.EMBEDDING_MODEL_NAME
```

Поэтому после обучения не нужно переписывать `SearchService` или `IndexingService`.

Достаточно:

```text
1. обучить модель;
2. сохранить ее в instance/models/news-embeddings;
3. пересобрать FAISS.
```

## Пересборка FAISS после обучения

После fine-tuning рабочий FAISS-индекс пересобран на adapted-модели.

Результат:

```text
articles = 11057
vector_size = 384
```

Файлы:

```text
project/instance/news.index
project/instance/news_index_ids.json
```

## Baseline после fine-tuning

Ручной baseline после обучения:

```text
Модель: project/instance/models/news-embeddings

hit@1 = 0.958
hit@3 = 0.958
hit@5 = 0.958
MRR   = 0.958
```

До обучения на multilingual-модели было:

```text
hit@1 = 0.875
hit@3 = 0.958
hit@5 = 1.000
MRR   = 0.925
```

Интерпретация:

- `hit@1` вырос;
- `MRR` вырос;
- релевантные результаты чаще оказываются прямо на первом месте;
- `hit@5` чуть снизился на ручном eval, поэтому нужна была дополнительная holdout-проверка.

## Holdout evaluation

Чтобы проверить, не переобучилась ли модель на train-наборе, добавлена holdout-проверка:

```text
project/app/ml/evaluation/holdout_retrieval.py
project/scripts/evaluate_holdout_retrieval.py
```

Она использует:

```text
project/instance/ml_datasets/test.jsonl
```

Этот split не участвовал в обучении.

Проверка:

```text
query = title из test.jsonl
correct document = positive text этой же статьи
```

Evaluator строит временный in-memory FAISS по текстам `positive` из `test.jsonl`, затем проверяет, найдет ли модель правильный текст по заголовку.

Результаты:

```text
Base multilingual:
hit@1  = 0.863
hit@3  = 0.918
hit@5  = 0.928
hit@10 = 0.947
MRR    = 0.893

Adapted local:
hit@1  = 0.953
hit@3  = 0.973
hit@5  = 0.979
hit@10 = 0.985
MRR    = 0.965
```

Вывод:

```text
Дообученная модель лучше базовой на отложенном test-наборе.
```

Это важнее, чем только ручной baseline, потому что test-набор не участвовал в обучении.

## Что считается завершенным

Для MVP ML-часть закрыта:

- есть embedding abstraction;
- есть FAISS search;
- есть baseline evaluation;
- есть model comparison;
- есть подготовка датасета;
- есть fine-tuning;
- есть подключение adapted-модели;
- есть пересборка FAISS;
- есть ручная и holdout-оценка качества.

## Что можно улучшить позже

Необязательные улучшения:

- сделать ручную разметку `query -> article_id`, а не только `expected_terms`;
- добавить hard negatives;
- балансировать датасет по источникам;
- добавить сравнение моделей в UI;
- сделать единый скрипт `train -> rebuild FAISS -> evaluate`;
- сохранять ML-эксперименты с версиями и датами.

Для текущей курсовой эти улучшения не блокируют завершение проекта.
