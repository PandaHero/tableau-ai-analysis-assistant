# VizQL多智能体分析系统 - UI设计规范

**版本**: v3.0 - 极简重构版
**最后更新**: 2025-10-30
**适用范围**: Tableau Extension插件

---

## 设计理念

### 核心原则

1. **极简主义** - 默认只显示核心信息，细节按需展开（参考Perplexity）
2. **信息密度优化** - 压缩垂直空间，提高信息密度，减少滚动
3. **清晰的层次结构** - 用视觉层次清晰区分：流程 → 任务 → 结果
4. **关系可视化** - 用流程图和连接线直观展示任务间的关系
5. **渐进式展开** - 从摘要到详情，用户控制信息展示深度

### 设计参考

| 产品 | 借鉴点 |
|------|--------|
| **Perplexity** | 折叠式信息架构、来源引用、思考过程展示 |
| **Claude** | 极简的消息设计、优雅的排版、舒适的阅读体验 |
| **ChatGPT** | 简洁的对话流、清晰的消息分隔 |
| **Linear** | 紧凑的卡片设计、清晰的状态标识 |
| **Notion** | 可折叠的内容块、灵活的展开/收起 |

### 关键优化策略

1. **默认折叠** - 所有详细内容默认折叠，只显示摘要
2. **紧凑布局** - 减少padding、margin，提高空间利用率
3. **流程图优先** - 用可视化流程图替代冗长的文字描述
4. **智能分组** - 按Stage分组，清晰展示并行/串行关系
5. **一键展开** - 提供"展开全部"按钮，方便深入查看

---

## 整体布局 - 极简重构版

### 设计目标

1. **压缩高度70%** - 默认视图高度从~2000px压缩到~600px
2. **清晰关系** - 用流程图直观展示任务依赖和执行顺序
3. **快速扫描** - 用户3秒内理解分析过程和结论
4. **按需深入** - 点击展开查看详细数据和洞察

### 页面结构（极简版）

```
┌─────────────────────────────────────────────────────────────┐
│  Header (固定顶部，高度48px)                                 │
│  [Logo] Tableau AI分析师                          [⚙️]      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  对话区域 (可滚动，紧凑布局)                                 │
│                                                              │
│  ┌──────────────────────────────────────────────────┐      │
│  │ 👤 2024年vs 2023年各地区的销售额对比             │      │
│  └──────────────────────────────────────────────────┘      │
│                                                              │
│  ┌──────────────────────────────────────────────────┐      │
│  │ 🤖 AI分析结果 (默认折叠，高度~500px)             │      │
│  │                                                   │      │
│  │ ⏱️ 18.5s · 3个查询 · 2轮分析                     │      │
│  │                                                   │      │
│  │ ┌─ 执行流程 ────────────────────────────────┐   │      │
│  │ │ 理解→规划→[Q1,Q2]→合并→洞察→总结          │   │      │
│  │ │ 1.5s 2s  ↓ 6s ↓  1.5s 2s  1.5s          │   │      │
│  │ └────────────────────────────────────────────┘   │      │
│  │                                                   │      │
│  │ 💡 **核心结论**                                   │      │
│  │ 2024年销售额850万，同比增长18.1%。华东地区...   │      │
│  │                                                   │      │
│  │ 📊 **关键数据** [展开3个查询 ▼]                  │      │
│  │ • Q1: 2024年销售额 850万 (3.0s)                 │      │
│  │ • Q2: 2023年销售额 720万 (3.0s)                 │      │
│  │ • Q3: 同比增长分析 +18.1% (3.5s)                │      │
│  │                                                   │      │
│  │ 🎯 **业务洞察** [展开 ▼]                         │      │
│  │ • 华东地区增长最快 (+22.5%)                      │      │
│  │ • 西北地区需关注 (+5.2%)                         │      │
│  │                                                   │      │
│  │ [查看完整分析报告 →]                             │      │
│  └──────────────────────────────────────────────────┘      │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  输入区域 (固定底部，高度72px)                               │
│  [✨] [输入框...]                                   [发送]  │
└─────────────────────────────────────────────────────────────┘
```

### 关键优化点

