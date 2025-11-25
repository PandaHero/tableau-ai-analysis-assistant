# VizQL多智能体分析系统 - UI设计规范

## 设计理念

### 核心原则
1. **简洁至上** - 去除一切不必要的视觉元素，让数据和分析结果成为焦点
2. **渐进式展示** - 信息分层展示，用户可以按需深入查看细节
3. **流畅体验** - 流式加载，实时反馈，减少等待焦虑
4. **专业可信** - 数据分析场景需要传递专业、可靠的视觉感受

### 参考对象
- **ChatGPT** - 简洁的对话流、清晰的消息分隔
- **Claude** - 优雅的排版、舒适的阅读体验
- **Perplexity** - 结构化的信息展示、来源引用
- **Notion AI** - 内联操作、渐进式展开

---

## 整体布局

### 页面结构
```
┌─────────────────────────────────────────────────────────────┐
│  Header (固定顶部)                                           │
│  [Logo] VizQL智能分析  [数据源: 销售数据]  [设置]           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  对话区域 (可滚动)                                           │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  用户消息气泡                                       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  AI消息气泡                                         │    │
│  │  ├─ 分析流程时间线                                  │    │
│  │  ├─ 子任务卡片 1                                    │    │
│  │  ├─ 子任务卡片 2                                    │    │
│  │  └─ 最终总结                                        │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  输入区域 (固定底部)                                         │
│  ┌────────────────────────────────────────────────────┐    │
│  │  [输入框]                                    [发送] │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 尺寸规范
- **最大宽度**: 1200px (居中显示)
- **对话区域**: 左右各留 24px padding
- **消息间距**: 24px
- **卡片圆角**: 12px (大卡片), 8px (小卡片)
- **阴影**: 0 2px 8px rgba(0,0,0,0.08) (悬浮), 0 1px 3px rgba(0,0,0,0.06) (静态)

---

## 配色方案

### 主色调 (专业、可信)
```css
/* 主色 - 蓝色系 (专业、科技) */
--primary-50: #E3F2FD;
--primary-100: #BBDEFB;
--primary-500: #2196F3;  /* 主要按钮、链接 */
--primary-600: #1E88E5;  /* 悬浮状态 */
--primary-700: #1976D2;  /* 激活状态 */

/* 中性色 - 灰色系 (背景、文本) */
--gray-50: #FAFAFA;      /* 页面背景 */
--gray-100: #F5F5F5;     /* AI消息背景 */
--gray-200: #EEEEEE;     /* 分隔线 */
--gray-300: #E0E0E0;     /* 边框 */
--gray-500: #9E9E9E;     /* 次要文本 */
--gray-700: #616161;     /* 主要文本 */
--gray-900: #212121;     /* 标题 */

/* 功能色 */
--success: #4CAF50;      /* 成功、完成 */
--warning: #FF9800;      /* 警告、重规划 */
--error: #F44336;        /* 错误 */
--info: #2196F3;         /* 信息提示 */

/* 用户消息 */
--user-bg: #2196F3;      /* 用户消息背景 */
--user-text: #FFFFFF;    /* 用户消息文本 */

/* AI消息 */
--ai-bg: #FFFFFF;        /* AI消息背景 (白色卡片) */
--ai-border: #E0E0E0;    /* AI消息边框 */
```

### 字体规范
```css
/* 字体家族 */
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, sans-serif;
--font-mono: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono",
             Consolas, monospace;

/* 字号 */
--text-xs: 12px;    /* 辅助信息 */
--text-sm: 14px;    /* 正文 */
--text-base: 16px;  /* 用户输入 */
--text-lg: 18px;    /* 小标题 */
--text-xl: 20px;    /* 大标题 */
--text-2xl: 24px;   /* 页面标题 */

/* 行高 */
--leading-tight: 1.25;
--leading-normal: 1.5;
--leading-relaxed: 1.75;

