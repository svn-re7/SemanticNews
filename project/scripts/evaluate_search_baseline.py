from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.evaluation.search_baseline import (  # noqa: E402
    SearchBaselineEvaluator,
    load_evaluation_queries,
    save_baseline_report,
)


def main() -> None:
    """Запустить baseline-оценку текущего semantic search без записи в историю поиска."""
    queries = load_evaluation_queries()
    report = SearchBaselineEvaluator().evaluate(
        queries,
        top_k=5,
        active_only=False,
    )
    output_path = save_baseline_report(report)

    print(f"Eval-запросов: {report.queries_count}")
    print(f"Модель: {report.model_name}")
    print(f"hit@1: {report.hit_at_1:.3f}")
    print(f"hit@3: {report.hit_at_3:.3f}")
    print(f"hit@5: {report.hit_at_5:.3f}")
    print(f"MRR: {report.mean_mrr:.3f}")
    print(f"Отчет сохранен: {output_path}")


if __name__ == "__main__":
    main()