| 优化项 | 优化前 | 优化后 | 效果 |
|--------|--------|--------|------|
| **默认高度** | ~2000px | ~500px | ↓75% |
| **信息层级** | 平铺展示 | 3层折叠 | 更清晰 |
| **流程展示** | 文字描述 | 可视化流程图 | 更直观 |
| **任务关系** | 不明显 | 流程图+分组 | 更清晰 |
| **数据展示** | 默认展开 | 默认折叠 | 更紧凑 |

### 信息层级设计

```
第1层（默认显示，~500px）
├─ 执行流程图（紧凑横向布局）
├─ 核心结论（1-2句话）
├─ 关键数据（折叠列表）
└─ 业务洞察（折叠列表）

第2层（点击"展开3个查询"）
├─ Q1: 查询卡片（折叠状态）
├─ Q2: 查询卡片（折叠状态）
└─ Q3: 查询卡片（折叠状态）

第3层（点击单个查询卡片）
├─ 查询详情
├─ 数据表格/图表
├─ 统计分析
└─ 业务洞察
```



---

## 详细组件设计

### 1. 顶部Header（极简设计）

**设计原则**：
- 固定高度48px，最小化占用空间
- 数据源选择放在设置面板
- 有对话时只显示Logo和设置按钮

**视觉设计**：
```
┌─────────────────────────────────────────────────────────┐
│  [Logo] Tableau AI分析师                      [⚙️]      │
└─────────────────────────────────────────────────────────┘
```

**样式规范**：
```css
.header {
  position: sticky;
  top: 0;
  height: 48px;
  background: white;
  border-bottom: 1px solid #E5E7EB;
  padding: 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 100;

  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;

    .logo {
      width: 24px;
      height: 24px;
    }

    .title {
      font-size: 15px;
      font-weight: 600;
      color: #111827;
    }
  }

  .header-right {
    .settings-btn {
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      border: none;
      background: transparent;
      border-radius: 6px;
      cursor: pointer;
      color: #6B7280;
      transition: all 0.15s ease;

      &:hover {
        background: #F3F4F6;
        color: #111827;
      }
    }
  }
}
```

---

### 2. 执行流程图（紧凑可视化）

**设计原则**：
- 极简横向流程图，高度仅60px
- 清晰展示并行/串行关系
- 悬浮显示详细信息
- 可点击跳转到对应任务

**视觉设计（紧凑版）**：
```
┌─ 执行流程 ──────────────────────────────────────────┐
│ 理解 → 规划 → [Q1,Q2] → 合并 → 洞察 → 总结          │
│ 1.5s  2.0s   ↓ 6.0s↓  1.5s  2.0s  1.5s           │
└──────────────────────────────────────────────────────┘
```

**交互说明**：
- 悬浮节点显示详细信息（Agent名称、输入输出、状态）
- 点击节点滚动到对应的详细内容
- 并行任务用`[Q1,Q2]`表示，悬浮显示依赖关系

**样式规范**：
```css
.execution-flow {
  padding: 12px 16px;
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  margin-bottom: 12px;

  .flow-title {
    font-size: 12px;
    font-weight: 600;
    color: #6B7280;
    margin-bottom: 8px;
  }

  .flow-diagram {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    line-height: 1.4;

    .node {
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
      padding: 6px 10px;
      background: white;
      border: 1.5px solid #E5E7EB;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;

      .node-name {
        font-weight: 500;
        color: #111827;
      }

      .node-time {
        font-size: 11px;
        color: #9CA3AF;
      }

      &:hover {
        border-color: #3B82F6;
        background: #EFF6FF;
        transform: translateY(-1px);
      }

      &.completed {
        border-color: #10B981;
        background: #ECFDF5;

        .node-name {
          color: #059669;
        }
      }

      &.running {
        border-color: #3B82F6;
        background: #EFF6FF;
        animation: pulse 1.5s ease-in-out infinite;

        .node-name {
          color: #2563EB;
        }
      }

      /* 并行任务组 */
      &.parallel-group {
        padding: 4px 8px;
        background: #FEF3C7;
        border-color: #FCD34D;

        .node-name {
          font-size: 12px;
          color: #92400E;
        }
      }
    }

    .arrow {
      color: #D1D5DB;
      font-size: 14px;
    }

    /* 并行箭头（向下） */
    .parallel-arrow {
      display: flex;
      flex-direction: column;
      align-items: center;
      color: #FCD34D;
      font-size: 12px;
      line-height: 1;
    }
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}
```

