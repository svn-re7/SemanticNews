from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.config import Config  # noqa: E402
from app.ml.training.model_trainer import TrainingConfig, train_embedding_model  # noqa: E402


def main() -> None:
    """Запустить fine-tuning embedding-модели на подготовленном JSONL-датасете."""
    parser = argparse.ArgumentParser(
        description="Дообучить SentenceTransformer на парах title -> text из SemanticNews.",
    )
    parser.add_argument(
        "--base-model",
        default=Config.EMBEDDING_MODEL_NAME,
        help="Базовая SentenceTransformer-модель.",
    )
    parser.add_argument(
        "--train-path",
        type=Path,
        default=Config.ML_DATASET_DIR / "train.jsonl",
        help="Путь к train.jsonl.",
    )
    parser.add_argument(
        "--validation-path",
        type=Path,
        default=Config.ML_DATASET_DIR / "validation.jsonl",
        help="Путь к validation.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Config.ADAPTED_EMBEDDING_MODEL_DIR,
        help="Куда сохранить дообученную модель.",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--evaluation-steps", type=int, default=500)
    parser.add_argument(
        "--max-train-examples",
        type=int,
        default=None,
        help="Ограничить число train-примеров для smoke-run.",
    )
    parser.add_argument(
        "--max-validation-examples",
        type=int,
        default=None,
        help="Ограничить число validation-примеров для smoke-run.",
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="Удалить существующий output-dir перед обучением.",
    )
    args = parser.parse_args()

    result = train_embedding_model(
        TrainingConfig(
            base_model_name=args.base_model,
            train_path=args.train_path,
            validation_path=args.validation_path,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            warmup_ratio=args.warmup_ratio,
            evaluation_steps=args.evaluation_steps,
            max_train_examples=args.max_train_examples,
            max_validation_examples=args.max_validation_examples,
            overwrite_output=args.overwrite_output,
        )
    )

    print(f"Базовая модель: {result.base_model_name}")
    print(f"Train examples: {result.train_examples}")
    print(f"Validation examples: {result.validation_examples}")
    print(f"Batch size: {result.batch_size}")
    print(f"Epochs: {result.epochs}")
    print(f"Warmup steps: {result.warmup_steps}")
    print(f"Модель сохранена: {result.output_dir}")


if __name__ == "__main__":
    main()
