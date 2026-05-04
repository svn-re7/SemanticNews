from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import Config
from app.models.entities import Article
from app.repositories.news_repository import NewsRepository


@dataclass(frozen=True)
class DatasetBuildConfig:
    """Настройки сборки train/validation/test датасета из SQLite."""

    output_dir: Path = Config.ML_DATASET_DIR
    train_ratio: float = 0.8
    validation_ratio: float = 0.1
    random_seed: int = 42
    max_text_chars: int = 2000
    min_title_chars: int = 10
    min_text_chars: int = 100


@dataclass(frozen=True)
class DatasetBuildResult:
    """Краткий итог сборки ML-датасета."""

    total_articles: int
    accepted_articles: int
    split_counts: dict[str, int]
    train_path: Path
    validation_path: Path
    test_path: Path
    stats_path: Path


@dataclass(frozen=True)
class TrainingPair:
    """Одна обучающая пара title -> text для адаптации embedding-модели."""

    article_id: int
    query: str
    positive: str
    source_id: int
    source_name: str
    direct_url: str
    published_at: str


class TrainingDatasetBuilder:
    """Сборщик JSONL-датасета для последующего fine-tuning embedding-модели."""

    def __init__(
        self,
        *,
        news_repository: NewsRepository | None = None,
        config: DatasetBuildConfig | None = None,
    ) -> None:
        self.news_repository = news_repository if news_repository is not None else NewsRepository()
        self.config = config if config is not None else DatasetBuildConfig()

    def build(self) -> DatasetBuildResult:
        """Собрать train/validation/test JSONL-файлы и stats.json."""
        self._validate_config()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        total_articles = self.news_repository.count_articles()
        articles = self.news_repository.list_articles(limit=total_articles, offset=0)
        pairs, skipped = self._build_pairs(articles)
        splits = self._split_pairs(pairs)

        train_path = self.config.output_dir / "train.jsonl"
        validation_path = self.config.output_dir / "validation.jsonl"
        test_path = self.config.output_dir / "test.jsonl"
        stats_path = self.config.output_dir / "stats.json"

        self._write_jsonl(train_path, splits["train"])
        self._write_jsonl(validation_path, splits["validation"])
        self._write_jsonl(test_path, splits["test"])
        self._write_stats(
            stats_path,
            total_articles=total_articles,
            accepted_articles=len(pairs),
            skipped=skipped,
            splits=splits,
        )

        return DatasetBuildResult(
            total_articles=total_articles,
            accepted_articles=len(pairs),
            split_counts={name: len(items) for name, items in splits.items()},
            train_path=train_path,
            validation_path=validation_path,
            test_path=test_path,
            stats_path=stats_path,
        )

    def _build_pairs(self, articles: list[Article]) -> tuple[list[TrainingPair], dict[str, int]]:
        """Превратить статьи в пары title -> text и посчитать причины отбраковки."""
        pairs: list[TrainingPair] = []
        skipped = {
            "short_title": 0,
            "short_text": 0,
        }

        for article in articles:
            title = _compact_text(article.title)
            text = _compact_text(article.text)
            if len(title) < self.config.min_title_chars:
                skipped["short_title"] += 1
                continue
            if len(text) < self.config.min_text_chars:
                skipped["short_text"] += 1
                continue

            # Для обучения берем ограниченное начало статьи: в новостях основной смысл обычно в первых абзацах.
            limited_text = text[: self.config.max_text_chars].strip()
            pairs.append(
                TrainingPair(
                    article_id=article.id,
                    query=title,
                    positive=limited_text,
                    source_id=article.source_id,
                    source_name=_source_name(article),
                    direct_url=article.direct_url,
                    published_at=article.published_at.isoformat(timespec="seconds"),
                )
            )

        return pairs, skipped

    def _split_pairs(self, pairs: list[TrainingPair]) -> dict[str, list[TrainingPair]]:
        """Детерминированно разбить пары на train/validation/test без пересечения статей."""
        shuffled_pairs = list(pairs)
        random.Random(self.config.random_seed).shuffle(shuffled_pairs)

        train_count = int(len(shuffled_pairs) * self.config.train_ratio)
        validation_count = int(len(shuffled_pairs) * self.config.validation_ratio)
        validation_end = train_count + validation_count

        return {
            "train": shuffled_pairs[:train_count],
            "validation": shuffled_pairs[train_count:validation_end],
            "test": shuffled_pairs[validation_end:],
        }

    def _write_jsonl(self, path: Path, pairs: list[TrainingPair]) -> None:
        """Записать split в JSONL: одна обучающая пара на строку."""
        lines = [
            json.dumps(asdict(pair), ensure_ascii=False)
            for pair in pairs
        ]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _write_stats(
        self,
        path: Path,
        *,
        total_articles: int,
        accepted_articles: int,
        skipped: dict[str, int],
        splits: dict[str, list[TrainingPair]],
    ) -> None:
        """Сохранить технический отчет по качеству и составу датасета."""
        payload = {
            "total_articles": total_articles,
            "accepted_articles": accepted_articles,
            "skipped": skipped,
            "split_counts": {name: len(items) for name, items in splits.items()},
            "source_counts": _source_counts([pair for items in splits.values() for pair in items]),
            "config": {
                "train_ratio": self.config.train_ratio,
                "validation_ratio": self.config.validation_ratio,
                "test_ratio": round(self._test_ratio, 6),
                "random_seed": self.config.random_seed,
                "max_text_chars": self.config.max_text_chars,
                "min_title_chars": self.config.min_title_chars,
                "min_text_chars": self.config.min_text_chars,
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _validate_config(self) -> None:
        """Проверить, что настройки split и длины текстов не противоречат друг другу."""
        if self.config.train_ratio <= 0:
            raise ValueError("train_ratio должен быть положительным.")
        if self.config.validation_ratio < 0:
            raise ValueError("validation_ratio не может быть отрицательным.")
        if self._test_ratio < 0:
            raise ValueError("Сумма train_ratio и validation_ratio не должна превышать 1.")
        if self.config.max_text_chars <= 0:
            raise ValueError("max_text_chars должен быть положительным.")

    @property
    def _test_ratio(self) -> float:
        """Вернуть долю test-split как остаток после train и validation."""
        return 1.0 - self.config.train_ratio - self.config.validation_ratio


def _compact_text(text: str) -> str:
    """Сжать пробельные символы, не меняя смысл текста."""
    return re.sub(r"\s+", " ", text).strip()


def _source_name(article: Article) -> str:
    """Безопасно получить имя источника для статистики датасета."""
    if article.source is None:
        return "unknown"
    return article.source.name


def _source_counts(pairs: list[TrainingPair]) -> dict[str, int]:
    """Посчитать распределение обучающих пар по источникам."""
    counts: dict[str, int] = {}
    for pair in pairs:
        counts[pair.source_name] = counts.get(pair.source_name, 0) + 1
    return counts
