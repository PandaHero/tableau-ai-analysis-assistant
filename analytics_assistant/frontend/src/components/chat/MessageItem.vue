<template>
  <!-- 用户消息 -->
  <div v-if="message.type === 'user'" class="message-row message-row--user">
    <div class="user-bubble">
      <div class="user-text">{{ message.content }}</div>
      <div v-if="formattedTime" class="user-time">{{ formattedTime }}</div>
    </div>
  </div>

  <!-- AI 消息 -->
  <div v-else-if="message.type === 'ai'" class="message-row message-row--ai">
    <div class="ai-card">
      <!-- 卡片头部 -->
      <div class="ai-card-header">
        <span class="ai-title">🤖 AI 助手</span>
        <button class="copy-btn" @click="handleCopy" :title="copied ? '已复制' : '复制'">
          {{ copied ? '✓ 已复制' : '📋 复制' }}
        </button>
      </div>

      <!-- 卡片内容 -->
      <div class="ai-card-body">
        <!-- 多轮分析场景 -->
        <template v-if="aiMessage.rounds && aiMessage.rounds.length > 0">
          <template v-for="(round, idx) in aiMessage.rounds" :key="idx">
            <!-- 分析轮次卡片 -->
            <div class="analysis-round-card">
              <!-- 轮次问题标题（多轮时显示） -->
              <div v-if="aiMessage.rounds!.length > 1 && round.question" class="round-question">
                ❓ {{ round.question }}
              </div>
              <div class="round-divider-dashed" v-if="aiMessage.rounds!.length > 1 && round.question"></div>

              <!-- 查询结果表格 -->
              <template v-if="round.data && round.data.rows.length > 0">
                <div class="section-label">📊 查询结果</div>
                <DataTable :data="round.data" />
              </template>

              <!-- 发现/洞察 -->
              <template v-if="round.insights && round.insights.length > 0">
                <div class="round-divider-dashed"></div>
                <div class="section-label">💡 发现</div>
                <ul class="insights-list">
                  <li v-for="(ins, i) in round.insights" :key="i" class="insight-item">
                    <span v-if="ins.type === 'anomaly'">⚠️</span>
                    {{ ins.content }}
                  </li>
                </ul>
              </template>
            </div>

            <!-- 思考气泡（轮次之间，非最后一轮） -->
            <div v-if="round.reason && idx < aiMessage.rounds!.length - 1" class="thinking-process-container">
              <details class="thinking-details">
                <summary class="thinking-summary">
                  <span class="thinking-icon">💭</span>
                  <span class="thinking-label">思考过程</span>
                </summary>
                <div class="thinking-content">
                  {{ round.reason }}
                </div>
              </details>
              <div class="thinking-line-connector"></div>
            </div>
          </template>

          <!-- 双线分隔 -->
          <div class="divider-double"></div>
        </template>

        <!-- 单轮表格数据（tableData，兼容旧结构） -->
        <template v-else-if="aiMessage.tableData && aiMessage.tableData.rows.length > 0">
          <div class="section-label">📊 查询结果</div>
          <DataTable :data="aiMessage.tableData" />
          <div class="round-divider-dashed" v-if="aiMessage.content || (aiMessage.insights && aiMessage.insights.length > 0)"></div>
        </template>

        <!-- 总结内容（Markdown） -->
        <template v-if="aiMessage.content">
          <div class="section-label" v-if="aiMessage.rounds && aiMessage.rounds.length > 0">📝 总结</div>
          <div class="ai-summary markdown-body" v-html="renderedContent" />
        </template>

        <!-- 流式输出中的占位 -->
        <div v-if="!aiMessage.content && !aiMessage.tableData && !(aiMessage.rounds && aiMessage.rounds.length > 0)" class="ai-streaming-placeholder">
          <span class="streaming-dot"></span>
          <span class="streaming-dot"></span>
          <span class="streaming-dot"></span>
        </div>

        <!-- 推荐问题 -->
        <template v-if="aiMessage.suggestions && aiMessage.suggestions.length > 0 && !aiMessage.isStreaming">
          <div class="divider-single"></div>
          <div class="suggestions-section">
            <div class="suggestions-label">💬 继续探索</div>
            <div class="suggestions-chips">
              <button
                v-for="(s, i) in aiMessage.suggestions.slice(0, 3)"
                :key="i"
                class="suggestion-chip"
                @click="$emit('suggest', s)"
              >
                🔍 {{ s }}
              </button>
            </div>
          </div>
        </template>
      </div>

      <!-- 卡片底部时间戳 -->
      <div v-if="formattedTime" class="ai-card-footer">
        <span class="ai-time">{{ formattedTime }}</span>
      </div>
    </div>
  </div>

  <!-- 系统消息 / 错误消息 -->
  <div v-else-if="message.type === 'system'" class="message-row message-row--system">
    <div class="system-message" :class="`system-message--${(message as any).level}`">
      <span class="system-icon">⚠️</span>
      <span class="system-text">{{ message.content }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import type { Message, AIMessage } from '@/types'
import DataTable from '@/components/chat/DataTable.vue'

const md = new MarkdownIt({ html: false, breaks: true, linkify: true })

interface Props {
  message: Message
}

const props = defineProps<Props>()
const emit = defineEmits<{ suggest: [question: string] }>()

const copied = ref(false)

// AI 消息类型断言
const aiMessage = computed(() => props.message as AIMessage)

// 时间戳：<60s 不显示
const formattedTime = computed(() => {
  if (!props.message.timestamp) return ''
  const diff = Date.now() - props.message.timestamp
  if (diff < 60 * 1000) return ''
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / 3600000)}小时前`
  return `${Math.floor(diff / 86400000)}天前`
})

// 渲染 Markdown
const renderedContent = computed(() => {
  if (props.message.type !== 'ai') return ''
  try {
    return md.render((props.message as AIMessage).content || '')
  } catch {
    return (props.message as AIMessage).content || ''
  }
})

// 复制消息
async function handleCopy() {
  const text = props.message.type === 'ai' ? (props.message as AIMessage).content : props.message.content
  try {
    await navigator.clipboard.writeText(text || '')
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // fallback
  }
}
</script>

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;

// ── 消息行基础 ──
.message-row {
  display: flex;
  margin-bottom: 16px;
  animation: slideIn 250ms ease-out;
}

.message-row--user {
  justify-content: flex-end;
}

.message-row--ai {
  justify-content: flex-start;
}

.message-row--system {
  justify-content: center;
}

// ── 用户消息气泡 ──
.user-bubble {
  max-width: 80%;
  background: $tableau-blue; // #1F77B4
  color: #FFFFFF;
  border-radius: 12px 12px 0 12px; // 右下角直角
  padding: 12px 16px;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  position: relative;
  box-shadow: $shadow-sm;
}

.user-text {
  white-space: pre-wrap;
}

.user-time {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  text-align: right;
  margin-top: 4px;
}

// ── AI 消息卡片 ──
.ai-card {
  max-width: 90%;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 0 12px 12px 12px; // 左上角直角
  font-size: 14px;
  overflow: hidden;
  box-shadow: $shadow-sm;

  @media (max-width: 767px) {
    max-width: 95%;
  }
}

.ai-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-secondary); // #FAFAFA
}

.ai-title {
  font-size: 13px;
  font-weight: 600;
  color: #1A1A1A;
}

.copy-btn {
  font-size: 12px;
  color: #666666;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;

  &:hover {
    color: #1F77B4;
    background: #F0F7FF;
  }
}

.ai-card-body {
  padding: 16px;
}

.ai-card-footer {
  padding: 8px 16px;
  border-top: 1px solid #F0F0F0;
  text-align: right;
}

.ai-time {
  font-size: 12px;
  color: #999999;
}

// ── 分析轮次卡片 ──
.analysis-round-card {
  border: 1px solid #E8E8E8;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 0;
  background: #FFFFFF;
}

.round-question {
  font-size: 15px;
  font-weight: 600;
  color: #1A1A1A;
  margin-bottom: 12px;
}

.round-divider-dashed {
  border: none;
  border-top: 1px dashed #E0E0E0;
  margin: 12px 0;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: #444444;
  margin-bottom: 8px;
}

// ── 洞察列表 ──
.insights-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.insight-item {
  font-size: 14px;
  color: #333333;
  line-height: 1.5;
  padding-left: 4px;
}

// ── 思考过程（可折叠） ──
.thinking-process-container {
  margin: 8px 0;
  padding-left: 16px;
  position: relative;
}

.thinking-details {
  background: #F5F5F5;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #E0E0E0;
  
  &[open] {
    .thinking-summary {
      border-bottom: 1px solid #E0E0E0;
    }
  }
}

.thinking-summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #666666;
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
  
  &:hover {
    background: #EEEEEE;
  }
  
  &::marker {
    color: #999999;
  }
}

.thinking-content {
  padding: 12px;
  font-size: 13px;
  color: #333333;
  line-height: 1.6;
  background: #FAFAFA;
}

.thinking-line-connector {
  position: absolute;
  left: 24px;
  top: 100%;
  height: 12px;
  width: 2px;
  background: #E0E0E0;
}


// ── 分隔线 ──
.divider-double {
  border: none;
  border-top: 2px solid #E0E0E0;
  margin: 16px 0;
}

.divider-single {
  border: none;
  border-top: 1px solid #E8E8E8;
  margin: 16px 0;
}

// ── 总结内容 ──
.ai-summary {
  color: #1A1A1A;
  line-height: 1.6;
}

// ── 流式占位 ──
.ai-streaming-placeholder {
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 8px 0;
}

.streaming-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1F77B4;
  animation: dotPulse 1.5s infinite;

  &:nth-child(2) { animation-delay: 0.5s; }
  &:nth-child(3) { animation-delay: 1s; }
}

@keyframes dotPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

// ── 推荐问题 ──
.suggestions-section {
  margin-top: 0;
}

.suggestions-label {
  font-size: 13px;
  color: #666666;
  margin-bottom: 10px;
}

.suggestions-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.suggestion-chip {
  background: #F8F9FA;
  border: 1px solid #E8E8E8;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: #333333;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  text-align: left;
  min-width: 120px;

  &:hover {
    border-color: #1F77B4;
    background: #F0F7FF;
  }
}

// ── 系统消息 ──
.system-message {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #FEE2E2;
  border: 1px solid #D62728;
  border-radius: 8px;
  color: #991B1B;
  font-size: 14px;
  max-width: 90%;
}

// ── Markdown 样式 ──
.markdown-body {
  :deep(p) { margin: 0 0 8px 0; &:last-child { margin-bottom: 0; } }
  :deep(ul), :deep(ol) { margin: 8px 0; padding-left: 20px; }
  :deep(li) { margin: 4px 0; }
  :deep(code) { padding: 2px 6px; background: #F5F5F5; border-radius: 4px; font-size: 13px; font-family: 'Consolas', 'Monaco', monospace; }
  :deep(pre) { margin: 8px 0; padding: 12px; background: #F5F5F5; border-radius: 4px; overflow-x: auto; code { padding: 0; background: transparent; } }
  :deep(a) { color: #1F77B4; text-decoration: underline; }
  :deep(strong) { font-weight: 600; }
  :deep(h1), :deep(h2), :deep(h3) { margin: 12px 0 6px 0; font-weight: 600; }
}

// ── 动画 ──
@keyframes slideIn {
  from { transform: translateY(12px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
</style>
