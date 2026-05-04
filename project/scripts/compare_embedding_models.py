from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.evaluation.model_comparison import (  # noqa: E402
    comparison_models,
    evaluate_embedding_model,
)
from app.ml.evaluation.search_baseline import load_evaluation_queries  # noqa: E402


def main() -> None:
    """Сравнить несколько embedding-моделей на одном evaluation-наборе."""
    parser = argparse.ArgumentParser(
        description="Построить временные FAISS-индексы и сравнить качество embedding-моделей.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Имя модели Hugging Face. Можно указать несколько раз.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Сколько результатов выдачи учитывать для каждого eval-запроса.",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Оценивать только статьи активных источников.",
    )
    args = parser.parse_args()

    queries = load_evaluation_queries()
    models = comparison_models(args.model)

    print(f"Eval-запросов: {len(queries)}")
    print("Модели:")
    for model_name in models:
        print(f"- {model_name}")
    print()

    for model_name in models:
        # Каждый прогон использует отдельный runtime-индекс, рабочий индекс приложения не трогаем.
        result = evaluate_embedding_model(
            model_name=model_name,
            queries=queries,
            top_k=args.top_k,
            active_only=args.active_only,
        )

        print(f"Модель: {result.model_name}")
        print(f"hit@1: {result.report.hit_at_1:.3f}")
        print(f"hit@3: {result.report.hit_at_3:.3f}")
        print(f"hit@5: {result.report.hit_at_5:.3f}")
        print(f"MRR: {result.report.mean_mrr:.3f}")
        print(f"Отчет: {result.report_path}")
        print(f"Временный индекс: {result.index_path}")
        print()


if __name__ == "__main__":
    main()
