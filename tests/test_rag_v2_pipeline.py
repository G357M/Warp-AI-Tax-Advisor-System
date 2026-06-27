import unittest

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

    def test_dispute_query_prefers_court_decision(self):
        trace, top = self._top("Какое решение по спору №19068/2/2023?")
        self.assertEqual(trace.classification["question_class"], "dispute_practice")
        self.assertEqual(trace.candidate_generation["channels_used"], ["citation_resolver"])
        self.assertEqual(top["document_type"], "court_decision")
        self.assertTrue(trace.source_audit["passed"])

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


if __name__ == "__main__":
    unittest.main()
