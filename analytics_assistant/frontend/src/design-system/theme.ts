/**
 * 主题系统 (Theme System)
 * 
 * 实现浅色/深色主题切换和主题管理
 */

import type { DesignTokens, ColorScale } from './tokens';
import { tokens } from './tokens';

// ============================================================================
// 主题类型定义
// ============================================================================

export type ThemeMode = 'light' | 'dark' | 'auto';

export interface Theme {
  mode: ThemeMode;
  tokens: DesignTokens;
}

// ============================================================================
// 浅色主题 (Light Theme)
// ============================================================================

export const lightTheme: Theme = {
  mode: 'light',
  tokens: {
    ...tokens,
    colors: {
      ...tokens.colors,
      // 浅色主题使用标准 Tableau 色板
    },
  },
};

// ============================================================================
// 深色主题 (Dark Theme)
// ============================================================================

// 深色主题的中性色（反转）
const darkNeutralColors: ColorScale = {
  50: '#1A1A1A',   // 深灰背景
  100: '#2D2D2D',  // 卡片背景
  200: '#424242',  // 边框
  300: '#616161',
  400: '#757575',
  500: '#9E9E9E',
  600: '#B0B0B0',  // 次要文字
  700: '#BDBDBD',
  800: '#E0E0E0',  // 主要文字
  900: '#F5F5F5',
};

// 深色主题的主色（稍微调亮）
const darkPrimaryColors: ColorScale = {
  50: '#0D47A1',
  100: '#1565C0',
  200: '#1976D2',
  300: '#1E88E5',
  400: '#42A5F5',
  500: '#64B5F6',  // 深色主题主色（比浅色主题更亮）
  600: '#90CAF9',
  700: '#BBDEFB',
  800: '#E3F2FD',
  900: '#F3F9FF',
};

export const darkTheme: Theme = {
  mode: 'dark',
  tokens: {
    ...tokens,
    colors: {
      primary: darkPrimaryColors,
      neutral: darkNeutralColors,
      success: tokens.colors.success,  // 成功色保持不变
      warning: tokens.colors.warning,  // 警告色保持不变
      error: tokens.colors.error,      // 错误色保持不变
      info: darkPrimaryColors,
    },
  },
};

// ============================================================================
// 主题管理器 (Theme Manager)
// ============================================================================

export class ThemeManager {
  private static _instance: ThemeManager | null = null;

  private _currentTheme: Theme = lightTheme;
  private _systemPreference: 'light' | 'dark' = 'light';
  private _userPreference: ThemeMode = 'auto';
  private _themeChangeCallbacks: Array<(mode: ThemeMode) => void> = [];
  private _initialized = false;

  constructor() {
    this._detectSystemPreference();
    this._loadUserPreference();
    this._applyTheme();
    this._watchSystemPreference();
  }

  // ── 单例 ─────────────────────────────────────────────────────────────────

  static getInstance(): ThemeManager {
    if (!ThemeManager._instance) {
      ThemeManager._instance = new ThemeManager();
    }
    return ThemeManager._instance;
  }

  // ── 初始化（兼容 main.ts / ui.ts 调用） ────────────────────────────────

  init(): void {
    if (this._initialized) return;
    this._initialized = true;
    // 已在构造函数中完成初始化，此处仅作标记
  }

  // ── 系统偏好检测 ────────────────────────────────────────────────────────

  private _detectSystemPreference(): void {
    if (typeof window === 'undefined') return;
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    this._systemPreference = darkModeQuery.matches ? 'dark' : 'light';
  }

  private _watchSystemPreference(): void {
    if (typeof window === 'undefined') return;
    const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
    darkModeQuery.addEventListener('change', (e) => {
      this._systemPreference = e.matches ? 'dark' : 'light';
      if (this._userPreference === 'auto') {
        this._applyTheme();
        this._notifyThemeChange();
      }
    });
  }

  // ── 用户偏好持久化 ───────────────────────────────────────────────────────

  private _loadUserPreference(): void {
    if (typeof window === 'undefined') return;
    const saved = localStorage.getItem('theme-preference');
    if (saved && (saved === 'light' || saved === 'dark' || saved === 'auto')) {
      this._userPreference = saved as ThemeMode;
    }
  }

