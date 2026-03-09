import apiClient from './client'

export interface UserSettings {
  tableau_username: string
  language: 'zh' | 'en'
  analysis_depth: 'detailed' | 'comprehensive'
  theme: 'light' | 'dark' | 'system'
  default_datasource_id: string | null
  show_thinking_process: boolean
  created_at: string
  updated_at: string
}

export interface UpdateUserSettingsRequest {
  language?: 'zh' | 'en'
  analysis_depth?: 'detailed' | 'comprehensive'
  theme?: 'light' | 'dark' | 'system'
  default_datasource_id?: string | null
  show_thinking_process?: boolean
}

export const settingsApi = {
  async getSettings(): Promise<UserSettings> {
    return apiClient.get<UserSettings>('/api/settings')
  },

  async updateSettings(settings: UpdateUserSettingsRequest): Promise<UserSettings> {
    return apiClient.put<UserSettings>('/api/settings', settings)
  },
}
