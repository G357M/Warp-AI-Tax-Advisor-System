export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

export interface AIResponse {
  answer: string
  sources?: Array<{
    title: string
    url: string
    snippet: string
  }>
}

export interface SourceInfo {
  text: string;
  relevance: number;
  metadata?: {
    title?: string;
    document_type?: string;
    source_url?: string;
    article_ref?: string | null;
    point_ref?: string | null;
    section_label?: string | null;
    document_number?: string | null;
    date_published?: string | null;
    date_effective?: string | null;
    document_status?: string | null;
    authority?: string | null;
    retrieval_channel?: string | null;
  };
}

export interface EvidenceInfo {
  status: 'grounded' | 'partial' | 'insufficient' | 'out_of_scope';
  basis: 'retrieval' | 'authoritative' | 'none' | 'scope';
  coverage: 'exact_provision' | 'official_documents' | 'none';
  question_class?: string | null;
  source_count: number;
  official_sources_only: boolean;
  has_precise_citation: boolean;
  generated_at: string;
}
