import axios from 'axios'
import { AIResponse, EvidenceInfo, SourceInfo } from './types'

export type { SourceInfo } from './types'

const API_URL = '/api/v1/public'

export const apiClient = axios.create({
  baseURL: API_URL,
  // RAG answers can take a while, but a hung request must eventually
  // surface as an honest error instead of an endless "searching" state.
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export interface QueryRequest {
  query: string;
  language?: string;
}

export interface QueryResponse {
  response: string;
  sources: SourceInfo[];
  evidence: EvidenceInfo;
  retrieved_count: number;
  processing_time: number;
}

export async function sendQuery(question: string): Promise<AIResponse> {
  const response = await axios.post(`${API_URL}/query`, {
    query: question,
    language: 'ka'
  })
  return {
    answer: response.data.response,
    sources: response.data.sources
  }
}

export async function getHealth() {
  const response = await axios.get('/health')
  return response.data
}
