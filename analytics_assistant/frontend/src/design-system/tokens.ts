
/**
 * 设计令牌 (Design Tokens)
 * 
 * 基于 Tableau 设计语言的设计令牌系统
 * 定义颜色、字体、间距、阴影等基础设计元素
 */

// ============================================================================
// 颜色令牌 (Color Tokens)
// ============================================================================

export interface ColorScale {
  50: string;   // 最浅
  100: string;
  200: string;
  300: string;
  400: string;
  500: string;  // 基准色
  600: string;
  700: string;
  800: string;
  900: string;  // 最深
}

export interface ColorTokens {
  // Tableau 主色 - 蓝色
  primary: ColorScale;
  // 中性色
  neutral: ColorScale;
  // 语义色
  success: ColorScale;
  warning: ColorScale;
  error: ColorScale;
  info: ColorScale;
}

// Tableau 10 色板 - 主蓝色
export const tableauBlue: ColorScale = {
  50: '#E3F2FD',
  100: '#BBDEFB',
  200: '#90CAF9',
  300: '#64B5F6',
  400: '#42A5F5',
  500: '#1F77B4',  // Tableau 主蓝色
  600: '#1E88E5',
  700: '#1976D2',
  800: '#1565C0',
  900: '#0D47A1',
};

// 中性色系
export const neutralColors: ColorScale = {
  50: '#FAFAFA',   // 浅灰背景
  100: '#F5F5F5',
  200: '#E0E0E0',  // 边框灰
  300: '#BDBDBD',
  400: '#9E9E9E',
  500: '#757575',
  600: '#666666',  // 次要文字
  700: '#616161',
  800: '#424242',
  900: '#333333',  // 主要文字
};

// 成功色 - Tableau 绿色
export const successColors: ColorScale = {
  50: '#E8F5E9',
  100: '#C8E6C9',
  200: '#A5D6A7',
  300: '#81C784',
  400: '#66BB6A',
  500: '#2CA02C',  // Tableau 绿色
  600: '#43A047',
  700: '#388E3C',
  800: '#2E7D32',
  900: '#1B5E20',
};

// 警告色 - Tableau 橙色
export const warningColors: ColorScale = {
  50: '#FFF3E0',
  100: '#FFE0B2',
  200: '#FFCC80',
  300: '#FFB74D',
  400: '#FFA726',
  500: '#FF7F0E',  // Tableau 橙色
  600: '#FB8C00',
  700: '#F57C00',
  800: '#EF6C00',
  900: '#E65100',
};

// 错误色 - Tableau 红色
export const errorColors: ColorScale = {
  50: '#FFEBEE',
  100: '#FFCDD2',
  200: '#EF9A9A',
  300: '#E57373',
  400: '#EF5350',
  500: '#D62728',  // Tableau 红色
  600: '#E53935',
  700: '#D32F2F',
  800: '#C62828',
  900: '#B71C1C',
};

// 信息色 - 使用主蓝色
export const infoColors: ColorScale = tableauBlue;

export const colors: ColorTokens = {
  primary: tableauBlue,
  neutral: neutralColors,
  success: successColors,
  warning: warningColors,
  error: errorColors,
  info: infoColors,
};

// ============================================================================
// 字体令牌 (Typography Tokens)
// ============================================================================

export interface TypographyTokens {
  fontFamily: {
    base: string;
    heading: string;
    mono: string;
  };
  fontSize: {
    xs: string;    // 12px
    sm: string;    // 14px
    base: string;  // 16px
    lg: string;    // 18px
    xl: string;    // 20px
    '2xl': string; // 24px
    '3xl': string; // 30px
    '4xl': string; // 36px
  };
  fontWeight: {
    light: number;    // 300
    normal: number;   // 400
    medium: number;   // 500
    semibold: number; // 600
    bold: number;     // 700
  };
  lineHeight: {
    tight: number;   // 1.25
    normal: number;  // 1.5
    relaxed: number; // 1.75
  };
}

export const typography: TypographyTokens = {
  fontFamily: {
    base: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    heading: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    mono: '"SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace',
  },
  fontSize: {
    xs: '12px',
    sm: '14px',
    base: '16px',
    lg: '18px',
    xl: '20px',
    '2xl': '24px',
    '3xl': '30px',
    '4xl': '36px',
  },
  fontWeight: {
    light: 300,
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  lineHeight: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
  },
};

// ============================================================================
// 间距令牌 (Spacing Tokens)
// ============================================================================

export interface SpacingTokens {
  0: string;    // 0
  1: string;    // 4px
  2: string;    // 8px
  3: string;    // 12px
  4: string;    // 16px
  5: string;    // 20px
  6: string;    // 24px
  8: string;    // 32px
  10: string;   // 40px
  12: string;   // 48px
  16: string;   // 64px
  20: string;   // 80px
}

export const spacing: SpacingTokens = {
  0: '0',
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '20px',
  6: '24px',
  8: '32px',
  10: '40px',
  12: '48px',
  16: '64px',
  20: '80px',
};

// ============================================================================
// 阴影令牌 (Shadow Tokens)
// ============================================================================

export interface ShadowTokens {
  sm: string;   // 小阴影
  base: string; // 基础阴影
  md: string;   // 中等阴影
  lg: string;   // 大阴影
  xl: string;   // 超大阴影
}

export const shadows: ShadowTokens = {
  sm: '0 1px 3px rgba(0, 0, 0, 0.08)',
  base: '0 1px 4px rgba(0, 0, 0, 0.12)',
  md: '0 2px 8px rgba(0, 0, 0, 0.12)',
  lg: '0 4px 16px rgba(0, 0, 0, 0.16)',
  xl: '0 8px 32px rgba(0, 0, 0, 0.20)',
};

// ============================================================================
// 边框令牌 (Border Tokens)
// ============================================================================

export interface BorderTokens {
  radius: {
    none: string;   // 0
    sm: string;     // 4px
    base: string;   // 8px
    md: string;     // 12px
    lg: string;     // 16px
    full: string;   // 9999px
  };
  width: {
    thin: string;   // 1px
    base: string;   // 2px
    thick: string;  // 4px
  };
}

export const borders: BorderTokens = {
  radius: {
    none: '0',
    sm: '4px',
    base: '8px',
    md: '12px',
    lg: '16px',
    full: '9999px',
  },
  width: {
    thin: '1px',
    base: '2px',
    thick: '4px',
  },
};

// ============================================================================
// 过渡令牌 (Transition Tokens)
// ============================================================================

export interface TransitionTokens {
  duration: {
    fast: string;     // 150ms
    base: string;     // 250ms
    slow: string;     // 400ms
  };
  timing: {
    linear: string;
    easeIn: string;
    easeOut: string;
    easeInOut: string;
  };
}

export const transitions: TransitionTokens = {
  duration: {
    fast: '150ms',
    base: '250ms',
    slow: '400ms',
  },
  timing: {
    linear: 'linear',
    easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
    easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
    easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
  },
};

// ============================================================================
// 设计令牌集合
// ============================================================================

export interface DesignTokens {
  colors: ColorTokens;
  typography: TypographyTokens;
  spacing: SpacingTokens;
  shadows: ShadowTokens;
  borders: BorderTokens;
  transitions: TransitionTokens;
}

export const tokens: DesignTokens = {
  colors,
  typography,
  spacing,
  shadows,
  borders,
  transitions,
};

export default tokens;