/* 字重 */
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
```

---

## 用户消息气泡

### 设计原则
- 简洁明了，突出用户意图
- 右对齐，与AI消息形成对比
- 使用主色调，传递"我的问题"的归属感

### 视觉设计
```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│                              ┌──────────────────────────┐   │
│                              │ 本月销售额TOP10的门店    │   │
│                              │ 是哪些？                 │   │
│                              └──────────────────────────┘   │
│                                   ↑ 用户头像 (可选)         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.user-message {
  /* 布局 */
  display: flex;
  justify-content: flex-end;
  margin: 24px 0;

  /* 气泡容器 */
  .bubble {
    max-width: 70%;
    padding: 12px 16px;
    background: var(--primary-500);
    color: white;
    border-radius: 16px 16px 4px 16px;
    box-shadow: 0 2px 8px rgba(33, 150, 243, 0.2);

    /* 文本 */
    font-size: var(--text-base);
    line-height: var(--leading-normal);
    word-wrap: break-word;
  }

  /* 头像 (可选) */
  .avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    margin-left: 12px;
    background: var(--primary-700);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: var(--font-semibold);
  }
}
```

### 交互状态
- **默认**: 静态显示
- **悬浮**: 无特殊效果 (避免干扰)
- **动画**: 从右侧淡入 (0.3s ease-out)

---

## AI消息气泡

### 设计原则
- **分层展示**: 时间线 → 子任务 → 总结，逐层深入
- **可折叠**: 用户可以控制信息密度
- **实时更新**: 流式加载，逐步显示内容
- **专业感**: 白色卡片 + 细边框，类似报告/文档

### 整体结构
```
┌─────────────────────────────────────────────────────────────┐
│ AI消息容器 (白色背景，细边框)                                │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 📊 分析流程时间线                                     │   │
│ │ Plan → Decompose → Stage 1 → Stage 2 → Compose       │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 子任务卡片 1 (可折叠)                                 │   │
│ │ ├─ Stage 1 | 查询本月销售额                          │   │
│ │ ├─ [VizQL查询] (折叠)                                │   │
│ │ ├─ [查询结果] (表格，默认展开)                       │   │
│ │ └─ [分析结果] (Markdown)                             │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 子任务卡片 2                                          │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ 💡 最终总结                                           │   │
│ │ 根据分析结果，本月销售额TOP10的门店是...             │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.ai-message {
  /* 布局 */
  display: flex;
  justify-content: flex-start;
  margin: 24px 0;

  /* 主容器 */
  .container {
    max-width: 100%;
    width: 100%;
  }

  /* 头像 (可选) */
  .avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    margin-right: 12px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: var(--font-semibold);
    flex-shrink: 0;
  }

  /* 内容区域 */
  .content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
}
```

---

## 分析流程时间线

### 设计原则
- 横向展示，清晰展示分析流程
- 使用图标 + 文字，增强可读性
- 当前步骤高亮，已完成步骤打勾

### 视觉设计
```
┌──────────────────────────────────────────────────────────┐
│  ✓ Plan  →  ✓ Decompose  →  ⟳ Stage 1  →  ○ Stage 2  →  ○ Compose  │
│  规划        拆分            执行中        待执行        总结      │
└──────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.timeline {
  background: white;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  overflow-x: auto;

  /* 步骤项 */
  .step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-width: 80px;
    position: relative;

    /* 图标 */
    .icon {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      font-weight: var(--font-semibold);
      transition: all 0.3s ease;
    }

    /* 标签 */
    .label {
      font-size: var(--text-xs);
      color: var(--gray-500);
      text-align: center;
    }

    /* 连接线 */
    &:not(:last-child)::after {
      content: '→';
      position: absolute;
      right: -18px;
      top: 18px;
      color: var(--gray-300);
      font-size: 14px;
    }
  }

  /* 已完成 */
  .step.completed {
    .icon {
      background: var(--success);
      color: white;
    }
    .label {
      color: var(--gray-700);
    }
  }

  /* 进行中 */
  .step.current {
    .icon {
      background: var(--primary-500);
      color: white;
      animation: pulse 1.5s infinite;
    }
    .label {
      color: var(--primary-600);
      font-weight: var(--font-medium);
    }
  }

  /* 待执行 */
  .step.pending {
    .icon {
      background: var(--gray-100);
      color: var(--gray-400);
    }
  }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}
