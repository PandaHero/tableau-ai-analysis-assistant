/**
 * 颜色对比度检查脚本
 * 用于验证设计系统中的颜色组合是否符合 WCAG 2.1 标准
 */
import { batchCheckContrast, generateContrastReport, type ColorPair } from '../src/utils/contrast'

// 定义需要检查的颜色组合
const colorPairs: ColorPair[] = [
  // 主色组合
  {
    name: '主色按钮 - 白色文字',
    foreground: '#FFFFFF',
    background: '#1F77B4'
  },
  {
    name: '主色按钮悬停 - 白色文字',
    foreground: '#FFFFFF',
    background: '#1565A8'
  },
  {
    name: '主色文字 - 白色背景',
    foreground: '#1F77B4',
    background: '#FFFFFF'
  },
  
  // 成功色组合
  {
    name: '成功按钮 - 白色文字',
    foreground: '#FFFFFF',
    background: '#2CA02C'
  },
  {
    name: '成功文字 - 白色背景',
    foreground: '#2CA02C',
    background: '#FFFFFF'
  },
  
  // 警告色组合
  {
    name: '警告按钮 - 白色文字',
    foreground: '#FFFFFF',
    background: '#FF7F0E'
  },
  {
    name: '警告文字 - 白色背景',
    foreground: '#FF7F0E',
    background: '#FFFFFF'
  },
  
  // 错误色组合
  {
    name: '错误按钮 - 白色文字',
    foreground: '#FFFFFF',
    background: '#D62728'
  },
  {
    name: '错误文字 - 白色背景',
    foreground: '#D62728',
    background: '#FFFFFF'
  },
  
  // 文字颜色组合
  {
    name: '主要文字 - 白色背景',
    foreground: '#333333',
    background: '#FFFFFF'
  },
  {
    name: '次要文字 - 白色背景',
    foreground: '#666666',
    background: '#FFFFFF'
  },
  {
    name: '辅助文字 - 白色背景',
    foreground: '#999999',
    background: '#FFFFFF'
  },
  
  // 背景色组合
  {
    name: '主要文字 - 浅灰背景',
    foreground: '#333333',
    background: '#FAFAFA'
  },
  {
    name: '主要文字 - 中灰背景',
    foreground: '#333333',
    background: '#E0E0E0'
  },
  
  // 深色主题组合
  {
    name: '白色文字 - 深色背景',
    foreground: '#FFFFFF',
    background: '#1A1A1A'
  },
  {
    name: '浅灰文字 - 深色背景',
    foreground: '#E0E0E0',
    background: '#1A1A1A'
  },
  {
    name: '主色 - 深色背景',
    foreground: '#64B5F6',
    background: '#1A1A1A'
  },
  
  // 链接颜色
  {
    name: '链接 - 白色背景',
    foreground: '#1F77B4',
    background: '#FFFFFF'
  },
  {
    name: '链接悬停 - 白色背景',
    foreground: '#1565A8',
    background: '#FFFFFF'
  },
  
  // 禁用状态
  {
    name: '禁用文字 - 白色背景',
    foreground: '#CCCCCC',
    background: '#FFFFFF'
  },
  {
    name: '禁用文字 - 浅灰背景',
    foreground: '#CCCCCC',
    background: '#FAFAFA'
  }
]

// 执行检查
console.log('开始检查颜色对比度...\n')

const results = batchCheckContrast(colorPairs, 'AA')

console.log('='.repeat(80))
console.log('颜色对比度检查结果')
console.log('='.repeat(80))
console.log()

console.log(`总计: ${colorPairs.length} 个颜色组合`)
console.log(`通过 (AA): ${results.passed.length}`)
console.log(`失败 (AA): ${results.failed.length}`)
console.log()

if (results.failed.length > 0) {
  console.log('❌ 未通过 WCAG 2.1 AA 标准的颜色组合:')
  console.log('-'.repeat(80))
  
  for (const pair of results.failed) {
    const result = results.results.get(pair.name)!
    console.log()
    console.log(`名称: ${pair.name}`)
    console.log(`前景色: ${pair.foreground}`)
    console.log(`背景色: ${pair.background}`)
    console.log(`对比度: ${result.ratio}:1`)
    console.log(`等级: ${result.level}`)
    console.log(`正文 AA: ${result.normalText.aa ? '✓' : '✗'}`)
    console.log(`正文 AAA: ${result.normalText.aaa ? '✓' : '✗'}`)
    console.log(`大文本 AA: ${result.largeText.aa ? '✓' : '✗'}`)
    console.log(`大文本 AAA: ${result.largeText.aaa ? '✓' : '✗'}`)
  }
  
  console.log()
  console.log('-'.repeat(80))
}

if (results.passed.length > 0) {
  console.log()
  console.log('✓ 通过 WCAG 2.1 AA 标准的颜色组合:')
  console.log('-'.repeat(80))
  
  for (const pair of results.passed) {
    const result = results.results.get(pair.name)!
    console.log()
    console.log(`名称: ${pair.name}`)
    console.log(`前景色: ${pair.foreground}`)
    console.log(`背景色: ${pair.background}`)
    console.log(`对比度: ${result.ratio}:1`)
    console.log(`等级: ${result.level}`)
  }
  
  console.log()
  console.log('-'.repeat(80))
}

// 生成详细报告
console.log()
console.log('生成详细报告...')
const report = generateContrastReport(colorPairs)

// 保存报告到文件
import { writeFileSync } from 'fs'
import { join } from 'path'

const reportPath = join(__dirname, '../docs/contrast-report.md')
writeFileSync(reportPath, report, 'utf-8')

console.log(`报告已保存到: ${reportPath}`)
console.log()

// 退出码
if (results.failed.length > 0) {
  console.log('⚠️  存在不符合 WCAG 2.1 AA 标准的颜色组合,请检查并修复!')
  process.exit(1)
} else {
  console.log('✓ 所有颜色组合均符合 WCAG 2.1 AA 标准!')
  process.exit(0)
}
