import types
import unittest

from backend.rag_v2.faq_tax_matrix import TAX_FAQ_MATRIX
from backend.rag_v2.public_response import (
    compress_canonical_section_text,
    compress_rollout_context_text,
    authoritative_tax_fact_response,
    direct_tax_faq_response,
    dividend_tax_rate_response,
    finalize_rollout_response,
    import_vat_response,
    income_tax_rate_response,
    individual_property_tax_rate_response,
    interest_tax_rate_response,
    nonresident_withholding_tax_response,
    normalize_public_response_text,
    out_of_domain_response,
    out_of_jurisdiction_response,
    profit_tax_rate_response,
    rental_income_tax_rate_response,
    royalty_tax_rate_response,
    small_business_legal_form_response,
    small_business_tax_rate_response,
    tax_appeal_procedure_response,
    vat_rate_response,
)


class PublicResponseShapeTests(unittest.TestCase):
    def test_residency_and_late_payment_answers_name_exact_articles_in_all_languages(self):
        cases = (
            ("ru", "residency_status", "tax_residency", "183", "34"),
            ("en", "residency_status", "tax_residency", "183", "34"),
            ("ka", "residency_status", "tax_residency", "183", "34"),
            ("ru", "penalty_rate", "late_payment_interest", "0,05%", "272"),
            ("en", "penalty_rate", "late_payment_interest", "0.05%", "272"),
            ("ka", "penalty_rate", "late_payment_interest", "0,05%", "272"),
        )
        for language, goal, topic, value, article in cases:
            with self.subTest(language=language, goal=goal):
                trace = types.SimpleNamespace(
                    parsed_query={
                        "language": language,
                        "normalized_query": "",
                        "goal": goal,
                    }
                )
                actual_topic, answer = authoritative_tax_fact_response(trace)
                self.assertEqual(actual_topic, topic)
                self.assertIn(value, answer)
                self.assertIn(article, answer)

    def test_out_of_jurisdiction_response_supports_all_public_languages(self):
        cases = (
            ("ru", "Какая ставка налога в США?", "Грузии"),
            ("en", "What is the tax rate in the United States?", "Georgian"),
            ("ka", "როგორია გადასახადის განაკვეთი აშშ-ში?", "საქართველოს"),
        )
        for language, query, expected in cases:
            with self.subTest(language=language):
                trace = types.SimpleNamespace(
                    parsed_query={"language": language, "normalized_query": query.lower()}
                )
                self.assertIn(expected, out_of_jurisdiction_response(trace))

    def test_out_of_domain_weather_response_supports_all_public_languages(self):
        cases = (
            ("ru", "Какая погода завтра?", "вне тематики"),
            ("en", "What is tomorrow's weather?", "outside the scope"),
            ("ka", "როგორი ამინდია ხვალ?", "ფარგლებს გარეთ"),
        )
        for language, query, expected in cases:
            with self.subTest(language=language):
                trace = types.SimpleNamespace(
                    parsed_query={"language": language, "normalized_query": query.lower()}
                )
                self.assertIn(expected, out_of_domain_response(trace))

    def test_tax_appeal_procedure_is_precise_in_all_public_languages(self):
        cases = (
            (
                "ru",
                "со дня его вручения",
                "Службу доходов",
                "электронной форме",
                "Источник: Налоговый кодекс Грузии, статьи 296, 297 и 299.",
            ),
            (
                "en",
                "after it is delivered",
                "Revenue Service",
                "filed electronically",
                "Source: Tax Code of Georgia, Articles 296, 297 and 299.",
            ),
            (
                "ka",
                "მისი ჩაბარებიდან",
                "შემოსავლების სამსახურში",
                "ელექტრონული ფორმით",
                "წყარო: საქართველოს საგადასახადო კოდექსი, მუხლები 296, 297 და 299.",
            ),
        )
        for language, delivery_rule, filing_body, filing_form, citation in cases:
            with self.subTest(language=language):
                trace = types.SimpleNamespace(
                    parsed_query={"language": language, "goal": "appeal_procedure"}
                )
                result = tax_appeal_procedure_response(trace)
                self.assertIn("30", result)
                self.assertIn(delivery_rule, result)
                self.assertIn(filing_body, result)
                self.assertIn(filing_form, result)
                self.assertIn(citation, result)
                self.assertNotIn("статист", result.lower())
                self.assertNotIn("statistics", result.lower())
                self.assertNotIn("სტატისტ", result.lower())

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

    def test_homepage_llc_response_is_narrow_and_multilingual(self):
        cases = (
            ("ru", "Может ли ООО применять налог 1%?", "ООО", "индивидуальному"),
            ("en", "Can an LLC use the 1% tax regime?", "LLC", "individual"),
            ("ka", "შეუძლია თუ არა შპს-ს 1%-იანი გადასახადი?", "შპს", "ინდივიდუალური"),
        )
        for language, query, legal_form, eligible_person in cases:
            with self.subTest(language=language):
                trace = types.SimpleNamespace(
                    parsed_query={
                        "language": language,
                        "normalized_query": query.lower(),
                        "goal": "small_business_eligibility",
                    }
                )
                result = small_business_legal_form_response(trace)
                self.assertIn("1%", result)
                self.assertIn(legal_form, result)
                self.assertIn(eligible_person, result)
                self.assertNotIn("15%", result)

    def test_llc_property_tax_does_not_trigger_small_business_guard(self):
        cases = (
            ("ru", "Какая ставка налога на имущество для ООО - 1%?"),
            ("en", "Is the LLC property tax rate 1%?"),
            ("ka", "შპს-ს ქონების გადასახადის განაკვეთი 1%-ია?"),
        )
        for language, query in cases:
            with self.subTest(language=language):
                trace = types.SimpleNamespace(
                    parsed_query={
                        "language": language,
                        "normalized_query": query.lower(),
                        "goal": "rate_lookup",
                    }
                )
                self.assertIsNone(small_business_legal_form_response(trace))

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
