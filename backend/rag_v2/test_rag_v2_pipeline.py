import unittest

from backend.rag_v2.faq_tax_matrix import TAX_FAQ_MATRIX, CANONICAL_TAX_CODE_TITLE
from backend.rag_v2.pipeline_v2 import pipeline_v2
from backend.rag_v2.query_parser import parse_query


class PipelineV2RegressionTests(unittest.TestCase):
    def _top(self, query: str):
        trace = pipeline_v2.build_trace(query)
        top = trace.reranking["top_ranked_documents"][0]
        return trace, top

    def test_practical_guidance_prefers_guideline(self):
        trace, top = self._top("Как рассчитывается налог на имущество физлица?")
        self.assertEqual(trace.classification["question_class"], "practical_tax_guidance")
        self.assertEqual(top["document_type"], "guideline")
        self.assertTrue(trace.source_audit["passed"])

    def test_named_document_stops_on_direct_resolution(self):
        trace, top = self._top("Что в документе N1432?")
        self.assertEqual(trace.classification["question_class"], "named_document_lookup")
        self.assertEqual(trace.candidate_generation["channels_used"], ["citation_resolver"])
        self.assertEqual(top["document_id"], "property-guidance-1432")
        self.assertEqual(top["channel"], "citation_resolver")
        self.assertTrue(trace.source_audit["passed"])

    def test_english_no_document_reference_stops_on_direct_resolution(self):
        trace = pipeline_v2.build_trace(
            "What does document No. 1432 say?", language="en"
        )
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(trace.classification["question_class"], "named_document_lookup")
        self.assertEqual(trace.candidate_generation["channels_used"], ["citation_resolver"])
        self.assertEqual(top["document_id"], "property-guidance-1432")
        self.assertEqual(top["channel"], "citation_resolver")
        self.assertTrue(trace.source_audit["passed"])

    def test_english_negative_no_before_number_is_not_a_document_reference(self):
        parsed = parse_query("There were no 1432 responses", language="en")
        self.assertIsNone(parsed.document_ref)

    def test_english_part_before_number_is_not_an_article_reference(self):
        parsed = parse_query("This is part 202 of the Tax Code", language="en")
        self.assertIsNone(parsed.article_ref)
        self.assertIsNone(parsed.point_ref)

    def test_article_lookup_prefers_article_resolver(self):
        trace, top = self._top("Что говорит статья 168 Налогового кодекса?")
        self.assertEqual(trace.classification["question_class"], "canonical_law_lookup")
        self.assertEqual(top["channel"], "article_resolver")
        self.assertEqual(top["document_type"], "law")
        self.assertTrue(trace.source_audit["passed"])

    def test_generic_article_lookup_uses_article_resolver_for_tax_code(self):
        trace, top = self._top("Что говорит статья 169 Налогового кодекса?")
        self.assertEqual(trace.classification["question_class"], "canonical_law_lookup")
        self.assertEqual(top["channel"], "article_resolver")
        self.assertEqual(top["document_type"], "law")
        self.assertEqual(top["metadata"].get("article_ref"), "169")
        self.assertEqual(top["metadata"].get("section_label"), "მუხლი 169")
        self.assertTrue(trace.source_audit["passed"])

    def test_generic_point_lookup_uses_point_resolver_for_tax_code(self):
        trace, top = self._top("Что говорит статья 169 пункт 1 Налогового кодекса?")
        self.assertEqual(trace.classification["question_class"], "canonical_law_lookup")
        self.assertEqual(top["channel"], "point_resolver")
        self.assertEqual(top["document_type"], "law")
        self.assertEqual(top["metadata"].get("point_ref"), "169.1")
        self.assertEqual(top["metadata"].get("section_label"), "მუხლი 169 პუნქტი 1")
        self.assertTrue(trace.source_audit["passed"])

    def test_russian_tax_code_abbreviation_routes_generic_article(self):
        trace, top = self._top("Что говорит ст. 202 НК Грузии?")
        self.assertEqual(trace.parsed_query["topic"], "tax")
        self.assertEqual(trace.classification["question_class"], "canonical_law_lookup")
        self.assertEqual(top["channel"], "article_resolver")
        self.assertEqual(top["metadata"].get("article_ref"), "202")
        self.assertTrue(trace.source_audit["passed"])

    def test_english_art_abbreviation_routes_generic_article(self):
        trace = pipeline_v2.build_trace(
            "What does Art. 202 of the Georgian Tax Code say?", language="en"
        )
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(trace.parsed_query["article_ref"], "202")
        self.assertEqual(top["channel"], "article_resolver")
        self.assertEqual(top["metadata"].get("article_ref"), "202")
        self.assertTrue(trace.source_audit["passed"])

    def test_parenthetical_point_references_route_to_point_resolver(self):
        cases = (
            ("ru", "Что говорит ст. 169(1) Налогового кодекса?"),
            ("en", "What does Article 169(1) of the Tax Code say?"),
            ("ka", "რა წერია საგადასახადო კოდექსის 169-ე მუხლის (1) პუნქტში?"),
        )
        for language, query in cases:
            with self.subTest(language=language):
                trace = pipeline_v2.build_trace(query, language=language)
                top = trace.reranking["top_ranked_documents"][0]
                self.assertEqual(trace.parsed_query["article_ref"], "169")
                self.assertEqual(trace.parsed_query["point_ref"], "169.1")
                self.assertEqual(top["channel"], "point_resolver")
                self.assertEqual(top["metadata"].get("point_ref"), "169.1")
                self.assertTrue(trace.source_audit["passed"])

    def test_dispute_query_prefers_court_decision(self):
        trace, top = self._top("Какое решение по спору №19068/2/2023?")
        self.assertEqual(trace.classification["question_class"], "dispute_practice")
        self.assertEqual(trace.candidate_generation["channels_used"], ["citation_resolver"])
        self.assertEqual(top["document_type"], "court_decision")
        self.assertTrue(trace.source_audit["passed"])

    def test_homepage_appeal_examples_route_to_normative_guidance(self):
        cases = (
            ("ru", "Как обжаловать решение налоговой?"),
            ("en", "How do I appeal a tax decision?"),
            ("ka", "როგორ გავასაჩივრო საგადასახადოს გადაწყვეტილება?"),
        )
        for language, query in cases:
            with self.subTest(language=language):
                parsed = parse_query(query, language=language)
                self.assertEqual(parsed.topic, "tax")
                self.assertEqual(parsed.goal, "appeal_procedure")
                self.assertIn("appeal_procedure", parsed.signals)
                self.assertNotIn("dispute", parsed.signals)

                trace = pipeline_v2.build_trace(
                    query,
                    language=language,
                    disabled_channels={"semantic_search"},
                )
                self.assertEqual(
                    trace.classification["question_class"],
                    "practical_tax_guidance",
                )
                top = trace.reranking["top_ranked_documents"][0]
                self.assertNotEqual(top["document_type"], "court_decision")
                self.assertTrue(trace.source_audit["passed"])

    def test_homepage_llc_examples_resolve_article_88_without_semantic_search(self):
        cases = (
            ("ru", "Может ли ООО применять налог 1%?"),
            ("en", "Can an LLC use the 1% tax regime?"),
            ("ka", "შეუძლია თუ არა შპს-ს 1%-იანი გადასახადი?"),
        )
        for language, query in cases:
            with self.subTest(language=language):
                trace = pipeline_v2.build_trace(query, language=language)
                top = trace.reranking["top_ranked_documents"][0]
                self.assertEqual(trace.parsed_query["topic"], "small_business")
                self.assertEqual(trace.parsed_query["subject"], "legal_entity")
                self.assertEqual(
                    trace.parsed_query["goal"], "small_business_eligibility"
                )
                self.assertEqual(
                    trace.candidate_generation["channels_used"], ["metadata_search"]
                )
                self.assertEqual(top["document_id"], "7413ae69-672c-4c48-b3d5-8c04b09dfb43")
                self.assertEqual(top["metadata"].get("article_ref"), "88")
                self.assertTrue(trace.source_audit["passed"])

    def test_residency_and_late_payment_queries_resolve_exact_articles_in_all_languages(self):
        cases = (
            ("ru", "Когда физлицо становится налоговым резидентом Грузии?", "tax_residency", "residency_status", "34"),
            ("en", "When does an individual become a tax resident of Georgia?", "tax_residency", "residency_status", "34"),
            ("ka", "როდის ითვლება ფიზიკური პირი საქართველოს საგადასახადო რეზიდენტად?", "tax_residency", "residency_status", "34"),
            ("ru", "Какая пеня начисляется за просрочку уплаты налога в Грузии?", "late_payment_interest", "penalty_rate", "272"),
            ("en", "What late payment interest applies to overdue tax in Georgia?", "late_payment_interest", "penalty_rate", "272"),
            ("ka", "რა საურავი ერიცხება ვადაგადაცილებულ გადასახადს საქართველოში?", "late_payment_interest", "penalty_rate", "272"),
        )
        for language, query, topic, goal, article_ref in cases:
            with self.subTest(language=language, goal=goal):
                trace = pipeline_v2.build_trace(query, language=language)
                top = trace.reranking["top_ranked_documents"][0]
                self.assertEqual(trace.parsed_query["topic"], topic)
                self.assertEqual(trace.parsed_query["goal"], goal)
                self.assertEqual(trace.classification["question_class"], "canonical_law_lookup")
                self.assertEqual(trace.candidate_generation["channels_used"], ["metadata_search"])
                self.assertEqual(top["metadata"].get("article_ref"), article_ref)
                self.assertTrue(trace.source_audit["passed"])

    def test_llc_property_tax_is_not_misrouted_to_small_business(self):
        cases = (
            ("ru", "Какая ставка налога на имущество для ООО - 1%?"),
            ("en", "Is the LLC property tax rate 1%?"),
            ("ka", "შპს-ს ქონების გადასახადის განაკვეთი 1%-ია?"),
        )
        for language, query in cases:
            with self.subTest(language=language):
                parsed = parse_query(query, language=language)
                self.assertEqual(parsed.topic, "property_tax")
                self.assertEqual(parsed.subject, "legal_entity")
                self.assertNotEqual(parsed.goal, "small_business_eligibility")

    def test_english_dispute_query_is_not_downgraded_to_named_document(self):
        trace = pipeline_v2.build_trace(
            "What was the decision in dispute №19068/2/2023?", language="en"
        )
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(trace.classification["question_class"], "dispute_practice")
        self.assertEqual(top["document_type"], "court_decision")
        self.assertTrue(trace.source_audit["passed"])

    def test_explicit_channel_disable_is_recorded_and_enforced(self):
        trace = pipeline_v2.build_trace(
            "What does Article 168 of the Tax Code say?",
            language="en",
            disabled_channels={"semantic_search"},
        )
        self.assertIn("semantic_search", trace.routing["disabled_channels"])
        self.assertNotIn("semantic_search", trace.routing["enabled_channels"])
        self.assertNotIn("semantic_search", trace.candidate_generation["channels_used"])

    def test_dispute_query_rejects_neighboring_dispute_reference(self):
        trace, top = self._top("Какое решение по спору №19068/3/2023?")
        self.assertEqual(trace.classification["question_class"], "dispute_practice")
        self.assertEqual(top["document_type"], "court_decision")
        self.assertFalse(trace.source_audit["passed"])
        self.assertIn("exact dispute reference match", " ".join(trace.source_audit["warnings"]))

    def test_local_query_prefers_regulation(self):
        trace, top = self._top("Какая ставка налога на имущество в Дманиси?")
        self.assertEqual(trace.classification["question_class"], "local_regulation_lookup")
        self.assertEqual(top["document_type"], "regulation")
        self.assertIn("metadata_search", trace.candidate_generation["channels_used"])
        self.assertTrue(trace.source_audit["passed"])

    def test_tbilisi_property_tax_query_is_classified_as_local_regulation(self):
        parsed = parse_query("Какая ставка налога на имущество в Тбилиси?")
        self.assertEqual(parsed.locality, "tbilisi")
        trace = pipeline_v2.build_trace("Какая ставка налога на имущество в Тбилиси?")
        self.assertEqual(trace.classification["question_class"], "local_regulation_lookup")

    def test_tbilisi_individual_property_tax_query_prefers_practical_guidance(self):
        parsed = parse_query("Какая ставка налога на имущество физлица в Тбилиси?")
        self.assertEqual(parsed.locality, "tbilisi")
        self.assertEqual(parsed.subject, "individual")
        trace = pipeline_v2.build_trace("Какая ставка налога на имущество физлица в Тбилиси?")
        self.assertEqual(trace.classification["question_class"], "practical_tax_guidance")

    def test_tbilisi_individual_property_tax_query_with_skolko_detects_rate_lookup(self):
        parsed = parse_query("Сколько налог на имущество для физлица в Тбилиси?")
        self.assertEqual(parsed.locality, "tbilisi")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")
        trace = pipeline_v2.build_trace("Сколько налог на имущество для физлица в Тбилиси?")
        self.assertEqual(trace.classification["question_class"], "practical_tax_guidance")

    def test_amendment_query_prefers_current_law(self):
        trace, top = self._top("Какие изменения по НДС в 2026 году?")
        self.assertEqual(trace.classification["question_class"], "amendment_tracking")
        self.assertEqual(top["document_type"], "law")
        self.assertTrue(top["metadata"].get("is_current"))
        self.assertTrue(trace.source_audit["passed"])

    def test_amendment_query_recognizes_popravki_phrasing(self):
        parsed = parse_query("Какие поправки в налоговом кодексе были приняты 1 апреля 2026 года?")
        self.assertEqual(parsed.goal, "amendment_tracking")
        self.assertEqual(parsed.topic, "tax")

    def test_amendment_query_detects_profit_tax_topic(self):
        parsed = parse_query("Какие изменения по налогу на прибыль в 2026 году?")
        self.assertEqual(parsed.goal, "amendment_tracking")
        self.assertEqual(parsed.topic, "profit_tax")

    def test_amendment_query_detects_customs_topic(self):
        parsed = parse_query("Какие изменения по таможне в 2026 году?")
        self.assertEqual(parsed.goal, "amendment_tracking")
        self.assertEqual(parsed.topic, "customs")

    def test_amendment_query_detects_excise_topic(self):
        parsed = parse_query("Какие изменения по акцизу в 2026 году?")
        self.assertEqual(parsed.goal, "amendment_tracking")
        self.assertEqual(parsed.topic, "excise")

    def test_georgian_article_lookup_extracts_article_ref(self):
        parsed = parse_query("რა წერია საქართველოს საგადასახადო კოდექსის 168-ე მუხლში?", language="ka")
        self.assertEqual(parsed.article_ref, "168")
        self.assertEqual(parsed.topic, "tax")

    def test_georgian_article_lookup_prefers_article_resolver(self):
        trace = pipeline_v2.build_trace("რა წერია საქართველოს საგადასახადო კოდექსის 168-ე მუხლში?", language="ka")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(trace.classification["question_class"], "canonical_law_lookup")
        self.assertEqual(top["channel"], "article_resolver")
        self.assertEqual(top["metadata"].get("article_ref"), "168")

    def test_english_article_lookup_extracts_article_ref(self):
        parsed = parse_query("What does Article 168 of the Tax Code say?", language="en")
        self.assertEqual(parsed.article_ref, "168")
        self.assertEqual(parsed.topic, "tax")

    def test_english_amendment_query_is_not_misread_as_document_number(self):
        parsed = parse_query("What changes to VAT were made in 2026?", language="en")
        self.assertIsNone(parsed.document_ref)
        self.assertEqual(parsed.goal, "amendment_tracking")
        trace = pipeline_v2.build_trace("What changes to VAT were made in 2026?", language="en")
        self.assertEqual(trace.classification["question_class"], "amendment_tracking")

    def test_russian_income_tax_rate_query_is_detected(self):
        parsed = parse_query("Какой подоходный налог в Грузии?")
        self.assertEqual(parsed.topic, "tax")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")
        trace = pipeline_v2.build_trace("Какой подоходный налог в Грузии?")
        self.assertIn("metadata_search", trace.candidate_generation["channels_used"])
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "81")
        self.assertTrue(trace.source_audit["passed"])

    def test_vat_rate_query_prefers_tax_code_article_166(self):
        trace = pipeline_v2.build_trace("Сколько процентов НДС в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "166")

    def test_profit_tax_rate_query_prefers_tax_code_article_98(self):
        trace = pipeline_v2.build_trace("Какой налог на прибыль в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "98")

    def test_interest_tax_rate_query_prefers_tax_code_article_131(self):
        trace = pipeline_v2.build_trace("Какой налог на проценты в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "131")

    def test_royalty_tax_rate_query_prefers_tax_code_article_132(self):
        trace = pipeline_v2.build_trace("Какой налог на роялти в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "132")

    def test_import_vat_query_prefers_tax_code_article_168(self):
        trace = pipeline_v2.build_trace("Есть ли НДС при импорте в Грузию?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "168")

    def test_apartment_sale_query_prefers_tax_code_article_81(self):
        trace = pipeline_v2.build_trace("Какой налог на продажу квартиры в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "81")

    def test_vehicle_sale_query_prefers_tax_code_article_81(self):
        trace = pipeline_v2.build_trace("Какой налог на продажу машины в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "81")

    def test_vat_registration_threshold_query_prefers_tax_code_article_165(self):
        trace = pipeline_v2.build_trace("Какой порог регистрации по НДС в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "165")

    def test_vat_registration_timing_query_prefers_tax_code_article_165(self):
        trace = pipeline_v2.build_trace("С какого момента возникает обязанность регистрации по НДС в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "165")

    def test_vat_deregistration_threshold_query_prefers_tax_code_article_1651(self):
        trace = pipeline_v2.build_trace("Какой порог для отмены регистрации по НДС в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "165-1")

    def test_property_tax_company_query_prefers_tax_code_article_202(self):
        trace = pipeline_v2.build_trace("Какой налог на имущество для компании в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "202")

    def test_excise_query_prefers_tax_code_article_188(self):
        trace = pipeline_v2.build_trace("Какой акциз в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "188")

    def test_customs_query_prefers_tax_code_article_197(self):
        trace = pipeline_v2.build_trace("Какая таможенная пошлина в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "197")

    def test_nonresident_service_wht_query_prefers_tax_code_article_134(self):
        trace = pipeline_v2.build_trace("Какой налог у источника на услуги нерезидента в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "134")

    def test_nonresident_wht_query_prefers_tax_code_article_134(self):
        trace = pipeline_v2.build_trace("Какой налог удерживается у источника для нерезидента в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "134")
    def test_georgian_import_vat_question_is_detected(self):
        parsed = parse_query("აქვს თუ არა იმპორტს დღგ საქართველოში?", language="ka")
        self.assertEqual(parsed.topic, "import_vat")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_english_import_vat_question_is_detected(self):
        parsed = parse_query("Is VAT charged on import into Georgia?", language="en")
        self.assertEqual(parsed.topic, "import_vat")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_english_non_residents_question_prefers_tax_code_article_134(self):
        trace = pipeline_v2.build_trace("What withholding tax applies to non-residents in Georgia?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "134")


    def test_dividend_tax_rate_query_prefers_tax_code_article_130(self):
        trace = pipeline_v2.build_trace("Какой налог на дивиденды в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "130")

    def test_small_business_rate_query_prefers_tax_code_article_90(self):
        trace = pipeline_v2.build_trace("Какой налог для малого бизнеса в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "90")

    def test_short_term_rental_query_prefers_tax_code_article_309(self):
        trace = pipeline_v2.build_trace("Какой налог на посуточную аренду квартиры в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "309")

    def test_rental_income_rate_query_prefers_tax_code_article_81(self):
        trace = pipeline_v2.build_trace("Сколько налог на аренду жилья в Грузии?")
        top = trace.reranking["top_ranked_documents"][0]
        self.assertEqual(top["title"], "საქართველოს საგადასახადო კოდექსი.")
        self.assertEqual(top["metadata"].get("article_ref"), "81")

    def test_georgian_income_tax_rate_query_is_detected(self):
        parsed = parse_query("რა პროცენტია საშემოსავლო გადასახადი?", language="ka")
        self.assertEqual(parsed.topic, "tax")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_english_income_tax_rate_query_is_detected(self):
        parsed = parse_query("What is the personal income tax rate in Georgia?", language="en")
        self.assertEqual(parsed.topic, "tax")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_salary_tax_query_is_detected_as_income_tax(self):
        parsed = parse_query("Какой налог на зарплату в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "tax")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_apartment_sale_query_is_detected(self):
        parsed = parse_query("Какой налог на продажу квартиры в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "apartment_sale_tax")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_english_apartment_sale_query_is_detected(self):
        parsed = parse_query("What tax applies to the sale of an apartment in Georgia?", language="en")
        self.assertEqual(parsed.topic, "apartment_sale_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_house_sale_query_is_detected(self):
        parsed = parse_query("Какой налог на продажу дома в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "apartment_sale_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_timing_query_is_detected(self):
        parsed = parse_query("When does the VAT registration obligation arise in Georgia?", language="en")
        self.assertEqual(parsed.topic, "vat_registration_timing")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_nonresident_service_wht_query_is_detected(self):
        parsed = parse_query("What withholding tax applies to non-resident services in Georgia?", language="en")
        self.assertEqual(parsed.topic, "nonresident_service_wht")
        self.assertEqual(parsed.subject, "non_resident")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_property_tax_company_query_is_detected(self):
        parsed = parse_query("What is the property tax for a company in Georgia?", language="en")
        self.assertEqual(parsed.topic, "property_tax_company")
        self.assertEqual(parsed.subject, "legal_entity")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_excise_query_is_detected(self):
        parsed = parse_query("What is the excise tax in Georgia?", language="en")
        self.assertEqual(parsed.topic, "excise")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_customs_query_is_detected(self):
        parsed = parse_query("What customs duty applies in Georgia?", language="en")
        self.assertEqual(parsed.topic, "customs")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_nonresident_service_wht_ru_alt_phrasing_is_detected(self):
        parsed = parse_query("Какое удержание у источника по услугам нерезидента в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "nonresident_service_wht")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_nonresident_service_wht_en_alt_phrasing_is_detected(self):
        parsed = parse_query("What tax applies to services paid to a non-resident in Georgia?", language="en")
        self.assertEqual(parsed.topic, "nonresident_service_wht")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_deregistration_threshold_query_is_detected(self):
        parsed = parse_query("What is the VAT deregistration threshold in Georgia?", language="en")
        self.assertEqual(parsed.topic, "vat_deregistration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_georgian_vat_deregistration_query_is_detected(self):
        parsed = parse_query("როგორ უქმდება დღგ-ის გადამხდელად რეგისტრაცია საქართველოში?", language="ka")
        self.assertEqual(parsed.topic, "vat_deregistration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_threshold_query_is_detected(self):
        parsed = parse_query("What is the VAT registration threshold in Georgia?", language="en")
        self.assertEqual(parsed.topic, "vat_registration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_deregistration_ru_colloquial_is_detected(self):
        parsed = parse_query("Как сняться с НДС в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "vat_deregistration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_timing_ru_colloquial_is_detected(self):
        parsed = parse_query("Когда надо регистрироваться по НДС в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "vat_registration_timing")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_threshold_ru_colloquial_is_detected(self):
        parsed = parse_query("Какой лимит по НДС в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "vat_registration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_house_sale_ru_colloquial_is_detected(self):
        parsed = parse_query("Какой налог при продаже дома в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "apartment_sale_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vehicle_sale_ru_colloquial_is_detected(self):
        parsed = parse_query("Какой налог при продаже машины в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "vehicle_sale_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_nonresident_service_wht_en_colloquial_is_detected(self):
        parsed = parse_query("What tax applies to services paid to a non-resident in Georgia?", language="en")
        self.assertEqual(parsed.topic, "nonresident_service_wht")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_short_term_rental_query_is_detected(self):
        parsed = parse_query("What tax applies to Airbnb income in Georgia?", language="en")
        self.assertEqual(parsed.topic, "short_term_rental_tax")
        self.assertEqual(parsed.subject, "individual")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_airbnb_vat_query_is_detected_as_short_term_rental(self):
        parsed = parse_query("Is Airbnb income subject to VAT in Georgia?", language="en")
        self.assertEqual(parsed.topic, "short_term_rental_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_booking_rental_query_is_detected_as_short_term_rental(self):
        parsed = parse_query("What tax applies to Booking.com apartment rental in Georgia?", language="en")
        self.assertEqual(parsed.topic, "short_term_rental_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_airbnb_vat_ru_colloquial_is_detected(self):
        parsed = parse_query("Нужно ли платить НДС с Airbnb в Грузии?", language="ru")
        self.assertEqual(parsed.topic, "short_term_rental_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_short_term_rental_vat_en_colloquial_is_detected(self):
        parsed = parse_query("Does short-term rental trigger VAT in Georgia?", language="en")
        self.assertEqual(parsed.topic, "short_term_rental_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_interest_tax_georgian_colloquial_is_detected(self):
        parsed = parse_query("რამდენია პროცენტის გადასახადი საქართველოში?", language="ka")
        self.assertEqual(parsed.topic, "interest_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_timing_georgian_colloquial_is_detected(self):
        parsed = parse_query("როდის ხდება დღგ-ზე რეგისტრაცია სავალდებულო?", language="ka")
        self.assertEqual(parsed.topic, "vat_registration_timing")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_deregistration_georgian_colloquial_is_detected(self):
        parsed = parse_query("როგორ მოვიხსნა დღგ-დან?", language="ka")
        self.assertEqual(parsed.topic, "vat_deregistration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_nonresident_service_payment_georgian_colloquial_is_detected(self):
        parsed = parse_query("საქართველოში არარეზიდენტს მომსახურების გადახდაზე რა გადასახადია?", language="ka")
        self.assertEqual(parsed.topic, "nonresident_service_wht")
        self.assertEqual(parsed.subject, "non_resident")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_small_business_georgian_colloquial_is_detected(self):
        parsed = parse_query("რამდენია მცირე მეწარმის გადასახადი საქართველოში?", language="ka")
        self.assertEqual(parsed.topic, "small_business")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_timing_georgian_mitsevs_is_detected(self):
        parsed = parse_query("როდის მიწევს დღგ-ზე დარეგისტრირება?", language="ka")
        self.assertEqual(parsed.topic, "vat_registration_timing")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_registration_timing_georgian_valdebuli_is_detected(self):
        parsed = parse_query("როდის ვალდებული ვარ დღგ-ზე დარეგისტრირდე?", language="ka")
        self.assertEqual(parsed.topic, "vat_registration_timing")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_vat_deregistration_georgian_gavaukmo_is_detected(self):
        parsed = parse_query("როგორ გავაუქმო დღგ-ის რეგისტრაცია?", language="ka")
        self.assertEqual(parsed.topic, "vat_deregistration_threshold")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_rental_income_georgian_qiridan_is_detected(self):
        parsed = parse_query("რამდენია ქირიდან გადასახადი საქართველოში?", language="ka")
        self.assertEqual(parsed.topic, "rental_income")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_airbnb_vat_georgian_unda_gadavikhado_is_detected(self):
        parsed = parse_query("დღგ უნდა გადავიხადო Airbnb-ზე?", language="ka")
        self.assertEqual(parsed.topic, "short_term_rental_tax")
        self.assertEqual(parsed.goal, "rate_lookup")

    def test_tax_faq_matrix_canonical_entries_resolve_to_expected_articles(self):
        for entry in TAX_FAQ_MATRIX:
            if entry.question_class != "canonical_law_lookup":
                continue
            with self.subTest(topic=entry.topic):
                trace = pipeline_v2.build_trace(entry.sample_queries["ru"])
                top = trace.reranking["top_ranked_documents"][0]
                self.assertEqual(top["title"], CANONICAL_TAX_CODE_TITLE)
                self.assertEqual(top["metadata"].get("article_ref"), entry.article_ref)

    def test_tax_faq_matrix_queries_are_classified_as_expected(self):
        for entry in TAX_FAQ_MATRIX:
            with self.subTest(topic=entry.topic):
                parsed = parse_query(entry.sample_queries["ru"], language="ru")
                self.assertEqual(parsed.topic, entry.topic)
                self.assertEqual(parsed.goal, "rate_lookup")
                if entry.subject:
                    self.assertEqual(parsed.subject, entry.subject)


if __name__ == "__main__":
    unittest.main()
