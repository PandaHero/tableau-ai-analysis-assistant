/**
 * ARIA 属性工具函数
 * 提供无障碍属性的辅助函数
 */

/**
 * 生成唯一 ID
 */
let idCounter = 0
export function generateId(prefix: string = 'aria'): string {
  return `${prefix}-${++idCounter}`
}

/**
 * ARIA 实时区域类型
 */
export type AriaLive = 'off' | 'polite' | 'assertive'

/**
 * ARIA 角色类型
 */
export type AriaRole =
  | 'alert'
  | 'alertdialog'
  | 'button'
  | 'checkbox'
  | 'dialog'
  | 'gridcell'
  | 'link'
  | 'log'
  | 'marquee'
  | 'menuitem'
  | 'menuitemcheckbox'
  | 'menuitemradio'
  | 'option'
  | 'progressbar'
  | 'radio'
  | 'scrollbar'
  | 'searchbox'
  | 'slider'
  | 'spinbutton'
  | 'status'
  | 'switch'
  | 'tab'
  | 'tabpanel'
  | 'textbox'
  | 'timer'
  | 'tooltip'
  | 'treeitem'
  | 'combobox'
  | 'grid'
  | 'listbox'
  | 'menu'
  | 'menubar'
  | 'radiogroup'
  | 'tablist'
  | 'tree'
  | 'treegrid'
  | 'application'
  | 'article'
  | 'cell'
  | 'columnheader'
  | 'definition'
  | 'directory'
  | 'document'
  | 'feed'
  | 'figure'
  | 'group'
  | 'heading'
  | 'img'
  | 'list'
  | 'listitem'
  | 'math'
  | 'none'
  | 'note'
  | 'presentation'
  | 'region'
  | 'row'
  | 'rowgroup'
  | 'rowheader'
  | 'separator'
  | 'table'
  | 'term'
  | 'toolbar'
  | 'banner'
  | 'complementary'
  | 'contentinfo'
  | 'form'
  | 'main'
  | 'navigation'
  | 'search'

/**
 * 创建 ARIA 属性对象
 */
export interface AriaAttributes {
  role?: AriaRole
  'aria-label'?: string
  'aria-labelledby'?: string
  'aria-describedby'?: string
  'aria-hidden'?: boolean
  'aria-expanded'?: boolean
  'aria-selected'?: boolean
  'aria-checked'?: boolean | 'mixed'
  'aria-disabled'?: boolean
  'aria-readonly'?: boolean
  'aria-required'?: boolean
  'aria-invalid'?: boolean
  'aria-live'?: AriaLive
  'aria-atomic'?: boolean
  'aria-busy'?: boolean
  'aria-controls'?: string
  'aria-current'?: boolean | 'page' | 'step' | 'location' | 'date' | 'time'
  'aria-haspopup'?: boolean | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog'
  'aria-modal'?: boolean
  'aria-multiselectable'?: boolean
  'aria-orientation'?: 'horizontal' | 'vertical'
  'aria-placeholder'?: string
  'aria-pressed'?: boolean | 'mixed'
  'aria-valuemin'?: number
  'aria-valuemax'?: number
  'aria-valuenow'?: number
  'aria-valuetext'?: string
  'aria-level'?: number
  'aria-posinset'?: number
  'aria-setsize'?: number
}

/**
 * 创建按钮的 ARIA 属性
 */
export function createButtonAria(options: {
  label?: string
  pressed?: boolean
  expanded?: boolean
  disabled?: boolean
  controls?: string
  haspopup?: boolean | 'menu' | 'listbox' | 'tree' | 'grid' | 'dialog'
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'button'
  }
  
  if (options.label) attrs['aria-label'] = options.label
  if (options.pressed !== undefined) attrs['aria-pressed'] = options.pressed
  if (options.expanded !== undefined) attrs['aria-expanded'] = options.expanded
  if (options.disabled) attrs['aria-disabled'] = true
  if (options.controls) attrs['aria-controls'] = options.controls
  if (options.haspopup) attrs['aria-haspopup'] = options.haspopup
  
  return attrs
}

/**
 * 创建对话框的 ARIA 属性
 */
export function createDialogAria(options: {
  label?: string
  labelledby?: string
  describedby?: string
  modal?: boolean
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'dialog'
  }
  
  if (options.label) attrs['aria-label'] = options.label
  if (options.labelledby) attrs['aria-labelledby'] = options.labelledby
  if (options.describedby) attrs['aria-describedby'] = options.describedby
  if (options.modal !== undefined) attrs['aria-modal'] = options.modal
  
  return attrs
}

/**
 * 创建标签页的 ARIA 属性
 */