---

### 3. AI消息卡片（极简重构）

**设计原则**：
- 默认只显示核心信息（流程图+结论+摘要）
- 所有详细内容默认折叠
- 紧凑布局，减少垂直空间
- 清晰的视觉层次

**视觉设计（默认折叠状态）**：
```
┌─ AI分析结果 ────────────────────────────────────────┐
│ ⏱️ 18.5s · 3个查询 · 2轮分析                        │
│                                                      │
│ ┌─ 执行流程 ────────────────────────────────────┐  │
│ │ 理解→规划→[Q1,Q2]→合并→洞察→总结              │  │
│ │ 1.5s 2s  ↓ 6s ↓  1.5s 2s  1.5s              │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ 💡 **核心结论**                                      │
│ 2024年销售额850万，同比增长18.1%。华东地区...      │
│                                                      │
│ 📊 **关键数据** [展开3个查询 ▼]                     │
│ • Q1: 2024年销售额 850万 (3.0s)                    │
│ • Q2: 2023年销售额 720万 (3.0s)                    │
│ • Q3: 同比增长分析 +18.1% (3.5s)                   │
│                                                      │
│ 🎯 **业务洞察** [展开 ▼]                            │
│ • 华东地区增长最快 (+22.5%)                         │
│ • 西北地区需关注 (+5.2%)                            │
│                                                      │
│ [查看完整分析报告 →]                                │
└──────────────────────────────────────────────────────┘
```

**样式规范**：
```css
.ai-message {
  max-width: 90%;
  margin: 16px 0;
  padding: 16px;
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

  /* 顶部元信息 */
  .meta-info {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 12px;
    margin-bottom: 12px;
    border-bottom: 1px solid #F3F4F6;
    font-size: 13px;
    color: #6B7280;

    .meta-item {
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .separator {
      color: #D1D5DB;
    }
  }

  /* 核心结论 */
  .core-conclusion {
    margin: 12px 0;

    .conclusion-title {
      font-size: 13px;
      font-weight: 600;
      color: #111827;
      margin-bottom: 6px;
    }

    .conclusion-text {
      font-size: 14px;
      line-height: 1.6;
      color: #374151;
    }
  }

  /* 折叠区域 */
  .collapsible-section {
    margin: 12px 0;
    border-top: 1px solid #F3F4F6;
    padding-top: 12px;

    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 0;
      cursor: pointer;
      user-select: none;

      .section-title {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        font-weight: 600;
        color: #111827;
      }

      .toggle-icon {
        color: #9CA3AF;
        font-size: 14px;
        transition: transform 0.2s ease;

        &.expanded {
          transform: rotate(180deg);
        }
      }

      &:hover {
        .section-title {
          color: #3B82F6;
        }
      }
    }

    .section-content {
      padding: 8px 0;
      font-size: 13px;
      line-height: 1.6;
      color: #6B7280;

      /* 列表样式 */
      ul {
        margin: 0;
        padding-left: 20px;

        li {
          margin: 4px 0;
          padding-left: 4px;

          &::marker {
            color: #9CA3AF;
          }
        }
      }

      /* 查询摘要项 */
      .query-summary-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 6px 0;
        cursor: pointer;
        transition: all 0.15s ease;

        &:hover {
          color: #3B82F6;
          padding-left: 4px;
        }

        .query-info {
          display: flex;
          align-items: center;
          gap: 8px;

          .query-id {
            font-weight: 600;
            color: #111827;
          }
        }

        .query-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          color: #9CA3AF;
        }
      }
    }
  }

  /* 查看完整报告按钮 */
  .view-full-report {
    margin-top: 12px;
    padding: 8px 16px;
    width: 100%;
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    color: #374151;
    cursor: pointer;
    transition: all 0.15s ease;

    &:hover {
      background: #F3F4F6;
      border-color: #D1D5DB;
    }
  }
}
```

---

### 4. 查询详情卡片（紧凑折叠设计）

**设计原则**：
- 默认折叠状态，只显示摘要（高度~60px）
- 点击展开查看完整内容
- 支持表格/图表快速切换
- 清晰展示任务依赖关系

