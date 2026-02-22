"""
SQLAlchemy models for documents and related entities.
"""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Date,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Integer,
    Boolean,
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
    embedding = Column(Vector(768), nullable=True)  # pgvector for semantic search

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