export function createTabAria(options: {
  selected?: boolean
  controls?: string
  labelledby?: string
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'tab'
  }
  
  if (options.selected !== undefined) attrs['aria-selected'] = options.selected
  if (options.controls) attrs['aria-controls'] = options.controls
  if (options.labelledby) attrs['aria-labelledby'] = options.labelledby
  
  return attrs
}

/**
 * 创建标签面板的 ARIA 属性
 */
export function createTabPanelAria(options: {
  labelledby?: string
  hidden?: boolean
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'tabpanel'
  }
  
  if (options.labelledby) attrs['aria-labelledby'] = options.labelledby
  if (options.hidden !== undefined) attrs['aria-hidden'] = options.hidden
  
  return attrs
}

/**
 * 创建实时区域的 ARIA 属性
 */
export function createLiveRegionAria(options: {
  live?: AriaLive
  atomic?: boolean
  relevant?: string
}): AriaAttributes {
  const attrs: AriaAttributes = {}
  
  if (options.live) attrs['aria-live'] = options.live
  if (options.atomic !== undefined) attrs['aria-atomic'] = options.atomic
  
  return attrs
}

/**
 * 创建进度条的 ARIA 属性
 */
export function createProgressAria(options: {
  label?: string
  valuemin?: number
  valuemax?: number
  valuenow?: number
  valuetext?: string
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'progressbar'
  }
  
  if (options.label) attrs['aria-label'] = options.label
  if (options.valuemin !== undefined) attrs['aria-valuemin'] = options.valuemin
  if (options.valuemax !== undefined) attrs['aria-valuemax'] = options.valuemax
  if (options.valuenow !== undefined) attrs['aria-valuenow'] = options.valuenow
  if (options.valuetext) attrs['aria-valuetext'] = options.valuetext
  
  return attrs
}

/**
 * 创建列表的 ARIA 属性
 */
export function createListAria(options: {
  label?: string
  multiselectable?: boolean
  orientation?: 'horizontal' | 'vertical'
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'list'
  }
  
  if (options.label) attrs['aria-label'] = options.label
  if (options.multiselectable !== undefined) attrs['aria-multiselectable'] = options.multiselectable
  if (options.orientation) attrs['aria-orientation'] = options.orientation
  
  return attrs
}

/**
 * 创建列表项的 ARIA 属性
 */
export function createListItemAria(options: {
  selected?: boolean
  level?: number
  posinset?: number
  setsize?: number
}): AriaAttributes {
  const attrs: AriaAttributes = {
    role: 'listitem'
  }
  
  if (options.selected !== undefined) attrs['aria-selected'] = options.selected
  if (options.level !== undefined) attrs['aria-level'] = options.level
  if (options.posinset !== undefined) attrs['aria-posinset'] = options.posinset
  if (options.setsize !== undefined) attrs['aria-setsize'] = options.setsize
  
  return attrs
}

/**
 * 创建表单字段的 ARIA 属性
 */
export function createFieldAria(options: {
  label?: string
  labelledby?: string
  describedby?: string
  required?: boolean
  invalid?: boolean
  disabled?: boolean
  readonly?: boolean
  placeholder?: string
}): AriaAttributes {
  const attrs: AriaAttributes = {}
  
  if (options.label) attrs['aria-label'] = options.label
  if (options.labelledby) attrs['aria-labelledby'] = options.labelledby
  if (options.describedby) attrs['aria-describedby'] = options.describedby
  if (options.required) attrs['aria-required'] = true
  if (options.invalid) attrs['aria-invalid'] = true
  if (options.disabled) attrs['aria-disabled'] = true
  if (options.readonly) attrs['aria-readonly'] = true
  if (options.placeholder) attrs['aria-placeholder'] = options.placeholder
  
  return attrs
}

/**
 * 宣布消息给屏幕阅读器
 */
export function announceToScreenReader(
  message: string,
  priority: AriaLive = 'polite'
): void {
  const announcement = document.createElement('div')
  announcement.setAttribute('role', 'status')
  announcement.setAttribute('aria-live', priority)
  announcement.setAttribute('aria-atomic', 'true')
  announcement.className = 'sr-only'
  announcement.textContent = message
  
  document.body.appendChild(announcement)
  
  // 1秒后移除
  setTimeout(() => {
    document.body.removeChild(announcement)
  }, 1000)
}

/**
 * 检查元素是否可访问
 */
export function isAccessible(element: HTMLElement): boolean {
  // 检查是否有 aria-hidden
  if (element.getAttribute('aria-hidden') === 'true') {
    return false
  }
  
  // 检查是否有 tabindex="-1"
  if (element.getAttribute('tabindex') === '-1') {
    return false
  }
  
  // 检查是否被禁用
  if (element.hasAttribute('disabled')) {
    return false
  }
  
  // 检查是否可见
  const style = window.getComputedStyle(element)
  if (style.display === 'none' || style.visibility === 'hidden') {
    return false
  }
  
  return true
}