```

---

## 子任务卡片

### 设计原则
- **卡片式设计**: 每个子任务独立成卡片，清晰分隔
- **渐进式展开**: 默认显示核心信息，细节可折叠
- **状态标识**: 通过颜色和图标区分执行状态
- **数据优先**: 查询结果默认展开，VizQL查询默认折叠

### 视觉设计
```
┌────────────────────────────────────────────────────────────┐
│ ┌─ 子任务卡片 ─────────────────────────────────────────┐  │
│ │                                                        │  │
│ │ [Stage 1] 查询本月销售额TOP10门店          [✓ 完成]  │  │
│ │ ─────────────────────────────────────────────────────  │  │
│ │                                                        │  │
│ │ 📝 任务描述                                            │  │
│ │ 查询2025年1月的销售额，按门店分组，取TOP10            │  │
│ │                                                        │  │
│ │ ▼ VizQL查询 (点击展开)                                │  │
│ │                                                        │  │
│ │ ▼ 查询结果 (默认展开)                                 │  │
│ │ ┌──────────────────────────────────────────────────┐ │  │
│ │ │ 门店名称    │ 销售额      │ 占比    │ 排名     │ │  │
│ │ ├──────────────────────────────────────────────────┤ │  │
│ │ │ 北京旗舰店  │ ¥1,234,567  │ 15.2%   │ 1       │ │  │
│ │ │ 上海中心店  │ ¥987,654    │ 12.1%   │ 2       │ │  │
│ │ │ ...         │ ...         │ ...     │ ...     │ │  │
│ │ └──────────────────────────────────────────────────┘ │  │
│ │                                                        │  │
│ │ 💡 分析结果                                            │  │
│ │ 本月销售额TOP10门店中，北京旗舰店以123万元位居第一... │  │
│ │                                                        │  │
│ │ ⚙️ 规则说明 (点击展开)                                │  │
│ │                                                        │  │
│ └────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.subtask-card {
  background: white;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 20px;
  transition: all 0.3s ease;

  /* 悬浮效果 */
  &:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    border-color: var(--gray-300);
  }

  /* 卡片头部 */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--gray-100);

    .title {
      display: flex;
      align-items: center;
      gap: 12px;

      .stage-badge {
        background: var(--primary-50);
        color: var(--primary-700);
        padding: 4px 10px;
        border-radius: 6px;
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
      }

      .task-name {
        font-size: var(--text-lg);
        font-weight: var(--font-semibold);
        color: var(--gray-900);
      }
    }

    .status {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: var(--text-sm);

      &.completed {
        color: var(--success);
      }
      &.running {
        color: var(--primary-500);
      }
      &.error {
        color: var(--error);
      }
    }
  }

  /* 任务描述 */
  .description {
    margin-bottom: 16px;
    padding: 12px;
    background: var(--gray-50);
    border-radius: 8px;
    font-size: var(--text-sm);
    line-height: var(--leading-relaxed);
    color: var(--gray-700);
  }
}
```

---

## 可折叠区域 (Collapsible)

### 设计原则
- 默认状态根据内容重要性决定 (查询结果展开，VizQL折叠)
- 清晰的展开/折叠指示器
- 平滑的动画过渡

### 视觉设计
```
折叠状态:
┌────────────────────────────────────────────────────────┐
│ ▶ VizQL查询                                    [展开]  │
└────────────────────────────────────────────────────────┘

展开状态:
┌────────────────────────────────────────────────────────┐
│ ▼ VizQL查询                                    [折叠]  │
│ ┌────────────────────────────────────────────────────┐ │
│ │ {                                                  │ │
│ │   "fields": [                                      │ │
│ │     {"fieldCaption": "门店名称"},                  │ │
│ │     {"fieldCaption": "销售额", "function": "SUM"}  │ │
│ │   ],                                               │ │
│ │   "filters": [...]                                 │ │
│ │ }                                                  │ │
│ └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.collapsible {
  margin: 16px 0;

  /* 触发器 */
  .trigger {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s ease;

    &:hover {
      background: var(--gray-100);
      border-color: var(--gray-300);
    }

    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: var(--text-sm);
      font-weight: var(--font-medium);
      color: var(--gray-700);

      .icon {
        transition: transform 0.2s ease;
      }
    }

    .action {
      font-size: var(--text-xs);
      color: var(--primary-500);
    }
  }

  /* 展开时旋转图标 */
  &.open .trigger .icon {
    transform: rotate(90deg);
  }

  /* 内容区域 */
  .content {
    margin-top: 8px;
    padding: 16px;
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    overflow: hidden;

    /* 动画 */
    animation: slideDown 0.3s ease-out;
  }
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

