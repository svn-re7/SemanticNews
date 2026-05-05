from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.training.model_trainer import (  # noqa: E402
    TrainingConfig,
    build_validation_retrieval_data,
    calculate_warmup_steps,
    load_training_pairs,
)


class EmbeddingModelTrainerTest(unittest.TestCase):
    def test_load_training_pairs_reads_query_and_positive_from_jsonl(self) -> None:
        """JSONL-пары превращаются в InputExample для sentence-transformers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "train.jsonl"
            path.write_text(
                "\n".join(
                    [
                        '{"article_id": 10, "query": "Заголовок", "positive": "Текст статьи"}',
                        '{"article_id": 20, "query": "Другой заголовок", "positive": "Другой текст"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            examples = load_training_pairs(path)

            self.assertEqual(len(examples), 2)
            self.assertEqual(examples[0].texts, ["Заголовок", "Текст статьи"])
            self.assertEqual(examples[1].texts, ["Другой заголовок", "Другой текст"])

    def test_build_validation_retrieval_data_keeps_article_as_relevant_document(self) -> None:
        """Validation-набор хранит соответствие query конкретному positive-тексту этой же статьи."""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "validation.jsonl"
            path.write_text(
                '{"article_id": 10, "query": "Запрос", "positive": "Правильный текст"}\n',
                encoding="utf-8",
            )

            queries, corpus, relevant_docs = build_validation_retrieval_data(path)

            self.assertEqual(queries, {"q_10": "Запрос"})
            self.assertEqual(corpus, {"a_10": "Правильный текст"})
            self.assertEqual(relevant_docs, {"q_10": {"a_10"}})

    def test_calculate_warmup_steps_uses_fraction_of_training_steps(self) -> None:
        """Warmup считается как небольшая доля от общего числа training steps."""
        config = TrainingConfig(batch_size=16, epochs=2, warmup_ratio=0.1)

        self.assertEqual(calculate_warmup_steps(examples_count=100, config=config), 2)
        self.assertEqual(calculate_warmup_steps(examples_count=1, config=config), 1)


if __name__ == "__main__":
    unittest.main()
