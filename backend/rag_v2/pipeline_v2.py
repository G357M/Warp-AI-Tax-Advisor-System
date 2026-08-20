from __future__ import annotations

from collections.abc import Iterable

from .query_parser import parse_query
from .query_classifier import classify_query
from .candidate_generators import generate_candidates
from .candidate_merger import merge_candidates
from .legal_reranker import rerank_candidates
from .context_builder import build_context_plan
from .source_audit import audit_sources
from .answer_policy import build_answer_policy
from .models import ExplainabilityTrace


class PipelineV2:
    def build_trace(
        self,
        query: str,
        language: str = "ru",
        disabled_channels: Iterable[str] | None = None,
    ) -> ExplainabilityTrace:
        parsed = parse_query(query, language=language)
        classification = classify_query(parsed)
        routing_profile = self._routing_profile(parsed, classification.question_class)
        requested_disabled = set(disabled_channels or ())
        known_channels = set(routing_profile["enabled_channels"]) | set(
            routing_profile["disabled_channels"]
        )
        unknown_channels = requested_disabled - known_channels
        if unknown_channels:
            raise ValueError(
                "unknown RAG v2 channels: " + ", ".join(sorted(unknown_channels))
            )
        routing_profile["disabled_channels"] = sorted(
            set(routing_profile["disabled_channels"]) | requested_disabled
        )
        routing_profile["enabled_channels"] = sorted(
            known_channels - set(routing_profile["disabled_channels"])
        )
        routing = {
            "question_class": classification.question_class,
            "retrieval_mode": self._routing_mode(classification.question_class),
            "primary_source_classes": self._primary_source_classes(classification.question_class),
            "channel_priority": routing_profile["channel_priority"],
            "enabled_channels": routing_profile["enabled_channels"],
            "disabled_channels": routing_profile["disabled_channels"],
            "stop_on_exact": routing_profile["stop_on_exact"],
        }

        candidate_map = generate_candidates(parsed, routing_profile=routing_profile)
        candidate_generation = {
            "channels_used": [name for name, items in candidate_map.items() if items],
            "channels_skipped": [name for name, items in candidate_map.items() if not items],
            "channel_outputs": {
                name: [item.model_dump() for item in items]
                for name, items in candidate_map.items()
            },
        }

        merge_result = merge_candidates(candidate_map)
        merged_candidates = merge_result["merged_candidates"]

        reranking = rerank_candidates(parsed, classification, merged_candidates)
        reranking["merge_summary"] = {
            "input_candidate_count": sum(len(items) for items in candidate_map.values()),
            "merged_candidate_count": len(merged_candidates),
        }
        context_assembly = build_context_plan(reranking, classification.question_class)
        answer_policy = build_answer_policy(classification, parsed.model_dump())
        source_audit = audit_sources(parsed, classification, reranking)

        return ExplainabilityTrace(
            query={
                "raw": query,
                "language": language,
                "normalized": parsed.normalized_query,
            },
            parsed_query=parsed.model_dump(),
            classification=classification.model_dump(),
            routing=routing,
            candidate_generation=candidate_generation,
            reranking=reranking,
            context_assembly=context_assembly,
            answer_policy=answer_policy,
            source_audit=source_audit,
            final_output={},
        )

    @staticmethod
    def _routing_mode(question_class: str) -> str:
        mapping = {
            "canonical_law_lookup": "code_first",
            "practical_tax_guidance": "guidance_first",
            "local_regulation_lookup": "local_first",
            "dispute_practice": "dispute_first",
            "named_document_lookup": "exact_document_first",
            "amendment_tracking": "amendment_first",
        }
        return mapping.get(question_class, "generic")

    @staticmethod
    def _primary_source_classes(question_class: str):
        mapping = {
            "canonical_law_lookup": ["law", "regulation"],
            "practical_tax_guidance": ["guideline", "law", "regulation"],
            "local_regulation_lookup": ["regulation", "law"],
            "dispute_practice": ["court_decision"],
            "named_document_lookup": ["exact_document"],
            "amendment_tracking": ["law", "regulation"],
        }
        return mapping.get(question_class, [])

    @staticmethod
    def _routing_profile(parsed, question_class: str) -> dict:
        base_channels = {
            "exact_doc_resolver",
            "citation_resolver",
            "article_resolver",
            "point_resolver",
            "metadata_search",
            "bm25_search",
            "semantic_search",
        }
        profiles = {
            "canonical_law_lookup": {
                "enabled_channels": list(base_channels),
                "disabled_channels": [],
                "channel_priority": {
                    "point_resolver": 100,
                    "article_resolver": 95,
                    "citation_resolver": 90,
                    "exact_doc_resolver": 85,
                    "metadata_search": 70,
                    "bm25_search": 60,
                    "semantic_search": 50,
                },
                "stop_on_exact": False,
            },
            "practical_tax_guidance": {
                "enabled_channels": list(base_channels),
                "disabled_channels": [],
                "channel_priority": {
                    "metadata_search": 100,
                    "bm25_search": 90,
                    "semantic_search": 85,
                    "citation_resolver": 70,
                    "article_resolver": 65,
                    "point_resolver": 60,
                    "exact_doc_resolver": 55,
                },
                "stop_on_exact": False,
            },
            "local_regulation_lookup": {
                "enabled_channels": list(base_channels),
                "disabled_channels": [],
                "channel_priority": {
                    "metadata_search": 100,
                    "bm25_search": 92,
                    "semantic_search": 75,
                    "citation_resolver": 60,
                    "article_resolver": 55,
                    "point_resolver": 50,
                    "exact_doc_resolver": 50,
                },
                "stop_on_exact": False,
            },
            "dispute_practice": {
                "enabled_channels": list(base_channels),
                "disabled_channels": [],
                "channel_priority": {
                    "citation_resolver": 100,
                    "metadata_search": 95,
                    "bm25_search": 85,
                    "semantic_search": 80,
                    "exact_doc_resolver": 75,
                    "article_resolver": 55,
                    "point_resolver": 50,
                },
                "stop_on_exact": False,
            },
            "named_document_lookup": {
                "enabled_channels": list(base_channels),
                "disabled_channels": [],
                "channel_priority": {
                    "exact_doc_resolver": 100,
                    "citation_resolver": 95,
                    "article_resolver": 65,
                    "point_resolver": 60,
                    "metadata_search": 45,
                    "bm25_search": 25,
                    "semantic_search": 10,
                },
                "stop_on_exact": True,
            },
            "amendment_tracking": {
                "enabled_channels": list(base_channels),
                "disabled_channels": [],
                "channel_priority": {
                    "citation_resolver": 100,
                    "metadata_search": 92,
                    "bm25_search": 85,
                    "semantic_search": 72,
                    "exact_doc_resolver": 70,
                    "article_resolver": 55,
                    "point_resolver": 50,
                },
                "stop_on_exact": False,
            },
        }

        profile = dict(profiles.get(question_class, profiles["canonical_law_lookup"]))
        if parsed.document_ref or parsed.decision_ref:
            profile["stop_on_exact"] = True
            profile["channel_priority"] = {
                **profile["channel_priority"],
                "exact_doc_resolver": 110,
                "citation_resolver": 105,
            }
        return profile


pipeline_v2 = PipelineV2()
