# 渐进式洞察系统详细设计

## 概述

渐进式洞察系统是DeepAgent的核心创新功能，用于处理大规模数据集的智能分析。系统通过智能分块、增量分析、早停机制，在保证洞察质量的同时显著降低成本和延迟。

**设计目标**：
- ✅ **智能分块** - 基于数据特征的语义分块，而非简单的行数分块
- ✅ **增量分析** - 逐块分析并累积洞察，支持早停
- ✅ **质量保证** - 去重、过滤、合并，确保洞察质量
- ✅ **成本优化** - 通过早停和智能采样降低LLM调用成本

---

## 1. 系统架构

### 1.1 四层架构

```
┌─────────────────────────────────────────────────────────┐
│                    准备层 (Preparation)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Coordinator  │  │DataProfiler  │  │SemanticChunk │  │
│  │  决策器      │  │  数据画像    │  │  智能分块    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    分析层 (Analysis)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ChunkAnalyzer │  │PatternDetect │  │AnomalyDetect │  │
│  │  块分析器    │  │  模式检测    │  │  异常检测    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    累积层 (Accumulation)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │InsightAccum  │  │QualityFilter │  │ DedupMerger  │  │
│  │  洞察累积    │  │  质量过滤    │  │  去重合并    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    合成层 (Synthesis)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │InsightSynth  │  │SummaryGen    │  │RecommendGen  │  │
│  │  洞察合成    │  │  摘要生成    │  │  建议生成    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 1.2 组件职责

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **Coordinator** | 决定分析策略 | 数据规模、复杂度 | 分析策略（直接/渐进式） |
| **DataProfiler** | 生成数据画像 | 原始数据 | 数据分布、异常值位置 |
| **SemanticChunker** | 智能分块 | 数据画像 | 数据块列表（优先级排序） |
| **ChunkAnalyzer** | 分析单个块 | 数据块 | 块级洞察 |
| **PatternDetector** | 检测模式 | 数据块 | 模式列表 |
| **AnomalyDetector** | 检测异常 | 数据块 | 异常列表 |
| **InsightAccumulator** | 累积洞察 | 块级洞察 | 累积洞察 + 早停决策 |
| **QualityFilter** | 过滤低质量 | 洞察列表 | 高质量洞察 |
| **DedupMerger** | 去重合并 | 洞察列表 | 去重后洞察 |
| **InsightSynthesizer** | 合成最终洞察 | 累积洞察 | 最终洞察 |
| **SummaryGenerator** | 生成摘要 | 最终洞察 | 执行摘要 |
| **RecommendGenerator** | 生成建议 | 最终洞察 | 行动建议 |

---

## 2. 核心组件设计

### 2.1 Coordinator（决策器）

**职责**：根据数据规模和复杂度决定使用直接分析还是渐进式分析。

**决策逻辑**：

```python
class ProgressiveInsightCoordinator:
    """渐进式洞察协调器"""
    
    # 阈值配置
    DIRECT_ANALYSIS_THRESHOLD = 100  # 小于100行直接分析
    PROGRESSIVE_ANALYSIS_THRESHOLD = 100  # 大于100行渐进式分析
    
    def decide_strategy(
        self,
        data_size: int,
        complexity: str,
        available_budget: float
    ) -> str:
        """
        决定分析策略
        
        Args:
            data_size: 数据行数
            complexity: 复杂度 (simple/medium/complex)
            available_budget: 可用预算（Token数）
        
        Returns:
            "direct" 或 "progressive"
        """
        # 规则1：小数据集直接分析
        if data_size <= self.DIRECT_ANALYSIS_THRESHOLD:
            return "direct"
        
        # 规则2：大数据集渐进式分析
        if data_size > self.PROGRESSIVE_ANALYSIS_THRESHOLD:
            return "progressive"
        
        # 规则3：根据复杂度和预算决定
        estimated_tokens = self._estimate_tokens(data_size, complexity)
        if estimated_tokens > available_budget:
            return "progressive"
        
        return "direct"
    
    def _estimate_tokens(self, data_size: int, complexity: str) -> int:
        """估算所需Token数"""
        base_tokens = data_size * 10  # 每行约10个token
        
        complexity_multiplier = {
            "simple": 1.0,
            "medium": 1.5,
            "complex": 2.0
        }
        
        return int(base_tokens * complexity_multiplier.get(complexity, 1.0))
