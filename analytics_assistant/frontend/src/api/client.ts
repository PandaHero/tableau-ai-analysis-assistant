import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig } from 'axios'

import { API_BASE_URL } from './config'
import { getTableauUsername } from './tableauUser'

declare global {
  interface Window {
    tableau?: {
      extensions?: {
        environment?: {
          uniqueUserId?: string
        }
        settings?: {
          get(key: string): string | undefined
        }
      }
    }
  }
}

export interface ChatRequest {
  messages: Array<{
    role: 'user' | 'assistant' | 'system'
    content: string
  }>
  datasource_name: string
  session_id?: string
  analysis_depth?: 'detailed' | 'comprehensive'
  language?: 'zh' | 'en'
}

class ApiClient {
  private instance: AxiosInstance

  constructor() {
    this.instance = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    this.instance.interceptors.request.use((config) => {
      config.headers = config.headers || {}
      config.headers['X-Tableau-Username'] = getTableauUsername()
      return config
    })
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.get<T>(url, config)
    return response.data
  }

  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.post<T>(url, data, config)
    return response.data
  }

  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.put<T>(url, data, config)
    return response.data
  }

  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.patch<T>(url, data, config)
    return response.data
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.delete<T>(url, config)
    return response.data
  }
}

const apiClient = new ApiClient()

export default apiClient
export { apiClient }
