<template>
  <div class="data-table-wrapper">
    <!-- 表格 -->
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th
              v-for="col in data.columns"
              :key="col.key"
              class="table-th"
              :class="{ sortable: true }"
              @click="toggleSort(col.key)"
            >
              {{ col.label }}
              <span class="sort-icon">
                <template v-if="sortKey === col.key">{{ sortDir === 'asc' ? '▲' : '▼' }}</template>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in pagedRows"
            :key="idx"
            class="table-row"
          >
            <td
              v-for="col in data.columns"
              :key="col.key"
              class="table-td"
              :class="{ 'td-number': col.type === 'number', 'td-negative': isNegative(row[col.key]) }"
            >
              {{ formatCell(row[col.key], col.type) }}
            </td>
          </tr>
          <tr v-if="pagedRows.length === 0">
            <td :colspan="data.columns.length" class="empty-cell">📭 暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 工具栏 -->
    <div class="table-toolbar">
      <!-- 左：查询详情 -->
      <button class="toolbar-btn" @click="showTechDetails = !showTechDetails">
        🔧 查询详情
      </button>

      <!-- 中：共N条 + 分页 -->
      <div class="toolbar-center">
        <span class="total-count">共 {{ sortedRows.length }} 条</span>
        <template v-if="pageCount > 1">
          <button class="page-btn" :disabled="currentPage === 1" @click="currentPage--">◀</button>
          <span class="page-info">{{ currentPage }}/{{ pageCount }}</span>
          <button class="page-btn" :disabled="currentPage === pageCount" @click="currentPage++">▶</button>
        </template>
      </div>

      <!-- 右：导出 -->
      <button class="export-btn" @click="exportCSV">📥 导出</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { TableData } from '@/types'

const props = defineProps<{ data: TableData }>()

const PAGE_SIZE = 10
const currentPage = ref(1)
const sortKey = ref<string | null>(null)
const sortDir = ref<'asc' | 'desc'>('asc')
const showTechDetails = ref(false)

function toggleSort(key: string) {
  if (sortKey.value === key) {
    if (sortDir.value === 'asc') sortDir.value = 'desc'
    else if (sortDir.value === 'desc') { sortKey.value = null }
    else sortDir.value = 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
  currentPage.value = 1
}

const sortedRows = computed(() => {
  const rows = [...props.data.rows]
  if (!sortKey.value) return rows
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return rows.sort((a, b) => {
    const av = a[key], bv = b[key]
    if (av === bv) return 0
    return (av! > bv! ? 1 : -1) * dir
  })
})

const pageCount = computed(() => Math.ceil(sortedRows.value.length / PAGE_SIZE))

const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return sortedRows.value.slice(start, start + PAGE_SIZE)
})

function formatCell(val: unknown, type: string): string {
  if (val === null || val === undefined) return '-'
  if (type === 'number') {
    const n = Number(val)
    if (isNaN(n)) return String(val)
    return n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
  }
  return String(val)
}

function isNegative(val: unknown): boolean {
  if (val === null || val === undefined) return false
  const s = String(val)
  return s.startsWith('-') && !isNaN(Number(s.replace('%', '')))
}

function exportCSV() {
  const header = props.data.columns.map(c => c.label).join(',')
  const rows = props.data.rows.map(row =>
    props.data.columns.map(c => {
      const v = row[c.key]
      const s = v === null || v === undefined ? '' : String(v)
      return s.includes(',') ? `"${s}"` : s
    }).join(',')
  )
  const csv = [header, ...rows].join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'data.csv'
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped lang="scss">
.data-table-wrapper {
  font-size: 13px;
  margin-bottom: 0;
}

.table-scroll {
  overflow-x: auto;
  border-radius: 4px;
  border: 1px solid #E0E0E0;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  background: #FFFFFF;
}

.table-th {
  background: #F5F5F5;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 12px;
  border-bottom: 1px solid #E0E0E0;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;

  &:hover {
    background: #EEEEEE;
  }
}

.sort-icon {
  font-size: 10px;
  margin-left: 4px;
  color: #999999;
}

.table-row {
  &:hover td {
    background: #F9F9F9;
  }
}

.table-td {
  padding: 8px 12px;
  border-bottom: 1px solid #F0F0F0;
  color: #333333;
  font-size: 13px;
  line-height: 1.4;

  &.td-number {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  &.td-negative {
    color: #D62728;
  }
}

.empty-cell {
  text-align: center;
  padding: 24px;
  color: #999999;
}

// ── 工具栏 ──
.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  margin-top: 4px;
  font-size: 12px;
}

.toolbar-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: #666666;
  font-size: 12px;
  padding: 4px 0;

  &:hover {
    color: #1F77B4;
  }
}

.toolbar-center {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #999999;
}

.total-count {
  font-size: 12px;
}

.page-btn {
  background: none;
  border: 1px solid #E0E0E0;
  border-radius: 4px;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 11px;
  color: #666666;

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  &:hover:not(:disabled) {
    border-color: #1F77B4;
    color: #1F77B4;
  }
}

.page-info {
  font-weight: 600;
  color: #444444;
  font-size: 12px;
}

.export-btn {
  background: #1F77B4;
  color: #FFFFFF;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  padding: 4px 10px;
  font-size: 12px;

  &:hover {
    opacity: 0.9;
  }
}
</style>
