import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.run_public_stability_watch import _classify_response, _infer_question_class, _load_queries, _resolve_queries_path, _sleep_until_reset, _should_preemptive_wait


class PublicStabilityWatchTests(unittest.TestCase):
    def test_infer_question_class_uses_query_when_public_contract_hides_debug_fields(self):
        self.assertEqual(_infer_question_class('Что в документе N1432?', {}), 'named_document_lookup')
        self.assertEqual(_infer_question_class('Какие изменения в налоговом кодексе в 2026 году?', {}), 'amendment_tracking')
        self.assertEqual(_infer_question_class('Какое решение по спору №19068/2/2023?', {}), 'dispute_practice')

    def test_resolve_queries_path_prefers_explicit_path_over_profile(self):
        self.assertEqual(_resolve_queries_path('/tmp/x.txt', 'core'), '/tmp/x.txt')

    def test_resolve_queries_path_uses_profile_default(self):
        self.assertEqual(_resolve_queries_path(None, 'core'), 'scripts/public_canary_queries_core.txt')
        self.assertEqual(_resolve_queries_path(None, 'extended'), 'scripts/public_canary_queries_extended.txt')
        self.assertEqual(_resolve_queries_path(None, 'trimmed'), 'scripts/public_canary_queries_trimmed.txt')

    def test_load_queries_skips_comments_and_blank_lines(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "queries.txt"
            path.write_text("# canonical\n\nЧто говорит статья 168?\n  # local\nКакая ставка в Тбилиси?\n", encoding="utf-8")
            queries = _load_queries(str(path))
        self.assertEqual(queries, ["Что говорит статья 168?", "Какая ставка в Тбилиси?"])

    def test_sleep_until_reset_waits_until_reset_epoch(self):
        with patch('scripts.run_public_stability_watch.time.time', return_value=100), patch('scripts.run_public_stability_watch.time.sleep') as mock_sleep:
            _sleep_until_reset({'rate_limit_reset': '105'})
        mock_sleep.assert_called_once_with(6)

    def test_should_preemptive_wait_when_success_exhausts_remaining_budget(self):
        row = {'http_status': 200, 'rate_limit_remaining': '0'}
        self.assertTrue(_should_preemptive_wait(row))

    def test_should_not_preemptive_wait_when_budget_remains(self):
        row = {'http_status': 200, 'rate_limit_remaining': '2'}
        self.assertFalse(_should_preemptive_wait(row))

    def test_classify_response_keeps_rate_limit_headers_on_success(self):
        result = {
            'http_status': 200,
            'elapsed_s': 0.5,
            'body': {
                'response': 'Короткий ответ.\n\nИсточник: Источник, статья 1.',
                'retrieved_count': 1,
                'sources': [{'metadata': {'title': 'Источник'}}],
                '_rag_v2': {'question_class': 'canonical_law_lookup'},
            },
            'headers': {'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '12345'},
        }
        row = _classify_response('Что говорит статья 1?', 1, result)
        self.assertEqual(row['rate_limit_remaining'], '0')
        self.assertEqual(row['rate_limit_reset'], '12345')

    def test_classify_response_marks_duplicate_source_mentions_as_weak(self):
        result = {
            "http_status": 200,
            "elapsed_s": 1.23,
            "body": {
                "response": (
                    "Короткий ответ. Источник: საქართველოს საგადასახადო კოდექსი, статья 169.\n\n"
                    "Источник: საქართველოს საგადასახადო კოდექსი, статья 169."
                ),
                "retrieved_count": 1,
                "sources": [
                    {
                        "metadata": {"title": "საქართველოს საგადასახადო კოდექსი."}
                    }
                ],
                "_rag_v2": {"question_class": "canonical_law_lookup"},
            },
            "headers": {},
        }
        row = _classify_response("Что говорит статья 169 Налогового кодекса?", 1, result)
        self.assertEqual(row["source_mentions"], 2)
        self.assertFalse(row["success"])
        self.assertTrue(row["weak_answer"])

    def test_classify_response_accepts_clean_canonical_response(self):
        result = {
            "http_status": 200,
            "elapsed_s": 1.11,
            "body": {
                "response": (
                    "Короткий ответ по статье.\n\n"
                    "Источник: საქართველოს საგადასახადო კოდექსი, статья 168."
                ),
                "retrieved_count": 1,
                "sources": [
                    {
                        "metadata": {"title": "საქართველოს საგადასახადო კოდექსი."}
                    }
                ],
                "_rag_v2": {"question_class": "canonical_law_lookup"},
            },
            "headers": {},
        }
        row = _classify_response("Что говорит статья 168 Налогового кодекса?", 1, result)
        self.assertEqual(row["source_mentions"], 1)
        self.assertTrue(row["success"])
        self.assertFalse(row["weak_answer"])

    def test_classify_response_allows_grounded_no_evidence_without_source_citation_checks(self):
        result = {
            "http_status": 200,
            "elapsed_s": 1.4,
            "body": {
                "response": "Я не нашёл в найденных актах подтверждённых поправок по НДС за этот период.",
                "retrieved_count": 2,
                "sources": [
                    {
                        "metadata": {"title": "Закон о внесении изменений"}
                    }
                ],
                "_rag_v2": {
                    "question_class": "amendment_tracking",
                    "grounded_no_evidence": True,
                },
            },
            "headers": {},
        }
        row = _classify_response("Какие изменения по НДС в 2026 году?", 1, result)
        self.assertTrue(row["success"])
        self.assertTrue(row["grounded_no_evidence"])

    def test_classify_response_allows_local_grounded_no_evidence_without_sources(self):
        result = {
            "http_status": 200,
            "elapsed_s": 1.2,
            "body": {
                "response": "Я не нашёл в live corpus подтверждённый локальный нормативный акт по Тбилиси с точной ставкой налога на имущество, поэтому не буду придумывать ставку без надёжного источника.",
                "retrieved_count": 0,
                "sources": [],
                "_rag_v2": {
                    "question_class": "local_regulation_lookup",
                    "grounded_no_evidence": True,
                },
            },
            "headers": {},
        }
        row = _classify_response("Какая ставка налога на имущество в Тбилиси?", 1, result)
        self.assertTrue(row["success"])
        self.assertTrue(row["grounded_no_evidence"])
        self.assertIsNone(row["source_title"])

    def test_classify_response_allows_dispute_grounded_no_evidence_without_sources(self):
        result = {
            "http_status": 200,
            "elapsed_s": 0.9,
            "body": {
                "response": "Я не нашёл в live corpus подтверждённое решение именно по спору №19068/2/2023, поэтому не буду приписывать выводы другого дела этому спору.",
                "retrieved_count": 0,
                "sources": [],
                "_rag_v2": {
                    "question_class": "dispute_practice",
                    "grounded_no_evidence": True,
                },
            },
            "headers": {},
        }
        row = _classify_response("Какое решение по спору №19068/2/2023?", 1, result)
        self.assertTrue(row["success"])
        self.assertTrue(row["grounded_no_evidence"])

    def test_classify_response_rejects_overlong_named_document_summary(self):
        result = {
            "http_status": 200,
            "elapsed_s": 1.1,
            "body": {
                "response": "Документ N1432. " + ("Длинный пересказ. " * 40),
                "retrieved_count": 1,
                "sources": [{"metadata": {"title": "N1432"}}],
                "_rag_v2": {"question_class": "named_document_lookup"},
            },
            "headers": {},
        }
        row = _classify_response("Что в документе N1432?", 1, result)
        self.assertTrue(row["overlong_response"])
        self.assertFalse(row["success"])

    def test_classify_response_rejects_amendment_summary_with_too_many_points(self):
        result = {
            "http_status": 200,
            "elapsed_s": 1.2,
            "body": {
                "response": "В 2026 году:\n1. А.\n2. Б.\n3. В.",
                "retrieved_count": 2,
                "sources": [
                    {"metadata": {"title": "Act 1"}},
                    {"metadata": {"title": "Act 2"}},
                ],
                "_rag_v2": {"question_class": "amendment_tracking"},
            },
            "headers": {},
        }
        row = _classify_response("Какие изменения в налоговом кодексе в 2026 году?", 1, result)
        self.assertFalse(row["trimmed_point_shape_ok"])
        self.assertFalse(row["success"])


if __name__ == "__main__":
    unittest.main()
