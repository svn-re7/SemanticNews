from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.training.dataset_builder import (  # noqa: E402
    DatasetBuildConfig,
    TrainingDatasetBuilder,
)


def main() -> None:
    """Собрать JSONL-датасет для fine-tuning embedding-модели из текущей SQLite-базы."""
    parser = argparse.ArgumentParser(
        description="Собрать train/validation/test пары title -> text из SQLite.",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=2000,
        help="Максимальное количество символов текста статьи в поле positive.",
    )
    parser.add_argument(
        "--min-title-chars",
        type=int,
        default=10,
        help="Минимальная длина заголовка для попадания статьи в датасет.",
    )
    parser.add_argument(
        "--min-text-chars",
        type=int,
        default=100,
        help="Минимальная длина текста для попадания статьи в датасет.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed для воспроизводимого train/validation/test split.",
    )
    args = parser.parse_args()

    result = TrainingDatasetBuilder(
        config=DatasetBuildConfig(
            max_text_chars=args.max_text_chars,
            min_title_chars=args.min_title_chars,
            min_text_chars=args.min_text_chars,
            random_seed=args.seed,
        )
    ).build()

    print(f"Всего статей в БД: {result.total_articles}")
    print(f"Попало в датасет: {result.accepted_articles}")
    print(f"Train: {result.split_counts['train']}")
    print(f"Validation: {result.split_counts['validation']}")
    print(f"Test: {result.split_counts['test']}")
    print(f"Train file: {result.train_path}")
    print(f"Validation file: {result.validation_path}")
    print(f"Test file: {result.test_path}")
    print(f"Stats: {result.stats_path}")


if __name__ == "__main__":
    main()
