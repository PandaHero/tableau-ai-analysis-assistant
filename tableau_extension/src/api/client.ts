import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const API_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT) || 30000

class ApiClient {
  private instance: AxiosInstance

  constructor() {
    this.instance = axios.create({
      baseURL: API_BASE_URL,
      timeout: API_TIMEOUT,
      headers: {
        'Content-Type': 'application/json'
      }
    })

    // 请求拦截器
    this.instance.interceptors.request.use(
      (config) => {
        // 可以在这里添加token等
        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )

    // 响应拦截器
    this.instance.interceptors.response.use(
      (response) => {
        return response
      },
      (error) => {
        // 统一错误处理
        console.error('API Error:', error)
        return Promise.reject(error)
      }
    )
  }

  async get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.instance.get(url, config)
    return response.data
  }

  async post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.instance.post(url, data, config)
    return response.data
  }

  async put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.instance.put(url, data, config)
    return response.data
  }

  async delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response: AxiosResponse<T> = await this.instance.delete(url, config)
    return response.data
  }
}

export const apiClient = new ApiClient()

// ═══════════════════════════════════════════════════════════════════════════
// 预热 API
// ═══════════════════════════════════════════════════════════════════════════

export interface PreloadResponse {
  status: 'ready' | 'loading' | 'pending' | 'failed' | 'expired'
  task_id?: string
  message?: string
}

export interface PreloadStatusResponse {
  task_id: string
  status: 'ready' | 'loading' | 'pending' | 'failed' | 'expired'
  datasource_luid: string
  error?: string
  started_at?: string
  completed_at?: string
}

export interface CacheStatusResponse {
  datasource_luid: string
  is_valid: boolean
  ttl_remaining?: number
  cached_at?: string
}

/**
 * 启动维度层级预热
 */
export async function startDimensionHierarchyPreload(
  datasourceLuid: string,
  force: boolean = false
): Promise<PreloadResponse> {
  return apiClient.post<PreloadResponse>('/api/preload/dimension-hierarchy', {
    datasource_luid: datasourceLuid,
    force
  })
}

/**
 * 查询预热任务状态
 */
export async function getPreloadStatus(taskId: string): Promise<PreloadStatusResponse> {
  return apiClient.get<PreloadStatusResponse>(`/api/preload/status/${taskId}`)
}

/**
 * 使缓存失效
 */
export async function invalidatePreloadCache(datasourceLuid: string): Promise<{ success: boolean; message: string }> {
  return apiClient.post('/api/preload/invalidate', {
    datasource_luid: datasourceLuid
  })
}

/**
 * 查询缓存状态
 */
export async function getCacheStatus(datasourceLuid: string): Promise<CacheStatusResponse> {
  return apiClient.get<CacheStatusResponse>(`/api/preload/cache-status/${datasourceLuid}`)
}