## 数据表格

### 设计原则
- 清晰的表头和数据行分隔
- 支持排序 (点击表头)
- 数字右对齐，文本左对齐
- 斑马纹提升可读性
- 大数据集分页显示

### 视觉设计
```
┌──────────────────────────────────────────────────────────┐
│ 门店名称 ↓  │ 销售额 ↑    │ 占比        │ 排名          │
├──────────────────────────────────────────────────────────┤
│ 北京旗舰店   │ ¥1,234,567  │ 15.2%       │ 1            │
│ 上海中心店   │ ¥987,654    │ 12.1%       │ 2            │
│ 广州天河店   │ ¥876,543    │ 10.8%       │ 3            │
│ ...          │ ...         │ ...         │ ...          │
├──────────────────────────────────────────────────────────┤
│ 共10条记录                          [1] 2 3 4 5 > 尾页   │
└──────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);

  /* 表头 */
  thead {
    background: var(--gray-50);

    th {
      padding: 12px 16px;
      text-align: left;
      font-weight: var(--font-semibold);
      color: var(--gray-700);
      border-bottom: 2px solid var(--gray-200);
      white-space: nowrap;

      /* 可排序列 */
      &.sortable {
        cursor: pointer;
        user-select: none;

        &:hover {
          background: var(--gray-100);
        }

        /* 排序图标 */
        .sort-icon {
          margin-left: 4px;
          color: var(--gray-400);
          font-size: 12px;
        }

        &.sorted-asc .sort-icon::before {
          content: '↑';
          color: var(--primary-500);
        }

        &.sorted-desc .sort-icon::before {
          content: '↓';
          color: var(--primary-500);
        }
      }

      /* 数字列右对齐 */
      &.numeric {
        text-align: right;
      }
    }
  }

  /* 表体 */
  tbody {
    tr {
      border-bottom: 1px solid var(--gray-100);
      transition: background 0.2s ease;

      /* 斑马纹 */
      &:nth-child(even) {
        background: var(--gray-50);
      }

      /* 悬浮效果 */
      &:hover {
        background: var(--primary-50);
      }

      td {
        padding: 12px 16px;
        color: var(--gray-700);

        /* 数字列 */
        &.numeric {
          text-align: right;
          font-variant-numeric: tabular-nums;
        }

        /* 高亮列 (如排名第一) */
        &.highlight {
          font-weight: var(--font-semibold);
          color: var(--primary-600);
        }
      }
    }
  }

  /* 分页 */
  .pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--gray-50);
    border-top: 1px solid var(--gray-200);

    .info {
      font-size: var(--text-xs);
      color: var(--gray-500);
    }

    .controls {
      display: flex;
      gap: 4px;

      button {
        padding: 6px 12px;
        border: 1px solid var(--gray-300);
        background: white;
        border-radius: 6px;
        cursor: pointer;
        font-size: var(--text-xs);
        transition: all 0.2s ease;

        &:hover:not(:disabled) {
          background: var(--primary-50);
          border-color: var(--primary-500);
          color: var(--primary-600);
        }

        &.active {
          background: var(--primary-500);
          color: white;
          border-color: var(--primary-500);
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      }
    }
  }
}
```

---

## 代码块 (VizQL查询)

### 设计原则
- 使用等宽字体，提升代码可读性
- 语法高亮 (JSON)
- 支持复制按钮
- 深色背景，减少视觉疲劳