**视觉设计（折叠状态）**：
```
┌─ Q1: 2024年销售额 ──────────────────────────────────┐
│ ⏱️ 3.0s · Stage 1 · 850万                    [▼展开] │
└──────────────────────────────────────────────────────┘
```

**视觉设计（展开状态）**：
```
┌─ Q1: 2024年销售额 ──────────────────────────────────┐
│ ⏱️ 3.0s · Stage 1 · 850万                    [▲收起] │
│ ──────────────────────────────────────────────────── │
│                                                       │
│ 💭 **分析目的**                                       │
│ 获取2024年（当期）的销售数据，作为同比分析的基础     │
│                                                       │
│ 📊 **数据** [表格] [柱状图] [折线图]                 │
│ ┌───────────────────────────────────────────────┐   │
│ │ [数据表格或图表]                              │   │
│ └───────────────────────────────────────────────┘   │
│                                                       │
│ 💡 **关键发现**                                       │
│ • 华东地区销售额最高，达到280万                      │
│ • 一线城市占比65%                                     │
│                                                       │
│ [查看VizQL查询 ▼] [查看规则说明 ▼]                  │
└───────────────────────────────────────────────────────┘
```

**样式规范**：
```css
.query-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  margin: 8px 0;
  overflow: hidden;
  transition: all 0.2s ease;

  /* 折叠状态 */
  &.collapsed {
    .card-header {
      padding: 12px 16px;
      cursor: pointer;

      &:hover {
        background: #F9FAFB;
      }
    }

    .card-body {
      display: none;
    }
  }

  /* 展开状态 */
  &.expanded {
    border-color: #3B82F6;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);

    .card-header {
      padding: 12px 16px;
      border-bottom: 1px solid #F3F4F6;
      cursor: pointer;
    }

    .card-body {
      display: block;
      padding: 16px;
    }
  }

  /* 卡片头部 */
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: background 0.15s ease;

    .header-left {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;

      .query-title {
        font-size: 14px;
        font-weight: 600;
        color: #111827;
      }

      .query-meta {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 12px;
        color: #6B7280;

        .meta-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .separator {
          color: #D1D5DB;
        }

        /* 结果摘要 */
        .result-summary {
          font-weight: 600;
          color: #3B82F6;
        }
      }
    }

    .header-right {
      .toggle-btn {
        padding: 4px 12px;
        background: transparent;
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        font-size: 12px;
        color: #6B7280;
        cursor: pointer;
        transition: all 0.15s ease;

        &:hover {
          background: #F3F4F6;
          border-color: #D1D5DB;
        }
      }
    }
  }

  /* 卡片主体 */
  .card-body {
    .section {
      margin-bottom: 16px;

      &:last-child {
        margin-bottom: 0;
      }

      .section-title {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        font-weight: 600;
        color: #111827;
        margin-bottom: 8px;
      }

      .section-content {
        font-size: 13px;
        line-height: 1.6;
        color: #6B7280;
      }
    }

    /* 分析目的 */
    .purpose-section {
      padding: 10px 12px;
      background: #FFFBEB;
      border-left: 3px solid #F59E0B;
      border-radius: 6px;

      .section-content {
        color: #92400E;
      }
    }

    /* 数据展示区域 */
    .data-section {
      .view-tabs {
        display: flex;
        gap: 6px;
        margin-bottom: 10px;

        button {
          padding: 6px 12px;
          background: white;
          border: 1px solid #E5E7EB;
          border-radius: 6px;
          font-size: 12px;
          color: #6B7280;
          cursor: pointer;
          transition: all 0.15s ease;

          &:hover {
            background: #F9FAFB;
          }

          &.active {
            background: #3B82F6;
            color: white;
            border-color: #3B82F6;
          }
        }
      }

      .data-container {
        min-height: 200px;
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        overflow: hidden;
        background: #FAFAFA;

        /* 数据表格 */
        .data-table {
          width: 100%;
          background: white;
          font-size: 12px;

          thead {
            background: #F9FAFB;

            th {
              padding: 8px 12px;
              text-align: left;
              font-weight: 600;
              color: #6B7280;
              border-bottom: 1px solid #E5E7EB;
            }
          }

          tbody {
            tr {
              border-bottom: 1px solid #F3F4F6;

              &:hover {
                background: #F9FAFB;
              }

              td {
                padding: 8px 12px;
                color: #374151;
              }
            }
          }
        }

        /* 图表容器 */
        .chart-container {
          width: 100%;
          height: 250px;
          background: white;
        }
      }
    }

    /* 关键发现 */
    .findings-section {
      padding: 10px 12px;
      background: #F9FAFB;
      border-radius: 6px;

      ul {
        margin: 0;
        padding-left: 18px;

        li {
          margin: 4px 0;
          font-size: 13px;
          color: #374151;
        }
      }
    }

    /* 底部操作 */
    .card-actions {
      display: flex;
      gap: 8px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid #F3F4F6;

      button {
        padding: 6px 12px;
        background: transparent;
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        font-size: 12px;
        color: #6B7280;
        cursor: pointer;
        transition: all 0.15s ease;

        &:hover {
          background: #F9FAFB;
          border-color: #D1D5DB;
        }
      }
    }
  }
}
```

