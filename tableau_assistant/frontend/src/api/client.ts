/**
 * API 客户端
 */
import axios from 'axios'
import type { AxiosInstance } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://127.0.0.1:8000'

class ApiClient {
  private instance: AxiosInstance

  constructor() {
    this.instance = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: { 'Content-Type': 'application/json' }
    })

    this.instance.interceptors.response.use(
      response => response,
      error => {
        console.error('API Error:', error)
        return Promise.reject(error)
      }
    )
  }

  async get<T>(url: string): Promise<T> {
    const response = await this.instance.get<T>(url)
    return response.data
  }

  async post<T>(url: string, data?: unknown): Promise<T> {
    const response = await this.instance.post<T>(url, data)
    return response.data
  }
}

export const apiClient = new ApiClient()

// API 类型
// 注意：前端使用 datasource_name，后端任务 19.2 会实现 name → luid 转换
export interface ChatRequest {
  question: string
  datasource_name: string
  session_id?: string
  user_id?: string
  analysis_depth?: 'detailed' | 'comprehensive'
  language?: 'zh' | 'en'
}

// 聊天响应 - 与后端 VizQLQueryResponse 对应
export interface ChatResponse {
  executive_summary: string
  key_findings: string[]
  analysis_path: Array<{
    step: string
    description: string
    output: unknown
  }>
  recommendations: string[]
  visualizations: unknown[]
  metadata: {
    duration?: number
    replan_count?: number
    is_analysis_question?: boolean
  }
}

export interface CustomModel {
  name: string
  api_base: string
  api_key?: string
  model_id?: string
  created_at?: number
}

// ========== 聊天 API ==========

/**
 * 同步聊天查询
 */
export async function chat(request: ChatRequest): Promise<ChatResponse> {
  return apiClient.post('/api/chat', request)
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<{ status: string; timestamp: number }> {
  return apiClient.get('/api/health')
}

// ========== 自定义模型 API ==========

export async function getCustomModels(): Promise<{ models: CustomModel[] }> {
  return apiClient.get('/api/models/custom')
}

export async function addCustomModel(model: CustomModel): Promise<{ success: boolean }> {
  return apiClient.post('/api/models/custom', model)
}

export async function testCustomModel(model: Partial<CustomModel>): Promise<{ success: boolean; latency_ms?: number }> {
  return apiClient.post('/api/models/custom/test', model)
}

// ========== 预热 API ==========

export interface PreloadRequest {
  datasource_luid: string
  force?: boolean
}

export interface PreloadResponse {
  status: string
  task_id?: string
  message?: string
  cached: boolean
}

export async function startPreload(request: PreloadRequest): Promise<PreloadResponse> {
  return apiClient.post('/api/preload/dimension-hierarchy', request)
}

export async function getPreloadStatus(taskId: string): Promise<{
  task_id: string
  status: string
  progress?: number
  message?: string
  error?: string
}> {
  return apiClient.get(`/api/preload/status/${taskId}`)
}

export async function getCacheStatus(datasourceLuid: string): Promise<{
  datasource_luid: string
  is_valid: boolean
  status: string
  remaining_ttl_seconds?: number
  cached_at?: number
}> {
  return apiClient.get(`/api/preload/cache-status/${datasourceLuid}`)
}
