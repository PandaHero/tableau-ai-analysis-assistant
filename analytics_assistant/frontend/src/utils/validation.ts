/**
 * 检查字符串是否为空或只包含空白字符
 * 
 * @param str - 要检查的字符串
 * @returns 如果为空或只包含空白字符则返回 true
 */
export function isEmptyOrWhitespace(str: string | null | undefined): boolean {
  return !str || str.trim().length === 0
}

/**
 * 清理用户输入，移除潜在的危险字符
 * 
 * @param input - 用户输入的字符串
 * @returns 清理后的字符串
 */
export function sanitizeInput(input: string): string {
  if (!input || typeof input !== 'string') {
    return ''
  }

  // 移除控制字符（除了换行符和制表符）
  let sanitized = input.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')

  // 移除零宽字符
  sanitized = sanitized.replace(/[\u200B-\u200D\uFEFF]/g, '')

  // 移除 HTML 标签
  sanitized = sanitized.replace(/<[^>]*>/g, '')

  // 移除 JavaScript 协议
  sanitized = sanitized.replace(/javascript:/gi, '')

  return sanitized.trim()
}

/**
 * 验证消息长度
 * 
 * @param message - 消息内容
 * @param maxLength - 最大长度（默认 10000）
 * @returns 验证结果对象
 */
export function validateMessageLength(
  message: string,
  maxLength: number = 10000
): { valid: boolean; error?: string } {
  if (isEmptyOrWhitespace(message)) {
    return { valid: false, error: '消息不能为空' }
  }

  if (message.length > maxLength) {
    return { valid: false, error: `消息长度不能超过 ${maxLength} 个字符` }
  }

  return { valid: true }
}

/**
 * 截断文本到指定长度
 * 
 * @param text - 要截断的文本
 * @param maxLength - 最大长度
 * @param suffix - 截断后添加的后缀（默认 '...'）
 * @returns 截断后的文本
 */
export function truncateText(
  text: string,
  maxLength: number,
  suffix: string = '...'
): string {
  if (!text || text.length <= maxLength) {
    return text
  }

  return text.substring(0, maxLength - suffix.length) + suffix
}

/**
 * 验证会话标题
 * 
 * @param title - 会话标题
 * @returns 验证结果对象
 */
export function validateSessionTitle(title: string): { valid: boolean; error?: string } {
  if (isEmptyOrWhitespace(title)) {
    return { valid: false, error: '会话标题不能为空' }
  }

  if (title.length > 100) {
    return { valid: false, error: '会话标题不能超过 100 个字符' }
  }

  return { valid: true }
}

/**
 * 验证快捷提示
 * 
 * @param prompt - 快捷提示对象
 * @returns 验证结果对象
 */
export function validateBoostPrompt(prompt: {
  title: string
  content: string
}): { valid: boolean; error?: string } {
  if (isEmptyOrWhitespace(prompt.title)) {
    return { valid: false, error: '标题不能为空' }
  }

  if (prompt.title.length > 50) {
    return { valid: false, error: '标题不能超过 50 个字符' }
  }

  if (isEmptyOrWhitespace(prompt.content)) {
    return { valid: false, error: '内容不能为空' }
  }

  if (prompt.content.length > 500) {
    return { valid: false, error: '内容不能超过 500 个字符' }
  }

  return { valid: true }
}