  private _saveUserPreference(): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('theme-preference', this._userPreference);
  }

  // ── 实际生效的模式 ───────────────────────────────────────────────────────

  private _getEffectiveMode(): 'light' | 'dark' {
    if (this._userPreference === 'auto') {
      return this._systemPreference === 'dark' ? 'dark' : 'light';
    }
    return this._userPreference === 'dark' ? 'dark' : 'light';
  }

  // ── 变更通知 ─────────────────────────────────────────────────────────────

  onThemeChange(callback: (mode: ThemeMode) => void): void {
    this._themeChangeCallbacks.push(callback);
  }

  private _notifyThemeChange(): void {
    this._themeChangeCallbacks.forEach(cb => cb(this._userPreference));
  }

  // ── 公共 API ─────────────────────────────────────────────────────────────

  /** 设置主题并持久化 */
  setTheme(mode: ThemeMode): void {
    this._userPreference = mode;
    this._saveUserPreference();
    this._applyTheme();
    this._notifyThemeChange();
  }

  /** 获取当前用户偏好（ThemeMode 字符串） */
  getTheme(): ThemeMode {
    return this._userPreference;
  }

  /** 获取当前完整 Theme 对象 */
  getCurrentTheme(): Theme {
    return this._currentTheme;
  }

  /** 获取实际生效的主题模式 */
  getEffectiveThemeMode(): 'light' | 'dark' {
    return this._getEffectiveMode();
  }

  /** 切换主题（light ↔ dark） */
  toggleTheme(): void {
    const currentEffective = this._getEffectiveMode();
    this.setTheme(currentEffective === 'light' ? 'dark' : 'light');
  }

  /** 将当前主题应用到 DOM（外部可调用） */
  applyTheme(): void {
    this._applyTheme();
  }

  // ── 私有实现 ─────────────────────────────────────────────────────────────

  private _applyTheme(): void {
    const effectiveMode = this._getEffectiveMode();
    this._currentTheme = effectiveMode === 'dark' ? darkTheme : lightTheme;

    if (typeof window === 'undefined') return;

    const root = document.documentElement;

    // 加短暂过渡类，结束后移除（避免常态性能消耗）
    root.classList.add('theme-transitioning');
    setTimeout(() => root.classList.remove('theme-transitioning'), 300);

    const { tokens: t } = this._currentTheme;

    // 设置主题模式类名，并兼容旧样式选择器
    root.classList.remove('theme-light', 'theme-dark', 'light', 'dark');
    root.classList.add(`theme-${effectiveMode}`, effectiveMode);
    root.setAttribute('data-theme', effectiveMode);
    root.style.setProperty('color-scheme', effectiveMode);

    // 应用颜色令牌
    this._applyColorTokens(root, t.colors.primary, 'primary');
    this._applyColorTokens(root, t.colors.neutral, 'neutral');
    this._applyColorTokens(root, t.colors.success, 'success');
    this._applyColorTokens(root, t.colors.warning, 'warning');
    this._applyColorTokens(root, t.colors.error, 'error');
    this._applyColorTokens(root, t.colors.info, 'info');

    // 应用字体令牌
    root.style.setProperty('--font-family-base', t.typography.fontFamily.base);
    root.style.setProperty('--font-family-heading', t.typography.fontFamily.heading);
    root.style.setProperty('--font-family-mono', t.typography.fontFamily.mono);

    Object.entries(t.typography.fontSize).forEach(([key, value]) => {
      root.style.setProperty(`--font-size-${key}`, value);
    });

    Object.entries(t.typography.fontWeight).forEach(([key, value]) => {
      root.style.setProperty(`--font-weight-${key}`, value.toString());
    });

    Object.entries(t.typography.lineHeight).forEach(([key, value]) => {
      root.style.setProperty(`--line-height-${key}`, value.toString());
    });

    // 应用间距令牌
    Object.entries(t.spacing).forEach(([key, value]) => {
      root.style.setProperty(`--spacing-${key}`, value);
    });

    // 应用阴影令牌
    Object.entries(t.shadows).forEach(([key, value]) => {
      root.style.setProperty(`--shadow-${key}`, value);
    });

    // 应用边框令牌
    Object.entries(t.borders.radius).forEach(([key, value]) => {
      root.style.setProperty(`--border-radius-${key}`, value);
    });

    Object.entries(t.borders.width).forEach(([key, value]) => {
      root.style.setProperty(`--border-width-${key}`, value);
    });

    // 应用过渡令牌
    Object.entries(t.transitions.duration).forEach(([key, value]) => {
      root.style.setProperty(`--transition-duration-${key}`, value);
    });

    Object.entries(t.transitions.timing).forEach(([key, value]) => {
      root.style.setProperty(`--transition-timing-${key}`, value);
    });

    // 应用特殊颜色变量（常用颜色的快捷方式）
    root.style.setProperty('--color-white', '#FFFFFF');
    root.style.setProperty('--color-black', '#000000');
    root.style.setProperty('--color-background', effectiveMode === 'dark' ? t.colors.neutral[50] : '#FFFFFF');
    root.style.setProperty('--color-surface', effectiveMode === 'dark' ? t.colors.neutral[100] : '#FFFFFF');
    root.style.setProperty('--color-bg-primary', t.colors.neutral[50]);
    root.style.setProperty('--color-bg-secondary', effectiveMode === 'light' ? '#FFFFFF' : t.colors.neutral[100]);
    root.style.setProperty('--color-text-primary', effectiveMode === 'dark' ? t.colors.neutral[900] : '#1A1A1A');
    root.style.setProperty('--color-text-secondary', t.colors.neutral[600]);
    root.style.setProperty('--color-border', t.colors.neutral[200]);
    root.style.setProperty('--color-primary', t.colors.primary[500]);
    root.style.setProperty('--color-error', t.colors.error[500]);
    root.style.setProperty('--color-warning', t.colors.warning[500]);
    root.style.setProperty('--color-success', t.colors.success[500]);

    // ── 兼容 SCSS 组件使用的 CSS 变量名 ──
    if (effectiveMode === 'dark') {
      root.style.setProperty('--bg-primary', '#1E1E1E');
      root.style.setProperty('--bg-secondary', '#2D2D2D');
      root.style.setProperty('--bg-tertiary', '#3D3D3D');
      root.style.setProperty('--bg-hover', '#404040');
      root.style.setProperty('--text-primary', '#E0E0E0');
      root.style.setProperty('--text-secondary', '#B0B0B0');
      root.style.setProperty('--text-tertiary', '#808080');
      root.style.setProperty('--text-disabled', '#4D4D4D');
      root.style.setProperty('--border-color', '#3D3D3D');
      root.style.setProperty('--border-light', '#2D2D2D');
      root.style.setProperty('--border-dark', '#4D4D4D');
      root.style.setProperty('--scrollbar-track', '#2D2D2D');
      root.style.setProperty('--scrollbar-thumb', '#3D3D3D');
      root.style.setProperty('--scrollbar-thumb-hover', '#4D4D4D');
    } else {
      root.style.setProperty('--bg-primary', '#FFFFFF');
      root.style.setProperty('--bg-secondary', '#FAFAFA');
      root.style.setProperty('--bg-tertiary', '#F5F5F5');
      root.style.setProperty('--bg-hover', '#F5F5F5');
      root.style.setProperty('--text-primary', '#333333');
      root.style.setProperty('--text-secondary', '#666666');
      root.style.setProperty('--text-tertiary', '#999999');
      root.style.setProperty('--text-disabled', '#CCCCCC');
      root.style.setProperty('--border-color', '#E0E0E0');
      root.style.setProperty('--border-light', '#F5F5F5');
      root.style.setProperty('--border-dark', '#CCCCCC');
      root.style.setProperty('--scrollbar-track', '#FAFAFA');
      root.style.setProperty('--scrollbar-thumb', '#E0E0E0');
      root.style.setProperty('--scrollbar-thumb-hover', '#CCCCCC');
    }
  }

  private _applyColorTokens(root: HTMLElement, colorScale: ColorScale, prefix: string): void {
    Object.entries(colorScale).forEach(([key, value]) => {
      root.style.setProperty(`--color-${prefix}-${key}`, value);
    });
  }
}

// ============================================================================
// 导出单例实例（向后兼容）
// ============================================================================

export function getThemeManager(): ThemeManager {
  return ThemeManager.getInstance();
}

export default ThemeManager;