---

### 5. 输入区域（极简设计）

**设计原则**：
- 固定高度72px，最小化占用空间
- Boost按钮放在输入框左侧
- 简洁的视觉设计

**视觉设计**：
```
┌────────────────────────────────────────────────────────┐
│ [✨] [输入框...]                               [发送]  │
└────────────────────────────────────────────────────────┘
```

**样式规范**：
```css
.input-area {
  position: sticky;
  bottom: 0;
  height: 72px;
  background: white;
  border-top: 1px solid #E5E7EB;
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 -1px 3px rgba(0, 0, 0, 0.05);

  /* Boost按钮 */
  .boost-btn {
    flex-shrink: 0;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.15s ease;

    .icon {
      font-size: 20px;
      color: white;
    }

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
    }

    &:active {
      transform: translateY(0);
    }
  }

  /* 输入框 */
  .input-wrapper {
    flex: 1;
    position: relative;

    textarea {
      width: 100%;
      height: 48px;
      padding: 12px 16px;
      border: 1.5px solid #E5E7EB;
      border-radius: 10px;
      font-size: 15px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.5;
      resize: none;
      transition: all 0.15s ease;

      &:focus {
        outline: none;
        border-color: #3B82F6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
      }

      &::placeholder {
        color: #9CA3AF;
      }
    }
  }

  /* 发送按钮 */
  .send-btn {
    flex-shrink: 0;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #3B82F6;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.15s ease;

    .icon {
      font-size: 18px;
      color: white;
    }

    &:hover:not(:disabled) {
      background: #2563EB;
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
    }

    &:disabled {
      background: #D1D5DB;
      cursor: not-allowed;
    }
  }
}
```

---

### 6. Stage分组展示（清晰的任务关系）

**设计原则**：
- 用视觉分组清晰展示并行/串行关系
- 紧凑布局，减少垂直空间
- 可折叠的Stage组

**视觉设计**：
```
┌─ Stage 1: 并行查询 (6.0s) ──────────────────── [▼展开] ┐
│ Q1: 2024年销售额 (3.0s) · 850万                        │
│ Q2: 2023年销售额 (3.0s) · 720万                        │
└─────────────────────────────────────────────────────────┘

┌─ Stage 2: 数据合并 (3.5s) ──────────────────── [▼展开] ┐
│ Q3: 同比增长分析 (3.5s) · +18.1%                       │
│ 🔗 依赖: Q1 + Q2                                        │
└─────────────────────────────────────────────────────────┘
```