### 视觉设计
```
┌────────────────────────────────────────────────────────┐
│ VizQL查询                                      [复制]  │
├────────────────────────────────────────────────────────┤
│ {                                                      │
│   "fields": [                                          │
│     {"fieldCaption": "门店名称"},                      │
│     {"fieldCaption": "销售额", "function": "SUM"}      │
│   ],                                                   │
│   "filters": [                                         │
│     {                                                  │
│       "field": {"fieldCaption": "日期"},               │
│       "filterType": "QUANTITATIVE_DATE",               │
│       "quantitativeFilterType": "RANGE",               │
│       "minDate": "2025-01-01",                         │
│       "maxDate": "2025-01-31"                          │
│     }                                                  │
│   ]                                                    │
│ }                                                      │
└────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.code-block {
  position: relative;
  margin: 12px 0;

  /* 头部 */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: #2d2d2d;
    border-radius: 8px 8px 0 0;

    .title {
      font-size: var(--text-xs);
      color: #a0a0a0;
      font-family: var(--font-mono);
    }

    .copy-btn {
      padding: 4px 8px;
      background: transparent;
      border: 1px solid #4a4a4a;
      border-radius: 4px;
      color: #a0a0a0;
      font-size: var(--text-xs);
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        background: #3a3a3a;
        border-color: #5a5a5a;
        color: white;
      }

      &.copied {
        background: var(--success);
        border-color: var(--success);
        color: white;
      }
    }
  }

  /* 代码内容 */
  pre {
    margin: 0;
    padding: 16px;
    background: #1e1e1e;
    border-radius: 0 0 8px 8px;
    overflow-x: auto;

    code {
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.6;
      color: #d4d4d4;

      /* JSON语法高亮 */
      .key { color: #9cdcfe; }
      .string { color: #ce9178; }
      .number { color: #b5cea8; }
      .boolean { color: #569cd6; }
      .null { color: #569cd6; }
    }
  }
}
```

---

## 最终总结区域

### 设计原则
- 突出显示，使用不同的背景色
- 支持Markdown渲染
- 清晰的视觉层次

### 视觉设计
```
┌────────────────────────────────────────────────────────┐
│ 💡 分析总结                                            │
├────────────────────────────────────────────────────────┤
│                                                        │
│ ## 核心发现                                            │
│                                                        │
│ 根据本月销售数据分析，以下是TOP10门店的表现：         │
│                                                        │
│ 1. **北京旗舰店** 以123万元位居第一，占总销售额15.2%  │
│ 2. **上海中心店** 紧随其后，销售额98万元              │
│ 3. ...                                                 │
│                                                        │
│ ## 业务洞察                                            │
│                                                        │
│ - 一线城市门店表现突出，占据TOP10中的7席              │
│ - 旗舰店模式效果显著，平均销售额高出普通店30%         │
│                                                        │
│ ## 建议                                                │
│                                                        │
│ 1. 加大一线城市旗舰店投入                              │
│ 2. 复制成功经验到二线城市                              │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.final-summary {
  margin-top: 24px;
  padding: 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  border-left: 4px solid var(--primary-500);
  border-radius: 12px;

  /* 标题 */
  .title {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 16px;
    font-size: var(--text-xl);
    font-weight: var(--font-semibold);
    color: var(--gray-900);

    .icon {
      font-size: 24px;
    }
  }

  /* Markdown内容 */
  .content {
    font-size: var(--text-sm);
    line-height: var(--leading-relaxed);
    color: var(--gray-700);

    /* 标题 */
    h2 {
      font-size: var(--text-lg);
      font-weight: var(--font-semibold);
      margin: 20px 0 12px 0;
      color: var(--gray-900);
    }

    h3 {
      font-size: var(--text-base);
      font-weight: var(--font-medium);
      margin: 16px 0 8px 0;
      color: var(--gray-800);
    }

    /* 段落 */
    p {
      margin: 12px 0;
    }

    /* 列表 */
    ul, ol {
      margin: 12px 0;
      padding-left: 24px;

      li {
        margin: 6px 0;
      }
    }

    /* 强调 */
    strong {
      font-weight: var(--font-semibold);
      color: var(--primary-600);
    }

    /* 代码 */
    code {
      padding: 2px 6px;
      background: rgba(0, 0, 0, 0.05);
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 0.9em;
    }
  }
}
```

---

## 输入区域

### 设计原则
- 固定在底部，始终可见
- 大输入框，支持多行输入
- 清晰的发送按钮
- 快捷键提示 (Enter发送，Shift+Enter换行)

