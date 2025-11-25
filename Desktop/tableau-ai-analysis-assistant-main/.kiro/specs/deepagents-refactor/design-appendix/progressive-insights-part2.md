# 渐进式洞察系统详细设计 - Part 2

## 2.4 ChunkAnalyzer（块分析器）

**职责**：分析单个数据块，生成块级洞察。

**分析流程**：

```
数据块
  ↓
1. 模式检测（PatternDetector）
   ├─ 趋势检测
   ├─ 周期性检测
   └─ 相关性检测
  ↓
2. 异常检测（AnomalyDetector）
   ├─ 统计异常
   ├─ 业务异常
   └─ 时序异常
  ↓
3. LLM洞察生成
   输入: 数据块 + 模式 + 异常
   输出: 结构化洞察
  ↓
块级洞察列表
```

**实现**：

```python
from typing import List, Dict
import pandas as pd

class ChunkInsight(BaseModel):
    """块级洞察"""
    chunk_id: int
    insight_type: str  # "trend" / "anomaly" / "pattern" / "comparison"
    description: str
    evidence: List[str]
    confidence: float
    importance: float
    data_points: List[Dict]  # 支持数据点

class ChunkAnalyzer:
    """块分析器"""
    
    def __init__(
        self,
        pattern_detector: 'PatternDetector',
        anomaly_detector: 'AnomalyDetector',
        llm_client: Any
    ):
        self.pattern_detector = pattern_detector
        self.anomaly_detector = anomaly_detector
        self.llm = llm_client
    
    async def analyze_chunk(
        self,
        df: pd.DataFrame,
        chunk: DataChunk,
        context: Dict
    ) -> List[ChunkInsight]:
        """分析数据块"""
        
        # 1. 提取数据块
        chunk_df = df.iloc[chunk.row_indices]
        
        # 2. 模式检测
        patterns = self.pattern_detector.detect_patterns(chunk_df, context)
        
        # 3. 异常检测
        anomalies = self.anomaly_detector.detect_anomalies(chunk_df, context)
        
        # 4. 准备LLM输入
        llm_input = self._prepare_llm_input(
            chunk_df=chunk_df,
            patterns=patterns,
            anomalies=anomalies,
            context=context
        )
        
        # 5. 调用LLM生成洞察
        insights = await self._generate_insights_with_llm(llm_input)
        
        # 6. 标记chunk_id
        for insight in insights:
            insight.chunk_id = chunk.chunk_id
        
        return insights
    
    def _prepare_llm_input(
        self,
        chunk_df: pd.DataFrame,
        patterns: List[Dict],
        anomalies: List[Dict],
        context: Dict
    ) -> str:
        """准备LLM输入"""
        
        # 数据摘要
        data_summary = self._summarize_data(chunk_df)
        
        # 模式摘要
        pattern_summary = self._summarize_patterns(patterns)
        
        # 异常摘要
        anomaly_summary = self._summarize_anomalies(anomalies)
        
        prompt = f"""
你是一个数据分析专家。请分析以下数据块并生成洞察。

**用户问题**: {context.get('question', '')}

**数据摘要**:
{data_summary}

**检测到的模式**:
{pattern_summary}

**检测到的异常**:
{anomaly_summary}

**任务**:
1. 基于数据、模式和异常，生成3-5个关键洞察
2. 每个洞察必须包含：
   - 类型（trend/anomaly/pattern/comparison）
   - 描述（清晰、具体）
   - 证据（数据支持）
   - 置信度（0-1）
   - 重要性（0-1）

**输出格式**（JSON）:
```json
[
  {{
    "insight_type": "trend",
    "description": "华东地区销售额呈上升趋势",
    "evidence": ["Q1: 100万", "Q2: 120万", "Q3: 150万"],
    "confidence": 0.9,
    "importance": 0.8,
    "data_points": [
      {{"dimension": "华东", "measure": "销售额", "value": 1000000, "period": "Q1"}},
      {{"dimension": "华东", "measure": "销售额", "value": 1200000, "period": "Q2"}}
    ]
  }}
]

