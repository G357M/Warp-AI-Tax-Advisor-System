import types
import unittest

from backend.rag_v2.faq_tax_matrix import TAX_FAQ_MATRIX
from backend.rag_v2.public_response import (
    compress_canonical_section_text,
    compress_rollout_context_text,
    direct_tax_faq_response,
    dividend_tax_rate_response,
    finalize_rollout_response,
    import_vat_response,
    income_tax_rate_response,
    individual_property_tax_rate_response,
    interest_tax_rate_response,
    nonresident_withholding_tax_response,
    normalize_public_response_text,
    profit_tax_rate_response,
    rental_income_tax_rate_response,
    royalty_tax_rate_response,
    small_business_tax_rate_response,
    vat_rate_response,
)


class PublicResponseShapeTests(unittest.TestCase):
    def test_normalize_public_response_text_removes_markdown_noise(self):
        text = "**Кратко:** см. [источник](https://example.com)\n\n\n__Важно__"
        self.assertEqual(
            normalize_public_response_text(text),
            "Кратко: см. источник\n\nВажно",
        )

    def test_finalize_rollout_response_adds_precise_citation_for_canonical(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            reranking={
                "top_ranked_documents": [
                    {
                        "title": "საქართველოს საგადასახადო კოდექსი. მუხლი 168",
                        "metadata": {"article_ref": "168"},
                    }
                ]
            },
        )
        result = finalize_rollout_response("**Ответ**", trace)
        self.assertEqual(result, "Ответ\n\nИсточник: საქართველოს საგადასახადო კოდექსი, статья 168.")

    def test_finalize_rollout_response_adds_point_level_precise_citation(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            reranking={
                "top_ranked_documents": [
                    {
                        "title": "საქართველოს საგადასახადო კოდექსი. მუხლი 169 პუნქტი 1",
                        "metadata": {"point_ref": "169.1"},
                    }
                ]
            },
        )
        result = finalize_rollout_response("Ответ по пункту", trace)
        self.assertEqual(
            result,
            "Ответ по пункту\n\nИсточник: საქართველოს საგადასახადო კოდექსი, статья 169, пункт 1.",
        )

    def test_finalize_rollout_response_keeps_amendment_answer_without_added_citation(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "amendment_tracking"},
            reranking={"top_ranked_documents": []},
        )
        result = finalize_rollout_response("**Есть изменения**", trace)
        self.assertEqual(result, "Есть изменения")

    def test_finalize_rollout_response_removes_inline_generated_source_then_adds_single_citation(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            reranking={
                "top_ranked_documents": [
                    {
                        "title": "საქართველოს საგადასახადო კოდექსი.",
                        "metadata": {"article_ref": "169"},
                    }
                ]
            },
        )
        result = finalize_rollout_response(
            "Короткий ответ по статье. Источник: საქართველოს საგადასახადო კოდექსი, статья 169.",
            trace,
        )
        self.assertEqual(
            result,
            "Короткий ответ по статье.\n\nИсточник: საქართველოს საგადასახადო კოდექსი, статья 169.",
        )

    def test_finalize_rollout_response_removes_parenthetical_inline_sources_in_amendment_answer(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "amendment_tracking"},
            reranking={"top_ranked_documents": []},
        )
        result = finalize_rollout_response(
            "1. Изменено правило А. (Источник: Закон N1, статья 1)\n2. Изменено правило Б. (Источник: Закон N2, статья 2)",
            trace,
        )
        self.assertEqual(result, "1. Изменено правило А.\n2. Изменено правило Б.")

    def test_finalize_rollout_response_removes_multiline_generated_source_block(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            reranking={
                "top_ranked_documents": [
                    {
                        "title": "საქართველოს საგადასახადო კოდექსი.",
                        "metadata": {"article_ref": "168"},
                    }
                ]
            },
        )
        result = finalize_rollout_response(
            "Первое предложение.\n\nИсточник: საქართველოს საგადასახადო კოდექსი, статья 168.\nЛишняя строка модели.",
            trace,
        )
        self.assertEqual(
            result,
            "Первое предложение.\n\nИсточник: საქართველოს საგადასახადო კოდექსი, статья 168.",
        )

    def test_compress_canonical_section_text_keeps_heading_and_trims_long_article(self):
        text = "Статья 168\n" + "\n\n".join(
            [f"{i}. Пункт {i} с довольно длинным описанием правила и условий его применения." for i in range(1, 10)]
        )
        compressed = compress_canonical_section_text(text, article_ref="168", article_budget=220)
        self.assertTrue(compressed.startswith("Статья 168"))
        self.assertLessEqual(len(compressed), len(text))
        self.assertIn("1. Пункт 1", compressed)
        self.assertNotIn("9. Пункт 9", compressed)

    def test_compress_rollout_context_text_trims_named_document_context(self):
        text = "**Заголовок**\n\n" + ("Факт. " * 300)
        compressed = compress_rollout_context_text(text, question_class="named_document_lookup")
        self.assertNotIn("**", compressed)
        self.assertLess(len(compressed), len(text))

    def test_compress_rollout_context_text_trims_amendment_context(self):
        text = "[Закон](https://example.com)\n\n" + ("Изменение нормы. " * 200)
        compressed = compress_rollout_context_text(text, question_class="amendment_tracking")
        self.assertNotIn("[", compressed)
        self.assertLess(len(compressed), len(text))

    def test_interest_tax_rate_response_ru_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "interest_tax", "goal": "rate_lookup"},
        )
        result = interest_tax_rate_response(trace)
        self.assertIn("5%", result)

    def test_royalty_tax_rate_response_ru_is_split(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "royalty_tax", "goal": "rate_lookup"},
        )
        result = royalty_tax_rate_response(trace)
        self.assertIn("20%", result)
        self.assertIn("5%", result)

    def test_import_vat_response_en_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "en", "topic": "import_vat", "goal": "rate_lookup"},
        )
        result = import_vat_response(trace)
        self.assertIn("18%", result)
        self.assertIn("Import", result)

    def test_nonresident_withholding_tax_response_ru_summarizes(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "nonresident_wht", "goal": "rate_lookup"},
        )
        result = nonresident_withholding_tax_response(trace)
        self.assertIn("проценты — 5%", result)
        self.assertIn("роялти — 5%", result)
        self.assertIn("10%", result)

    def test_rental_income_tax_rate_response_ru_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "rental_income", "goal": "rate_lookup"},
        )
        result = rental_income_tax_rate_response(trace)
        self.assertIn("5%", result)
        self.assertIn("20%", result)

    def test_dividend_tax_rate_response_ru_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "dividend_tax", "goal": "rate_lookup"},
        )
        result = dividend_tax_rate_response(trace)
        self.assertIn("5%", result)

    def test_small_business_tax_rate_response_en_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "en", "topic": "small_business", "goal": "rate_lookup"},
        )
        result = small_business_tax_rate_response(trace)
        self.assertIn("1%", result)
        self.assertIn("3%", result)

    def test_vat_rate_response_ru_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "vat", "goal": "rate_lookup"},
        )
        result = vat_rate_response(trace)
        self.assertEqual(result, "Стандартная ставка НДС в Грузии — 18%.")

    def test_profit_tax_rate_response_en_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "en", "topic": "profit_tax", "goal": "rate_lookup"},
        )
        result = profit_tax_rate_response(trace)
        self.assertIn("15%", result)
        self.assertIn("base rate", result)

    def test_income_tax_rate_response_ru_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "tax", "subject": "individual", "goal": "rate_lookup"},
        )
        result = income_tax_rate_response(trace)
        self.assertIn("20%", result)
        self.assertIn("5%", result)

    def test_income_tax_rate_response_ka_is_direct(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ka", "topic": "tax", "subject": "individual", "goal": "rate_lookup"},
        )
        result = income_tax_rate_response(trace)
        self.assertIn("20 პროცენტ", result)
        self.assertIn("5 პროცენტ", result)

    def test_individual_property_tax_rate_response_ka_is_localized(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "practical_tax_guidance"},
            parsed_query={
                "language": "ka",
                "topic": "property_tax",
                "subject": "individual",
                "goal": "rate_lookup",
                "locality": "tbilisi",
            },
        )
        result = individual_property_tax_rate_response(trace)
        self.assertIn("თბილისში", result)
        self.assertIn("0%-დან 0.8%-მდე", result)

    def test_individual_property_tax_rate_response_uses_individual_range_not_company_rate(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "practical_tax_guidance"},
            parsed_query={
                "topic": "property_tax",
                "subject": "individual",
                "goal": "rate_lookup",
                "locality": "tbilisi",
            },
        )
        result = individual_property_tax_rate_response(trace)
        self.assertIn("от 0% до 0.8%", result)
        self.assertIn("в Тбилиси", result)
        self.assertIn("ставка относится к организациям", result)

    def test_tax_faq_matrix_topics_have_direct_response_functions(self):
        for entry in TAX_FAQ_MATRIX:
            for lang in ("ru", "en", "ka"):
                with self.subTest(topic=entry.topic, lang=lang):
                    trace = types.SimpleNamespace(
                        classification={"question_class": entry.question_class},
                        parsed_query={
                            "language": lang,
                            "topic": entry.topic,
                            "subject": entry.subject,
                            "goal": "rate_lookup",
                        },
                    )
                    if entry.topic == "property_tax":
                        result = individual_property_tax_rate_response(trace)
                    else:
                        result = direct_tax_faq_response(trace)
                    self.assertEqual(result, entry.response_by_lang[lang])

    def test_nonresident_service_wht_response_mentions_possible_vat_separately(self):
        trace = types.SimpleNamespace(
            classification={"question_class": "canonical_law_lookup"},
            parsed_query={"language": "ru", "topic": "nonresident_service_wht", "subject": "non_resident", "goal": "rate_lookup"},
        )
        result = direct_tax_faq_response(trace)
        self.assertIn("10%", result)
        self.assertIn("15%", result)
        self.assertIn("НДС", result)


if __name__ == "__main__":
    unittest.main()
