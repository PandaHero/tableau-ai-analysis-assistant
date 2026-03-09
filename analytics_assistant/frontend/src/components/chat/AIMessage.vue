<template>
  <div class="ai-message">
    <div class="message-avatar">
      <img src="@/assets/tableau_logo.svg" alt="AI" width="24" height="24" />
    </div>
    <div class="message-body">

      <!-- 卡片头部 -->
      <div class="card-header">
        <span class="card-title">🤖 AI 助手</span>
        <button class="copy-btn" @click="copyContent" :class="{ copied: isCopied }">
          {{ isCopied ? '✓ 已复制' : '📋 复制' }}
        </button>
      </div>

      <!-- 内容区 -->
      <div class="card-body">

        <!-- 思维链：多轮分析卡片 -->
        <template v-if="hasRounds">
          <template v-for="(round, idx) in message.rounds" :key="idx">
            <!-- 分析卡片 -->
            <div class="analysis-round-card">
              <!-- ❓ 问题标题（多轮时显示） -->
              <div v-if="isMultiRound && round.question" class="round-question">
                <span class="round-question-icon">❓</span>
                <span class="round-question-text">{{ round.question }}</span>
              </div>

              <!-- 卡片内虚线分隔 -->
              <div v-if="isMultiRound && round.question" class="divider-dashed"></div>

              <!-- 📊 查询结果 -->
              <div v-if="round.data" class="round-section">
                <div class="section-label">📊 查询结果</div>
                <DataTable
                  :data="normalizeTableData(round.data)"
                  :sortable="true"
                  :exportable="true"
                />
              </div>

              <!-- 虚线分隔（表格和发现之间） -->
              <div v-if="round.data && round.insights?.length" class="divider-dashed"></div>

              <!-- 💡 发现 -->
              <div v-if="round.insights?.length" class="round-section">
                <div class="section-label">💡 发现</div>
                <ul class="insights-list">
                  <li
                    v-for="insight in round.insights"
                    :key="insight.id"
                    class="insight-item"
                    :class="`insight-${insight.type}`"
                  >
                    <span class="insight-icon">{{ INSIGHT_STYLES[insight.type]?.icon || '•' }}</span>
                    <span class="insight-text">{{ insight.description }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <!-- 💭 思考气泡（轮次之间，非最后一轮） -->
            <div v-if="round.reason && idx < (message.rounds?.length ?? 0) - 1" class="thought-bubble-wrapper">
              <div class="thought-connector"></div>
              <div class="thought-bubble">
                <span class="thought-icon">💭</span>
                <span class="thought-text">{{ round.reason }}</span>
              </div>
              <div class="thought-arrow">▼</div>
            </div>
          </template>
        </template>

        <!-- 兼容模式：无 rounds 时的单轮展示（tableData / data） -->
        <template v-else-if="normalizedTableData">
          <div class="analysis-round-card">
            <div class="round-section">
              <div class="section-label">📊 查询结果</div>
              <DataTable
                :data="normalizedTableData"
                :sortable="true"
                :exportable="true"
              />
            </div>
          </div>
        </template>

        <!-- 语义解析摘要（无 token 内容时显示） -->
        <div
          v-if="message.semanticSummary && !message.content && !hasRounds && !normalizedTableData"
          class="semantic-summary"
        >
          <div class="summary-header">
            <span class="summary-icon">🔍</span>
            <span class="summary-title">已理解您的问题</span>
          </div>
          <div v-if="message.semanticSummary.restated_question" class="summary-question">
            "{{ message.semanticSummary.restated_question }}"
          </div>
          <div class="summary-chips-row">
            <template v-if="message.semanticSummary.measures.length">
              <span class="chips-label">度量</span>
              <span
                v-for="m in message.semanticSummary.measures"
                :key="m"
                class="chip chip-measure"
              >{{ m }}</span>
            </template>
            <template v-if="message.semanticSummary.dimensions.length">
              <span class="chips-label" style="margin-left: 8px;">维度</span>
              <span
                v-for="d in message.semanticSummary.dimensions"
                :key="d"
                class="chip chip-dimension"
              >{{ d }}</span>
            </template>
            <template v-if="message.semanticSummary.filters.length">
              <span class="chips-label" style="margin-left: 8px;">筛选</span>
              <span
                v-for="f in message.semanticSummary.filters"
                :key="f"
                class="chip chip-filter"
              >{{ f }}</span>
            </template>
          </div>
        </div>

        <!-- ════ 双线分隔 ════（有轮次内容时才显示） -->
        <div v-if="(hasRounds || normalizedTableData) && message.content" class="divider-double"></div>

        <!-- 📝 总结（AI 文本内容，Markdown） -->
        <div v-if="message.content || message.isStreaming" class="summary-section">
          <div v-if="hasRounds || normalizedTableData" class="section-label">📝 总结</div>
          <MarkdownRenderer
            :content="message.content || ''"
            :streaming="message.isStreaming"
          />
        </div>

        <!-- ──── 单线分隔 ────（有总结和推荐问题时） -->
        <div v-if="message.suggestions?.length && (message.content || hasRounds)" class="divider-single"></div>

        <!-- 💬 继续探索（推荐问题卡片） -->
        <div v-if="message.suggestions?.length" class="suggestions-section">
          <div class="section-label">💬 继续探索</div>
          <div class="suggestion-cards">
            <button
              v-for="(suggestion, i) in message.suggestions.slice(0, 3)"
              :key="i"
              class="suggestion-card"
              @click="$emit('suggest', suggestion)"
            >
              <span class="suggestion-card-icon">🔍</span>
              <span class="suggestion-card-text">{{ suggestion }}</span>
            </button>
          </div>
        </div>

      </div><!-- /card-body -->

      <!-- 时间戳 -->
      <span v-if="showTimestamp" class="message-time">{{ formatTime(message.timestamp) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AIMessage as AIMessageType } from '@/types'
import type { TableData } from '@/types'
import { INSIGHT_STYLES } from '@/types'
import MarkdownRenderer from '@/components/content/MarkdownRenderer.vue'
import DataTable from '@/components/content/DataTable.vue'

const props = defineProps<{
  message: AIMessageType
}>()

defineEmits<{
  suggest: [question: string]
}>()

// 复制状态
const isCopied = ref(false)

function copyContent() {
  // 去除 Markdown 标记提取纯文本
  const text = props.message.content?.replace(/[#*`>_~]/g, '') || ''
  navigator.clipboard?.writeText(text).then(() => {
    isCopied.value = true
    setTimeout(() => { isCopied.value = false }, 2000)
  })
}

// 是否存在多轮分析数据
const hasRounds = computed(() => {
  return !!(props.message.rounds && props.message.rounds.length > 0)
})

const isMultiRound = computed(() => {
  return !!(props.message.rounds && props.message.rounds.length > 1)
})

/**
 * 兼容模式：单轮时从 tableData / data 获取表格
 */
const normalizedTableData = computed(() => {
  if (hasRounds.value) return null
  const raw = (props.message.tableData ?? props.message.data) as any
  return normalizeTableData(raw)
})

/**
 * 将后端返回的 tableData 格式转换为 DataTable 组件所需格式
 */
function normalizeTableData(raw: any): TableData | null {
  if (!raw) return null
  if (raw.columns && Array.isArray(raw.columns) && raw.columns.length > 0) {
    const firstCol = raw.columns[0]
    if ('name' in firstCol) {
      const columns = raw.columns.map((col: any) => ({
        key: col.name,
        label: col.name,
        type: inferColumnType(col.dataType),
        align: col.isMeasure ? 'right' as const : 'left' as const,
      }))
      return {
        columns,
        rows: (raw.rows || []).map((row: any) => {
          if (Array.isArray(row)) {
            const obj: Record<string, unknown> = {}
            raw.columns.forEach((col: any, i: number) => {
              obj[col.name] = row[i]
            })
            return obj
          }
          return row
        }),
        totalCount: raw.rowCount ?? raw.totalCount ?? (raw.rows?.length || 0),
      }
    }
    return {
      ...raw,
      totalCount: raw.totalCount ?? raw.rowCount ?? (raw.rows?.length || 0),
    }
  }
  return null
}

function inferColumnType(dataType: string): 'string' | 'number' | 'date' {
  if (!dataType) return 'string'
  const dt = dataType.toUpperCase()
  if (['INTEGER', 'FLOAT', 'REAL', 'NUMERIC', 'DECIMAL', 'DOUBLE'].some(t => dt.includes(t))) return 'number'
  if (['DATE', 'TIME', 'TIMESTAMP'].some(t => dt.includes(t))) return 'date'
  return 'string'
}

// 时间戳：<60s 不显示
const showTimestamp = computed(() => {
  const diff = Date.now() - props.message.timestamp
  return diff >= 60000
})

function formatTime(timestamp: number): string {
  const diff = Date.now() - timestamp
  if (diff < 60000) return ''
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  const days = Math.floor(diff / 86400000)
  return `${days} 天前`
}
</script>

<style scoped>
.ai-message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.message-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f0f7ff 0%, #dbeafe 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(31, 119, 180, 0.12);
  border: 1px solid rgba(31, 119, 180, 0.15);
}

.message-body {
  flex: 1;
  max-width: calc(100% - 46px);
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--color-card);
  border: 1px solid #E0E0E0;
  border-radius: 12px;
  overflow: hidden;
}

/* 卡片头部 */
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #E8E8E8;
  background: #FAFBFF;
}

.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.copy-btn {
  font-size: 12px;
  color: #999;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.copy-btn:hover {
  color: #1F77B4;
  background: rgba(31, 119, 180, 0.08);
}

.copy-btn.copied {
  color: #2CA02C;
}

/* 卡片主体 */
.card-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 分析轮次卡片 */
.analysis-round-card {
  border: 1px solid #E8E8E8;
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-card);
}