**样式规范**：
```css
.stage-group {
  margin: 12px 0;
  border: 1.5px solid #E5E7EB;
  border-radius: 8px;
  overflow: hidden;
  background: white;

  /* Stage头部 */
  .stage-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    background: #F9FAFB;
    border-bottom: 1px solid #E5E7EB;
    cursor: pointer;
    transition: background 0.15s ease;

    &:hover {
      background: #F3F4F6;
    }

    .stage-info {
      display: flex;
      align-items: center;
      gap: 10px;

      .stage-badge {
        padding: 4px 10px;
        background: #3B82F6;
        color: white;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
      }

      .stage-name {
        font-size: 14px;
        font-weight: 600;
        color: #111827;
      }

      .stage-time {
        font-size: 12px;
        color: #6B7280;
      }

      /* 并行标识 */
      .parallel-badge {
        padding: 3px 8px;
        background: #FEF3C7;
        color: #92400E;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
      }
    }

    .toggle-icon {
      color: #9CA3AF;
      transition: transform 0.2s ease;

      &.expanded {
        transform: rotate(180deg);
      }
    }
  }

  /* Stage内容 */
  .stage-body {
    padding: 12px;

    /* 查询卡片列表 */
    .query-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    /* 依赖关系提示 */
    .dependency-info {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      background: #FFF7ED;
      border-left: 3px solid #F59E0B;
      border-radius: 6px;
      margin-top: 8px;
      font-size: 12px;
      color: #92400E;

      .dependency-icon {
        color: #F59E0B;
      }

      .dependency-links {
        display: flex;
        gap: 6px;

        .query-link {
          color: #2563EB;
          text-decoration: underline;
          cursor: pointer;

          &:hover {
            color: #1D4ED8;
          }
        }
      }
    }
  }

  /* 折叠状态 */
  &.collapsed {
    .stage-body {
      display: none;
    }
  }
}
```

---

### 7. 用户消息（极简设计）

**视觉设计**：
```
┌──────────────────────────────────────────────────┐
│ 👤 2024年vs 2023年各地区的销售额对比             │
└──────────────────────────────────────────────────┘
```

**样式规范**：
```css
.user-message {
  max-width: 85%;
  margin: 12px 0 12px auto;
  padding: 12px 16px;
  background: #3B82F6;
  color: white;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.2);
}
```

---

## 配色方案（Tailwind风格）

```css
/* 主色调 - 蓝色系 */
--primary-50: #EFF6FF;
--primary-100: #DBEAFE;
--primary-200: #BFDBFE;
--primary-300: #93C5FD;
--primary-400: #60A5FA;
--primary-500: #3B82F6;  /* 主色 */
--primary-600: #2563EB;
--primary-700: #1D4ED8;

/* 中性色 - 灰色系 */
--gray-50: #F9FAFB;
--gray-100: #F3F4F6;
--gray-200: #E5E7EB;
--gray-300: #D1D5DB;
--gray-400: #9CA3AF;
--gray-500: #6B7280;
--gray-600: #4B5563;
--gray-700: #374151;
--gray-800: #1F2937;
--gray-900: #111827;

/* 功能色 */
--success-50: #ECFDF5;
--success-500: #10B981;
--success-600: #059669;

--warning-50: #FFFBEB;
--warning-500: #F59E0B;
--warning-600: #D97706;

--error-50: #FEF2F2;
--error-500: #EF4444;
--error-600: #DC2626;

/* 特殊用途 */
--boost-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
--stage-parallel-bg: #FEF3C7;
--stage-parallel-text: #92400E;
```

---

## 完整场景示例

### 场景: 同比分析（2024 vs 2023）

**用户问题**: "2024年vs 2023年各地区的销售额对比"

**默认视图（折叠状态，高度~500px）**：
```
┌─ AI分析结果 ────────────────────────────────────────┐
│ ⏱️ 18.5s · 3个查询 · 2轮分析                        │
│                                                      │
│ ┌─ 执行流程 ────────────────────────────────────┐  │
│ │ 理解→规划→[Q1,Q2]→合并→洞察→总结              │  │
│ │ 1.5s 2s  ↓ 6s ↓  1.5s 2s  1.5s              │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ 💡 **核心结论**                                      │
│ 2024年销售额850万，同比增长18.1%。华东地区增长      │
│ 最快(+22.5%)，西北地区需关注(+5.2%)。              │
│                                                      │
│ 📊 **关键数据** [展开3个查询 ▼]                     │
│ • Q1: 2024年销售额 850万 (3.0s)                    │
│ • Q2: 2023年销售额 720万 (3.0s)                    │
│ • Q3: 同比增长分析 +18.1% (3.5s)                   │
│                                                      │
│ 🎯 **业务洞察** [展开 ▼]                            │
│ • 华东地区增长最快，建议加大投入                    │
│ • 西北地区增长缓慢，需要分析原因                    │
│ • 一线城市表现突出，占总增长的70%                   │
│                                                      │
│ [查看完整分析报告 →]                                │
└──────────────────────────────────────────────────────┘
```