"""
        return prompt
    
    def _summarize_data(self, df: pd.DataFrame) -> str:
        """数据摘要"""
        summary_parts = []
        
        # 行数
        summary_parts.append(f"- 数据行数: {len(df)}")
        
        # 数值字段统计
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            summary_parts.append(
                f"- {col}: min={df[col].min():.2f}, "
                f"max={df[col].max():.2f}, "
                f"mean={df[col].mean():.2f}"
            )
        
        # 分类字段分布
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns
        for col in categorical_cols:
            top_values = df[col].value_counts().head(3)
            summary_parts.append(
                f"- {col}: {', '.join([f'{k}({v})' for k, v in top_values.items()])}"
            )
        
        return "\n".join(summary_parts)
    
    def _summarize_patterns(self, patterns: List[Dict]) -> str:
        """模式摘要"""
        if not patterns:
            return "无明显模式"
        
        summary_parts = []
        for p in patterns:
            summary_parts.append(
                f"- {p['type']}: {p['description']} (置信度: {p['confidence']:.2f})"
            )
        
        return "\n".join(summary_parts)
    
    def _summarize_anomalies(self, anomalies: List[Dict]) -> str:
        """异常摘要"""
        if not anomalies:
            return "无明显异常"
        
        summary_parts = []
        for a in anomalies:
            summary_parts.append(
                f"- {a['field']}: {a['value']} (Z-score: {a['z_score']:.2f})"
            )
        
        return "\n".join(summary_parts)
    
    async def _generate_insights_with_llm(self, prompt: str) -> List[ChunkInsight]:
        """使用LLM生成洞察"""
        
        # 调用LLM
        response = await self.llm.ainvoke(prompt)
        
        # 解析JSON响应
        try:
            insights_data = json.loads(response.content)
            insights = [ChunkInsight(**data) for data in insights_data]
            return insights
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return []
```

---

## 2.5 PatternDetector（模式检测器）

**职责**：检测数据中的模式（趋势、周期性、相关性）。

**检测类型**：

1. **趋势检测**：线性回归检测上升/下降趋势
2. **周期性检测**：自相关检测周期性模式
3. **相关性检测**：Pearson相关系数检测字段间相关性

**实现**：

```python
from scipy import stats
from scipy.signal import find_peaks
import numpy as np

class Pattern(BaseModel):
    """模式"""
    type: str  # "trend" / "periodicity" / "correlation"
    description: str
    confidence: float
    details: Dict

class PatternDetector:
    """模式检测器"""
    
    def detect_patterns(
        self,
        df: pd.DataFrame,
        context: Dict
    ) -> List[Pattern]:
        """检测模式"""
        patterns = []
        
        # 1. 趋势检测
        trends = self._detect_trends(df)
        patterns.extend(trends)
        
        # 2. 周期性检测
        periodicities = self._detect_periodicity(df)
        patterns.extend(periodicities)
        
        # 3. 相关性检测
        correlations = self._detect_correlations(df)
        patterns.extend(correlations)
        
        return patterns
    
    def _detect_trends(self, df: pd.DataFrame) -> List[Pattern]:
        """趋势检测（线性回归）"""
        patterns = []
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            # 线性回归
            x = np.arange(len(df))
            y = df[col].values
            
            # 去除NaN
            mask = ~np.isnan(y)
            if mask.sum() < 3:  # 至少需要3个点
                continue
            
            x_clean = x[mask]
            y_clean = y[mask]
            
            # 线性回归
            slope, intercept, r_value, p_value, std_err = stats.linregress(x_clean, y_clean)
            
            # 判断趋势显著性
            if abs(r_value) > 0.7 and p_value < 0.05:
                trend_type = "上升" if slope > 0 else "下降"
                
                patterns.append(Pattern(
                    type="trend",
                    description=f"{col}呈{trend_type}趋势",
                    confidence=abs(r_value),
                    details={
                        "field": col,
                        "slope": float(slope),
                        "r_squared": float(r_value ** 2),
                        "p_value": float(p_value)
                    }
                ))
        
        return patterns
    
    def _detect_periodicity(self, df: pd.DataFrame) -> List[Pattern]:
        """周期性检测（自相关）"""
        patterns = []
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            # 自相关
            y = df[col].dropna().values
            
            if len(y) < 10:  # 至少需要10个点
                continue
            
            # 计算自相关
            autocorr = np.correlate(y - y.mean(), y - y.mean(), mode='full')
            autocorr = autocorr[len(autocorr)//2:]
            autocorr = autocorr / autocorr[0]
            
            # 查找峰值
            peaks, properties = find_peaks(autocorr[1:], height=0.5)
            
            if len(peaks) > 0:
                # 第一个峰值位置即为周期
                period = peaks[0] + 1
                confidence = properties['peak_heights'][0]
                
                patterns.append(Pattern(
                    type="periodicity",
                    description=f"{col}存在周期性模式（周期约{period}）",
                    confidence=float(confidence),
                    details={
                        "field": col,
                        "period": int(period),
                        "peak_height": float(confidence)
                    }
                ))
        
        return patterns
    
    def _detect_correlations(self, df: pd.DataFrame) -> List[Pattern]:
        """相关性检测"""
        patterns = []
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if len(numeric_cols) < 2:
            return patterns
        
        # 计算相关矩阵
        corr_matrix = df[numeric_cols].corr()
        
        # 查找强相关（|r| > 0.7）
        for i in range(len(numeric_cols)):
            for j in range(i+1, len(numeric_cols)):
                corr_value = corr_matrix.iloc[i, j]
                
                if abs(corr_value) > 0.7:
                    col1 = numeric_cols[i]
                    col2 = numeric_cols[j]
                    
                    corr_type = "正相关" if corr_value > 0 else "负相关"
                    
                    patterns.append(Pattern(
                        type="correlation",
                        description=f"{col1}与{col2}存在{corr_type}",
                        confidence=abs(corr_value),
                        details={
                            "field1": col1,
                            "field2": col2,
                            "correlation": float(corr_value)
                        }
                    ))
        
        return patterns
```

---

## 2.6 AnomalyDetector（异常检测器）

**职责**：检测数据中的异常值。

**检测方法**：

1. **统计异常**：Z-score方法（|Z| > 3）
2. **业务异常**：基于业务规则（如负销售额）
3. **时序异常**：基于时间序列的异常检测

**实现**：

```python
class Anomaly(BaseModel):
    """异常"""
    type: str  # "statistical" / "business" / "temporal"
    description: str
    severity: str  # "high" / "medium" / "low"
    details: Dict

class AnomalyDetector:
    """异常检测器"""
    
    def detect_anomalies(
        self,
        df: pd.DataFrame,
        context: Dict
    ) -> List[Anomaly]:
        """检测异常"""
        anomalies = []
        
        # 1. 统计异常
        statistical_anomalies = self._detect_statistical_anomalies(df)
        anomalies.extend(statistical_anomalies)
        
        # 2. 业务异常
        business_anomalies = self._detect_business_anomalies(df, context)
        anomalies.extend(business_anomalies)
        
        return anomalies
    
    def _detect_statistical_anomalies(self, df: pd.DataFrame) -> List[Anomaly]:
        """统计异常检测（Z-score）"""
        anomalies = []
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            # 计算Z-score
            z_scores = np.abs(stats.zscore(df[col].dropna()))
            
            # 查找异常值（|Z| > 3）
            anomaly_mask = z_scores > 3
            
            if anomaly_mask.any():
                anomaly_count = anomaly_mask.sum()
                max_z = z_scores[anomaly_mask].max()
                
                # 判断严重程度
                if max_z > 5:
                    severity = "high"
                elif max_z > 4:
                    severity = "medium"
                else:
                    severity = "low"
                
                anomalies.append(Anomaly(
                    type="statistical",
                    description=f"{col}存在{anomaly_count}个统计异常值",
                    severity=severity,
                    details={
                        "field": col,
                        "count": int(anomaly_count),
                        "max_z_score": float(max_z),
                        "anomaly_values": df[col][anomaly_mask].tolist()
                    }
                ))
        
        return anomalies
    
    def _detect_business_anomalies(
        self,
        df: pd.DataFrame,
        context: Dict
    ) -> List[Anomaly]:
        """业务异常检测"""
        anomalies = []
        
        # 规则1：销售额/数量不应为负
        for col in df.columns:
            if any(keyword in col.lower() for keyword in ['sales', 'amount', 'quantity', '销售', '数量']):
                negative_mask = df[col] < 0
                
                if negative_mask.any():
                    anomalies.append(Anomaly(
                        type="business",
                        description=f"{col}存在负值（业务异常）",
                        severity="high",
                        details={
                            "field": col,
                            "count": int(negative_mask.sum()),
                            "negative_values": df[col][negative_mask].tolist()
                        }
                    ))
        
        # 规则2：日期不应在未来
        for col in df.columns:
            if df[col].dtype == 'datetime64[ns]':
                future_mask = df[col] > pd.Timestamp.now()
                
                if future_mask.any():
                    anomalies.append(Anomaly(
                        type="business",
                        description=f"{col}存在未来日期（业务异常）",
                        severity="medium",
                        details={
                            "field": col,
                            "count": int(future_mask.sum())
                        }
                    ))
        
        return anomalies
```

---

