/**
 * 生成简单的唯一 ID（基于时间戳和随机数）
 * 
 * @param prefix - ID 前缀（可选）
 * @returns 唯一 ID 字符串
 */
export function generateId(prefix: string = ''): string {
  const timestamp = Date.now().toString(36)
  const randomPart = Math.random().toString(36).substring(2, 9)
  return prefix ? `${prefix}_${timestamp}_${randomPart}` : `${timestamp}_${randomPart}`
}

/**
 * 生成 UUID v4
 * 
 * @returns UUID 字符串
 */
export function generateUUID(): string {
  // 使用 crypto.randomUUID() 如果可用（现代浏览器）
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }

  // 回退到手动实现
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

/**
 * 生成消息 ID
 * 
 * @returns 消息 ID
 */
export function generateMessageId(): string {
  return generateId('msg')
}

/**
 * 生成会话 ID
 * 
 * @returns 会话 ID
 */
export function generateSessionId(): string {
  return generateUUID()
}

/**
 * 生成快捷提示 ID
 * 
 * @returns 快捷提示 ID
 */
export function generateBoostPromptId(): string {
  return generateId('boost')
}