/* 问题标题 */
.round-question {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 14px;
  background: #FAFBFF;
}

.round-question-icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.round-question-text {
  font-size: 15px;
  font-weight: 600;
  color: #1A1A1A;
  line-height: 1.5;
}

/* 轮次内各分区 */
.round-section {
  padding: 12px 14px;
}

/* 分区标签 */
.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 8px;
}

/* 洞察列表 */
.insights-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.insight-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text);
}

.insight-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.insight-text {
  flex: 1;
}

.insight-anomaly .insight-text {
  color: #FF7F0E;
}

/* 卡片内虚线分隔 */
.divider-dashed {
  border: none;
  border-top: 1px dashed #E0E0E0;
  margin: 0;
}

/* 双线分隔（分析过程 vs 总结） */
.divider-double {
  border: none;
  border-top: 2px solid #E0E0E0;
  margin: 4px 0;
}

/* 单线分隔（总结 vs 推荐问题） */
.divider-single {
  border: none;
  border-top: 1px solid #E8E8E8;
  margin: 4px 0;
}

/* 思考气泡 */
.thought-bubble-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding-left: 20px;
  gap: 0;
}

.thought-connector {
  width: 2px;
  height: 12px;
  background: #E0E0E0;
  margin-left: 11px;
}

.thought-bubble {
  display: inline-flex;
  align-items: flex-start;
  gap: 6px;
  background: #F5F5F5;
  border-radius: 8px;
  padding: 8px 12px;
  max-width: 90%;
}