```

**决策流程图**：

```
数据集
  ↓
检查数据规模
  ├─ ≤ 100行 → 直接分析
  ├─ > 100行 → 检查复杂度
  │            ├─ 简单 → 直接分析
  │            ├─ 中等 → 检查预算
  │            │         ├─ 充足 → 直接分析
  │            │         └─ 不足 → 渐进式分析
  │            └─ 复杂 → 渐进式分析
  └─ 返回策略
```

---

### 2.2 DataProfiler（数据画像生成器）

**职责**：快速扫描数据，生成数据画像，为智能分块提供依据。

**数据画像内容**：

```python
from pydantic import BaseModel
from typing import List, Dict, Optional

class DataProfile(BaseModel):
    """数据画像"""
    
    # 基本统计
    total_rows: int
    total_columns: int
    
    # 数值字段分布
    numeric_distributions: Dict[str, Dict]
    # {
    #   "Sales Amount": {
    #     "min": 100,
    #     "max": 10000,
    #     "mean": 2500,
    #     "median": 2000,
    #     "std": 1500,
    #     "quartiles": [1000, 2000, 3500]
    #   }
    # }
    
    # 异常值位置
    anomaly_positions: List[Dict]
    # [
    #   {"row_index": 5, "field": "Sales Amount", "value": 50000, "z_score": 3.5},
    #   {"row_index": 23, "field": "Quantity", "value": -10, "z_score": -2.8}
    # ]
    
    # 分类字段分布
    categorical_distributions: Dict[str, Dict]
    # {
    #   "Region": {
    #     "unique_count": 4,
    #     "top_values": [("华东", 150), ("华北", 120), ...]
    #   }
    # }
    
    # 数据质量
    data_quality: Dict[str, float]
    # {
    #   "completeness": 0.95,  # 完整性
    #   "consistency": 0.90,   # 一致性
    #   "validity": 0.98       # 有效性
    # }
    
    # 推荐分块策略
    recommended_chunk_strategy: str  # "anomaly_first" / "top_first" / "random"
```

**实现**：

```python
import pandas as pd
import numpy as np
from scipy import stats

