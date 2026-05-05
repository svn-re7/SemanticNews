from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.config import Config  # noqa: E402
from app.ml.evaluation.holdout_retrieval import (  # noqa: E402
    HoldoutRetrievalEvaluator,
    build_embedding_service_for_model,
    load_holdout_items,
    save_holdout_report,
)


def main() -> None:
    """Сравнить base/adapted embedding-модели на holdout title -> own text retrieval."""
    parser = argparse.ArgumentParser(
        description="Оценить, находит ли модель текст статьи по заголовку на test.jsonl.",
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=Config.ML_DATASET_DIR / "test.jsonl",
        help="Путь к holdout test.jsonl.",
    )
    parser.add_argument(
        "--model",
        choices=["base", "adapted", "both"],
        default="both",
        help="Какую модель оценивать.",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить число test-примеров для быстрого smoke-run.",
    )
    args = parser.parse_args()

    items = load_holdout_items(args.dataset_path, limit=args.limit)
    model_modes = ["base", "adapted"] if args.model == "both" else [args.model]

    print(f"Holdout-примеров: {len(items)}")
    print(f"Dataset: {args.dataset_path}")
    print()

    for model_mode in model_modes:
        use_adapted_model = model_mode == "adapted"
        model_name = (
            str(Config.ADAPTED_EMBEDDING_MODEL_DIR)
            if use_adapted_model
            else Config.EMBEDDING_MODEL_NAME
        )
        service = build_embedding_service_for_model(
            model_name=Config.EMBEDDING_MODEL_NAME,
            use_adapted_model=use_adapted_model,
        )
        report = HoldoutRetrievalEvaluator(embedding_service=service).evaluate(
            items,
            model_name=model_name,
            dataset_path=args.dataset_path,
            top_k=args.top_k,
        )
        report_path = save_holdout_report(
            report,
            file_name=f"holdout_{model_mode}.json",
        )

        print(f"Модель: {model_mode} ({report.model_name})")
        print(f"hit@1: {report.metrics.hit_at_1:.3f}")
        print(f"hit@3: {report.metrics.hit_at_3:.3f}")
        print(f"hit@5: {report.metrics.hit_at_5:.3f}")
        print(f"hit@10: {report.metrics.hit_at_10:.3f}")
        print(f"MRR: {report.metrics.mean_mrr:.3f}")
        print(f"Отчет: {report_path}")
        print()


if __name__ == "__main__":
    main()