.thought-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.thought-text {
  font-size: 14px;
  color: #666666;
  font-style: italic;
  line-height: 1.5;
}

.thought-arrow {
  font-size: 11px;
  color: #E0E0E0;
  margin-left: 11px;
  line-height: 1;
  margin-top: 2px;
}

/* 总结区域 */
.summary-section {
  /* MarkdownRenderer 内部已有样式 */
}

/* 推荐问题卡片 */
.suggestions-section {
  padding-top: 4px;
}

.suggestion-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.suggestion-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  min-width: 120px;
  max-width: 200px;
  background: #F8F9FA;
  border: 1px solid #E8E8E8;
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--color-text);
  text-align: left;
  line-height: 1.4;
}

.suggestion-card:hover {
  background: #F0F7FF;
  border-color: #1F77B4;
  box-shadow: 0 2px 8px rgba(31, 119, 180, 0.15);
}

.suggestion-card-icon {
  font-size: 14px;
}

.suggestion-card-text {
  font-size: 13px;
  line-height: 1.4;
}

/* 语义解析摘要 */
.semantic-summary {
  background: linear-gradient(135deg, #f8faff 0%, #f0f7ff 100%);
  border: 1px solid rgba(31, 119, 180, 0.2);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.6;
}

.summary-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.summary-icon {
  font-size: 14px;
}

.summary-title {
  font-weight: 600;
  font-size: 13px;
  color: #1F77B4;
}

.summary-question {
  color: #374151;
  font-size: 13px;
  font-style: italic;
  margin-bottom: 10px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 6px;
  border-left: 3px solid #1F77B4;
}

.summary-chips-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  row-gap: 6px;
}

.chips-label {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.chip {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.chip-measure {
  background: rgba(31, 119, 180, 0.1);
  color: #1F77B4;
  border: 1px solid rgba(31, 119, 180, 0.25);
}

.chip-dimension {
  background: rgba(44, 160, 44, 0.1);
  color: #2CA02C;
  border: 1px solid rgba(44, 160, 44, 0.25);
}

.chip-filter {
  background: rgba(255, 127, 14, 0.1);
  color: #FF7F0E;
  border: 1px solid rgba(255, 127, 14, 0.25);
}

/* 时间戳 */
.message-time {
  display: block;
  font-size: 11px;
  color: var(--color-text-secondary);
  opacity: 0.7;
  padding: 6px 16px 8px;
  text-align: right;
}

/* 深色模式 */
html.dark .message-body {
  border-color: rgba(255, 255, 255, 0.12);
}

html.dark .message-avatar {
  background: linear-gradient(135deg, #1e3a5f 0%, #1a2e4a 100%);
  border-color: rgba(31, 119, 180, 0.3);
}

html.dark .card-header {
  background: linear-gradient(to right, #1a2535, #1e2d40);
}

html.dark .analysis-round-card {
  border-color: rgba(255, 255, 255, 0.1);
}

html.dark .round-question {
  background: #1a2535;
}

html.dark .round-question-text {
  color: #e2e8f0;
}

html.dark .thought-bubble {
  background: #1e2d3f;
}

html.dark .thought-text {
  color: #a0aec0;
}

html.dark .suggestion-card {
  background: #1a2535;
  border-color: rgba(255, 255, 255, 0.1);
}

html.dark .suggestion-card:hover {
  background: #1e3a5f;
  border-color: #1F77B4;
}

html.dark .semantic-summary {
  background: linear-gradient(135deg, #1a2535 0%, #1e2d40 100%);
  border-color: rgba(31, 119, 180, 0.3);
}

html.dark .summary-question {
  background: rgba(0, 0, 0, 0.2);
  color: #e2e8f0;
}
</style>