### 视觉设计
```
┌────────────────────────────────────────────────────────┐
│ ┌────────────────────────────────────────────────────┐ │
│ │ 请输入您的问题...                                  │ │
│ │                                                    │ │
│ │                                                    │ │
│ └────────────────────────────────────────────────────┘ │
│                                                        │
│ Enter发送 · Shift+Enter换行                    [发送] │
└────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.input-area {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  background: white;
  border-top: 1px solid var(--gray-200);
  padding: 16px 24px;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);

  .container {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    gap: 12px;
    align-items: flex-end;
  }

  /* 输入框容器 */
  .input-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;

    /* 文本域 */
    textarea {
      width: 100%;
      min-height: 56px;
      max-height: 200px;
      padding: 14px 16px;
      border: 2px solid var(--gray-200);
      border-radius: 12px;
      font-size: var(--text-base);
      font-family: var(--font-sans);
      line-height: var(--leading-normal);
      resize: vertical;
      transition: all 0.2s ease;

      &:focus {
        outline: none;
        border-color: var(--primary-500);
        box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
      }

      &::placeholder {
        color: var(--gray-400);
      }
    }

    /* 提示文本 */
    .hint {
      font-size: var(--text-xs);
      color: var(--gray-500);
    }
  }

  /* 发送按钮 */
  .send-btn {
    padding: 14px 24px;
    background: var(--primary-500);
    color: white;
    border: none;
    border-radius: 12px;
    font-size: var(--text-base);
    font-weight: var(--font-semibold);
    cursor: pointer;
    transition: all 0.2s ease;
    white-space: nowrap;

    &:hover:not(:disabled) {
      background: var(--primary-600);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(33, 150, 243, 0.3);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
    }

    &:disabled {
      background: var(--gray-300);
      cursor: not-allowed;
    }
  }
}
```

---

## 加载状态与动画

### 设计原则
- 提供清晰的加载反馈
- 使用微妙的动画，不干扰阅读
- 流式加载，逐步显示内容

### 1. 思考中动画
```
┌────────────────────────────────────────────────────────┐
│ AI正在思考中...                                        │
│ ● ● ●  (跳动动画)                                      │
└────────────────────────────────────────────────────────┘
```

```css
.thinking {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  color: var(--gray-500);
  font-size: var(--text-sm);

  .dots {
    display: flex;
    gap: 6px;

    span {
      width: 8px;
      height: 8px;
      background: var(--primary-500);
      border-radius: 50%;
      animation: bounce 1.4s infinite ease-in-out;

      &:nth-child(1) { animation-delay: -0.32s; }
      &:nth-child(2) { animation-delay: -0.16s; }
    }
  }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}
```

### 2. 流式文本加载
```css
.streaming-text {
  /* 打字机效果 */
  .cursor {
    display: inline-block;
    width: 2px;
    height: 1em;
    background: var(--primary-500);
    margin-left: 2px;
    animation: blink 1s infinite;
  }
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
```

### 3. 卡片进入动画
```css
.subtask-card {
  animation: fadeInUp 0.4s ease-out;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

---

## 错误状态

### 设计原则
- 清晰的错误提示
- 提供可能的解决方案
- 支持重试操作

### 视觉设计
```
┌────────────────────────────────────────────────────────┐
│ ⚠️ 查询执行失败                                        │
├────────────────────────────────────────────────────────┤
│                                                        │
│ 错误信息：                                             │
│ VizQL Data Service返回错误：字段"销售额"不存在        │
│                                                        │
│ 可能的原因：                                           │
│ • 字段名称拼写错误                                     │
│ • 数据源结构已变更                                     │
│                                                        │
│ [查看详情]  [重试]                                     │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 样式规范
```css
.error-card {
  padding: 20px;
  background: #fff5f5;
  border: 1px solid #ffcdd2;
  border-left: 4px solid var(--error);
  border-radius: 12px;

  .header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;

    .icon {
      font-size: 20px;
      color: var(--error);
    }

    .title {
      font-size: var(--text-lg);
      font-weight: var(--font-semibold);
      color: var(--error);
    }
  }

  .message {
    margin: 12px 0;
    padding: 12px;
    background: white;
    border-radius: 8px;
    font-size: var(--text-sm);
    color: var(--gray-700);
    font-family: var(--font-mono);
  }

  .suggestions {
    margin: 12px 0;

    .title {
      font-size: var(--text-sm);
      font-weight: var(--font-medium);
      color: var(--gray-700);
      margin-bottom: 8px;
    }

    ul {
      margin: 0;
      padding-left: 20px;

      li {
        margin: 4px 0;
        font-size: var(--text-sm);
        color: var(--gray-600);
      }
    }
  }

  .actions {
    display: flex;
    gap: 12px;
    margin-top: 16px;

    button {
      padding: 8px 16px;
      border-radius: 8px;
      font-size: var(--text-sm);
      font-weight: var(--font-medium);
      cursor: pointer;
      transition: all 0.2s ease;

      &.primary {
        background: var(--error);
        color: white;
        border: none;

        &:hover {
          background: #d32f2f;
        }
      }

      &.secondary {
        background: white;
        color: var(--error);
        border: 1px solid var(--error);

        &:hover {
          background: #fff5f5;
        }
      }
    }
  }
}
```

