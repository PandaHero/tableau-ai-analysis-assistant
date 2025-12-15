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
    
    <!-- 分页控件 -->
    <div v-if="showPagination" class="pagination">
      <span class="total-count">共 {{ data.totalCount }} 条</span>
      <div class="page-controls">
        <button 
          class="page-btn" 
          :disabled="currentPage === 1"
          @click="goToPage(currentPage - 1)"
        >
          ◀
        </button>
        <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
        <button 
          class="page-btn" 
          :disabled="currentPage === totalPages"
          @click="goToPage(currentPage + 1)"
        >
          ▶
        </button>
      </div>
    </div>
    
    <!-- 导出按钮 -->
    <div v-if="exportable && data.rows.length" class="export-bar">
      <button class="export-btn" @click="exportCSV">
        📥 导出 CSV
      </button>
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

<style scoped>
.data-table-container {
  width: 100%;
}

.empty-state {
  padding: 24px;
  text-align: center;
  color: #718096;
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
  padding: 10px 12px;
  border-bottom: 1px solid #e2e8f0;
}

.data-table th {
  background-color: #f7fafc;
  font-weight: 600;
  color: #4a5568;
  white-space: nowrap;
}

.data-table th.sortable {
  cursor: pointer;
  user-select: none;
}

.data-table th.sortable:hover {
  background-color: #edf2f7;
}

.data-table th.sorted {
  color: var(--tableau-blue, #1F77B4);
}

.th-content {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sort-icon {
  font-size: 10px;
  color: #a0aec0;
}

.sorted .sort-icon {
  color: var(--tableau-blue, #1F77B4);
}

.data-table td {
  color: #2d3748;
}

.data-table tr:hover td {
  background-color: #f7fafc;
}

.align-left { text-align: left; }
.align-center { text-align: center; }
.align-right { text-align: right; }

.number-cell {
  font-variant-numeric: tabular-nums;
}

.negative {
  color: #D62728;
}

/* 分页 */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  font-size: 13px;
  color: #718096;
}

.total-count {
  color: #a0aec0;
}

.page-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  background: white;
  color: #4a5568;
  cursor: pointer;
  font-size: 12px;
}

.page-btn:hover:not(:disabled) {
  background-color: #f7fafc;
  border-color: #cbd5e0;
}

.page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.page-info {
  min-width: 60px;
  text-align: center;
}

/* 导出 */
.export-bar {
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.export-btn {
  padding: 6px 12px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px;
  color: #4a5568;
  cursor: pointer;
  transition: all 0.2s;
}

.export-btn:hover {
  background-color: #f7fafc;
  border-color: #cbd5e0;
}
</style>