**展开"关键数据"后（高度~800px）**：
```
┌─ AI分析结果 ────────────────────────────────────────┐
│ ⏱️ 18.5s · 3个查询 · 2轮分析                        │
│                                                      │
│ [执行流程图...]                                      │
│                                                      │
│ 💡 **核心结论**                                      │
│ [结论文本...]                                        │
│                                                      │
│ 📊 **关键数据** [收起 ▲]                            │
│                                                      │
│ ┌─ Stage 1: 并行查询 (6.0s) ────────── [▼展开] ┐  │
│ │ Q1: 2024年销售额 (3.0s) · 850万                │  │
│ │ Q2: 2023年销售额 (3.0s) · 720万                │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ ┌─ Stage 2: 数据合并 (3.5s) ────────── [▼展开] ┐  │
│ │ Q3: 同比增长分析 (3.5s) · +18.1%               │  │
│ │ 🔗 依赖: Q1 + Q2                                │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ 🎯 **业务洞察** [展开 ▼]                            │
│ [洞察列表...]                                        │
│                                                      │
│ [查看完整分析报告 →]                                │
└──────────────────────────────────────────────────────┘
```

**展开单个查询后（高度~1100px）**：
```
┌─ Stage 1: 并行查询 (6.0s) ──────────────── [▲收起] ┐
│                                                      │
│ ┌─ Q1: 2024年销售额 ──────────────────── [▲收起] ┐ │
│ │ ⏱️ 3.0s · Stage 1 · 850万                       │ │
│ │ ──────────────────────────────────────────────  │ │
│ │                                                 │ │
│ │ 💭 **分析目的**                                 │ │
│ │ 获取2024年（当期）的销售数据                    │ │
│ │                                                 │ │
│ │ 📊 **数据** [表格] [柱状图] [折线图]           │ │
│ │ ┌─────────────────────────────────────────┐   │ │
│ │ │ [数据表格或图表]                        │   │ │
│ │ └─────────────────────────────────────────┘   │ │
│ │                                                 │ │
│ │ 💡 **关键发现**                                 │ │
│ │ • 华东地区销售额最高，达到280万                 │ │
│ │ • 一线城市占比65%                               │ │
│ │                                                 │ │
│ │ [查看VizQL查询 ▼] [查看规则说明 ▼]            │ │
│ └─────────────────────────────────────────────────┘ │
│                                                      │
│ ┌─ Q2: 2023年销售额 ──────────────────── [▼展开] ┐ │
│ │ ⏱️ 3.0s · Stage 1 · 720万                       │ │
│ └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 交互流程总结

### 信息展示层级

```
第1层（默认，~500px）
├─ 执行流程图（紧凑）
├─ 核心结论（1-2句话）
├─ 关键数据（折叠列表）
└─ 业务洞察（折叠列表）

第2层（展开"关键数据"，~800px）
├─ Stage 1分组（折叠）
│   ├─ Q1摘要
│   └─ Q2摘要
└─ Stage 2分组（折叠）
    └─ Q3摘要

第3层（展开单个查询，~1100px）
├─ 分析目的
├─ 数据表格/图表
├─ 关键发现
└─ VizQL查询（可选）
```

### 交互行为

1. **点击流程图节点** → 滚动到对应的查询卡片并高亮
2. **点击"展开X个查询"** → 展开Stage分组列表
3. **点击Stage分组** → 展开该Stage内的所有查询摘要
4. **点击查询摘要** → 展开查询详情（数据+洞察）
5. **点击依赖链接** → 高亮显示被依赖的查询
6. **悬浮流程图节点** → 显示详细信息（输入输出、状态）

---

## 响应式设计

### 窄屏适配（< 768px）

- 流程图改为垂直布局
- 查询卡片宽度100%
- Stage分组默认展开
- 减少padding和margin

### 宽屏优化（> 1200px）

- 并行查询可以横向排列
- 增加最大宽度限制（1200px）
- 优化表格和图表的显示

---

**文档版本**: v3.0 - 极简重构版
**最后更新**: 2025-10-30
**更新内容**:
- 全面重构UI设计，采用极简主义
- 默认高度从~2000px压缩到~500px（↓75%）
- 引入3层信息架构，渐进式展开
- 优化流程图，清晰展示任务关系
- 紧凑的卡片设计，提高信息密度
- 参考Perplexity、Claude、Linear等产品的设计理念