---

## 响应式设计

### 断点定义
```css
/* 移动端 */
@media (max-width: 768px) {
  .ai-message .container {
    max-width: 100%;
  }

  .subtask-card {
    padding: 16px;
  }

  .data-table {
    font-size: 12px;

    th, td {
      padding: 8px 12px;
    }
  }

  .input-area {
    padding: 12px 16px;

    .send-btn {
      padding: 12px 16px;
    }
  }

  /* 时间线垂直显示 */
  .timeline {
    flex-direction: column;
    align-items: flex-start;

    .step::after {
      content: '↓';
      right: auto;
      top: auto;
      bottom: -18px;
      left: 18px;
    }
  }
}

/* 平板 */
@media (min-width: 769px) and (max-width: 1024px) {
  .ai-message .container {
    max-width: 90%;
  }
}

/* 桌面 */
@media (min-width: 1025px) {
  .ai-message .container {
    max-width: 1200px;
  }
}
```

---

## 暗色模式 (可选)

### 配色方案
```css
[data-theme="dark"] {
  /* 背景色 */
  --bg-primary: #1a1a1a;
  --bg-secondary: #2d2d2d;
  --bg-tertiary: #3a3a3a;

  /* 文本色 */
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0a0;
  --text-tertiary: #707070;

  /* 边框色 */
  --border-primary: #3a3a3a;
  --border-secondary: #4a4a4a;

  /* 主色调整 */
  --primary-500: #42a5f5;

  /* 用户消息 */
  --user-bg: #1976d2;

  /* AI消息 */
  --ai-bg: #2d2d2d;
  --ai-border: #3a3a3a;

  /* 卡片 */
  .subtask-card {
    background: var(--bg-secondary);
    border-color: var(--border-primary);
  }

  /* 表格 */
  .data-table {
    thead {
      background: var(--bg-tertiary);
    }

    tbody tr {
      &:nth-child(even) {
        background: var(--bg-tertiary);
      }

      &:hover {
        background: rgba(66, 165, 245, 0.1);
      }
    }
  }
}
```

---

## 交互细节

### 1. 悬浮提示 (Tooltip)
```css
.tooltip {
  position: relative;

  &::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    padding: 6px 12px;
    background: rgba(0, 0, 0, 0.9);
    color: white;
    font-size: var(--text-xs);
    border-radius: 6px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s ease;
  }

  &:hover::after {
    opacity: 1;
  }
}
```

### 2. 复制反馈
```javascript
// 复制成功后的视觉反馈
function copyToClipboard(text) {
  navigator.clipboard.writeText(text)

  // 显示Toast提示
  showToast('已复制到剪贴板', 'success')

  // 按钮状态变化
  button.classList.add('copied')
  button.textContent = '已复制'

  setTimeout(() => {
    button.classList.remove('copied')
    button.textContent = '复制'
  }, 2000)
}
```

### 3. 平滑滚动
```javascript
// 新消息出现时自动滚动到底部
function scrollToBottom() {
  const container = document.querySelector('.messages-container')
  container.scrollTo({
    top: container.scrollHeight,
    behavior: 'smooth'
  })
}
```

---

## 可访问性 (Accessibility)

