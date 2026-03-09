/**
 * 国际化配置
 */
import zhCN from './zh-CN'
import enUS from './en-US'

export const messages = {
  'zh': zhCN,
  'zh-CN': zhCN,
  'en': enUS,
  'en-US': enUS
}

export type Locale = 'zh' | 'en'
export type MessageSchema = typeof zhCN

export { zhCN, enUS }
