"""
Pydantic schemas for API requests and responses.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID


# ==================== Auth Schemas ====================

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Query Schemas ====================

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    language: Optional[str] = Field(default="ka", pattern="^(ka|ru|en)$")
    conversation_id: Optional[UUID] = None


class SourceInfo(BaseModel):
    document_id: UUID
    title: str
    document_type: str
    url: str
    relevance: float


class QueryResponse(BaseModel):
    response: str
    sources: List[SourceInfo]
    conversation_id: UUID
    retrieved_count: int
    processing_time: Optional[float] = None


# ==================== Document Schemas ====================

class DocumentBase(BaseModel):
    title: str
    document_type: str
    document_number: Optional[str] = None
    language: str = "ka"
    category: Optional[str] = None


class DocumentCreate(DocumentBase):
    full_text: str
    source_url: str


class DocumentResponse(DocumentBase):
    id: UUID
    date_published: Optional[datetime]
    status: str
    source_url: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentDetailResponse(DocumentResponse):
    full_text: Optional[str] = None
    chunks_count: int = 0


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int


# ==================== Conversation Schemas ====================

class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    sources: Optional[List[SourceInfo]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages_count: int = 0

    class Config:
        from_attributes = True


class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse]


# ==================== Admin Schemas ====================

class SystemStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_users: int
    total_conversations: int
    vector_store_count: int


class ScrapeRequest(BaseModel):
    full_rescrape: bool = False
    max_pages: Optional[int] = None


class ScrapeStatus(BaseModel):
    status: str
    documents_scraped: int
    errors: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