class DataProfiler:
    """数据画像生成器"""
    
    def generate_profile(self, df: pd.DataFrame) -> DataProfile:
        """生成数据画像"""
        
        # 1. 基本统计
        total_rows = len(df)
        total_columns = len(df.columns)
        
        # 2. 数值字段分布
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        numeric_distributions = {}
        
        for col in numeric_cols:
            numeric_distributions[col] = {
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": float(df[col].mean()),
                "median": float(df[col].median()),
                "std": float(df[col].std()),
                "quartiles": df[col].quantile([0.25, 0.5, 0.75]).tolist()
            }
        
        # 3. 检测异常值（Z-score方法）
        anomaly_positions = self._detect_anomalies(df, numeric_cols)
        
        # 4. 分类字段分布
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        categorical_distributions = {}
        
        for col in categorical_cols:
            value_counts = df[col].value_counts()
            categorical_distributions[col] = {
                "unique_count": len(value_counts),
                "top_values": list(value_counts.head(10).items())
            }
        
        # 5. 数据质量评估
        data_quality = {
            "completeness": 1 - df.isnull().sum().sum() / (total_rows * total_columns),
            "consistency": self._check_consistency(df),
            "validity": self._check_validity(df)
        }
        
        # 6. 推荐分块策略
        recommended_strategy = self._recommend_chunk_strategy(
            anomaly_positions, total_rows
        )
        
        return DataProfile(
            total_rows=total_rows,
            total_columns=total_columns,
            numeric_distributions=numeric_distributions,
            anomaly_positions=anomaly_positions,
            categorical_distributions=categorical_distributions,
            data_quality=data_quality,
            recommended_chunk_strategy=recommended_strategy
        )
    
    def _detect_anomalies(
        self,
        df: pd.DataFrame,
        numeric_cols: List[str],
        threshold: float = 3.0
    ) -> List[Dict]:
        """检测异常值（Z-score > threshold）"""
        anomalies = []
        
        for col in numeric_cols:
            z_scores = np.abs(stats.zscore(df[col].dropna()))
            anomaly_indices = np.where(z_scores > threshold)[0]
            
            for idx in anomaly_indices:
                anomalies.append({
                    "row_index": int(idx),
                    "field": col,
                    "value": float(df[col].iloc[idx]),
                    "z_score": float(z_scores[idx])
                })
        
        # 按Z-score降序排序
        anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        
        return anomalies
    
    def _check_consistency(self, df: pd.DataFrame) -> float:
        """检查数据一致性"""
        # 简化实现：检查是否有重复行
        duplicate_ratio = df.duplicated().sum() / len(df)
        return 1.0 - duplicate_ratio
    
    def _check_validity(self, df: pd.DataFrame) -> float:
        """检查数据有效性"""
        # 简化实现：检查数值字段是否有负值（如果不应该有）
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        invalid_count = 0
        
        for col in numeric_cols:
            if (df[col] < 0).any():
                invalid_count += (df[col] < 0).sum()
        
        total_numeric_values = len(df) * len(numeric_cols)
        return 1.0 - (invalid_count / total_numeric_values) if total_numeric_values > 0 else 1.0
    
    def _recommend_chunk_strategy(
        self,
        anomaly_positions: List[Dict],
        total_rows: int
    ) -> str:
        """推荐分块策略"""
        anomaly_ratio = len(anomaly_positions) / total_rows
        
        if anomaly_ratio > 0.1:  # 异常值超过10%
            return "anomaly_first"
        elif anomaly_ratio > 0.01:  # 异常值1-10%
            return "mixed"
        else:
            return "top_first"
```

---

### 2.3 SemanticChunker（智能分块器）

**职责**：根据数据画像进行智能分块，而非简单的行数分块。

**分块策略**：

1. **异常值优先（anomaly_first）**：
   - 第1块：Top异常值（最重要）
   - 第2块：高值区间
   - 第3块：中值区间
   - 第4块：低值区间

2. **Top优先（top_first）**：
   - 第1块：Top N行（按主要度量排序）
   - 第2块：中间行
   - 第3块：尾部行

3. **混合策略（mixed）**：
   - 第1块：异常值 + Top值
   - 第2块：中间代表性样本
   - 第3块：尾部样本

**实现**：

```python
from typing import List
import pandas as pd

class DataChunk(BaseModel):
    """数据块"""
    chunk_id: int
    priority: int  # 优先级（1最高）
    row_indices: List[int]
    description: str
    estimated_importance: float