### ARIA标签
```html
<!-- 输入框 -->
<textarea
  aria-label="输入您的问题"
  aria-describedby="input-hint"
  role="textbox"
/>

<!-- 发送按钮 -->
<button
  aria-label="发送消息"
  :aria-disabled="!canSend"
/>

<!-- 折叠区域 -->
<button
  aria-expanded="false"
  aria-controls="content-1"
  @click="toggle"
/>

<!-- 表格 -->
<table role="table" aria-label="查询结果数据表">
  <thead role="rowgroup">
    <tr role="row">
      <th role="columnheader" aria-sort="ascending">门店名称</th>
    </tr>
  </thead>
</table>
```

### 键盘导航
```javascript
// 支持Tab键导航
// 支持Enter发送，Shift+Enter换行
// 支持Esc关闭折叠区域
// 支持方向键在表格中导航
```

---

## 性能优化

### 1. 虚拟滚动 (大数据表格)
```javascript
// 使用虚拟滚动优化大数据集渲染
import { useVirtualList } from '@vueuse/core'

const { list, containerProps, wrapperProps } = useVirtualList(
  dataRows,
  { itemHeight: 48 }
)
```

### 2. 懒加载图片
```html
<img
  :src="placeholder"
  :data-src="actualImage"
  loading="lazy"
  @load="onImageLoad"
/>
```

### 3. 防抖输入
```javascript
// 输入框防抖，减少不必要的渲染
import { useDebounceFn } from '@vueuse/core'

const debouncedInput = useDebounceFn((value) => {
  // 处理输入
}, 300)
```

---

## 组件库选择建议

### 推荐方案：Element Plus
**理由：**
- Vue 3原生支持，TypeScript友好
- 组件丰富，文档完善
- 中文社区活跃
- 可定制性强

**需要的组件：**
- `el-button` - 按钮
- `el-input` - 输入框
- `el-table` - 表格
- `el-collapse` - 折叠面板
- `el-pagination` - 分页
- `el-tooltip` - 提示
- `el-message` - 消息提示

### 备选方案：Ant Design Vue
**理由：**
- 设计规范成熟
- 企业级UI组件
- 国际化支持好

### 自定义组件
对于特殊需求（如时间线、子任务卡片），建议自己实现，保持设计一致性。

---

## 实现优先级

### P0 (核心功能，必须实现)
1. ✅ 用户消息气泡
2. ✅ AI消息容器
3. ✅ 子任务卡片
4. ✅ 数据表格
5. ✅ 输入区域
6. ✅ 加载状态

### P1 (重要功能，尽快实现)
1. ✅ 分析流程时间线
2. ✅ 可折叠区域
3. ✅ 代码块 (VizQL)
4. ✅ 最终总结
5. ✅ 错误状态

### P2 (增强功能，后续优化)
1. ⭕ 暗色模式
2. ⭕ 虚拟滚动
3. ⭕ 复制功能
4. ⭕ 导出功能
5. ⭕ 分享功能

---

## 设计交付物

### 1. Figma设计稿 (推荐)
- 完整的页面设计
- 组件库
- 交互原型
- 设计规范文档

### 2. 代码实现
- Vue 3组件
- CSS样式文件
- TypeScript类型定义
- Storybook组件文档

### 3. 设计系统文档
- 配色方案
- 字体规范
- 间距规范
- 组件使用指南

---

## 总结

这套UI设计方案的核心特点：

1. **简洁专业** - 白色卡片 + 细边框，类似文档/报告的专业感
2. **信息分层** - 时间线 → 子任务 → 总结，逐层深入
3. **渐进展示** - 默认显示核心信息，细节可折叠
4. **流畅体验** - 流式加载，实时反馈，平滑动画
5. **数据优先** - 表格、图表等数据展示是焦点
6. **现代化** - 参考ChatGPT、Claude等主流AI产品

**与React版本的区别：**
- ❌ 不使用花哨的渐变背景
- ❌ 不使用过多的阴影和装饰
- ❌ 不使用复杂的布局
- ✅ 使用简洁的白色卡片
- ✅ 使用清晰的视觉层次
- ✅ 使用舒适的间距和圆角
- ✅ 使用专业的配色方案

这套设计既保持了现代AI产品的简洁美感，又突出了数据分析场景的专业性和可信度。
