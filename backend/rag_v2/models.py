from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Literal

QuestionClass = Literal[
    "canonical_law_lookup",
    "practical_tax_guidance",
    "local_regulation_lookup",
    "dispute_practice",
    "named_document_lookup",
    "amendment_tracking",
]


@dataclass
class ParsedQuery:
    raw_query: str
    language: str = "ru"
    normalized_query: str = ""
    topic: Optional[str] = None
    subject: Optional[str] = None
    goal: Optional[str] = None
    document_ref: Optional[str] = None
    article_ref: Optional[str] = None
    point_ref: Optional[str] = None
    decision_ref: Optional[str] = None
    locality: Optional[str] = None
    signals: List[str] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuestionClassification:
    question_class: QuestionClass
    confidence: float = 0.0
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    why: List[str] = field(default_factory=list)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateDocument:
    channel: str
    document_id: Optional[str] = None
    title: str = ""
    document_type: Optional[str] = None
    source_url: Optional[str] = None
    channel_score: float = 0.0
    why: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExplainabilityTrace:
    trace_version: str = "v2"
    query: Dict[str, Any] = field(default_factory=dict)
    parsed_query: Dict[str, Any] = field(default_factory=dict)
    classification: Dict[str, Any] = field(default_factory=dict)
    routing: Dict[str, Any] = field(default_factory=dict)
    candidate_generation: Dict[str, Any] = field(default_factory=dict)
    reranking: Dict[str, Any] = field(default_factory=dict)
    context_assembly: Dict[str, Any] = field(default_factory=dict)
    answer_policy: Dict[str, Any] = field(default_factory=dict)
    source_audit: Dict[str, Any] = field(default_factory=dict)
    final_output: Dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)
