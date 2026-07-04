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
  metadata?: Record<string, any>;
}
