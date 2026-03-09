import apiClient from './client'

export interface SessionMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
}

export interface ApiSession {
  id: string
  tableau_username: string
  title: string
  messages: SessionMessage[]
  created_at: string
  updated_at: string
}

export interface SessionListResponse {
  sessions: ApiSession[]
  total: number
}

export interface CreateSessionRequest {
  title?: string
}

export interface UpdateSessionRequest {
  title?: string
  messages?: SessionMessage[]
}

export const sessionApi = {
  async getSessions(params?: { offset?: number; limit?: number }): Promise<SessionListResponse> {
    return apiClient.get<SessionListResponse>('/api/sessions', { params })
  },

  async getSession(sessionId: string): Promise<ApiSession> {
    return apiClient.get<ApiSession>(`/api/sessions/${sessionId}`)
  },

  async createSession(data: CreateSessionRequest): Promise<{ session_id: string; created_at: string }> {
    return apiClient.post<{ session_id: string; created_at: string }>('/api/sessions', data)
  },

  async updateSession(sessionId: string, data: UpdateSessionRequest): Promise<ApiSession> {
    return apiClient.put<ApiSession>(`/api/sessions/${sessionId}`, data)
  },

  async deleteSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/api/sessions/${sessionId}`)
  },
}
