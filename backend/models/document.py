"""
SQLAlchemy models for documents and related entities.
"""
from __future__ import annotations
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Date,
    DateTime,
    Text,
    JSON,
    Float,
    ForeignKey,
    Integer,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship

from core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String, nullable=False)
    document_type = Column(String(50), nullable=False)  # law | regulation | court_decision | guideline
    document_number = Column(String(100), nullable=True)
    date_published = Column(Date, nullable=True)
    date_effective = Column(Date, nullable=True)
    language = Column(String(2), nullable=False, default="ka")
    category = Column(String(50), nullable=True)
    authority = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    full_text = Column(Text, nullable=True)
    source_url = Column(String, nullable=False)
    file_hash = Column(String(64), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    relations_from = relationship("DocumentRelation", back_populates="source_document", foreign_keys="DocumentRelation.source_doc_id", cascade="all, delete-orphan")
    relations_to = relationship("DocumentRelation", back_populates="target_document", foreign_keys="DocumentRelation.target_doc_id", cascade="all, delete-orphan")


Index("idx_documents_type", Document.document_type)
Index("idx_documents_category", Document.category)
Index("idx_documents_date", Document.date_published)
Index("idx_documents_language", Document.language)
Index("idx_documents_status", Document.status)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    tokens_count = Column(Integer, nullable=True)
    start_position = Column(Integer, nullable=True)
    end_position = Column(Integer, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    embedding = Column(Vector(768), nullable=True)  # paraphrase-mpnet (legacy)
    embedding_v2 = Column(Vector(1024), nullable=True)  # bge-m3 (Phase 5)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="chunks")


Index("idx_chunks_document", DocumentChunk.document_id)


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_doc_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    target_doc_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(50), nullable=True)  # amends | references | repeals
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    source_document = relationship("Document", foreign_keys=[source_doc_id], back_populates="relations_from")
    target_document = relationship("Document", foreign_keys=[target_doc_id], back_populates="relations_to")


class DecisionFacts(Base):
    """Structured attributes extracted from one dispute/court decision.

    One row per court_decision document; the aggregate layer for dispute
    statistics (win rates by article / body / year) builds on this table.
    """
    __tablename__ = "decision_facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    authority_body = Column(String(40), nullable=True)   # revenue_service_council | mof_dispute_council | city_court | appeals_court | supreme_court | other
    decision_number = Column(String(100), nullable=True)
    decision_date = Column(Date, nullable=True)
    dispute_type = Column(String(20), nullable=True)     # tax | customs | both | other
    contested_articles = Column(JSON, nullable=True)     # ["304", "168", ...] Tax Code article numbers
    amount_gel = Column(Float, nullable=True)            # disputed amount when stated
    outcome = Column(String(30), nullable=True)          # satisfied | partially_satisfied | rejected | unclear
    in_favor = Column(String(20), nullable=True)         # taxpayer | authority | partial | unclear
    raw_json = Column(JSON, nullable=True)               # full LLM extraction payload
    model = Column(String(60), nullable=True)
    extraction_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document")


Index("idx_decision_facts_outcome", DecisionFacts.outcome)
Index("idx_decision_facts_body", DecisionFacts.authority_body)
Index("idx_decision_facts_date", DecisionFacts.decision_date)
Index("idx_decision_facts_type", DecisionFacts.dispute_type)


class LawAmendment(Base):
    """Structured attributes of one amendment act ("...კანონში ცვლილების შეტანის შესახებ").

    Feeds the law-change timeline: which law was amended, when the amendment
    was adopted, when it entered into force, and which articles it touched
    (with short old/new norm summaries).
    """
    __tablename__ = "law_amendments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    amendment_doc_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True)
    target_law_doc_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    target_law_title = Column(String, nullable=True)     # Georgian name of the amended law
    adoption_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=True)           # in_force | not_yet | unknown
    affected_articles = Column(JSON, nullable=True)      # [{article, action: amended|added|repealed, summary_ru, old_norm, new_norm}]
    raw_json = Column(JSON, nullable=True)
    model = Column(String(60), nullable=True)
    extraction_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    amendment_document = relationship("Document", foreign_keys=[amendment_doc_id])
    target_law_document = relationship("Document", foreign_keys=[target_law_doc_id])


Index("idx_law_amendments_target", LawAmendment.target_law_doc_id)
Index("idx_law_amendments_adoption", LawAmendment.adoption_date)