class SemanticChunker:
    """智能分块器"""
    
    def __init__(self, chunk_size: int = 100):
        self.chunk_size = chunk_size
    
    def chunk_data(
        self,
        df: pd.DataFrame,
        profile: DataProfile
    ) -> List[DataChunk]:
        """智能分块"""
        
        strategy = profile.recommended_chunk_strategy
        
        if strategy == "anomaly_first":
            return self._chunk_anomaly_first(df, profile)
        elif strategy == "top_first":
            return self._chunk_top_first(df, profile)
        else:  # mixed
            return self._chunk_mixed(df, profile)
    
    def _chunk_anomaly_first(
        self,
        df: pd.DataFrame,
        profile: DataProfile
    ) -> List[DataChunk]:
        """异常值优先分块"""
        chunks = []
        
        # 第1块：Top异常值
        anomaly_indices = [a["row_index"] for a in profile.anomaly_positions[:self.chunk_size]]
        if anomaly_indices:
            chunks.append(DataChunk(
                chunk_id=1,
                priority=1,
                row_indices=anomaly_indices,
                description="Top异常值",
                estimated_importance=1.0
            ))
        
        # 第2块：高值区间（排除异常值）
        remaining_indices = list(set(range(len(df))) - set(anomaly_indices))
        
        # 按主要度量字段排序
        main_measure = self._identify_main_measure(df, profile)
        if main_measure:
            sorted_indices = df.iloc[remaining_indices].sort_values(
                by=main_measure, ascending=False
            ).index.tolist()
            
            # 高值区间
            high_value_indices = sorted_indices[:self.chunk_size]
            chunks.append(DataChunk(
                chunk_id=2,
                priority=2,
                row_indices=high_value_indices,
                description="高值区间",
                estimated_importance=0.8
            ))
            
            # 中值区间
            mid_value_indices = sorted_indices[self.chunk_size:self.chunk_size*2]
            if mid_value_indices:
                chunks.append(DataChunk(
                    chunk_id=3,
                    priority=3,
                    row_indices=mid_value_indices,
                    description="中值区间",
                    estimated_importance=0.5
                ))
        
        return chunks
    
    def _chunk_top_first(
        self,
        df: pd.DataFrame,
        profile: DataProfile
    ) -> List[DataChunk]:
        """Top优先分块"""
        chunks = []
        
        # 识别主要度量字段
        main_measure = self._identify_main_measure(df, profile)
        
        if main_measure:
            # 按主要度量排序
            sorted_df = df.sort_values(by=main_measure, ascending=False)
            
            # 分块
            for i in range(0, len(df), self.chunk_size):
                chunk_indices = sorted_df.iloc[i:i+self.chunk_size].index.tolist()
                
                # 计算重要性（Top块更重要）
                importance = max(0.3, 1.0 - (i / len(df)))
                
                chunks.append(DataChunk(
                    chunk_id=len(chunks) + 1,
                    priority=len(chunks) + 1,
                    row_indices=chunk_indices,
                    description=f"第{len(chunks)+1}块（Top {i}-{i+len(chunk_indices)}）",
                    estimated_importance=importance
                ))
        
        return chunks
    
    def _chunk_mixed(
        self,
        df: pd.DataFrame,
        profile: DataProfile
    ) -> List[DataChunk]:
        """混合策略分块"""
        chunks = []
        
        # 第1块：异常值 + Top值
        anomaly_indices = [a["row_index"] for a in profile.anomaly_positions[:50]]
        
        main_measure = self._identify_main_measure(df, profile)
        if main_measure:
            top_indices = df.nlargest(50, main_measure).index.tolist()
            
            # 合并并去重
            combined_indices = list(set(anomaly_indices + top_indices))[:self.chunk_size]
            
            chunks.append(DataChunk(
                chunk_id=1,
                priority=1,
                row_indices=combined_indices,
                description="异常值 + Top值",
                estimated_importance=1.0
            ))
        
        # 后续块：随机采样
        remaining_indices = list(set(range(len(df))) - set(combined_indices))
        
        for i in range(0, len(remaining_indices), self.chunk_size):
            chunk_indices = remaining_indices[i:i+self.chunk_size]
            
            chunks.append(DataChunk(
                chunk_id=len(chunks) + 1,
                priority=len(chunks) + 1,
                row_indices=chunk_indices,
                description=f"采样块{len(chunks)+1}",
                estimated_importance=0.5
            ))
        
        return chunks
    
    def _identify_main_measure(
        self,
        df: pd.DataFrame,
        profile: DataProfile
    ) -> Optional[str]:
        """识别主要度量字段"""
        # 简化实现：选择方差最大的数值字段
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if len(numeric_cols) == 0:
            return None
        
        max_std = 0
        main_measure = None
        
        for col in numeric_cols:
            std = df[col].std()
            if std > max_std:
                max_std = std
                main_measure = col
        
        return main_measure
```

---

