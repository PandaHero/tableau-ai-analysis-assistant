/**
 * Session Store
 * 管理会话状态和持久化
 * Requirements: 12.1, 12.2, 12.3, 12.4, 12.6
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Message, Session } from '@/types'
import { STORAGE_KEYS, SESSION_ARCHIVE_THRESHOLD } from '@/types'

export const useSessionStore = defineStore('session', () => {
  // 当前会话ID
  const sessionId = ref<string>(generateUUID())
  
  // 所有会话列表
  const sessions = ref<Session[]>([])
  
  // 当前会话
  const currentSession = computed(() => 
    sessions.value.find(s => s.id === sessionId.value) || null
  )
  
  // 活跃会话（未归档）
  const activeSessions = computed(() => 
    sessions.value.filter(s => !s.archived)
  )
  
  // 归档会话
  const archivedSessions = computed(() => 
    sessions.value.filter(s => s.archived)
  )

  /**
   * 生成 UUID v4
   * Requirements: 12.1
   */
  function generateUUID(): string {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.random() * 16 | 0
      const v = c === 'x' ? r : (r & 0x3 | 0x8)
      return v.toString(16)
    })
  }

  /**
   * 初始化 - 从 localStorage 恢复
   * Requirements: 12.2
   */
  function initialize() {
    try {
      // 恢复会话列表
      const savedSessions = localStorage.getItem(STORAGE_KEYS.SESSIONS)
      if (savedSessions) {
        sessions.value = JSON.parse(savedSessions)
      }
      
      // 恢复当前会话ID
      const savedCurrentId = localStorage.getItem(STORAGE_KEYS.CURRENT_SESSION)
      if (savedCurrentId && sessions.value.some(s => s.id === savedCurrentId)) {
        sessionId.value = savedCurrentId
      } else {
        // 创建新会话
        createNewSession()
      }
      
      // 检查并归档过期会话
      archiveOldSessions()
    } catch (e) {
      console.error('Failed to restore sessions:', e)
      createNewSession()
    }
  }

  /**
   * 创建新会话
   * Requirements: 12.3
   */
  function createNewSession(): string {
    const newId = generateUUID()
    const newSession: Session = {
      id: newId,
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      archived: false
    }
    
    sessions.value.push(newSession)
    sessionId.value = newId
    
    persist()
    return newId
  }

  /**
   * 更新当前会话的消息
   */
  function updateMessages(messages: Message[]) {
    const session = sessions.value.find(s => s.id === sessionId.value)
    if (session) {
      session.messages = messages
      session.updatedAt = Date.now()
      persist()
    }
  }

  /**
   * 归档过期会话
   * Requirements: 12.4
   */
  function archiveOldSessions() {
    const now = Date.now()
    let changed = false
    
    sessions.value.forEach(session => {
      if (!session.archived && (now - session.createdAt) > SESSION_ARCHIVE_THRESHOLD) {
        session.archived = true
        changed = true
      }
    })
    
    if (changed) {
      persist()
    }
  }

  /**
   * 删除会话
   */
  function deleteSession(id: string) {
    const index = sessions.value.findIndex(s => s.id === id)
    if (index !== -1) {
      sessions.value.splice(index, 1)
      
      // 如果删除的是当前会话，创建新会话
      if (id === sessionId.value) {
        createNewSession()
      } else {
        persist()
      }
    }
  }

  /**
   * 清除所有历史
   * Requirements: 12.5
   */
  function clearAllSessions() {
    sessions.value = []
    createNewSession()
  }

  /**
   * 持久化到 localStorage
   * Requirements: 12.6
   */
  function persist() {
    try {
      localStorage.setItem(STORAGE_KEYS.SESSIONS, JSON.stringify(sessions.value))
      localStorage.setItem(STORAGE_KEYS.CURRENT_SESSION, sessionId.value)
    } catch (e) {
      console.error('Failed to persist sessions:', e)
    }
  }

  /**
   * 获取会话
   */
  function getSession(id: string): Session | null {
    return sessions.value.find(s => s.id === id) || null
  }

  return {
    // 状态
    sessionId,
    sessions,
    
    // 计算属性
    currentSession,
    activeSessions,
    archivedSessions,
    
    // 方法
    initialize,
    createNewSession,
    updateMessages,
    archiveOldSessions,
    deleteSession,
    clearAllSessions,
    getSession,
    generateUUID
  }
})
