<template>
  <div class="data-table-container">
    <!-- 空状态 -->
    <div v-if="!data.rows.length" class="empty-state">
      暂无数据
    </div>
    
    <!-- 表格 -->
    <div v-else class="table-wrapper" :class="{ 'has-scroll': needsScroll }">
      <table class="data-table">
        <thead>
          <tr>
            <th 
              v-for="col in data.columns" 
              :key="col.key"
              :class="[
                `align-${col.align || 'left'}`,
                { sortable, sorted: sortState.column === col.key }
              ]"
              @click="sortable && handleSort(col.key)"
            >
              <span class="th-content">
                {{ col.label }}
                <span v-if="sortable" class="sort-icon">
                  <template v-if="sortState.column === col.key">
                    {{ sortState.direction === 'asc' ? '▲' : '▼' }}
                  </template>
                  <template v-else>⇅</template>
                </span>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in displayedRows" :key="idx">
            <td 
              v-for="col in data.columns" 
              :key="col.key"
              :class="[
                `align-${col.align || 'left'}`,
                { 'number-cell': col.type === 'number' },
                { 'negative': col.type === 'number' && isNegative(row[col.key]) }
              ]"
            >
              {{ formatCell(row[col.key], col.type) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    
    <!-- 工具栏：三段式布局 -->
    <div v-if="data.rows.length" class="toolbar">
      <!-- 左：查询详情按钮 -->
      <div class="toolbar-left">
        <button class="toolbar-btn-secondary" @click="showTechDetails = !showTechDetails">
          🔧 查询详情
        </button>
      </div>

      <!-- 中：总数 + 分页控件 -->
      <div class="toolbar-center">
        <span class="total-count">共 {{ data.totalCount }} 条</span>
        <template v-if="showPagination">
          <button
            class="page-btn"
            :disabled="currentPage === 1"
            @click="goToPage(currentPage - 1)"
          >◀</button>
          <span class="page-info">{{ currentPage }}/{{ totalPages }}</span>
          <button
            class="page-btn"
            :disabled="currentPage === totalPages"
            @click="goToPage(currentPage + 1)"
          >▶</button>
        </template>
      </div>

      <!-- 右：导出 -->
      <div class="toolbar-right">
        <button v-if="exportable" class="toolbar-btn-primary" @click="exportCSV">
          📥 导出
        </button>
      </div>
    </div>

    <!-- 查询详情展开面板 -->
    <div v-if="showTechDetails" class="tech-details-panel">
      <div class="tech-details-content">
        <span class="tech-label">字段数：</span>{{ data.columns.length }} 列
        <span class="tech-label" style="margin-left: 12px;">总行数：</span>{{ data.totalCount }} 条
        <span class="tech-label" style="margin-left: 12px;">当前页：</span>{{ currentPage }}/{{ totalPages || 1 }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * DataTable 组件
 * 数据表格，支持分页、排序、导出
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
 */
import { ref, computed } from 'vue'

interface ColumnDef {
  key: string
  label: string
  type: 'string' | 'number' | 'date'
  align?: 'left' | 'center' | 'right'
}

interface TableData {
  columns: ColumnDef[]
  rows: Record<string, unknown>[]
  totalCount: number
}

const props = withDefaults(defineProps<{
  data: TableData
  pageSize?: number
  sortable?: boolean
  exportable?: boolean
}>(), {
  pageSize: 10,
  sortable: true,
  exportable: true
})

// 分页状态
const currentPage = ref(1)

// 查询详情展开状态
const showTechDetails = ref(false)

// 排序状态
const sortState = ref<{
  column: string | null
  direction: 'asc' | 'desc' | null
}>({
  column: null,
  direction: null
})

// 计算属性
const totalPages = computed(() => 
  Math.ceil(props.data.rows.length / props.pageSize)
)

const showPagination = computed(() => 
  props.data.rows.length > props.pageSize
)

const needsScroll = computed(() => 
  props.data.columns.length > 5
)

// 排序后的数据
const sortedRows = computed(() => {
  if (!sortState.value.column || !sortState.value.direction) {
    return props.data.rows
  }
  
  const col = sortState.value.column
  const dir = sortState.value.direction
  
  return [...props.data.rows].sort((a, b) => {
    const aVal = a[col]
    const bVal = b[col]
    
    if (aVal === bVal) return 0
    if (aVal === null || aVal === undefined) return 1
    if (bVal === null || bVal === undefined) return -1
    
    const comparison = aVal < bVal ? -1 : 1
    return dir === 'asc' ? comparison : -comparison
  })
})

// 当前页显示的数据
const displayedRows = computed(() => {
  const start = (currentPage.value - 1) * props.pageSize
  const end = start + props.pageSize
  return sortedRows.value.slice(start, end)
})

// 方法
function handleSort(column: string) {
  if (sortState.value.column === column) {
    // 循环：asc -> desc -> null
    if (sortState.value.direction === 'asc') {
      sortState.value.direction = 'desc'
    } else if (sortState.value.direction === 'desc') {
      sortState.value.column = null
      sortState.value.direction = null
    }
  } else {
    sortState.value.column = column
    sortState.value.direction = 'asc'
  }
  // 排序后回到第一页
  currentPage.value = 1
}

function goToPage(page: number) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
  }
}

function isNegative(value: unknown): boolean {
  return typeof value === 'number' && value < 0
}

function formatCell(value: unknown, type: string): string {
  if (value === null || value === undefined) return '-'
  
  if (type === 'number' && typeof value === 'number') {
    // 千分位分隔符，小数保留2位
    return value.toLocaleString('zh-CN', {
      minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
      maximumFractionDigits: 2
    })
  }
  
  if (type === 'date' && (typeof value === 'string' || typeof value === 'number')) {
    const date = new Date(value)
    if (!isNaN(date.getTime())) {
      return date.toLocaleDateString('zh-CN')
    }
  }
  
  return String(value)
}

function exportCSV() {
  // 生成 CSV 内容
  const headers = props.data.columns.map(c => c.label).join(',')
  const rows = props.data.rows.map(row => 
    props.data.columns.map(col => {
      const val = row[col.key]
      // 处理包含逗号或引号的值
      if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
        return `"${val.replace(/"/g, '""')}"`
      }
      return val ?? ''
    }).join(',')
  ).join('\n')
  
  const csv = `${headers}\n${rows}`
  
  // 生成文件名
  const now = new Date()
  const timestamp = now.toISOString().replace(/[-:T]/g, '').slice(0, 15)
  const filename = `tableau_data_${timestamp}.csv`
  
  // 下载
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped lang="scss">
@use "sass:color";
@use '@/assets/styles/variables.scss' as *;

.data-table-container {
  width: 100%;
  border: 1px solid var(--border-color);
  border-radius: $radius-sm;
  overflow: hidden;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 14px;
}

.table-wrapper {
  overflow-x: auto;
}

.table-wrapper.has-scroll {
  position: relative;
}

.table-wrapper.has-scroll::after {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 20px;
  background: linear-gradient(to right, transparent, rgba(0,0,0,0.05));
  pointer-events: none;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 12px 16px; // Increased padding
  border-bottom: 1px solid var(--border-light);
}

.data-table th {
  background-color: var(--bg-tertiary); // #F5F5F5
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
}

.data-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.data-table th.sortable:hover {
  background-color: var(--bg-active);
}

.data-table th.sorted {
  color: $tableau-blue;
}

.th-content {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sort-icon {
  font-size: 10px;
  color: var(--text-disabled);
}

.sorted .sort-icon {
  color: $tableau-blue;
}

.data-table td {
  color: var(--text-primary);
}

.data-table tr:hover td {
  background-color: var(--bg-hover);
}

.align-left { text-align: left; }
.align-center { text-align: center; }
.align-right { text-align: right; }

.number-cell {
  font-variant-numeric: tabular-nums;
}

.negative {
  color: $tableau-red;
}

/* 三段式工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
  background-color: var(--bg-secondary);
  font-size: 13px;
  gap: 8px;
}

.toolbar-left {
  flex: 0 0 auto;
}

.toolbar-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.toolbar-right {
  flex: 0 0 auto;
}

.toolbar-btn-secondary {
  padding: 4px 10px;
  background: none;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.toolbar-btn-secondary:hover {
  color: $tableau-blue;
  background: rgba(31, 119, 180, 0.08);
}

.toolbar-btn-primary {
  padding: 4px 12px;
  background: $tableau-blue;
  color: white;
  border: none;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.toolbar-btn-primary:hover {
  background: color.adjust($tableau-blue, $lightness: -10%);
  box-shadow: $shadow-sm;
}

.total-count {
  color: var(--text-tertiary);
  font-size: 12px;
}

.page-btn {
  width: 24px;
  height: 24px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: white;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.page-btn:hover:not(:disabled) {
  background-color: var(--bg-tertiary);
  border-color: $tableau-blue;
  color: $tableau-blue;
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  min-width: 40px;
  text-align: center;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 12px;
}

/* 查询详情面板 */
.tech-details-panel {
  border-top: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  padding: 8px 12px;
}

.tech-details-content {
  font-size: 12px;
  color: var(--text-secondary);
}

.tech-label {
  color: var(--text-tertiary);
  margin-right: 2px;
}
</style>
