/**
 * 颜色对比度检查工具
 * 基于 WCAG 2.1 标准
 */

/**
 * RGB 颜色
 */
export interface RGB {
  r: number
  g: number
  b: number
}

/**
 * 对比度等级
 */
export enum ContrastLevel {
  AAA = 'AAA',  // 7:1 (正文) 或 4.5:1 (大文本)
  AA = 'AA',    // 4.5:1 (正文) 或 3:1 (大文本)
  FAIL = 'FAIL' // 不符合标准
}

/**
 * 对比度检查结果
 */
export interface ContrastResult {
  ratio: number
  level: ContrastLevel
  normalText: {
    aa: boolean
    aaa: boolean
  }
  largeText: {
    aa: boolean
    aaa: boolean
  }
}

/**
 * 将十六进制颜色转换为 RGB
 */
export function hexToRgb(hex: string): RGB | null {
  // 移除 # 号
  hex = hex.replace(/^#/, '')
  
  // 支持简写形式 (#RGB)
  if (hex.length === 3) {
    hex = hex.split('').map(char => char + char).join('')
  }
  
  // 解析 RGB 值
  const result = /^([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  
  if (!result) {
    return null
  }
  
  return {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  }
}

/**
 * 将 RGB 颜色转换为相对亮度
 * 基于 WCAG 2.1 公式
 */
export function getLuminance(rgb: RGB): number {
  // 将 RGB 值转换为 0-1 范围
  const [r, g, b] = [rgb.r, rgb.g, rgb.b].map(val => {
    val = val / 255
    return val <= 0.03928
      ? val / 12.92
      : Math.pow((val + 0.055) / 1.055, 2.4)
  })
  
  // 计算相对亮度
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/**
 * 计算两个颜色之间的对比度
 * 返回值范围: 1-21
 */
export function getContrastRatio(color1: RGB, color2: RGB): number {
  const lum1 = getLuminance(color1)
  const lum2 = getLuminance(color2)
  
  const lighter = Math.max(lum1, lum2)
  const darker = Math.min(lum1, lum2)
  
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * 检查对比度是否符合 WCAG 标准
 */
export function checkContrast(
  foreground: string,
  background: string
): ContrastResult {
  const fg = hexToRgb(foreground)
  const bg = hexToRgb(background)
  
  if (!fg || !bg) {
    throw new Error('Invalid color format. Use hex format (#RRGGBB or #RGB)')
  }
  
  const ratio = getContrastRatio(fg, bg)
  
  // WCAG 2.1 标准:
  // AA 级别: 正文 4.5:1, 大文本 3:1
  // AAA 级别: 正文 7:1, 大文本 4.5:1
  const normalTextAA = ratio >= 4.5
  const normalTextAAA = ratio >= 7
  const largeTextAA = ratio >= 3
  const largeTextAAA = ratio >= 4.5
  
  let level: ContrastLevel
  if (normalTextAAA && largeTextAAA) {
    level = ContrastLevel.AAA
  } else if (normalTextAA && largeTextAA) {
    level = ContrastLevel.AA
  } else {
    level = ContrastLevel.FAIL
  }
  
  return {
    ratio: Math.round(ratio * 100) / 100,
    level,
    normalText: {
      aa: normalTextAA,
      aaa: normalTextAAA
    },
    largeText: {
      aa: largeTextAA,
      aaa: largeTextAAA
    }
  }
}

/**
 * 获取建议的前景色
 * 根据背景色自动选择黑色或白色文字
 */
export function getSuggestedForeground(background: string): string {
  const bg = hexToRgb(background)
  
  if (!bg) {
    return '#000000'
  }
  
  const luminance = getLuminance(bg)
  
  // 如果背景较亮,使用黑色文字;否则使用白色文字
  return luminance > 0.5 ? '#000000' : '#FFFFFF'
}

/**
 * 调整颜色以满足对比度要求
 */
export function adjustColorForContrast(
  foreground: string,
  background: string,
  targetRatio: number = 4.5
): string {
  const fg = hexToRgb(foreground)
  const bg = hexToRgb(background)
  
  if (!fg || !bg) {
    throw new Error('Invalid color format')
  }
  
  const currentRatio = getContrastRatio(fg, bg)
  
  // 如果已经满足要求,直接返回
  if (currentRatio >= targetRatio) {
    return foreground
  }
  
  // 判断应该调亮还是调暗
  const bgLuminance = getLuminance(bg)
  const shouldLighten = bgLuminance < 0.5
  
  // 二分查找合适的颜色
  let low = 0
  let high = 255
  let result = fg
  
  while (low <= high) {
    const mid = Math.floor((low + high) / 2)
    const adjusted: RGB = shouldLighten
      ? { r: mid, g: mid, b: mid }
      : { r: 255 - mid, g: 255 - mid, b: 255 - mid }
    
    const ratio = getContrastRatio(adjusted, bg)
    
    if (ratio >= targetRatio) {
      result = adjusted
      if (shouldLighten) {
        high = mid - 1
      } else {
        low = mid + 1
      }
    } else {
      if (shouldLighten) {
        low = mid + 1
      } else {
        high = mid - 1
      }
    }
  }
  
  return rgbToHex(result)
}

/**
 * 将 RGB 转换为十六进制
 */
export function rgbToHex(rgb: RGB): string {
  const toHex = (n: number) => {
    const hex = Math.round(n).toString(16)
    return hex.length === 1 ? '0' + hex : hex
  }
  
  return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`
}

/**
 * 批量检查颜色组合
 */
export interface ColorPair {
  name: string
  foreground: string
  background: string
}

export interface BatchCheckResult {
  passed: ColorPair[]
  failed: ColorPair[]
  results: Map<string, ContrastResult>
}

export function batchCheckContrast(
  pairs: ColorPair[],
  level: 'AA' | 'AAA' = 'AA'
): BatchCheckResult {
  const passed: ColorPair[] = []
  const failed: ColorPair[] = []
  const results = new Map<string, ContrastResult>()
  
  for (const pair of pairs) {
    const result = checkContrast(pair.foreground, pair.background)
    results.set(pair.name, result)
    
    const meetsRequirement = level === 'AAA'
      ? result.normalText.aaa
      : result.normalText.aa
    
    if (meetsRequirement) {
      passed.push(pair)
    } else {
      failed.push(pair)
    }
  }
  
  return { passed, failed, results }
}

/**
 * 生成对比度报告
 */
export function generateContrastReport(pairs: ColorPair[]): string {
  const results = batchCheckContrast(pairs)
  
  let report = '# 颜色对比度检查报告\n\n'
  
  report += `## 总结\n`
  report += `- 通过: ${results.passed.length}/${pairs.length}\n`
  report += `- 失败: ${results.failed.length}/${pairs.length}\n\n`
  
  if (results.failed.length > 0) {
    report += `## 未通过的颜色组合\n\n`
    for (const pair of results.failed) {
      const result = results.results.get(pair.name)!
      report += `### ${pair.name}\n`
      report += `- 前景色: ${pair.foreground}\n`
      report += `- 背景色: ${pair.background}\n`
      report += `- 对比度: ${result.ratio}:1\n`
      report += `- 等级: ${result.level}\n`
      report += `- 建议前景色: ${getSuggestedForeground(pair.background)}\n\n`
    }
  }
  
  if (results.passed.length > 0) {
    report += `## 通过的颜色组合\n\n`
    for (const pair of results.passed) {
      const result = results.results.get(pair.name)!
      report += `### ${pair.name}\n`
      report += `- 前景色: ${pair.foreground}\n`
      report += `- 背景色: ${pair.background}\n`
      report += `- 对比度: ${result.ratio}:1\n`
      report += `- 等级: ${result.level}\n\n`
    }
  }
  
  return report
}
