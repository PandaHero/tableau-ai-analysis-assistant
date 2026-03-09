import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

// 配置 markdown-it 实例
const md = new MarkdownIt({
  html: false, // 禁用 HTML 标签（安全性）
  xhtmlOut: true, // 使用 XHTML 风格的标签
  breaks: true, // 将换行符转换为 <br>
  linkify: true, // 自动识别 URL 并转换为链接
  typographer: true, // 启用智能引号和其他排版替换
  highlight: (str: string, lang: string) => {
    // 代码高亮
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (err) {
        console.error('代码高亮失败:', err)
      }
    }
    return '' // 使用默认转义
  }
})

/**
 * 渲染 Markdown 内容
 * 
 * @param content - 原始 Markdown 内容
 * @returns 渲染后的 HTML 字符串
 */
export function renderMarkdown(content: string): string {
  if (!content || typeof content !== 'string') {
    return ''
  }

  try {
    return md.render(content)
  } catch (err) {
    console.error('Markdown 渲染失败:', err)
    return content
  }
}

/**
 * 清理和渲染 Markdown 内容
 * 
 * @param content - 原始 Markdown 内容
 * @returns 渲染后的 HTML 字符串（已清理，防止 XSS）
 */
export function sanitizeMarkdown(content: string): string {
  if (!content || typeof content !== 'string') {
    return ''
  }

  try {
    // 渲染 Markdown
    const rendered = md.render(content)
    
    // 额外的安全清理：移除潜在的危险属性
    return rendered
      .replace(/on\w+="[^"]*"/gi, '') // 移除事件处理器
      .replace(/javascript:/gi, '') // 移除 javascript: 协议
  } catch (err) {
    console.error('Markdown 渲染失败:', err)
    return content // 渲染失败时返回原始内容
  }
}

/**
 * 渲染内联 Markdown（不包含块级元素）
 * 
 * @param content - 原始 Markdown 内容
 * @returns 渲染后的 HTML 字符串
 */
export function renderInlineMarkdown(content: string): string {
  if (!content || typeof content !== 'string') {
    return ''
  }

  try {
    return md.renderInline(content)
  } catch (err) {
    console.error('内联 Markdown 渲染失败:', err)
    return content
  }
}
