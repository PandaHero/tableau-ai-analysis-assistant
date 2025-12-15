<template>
  <div class="markdown-renderer" :class="{ streaming }">
    <div class="markdown-body" v-html="renderedHtml"></div>
    <span v-if="streaming" class="cursor-blink">▊</span>
  </div>
</template>

<script setup lang="ts">
/**
 * MarkdownRenderer 组件
 * 使用 markdown-it 渲染 Markdown 内容，支持语法高亮
 * Requirements: 2.3, 17.1, 17.2, 17.3
 */
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import sql from 'highlight.js/lib/languages/sql'
import python from 'highlight.js/lib/languages/python'
import javascript from 'highlight.js/lib/languages/javascript'

// 注册语言
hljs.registerLanguage('json', json)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('python', python)
hljs.registerLanguage('javascript', javascript)

const props = withDefaults(defineProps<{
  content: string
  streaming?: boolean
}>(), {
  streaming: false
})

// 配置 markdown-it
const md = new MarkdownIt({
  html: false,        // 禁用 HTML 标签（安全）
  linkify: true,      // 自动链接
  typographer: true,  // 排版优化
  breaks: true,       // 换行转 <br>
  highlight: (code: string, lang: string) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch {
        // 忽略高亮错误
      }
    }
    // 转义未识别语言的代码
    return escapeHtml(code)
  }
})

// HTML 转义
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// XSS 防护：移除危险标签和属性
function sanitizeHtml(html: string): string {
  return html
    // 移除 script 标签
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    // 移除 on* 事件属性
    .replace(/\s*on\w+\s*=\s*["'][^"']*["']/gi, '')
    // 移除 javascript: 协议
    .replace(/javascript:/gi, '')
}

// 渲染 Markdown
const renderedHtml = computed(() => {
  if (!props.content) return ''
  
  const html = md.render(props.content)
  return sanitizeHtml(html)
})
</script>

<style scoped>
.markdown-renderer {
  font-size: 14px;
  line-height: 1.7;
  color: #2d3748;
}

.markdown-body {
  word-break: break-word;
}

/* 标题 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin-top: 1em;
  margin-bottom: 0.5em;
  font-weight: 600;
  line-height: 1.4;
  color: #1a202c;
}

.markdown-body :deep(h1) { font-size: 1.5em; }
.markdown-body :deep(h2) { font-size: 1.3em; }
.markdown-body :deep(h3) { font-size: 1.15em; }
.markdown-body :deep(h4) { font-size: 1em; }

/* 段落 */
.markdown-body :deep(p) {
  margin: 0.5em 0;
}

/* 列表 */
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.5em;
}

.markdown-body :deep(li) {
  margin: 0.25em 0;
}

/* 加粗和斜体 */
.markdown-body :deep(strong) {
  font-weight: 600;
  color: #1a202c;
}

.markdown-body :deep(em) {
  font-style: italic;
}

/* 行内代码 */
.markdown-body :deep(code) {
  background-color: #f1f3f4;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 0.9em;
  color: #e83e8c;
}

/* 代码块 */
.markdown-body :deep(pre) {
  background-color: #1e1e1e;
  border-radius: 8px;
  padding: 12px 16px;
  margin: 0.75em 0;
  overflow-x: auto;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: #d4d4d4;
  font-size: 13px;
  line-height: 1.5;
}

/* 表格 */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75em 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 8px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background-color: #f7fafc;
  font-weight: 600;
}

.markdown-body :deep(tr:nth-child(even)) {
  background-color: #f9fafb;
}

/* 链接 */
.markdown-body :deep(a) {
  color: var(--tableau-blue, #1F77B4);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

/* 引用 */
.markdown-body :deep(blockquote) {
  border-left: 4px solid #e2e8f0;
  margin: 0.75em 0;
  padding: 0.5em 1em;
  color: #718096;
  background-color: #f7fafc;
}

/* 分隔线 */
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 1em 0;
}

/* 流式输出光标 */
.cursor-blink {
  animation: blink 1s infinite;
  color: var(--tableau-blue, #1F77B4);
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* highlight.js 语法高亮主题 */
.markdown-body :deep(.hljs-keyword) { color: #569cd6; }
.markdown-body :deep(.hljs-string) { color: #ce9178; }
.markdown-body :deep(.hljs-number) { color: #b5cea8; }
.markdown-body :deep(.hljs-comment) { color: #6a9955; }
.markdown-body :deep(.hljs-function) { color: #dcdcaa; }
.markdown-body :deep(.hljs-class) { color: #4ec9b0; }
.markdown-body :deep(.hljs-variable) { color: #9cdcfe; }
.markdown-body :deep(.hljs-operator) { color: #d4d4d4; }
.markdown-body :deep(.hljs-punctuation) { color: #d4d4d4; }
.markdown-body :deep(.hljs-property) { color: #9cdcfe; }
.markdown-body :deep(.hljs-attr) { color: #9cdcfe; }
.markdown-body :deep(.hljs-built_in) { color: #4ec9b0; }
</style>
