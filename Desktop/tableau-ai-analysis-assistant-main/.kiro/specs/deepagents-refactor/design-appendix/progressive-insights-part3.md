# 渐进式洞察系统详细设计 - Part 3

## 2.7 InsightAccumulator（洞察累积器）

**职责**：累积块级洞察，并决定是否早停。

**早停策略**：

1. **趋势稳定**：连续3个块的趋势一致
2. **洞察饱和**：新块的洞察与已有洞察重复度>80%
3. **置信度达标**：累积洞察的平均置信度>0.85
4. **预算耗尽**：已使用Token数超过预算

**实现**：

```python
from typing import List, Tuple
from collections import defaultdict

class AccumulatedInsights(BaseModel):
    """累积洞察"""
    insights: List[ChunkInsight]
    total_chunks_analyzed: int
    should_stop: bool
    stop_reason: Optional[str]
    confidence_score: float

class InsightAccumulator:
    """洞察累积器"""
    
    def __init__(
        self,
        similarity_threshold: float = 0.8,
        confidence_threshold: float = 0.85,
        max_chunks: int = 10
    ):
        self.similarity_threshold = similarity_threshold
        self.confidence_threshold = confidence_threshold
        self.max_chunks = max_chunks
        
        self.accumulated_insights: List[ChunkInsight] = []
        self.chunks_analyzed = 0
        self.trend_history: List[str] = []  # 记录趋势历史
    
    def accumulate(
        self,
        new_insights: List[ChunkInsight],
        chunk: DataChunk
    ) -> AccumulatedInsights:
        """累积新洞察并决定是否早停"""
        
        # 1. 添加新洞察
        self.accumulated_insights.extend(new_insights)
        self.chunks_analyzed += 1
        
        # 2. 记录趋势
        self._record_trends(new_insights)
        
        # 3. 检查早停条件
        should_stop, stop_reason = self._check_early_stop()
        
        # 4. 计算置信度
        confidence = self._calculate_confidence()
        
        return AccumulatedInsights(
            insights=self.accumulated_insights,
            total_chunks_analyzed=self.chunks_analyzed,
            should_stop=should_stop,
            stop_reason=stop_reason,
            confidence_score=confidence
        )
    
    def _record_trends(self, insights: List[ChunkInsight]):
        """记录趋势"""
        for insight in insights:
            if insight.insight_type == "trend":
                # 提取趋势方向
                if "上升" in insight.description:
                    self.trend_history.append("up")
                elif "下降" in insight.description:
                    self.trend_history.append("down")
                else:
                    self.trend_history.append("stable")
    
    def _check_early_stop(self) -> Tuple[bool, Optional[str]]:
        """检查早停条件"""
        
        # 条件1：达到最大块数
        if self.chunks_analyzed >= self.max_chunks:
            return True, "达到最大分析块数"
        
        # 条件2：趋势稳定（连续3个块趋势一致）
        if len(self.trend_history) >= 3:
            recent_trends = self.trend_history[-3:]
            if len(set(recent_trends)) == 1:  # 全部相同
                return True, "趋势已稳定"
        
        # 条件3：洞察饱和（新洞察重复度高）
        if self.chunks_analyzed >= 2:
            similarity = self._calculate_insight_similarity()
            if similarity > self.similarity_threshold:
                return True, "洞察已饱和"
        
        # 条件4：置信度达标
        confidence = self._calculate_confidence()
        if confidence > self.confidence_threshold and self.chunks_analyzed >= 2:
            return True, "置信度已达标"
        
        return False, None
    
    def _calculate_insight_similarity(self) -> float:
        """计算最新块与之前块的洞察相似度"""
        if self.chunks_analyzed < 2:
            return 0.0
        
        # 获取最新块的洞察
        latest_chunk_id = self.chunks_analyzed
        latest_insights = [
            i for i in self.accumulated_insights
            if i.chunk_id == latest_chunk_id
        ]
        
        # 获取之前的洞察
        previous_insights = [
            i for i in self.accumulated_insights
            if i.chunk_id < latest_chunk_id
        ]
        
        if not latest_insights or not previous_insights:
            return 0.0
        
        # 计算相似度（简化：基于描述的词汇重叠）
        latest_descriptions = [i.description for i in latest_insights]
        previous_descriptions = [i.description for i in previous_insights]
        
        # 计算Jaccard相似度
        latest_words = set(" ".join(latest_descriptions).split())
        previous_words = set(" ".join(previous_descriptions).split())
        
        intersection = len(latest_words & previous_words)
        union = len(latest_words | previous_words)
        
        return intersection / union if union > 0 else 0.0
    
    def _calculate_confidence(self) -> float:
        """计算累积洞察的平均置信度"""
        if not self.accumulated_insights:
            return 0.0
        
        total_confidence = sum(i.confidence for i in self.accumulated_insights)
        return total_confidence / len(self.accumulated_insights)
```

---

## 2.8 QualityFilter（质量过滤器）

**职责**：过滤低质量洞察。

**过滤规则**：

1. **置信度过低**：confidence < 0.5
2. **重要性过低**：importance < 0.3
3. **证据不足**：evidence列表为空
4. **描述过于模糊**：包含"可能"、"也许"等不确定词汇

**实现**：

```python
class QualityFilter:
    """质量过滤器"""
    
    def __init__(
        self,
        min_confidence: float = 0.5,
        min_importance: float = 0.3
    ):
        self.min_confidence = min_confidence
        self.min_importance = min_importance
        
        # 模糊词汇列表
        self.vague_words = ["可能", "也许", "大概", "似乎", "好像"]
    
    def filter_insights(
        self,
        insights: List[ChunkInsight]
    ) -> List[ChunkInsight]:
        """过滤低质量洞察"""
        
        filtered = []
        
        for insight in insights:
            # 规则1：置信度检查
            if insight.confidence < self.min_confidence:
                continue
            
            # 规则2：重要性检查
            if insight.importance < self.min_importance:
                continue
            
            # 规则3：证据检查
            if not insight.evidence:
                continue
            
            # 规则4：描述模糊度检查
            if self._is_vague(insight.description):
                continue
            
            filtered.append(insight)
        
        return filtered
    
    def _is_vague(self, description: str) -> bool:
        """检查描述是否模糊"""
        return any(word in description for word in self.vague_words)
```

---

## 2.9 DedupMerger（去重合并器）

**职责**：去重和合并相似洞察。

**合并策略**：

1. **完全重复**：描述完全相同 → 保留一个
2. **高度相似**：描述相似度>0.8 → 合并为一个
3. **互补**：描述不同但证据互补 → 合并证据

**实现**：

```python
from difflib import SequenceMatcher

class DedupMerger:
    """去重合并器"""
    
    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
    
    def deduplicate_and_merge(
        self,
        insights: List[ChunkInsight]
    ) -> List[ChunkInsight]:
        """去重和合并"""
        
        if not insights:
            return []
        
        # 1. 按类型分组
        grouped = defaultdict(list)
        for insight in insights:
            grouped[insight.insight_type].append(insight)
        
        # 2. 每组内去重合并
        merged = []
        for insight_type, group in grouped.items():
            merged.extend(self._merge_group(group))
        
        return merged
    
    def _merge_group(self, insights: List[ChunkInsight]) -> List[ChunkInsight]:
        """合并同类型洞察"""
        
        if len(insights) <= 1:
            return insights
        
        merged = []
        used = set()
        
        for i, insight1 in enumerate(insights):
            if i in used:
                continue
            
            # 查找相似洞察
            similar_indices = []
            for j, insight2 in enumerate(insights[i+1:], start=i+1):
                if j in used:
                    continue
                
                similarity = self._calculate_similarity(
                    insight1.description,
                    insight2.description
                )
                
                if similarity > self.similarity_threshold:
                    similar_indices.append(j)
            
            # 合并
            if similar_indices:
                merged_insight = self._merge_insights(
                    [insight1] + [insights[j] for j in similar_indices]
                )
                merged.append(merged_insight)
                
                used.add(i)
                used.update(similar_indices)
            else:
                merged.append(insight1)
                used.add(i)
        
        return merged
    
    def _calculate_similarity(self, desc1: str, desc2: str) -> float:
        """计算描述相似度"""
        return SequenceMatcher(None, desc1, desc2).ratio()
    
    def _merge_insights(self, insights: List[ChunkInsight]) -> ChunkInsight:
        """合并多个洞察"""
        
        # 选择置信度最高的作为基础
        base_insight = max(insights, key=lambda x: x.confidence)
        
        # 合并证据
        all_evidence = []
        for insight in insights:
            all_evidence.extend(insight.evidence)
        
        # 去重证据
        unique_evidence = list(set(all_evidence))
        
        # 合并数据点
        all_data_points = []
        for insight in insights:
            all_data_points.extend(insight.data_points)
        
        # 计算平均置信度和重要性
        avg_confidence = sum(i.confidence for i in insights) / len(insights)
        avg_importance = sum(i.importance for i in insights) / len(insights)
        
        return ChunkInsight(
            chunk_id=base_insight.chunk_id,
            insight_type=base_insight.insight_type,
            description=base_insight.description,
            evidence=unique_evidence,
            confidence=avg_confidence,
            importance=avg_importance,
            data_points=all_data_points
        )
```

---

## 2.10 InsightSynthesizer（洞察合成器）

**职责**：将块级洞察合成为最终洞察。

**合成策略**：

1. **优先级排序**：按重要性和置信度排序
2. **分类组织**：按类型（趋势、异常、模式）组织
3. **关联分析**：发现洞察之间的关联
4. **层次结构**：构建主洞察和支持洞察的层次

**实现**：

```python
class FinalInsight(BaseModel):
    """最终洞察"""
    insight_id: str
    type: str
    title: str
    description: str
    evidence: List[str]
    confidence: float
    importance: float
    supporting_insights: List[str]  # 支持洞察的ID
    data_points: List[Dict]

class InsightSynthesizer:
    """洞察合成器"""
    
    def synthesize(
        self,
        accumulated_insights: AccumulatedInsights
    ) -> List[FinalInsight]:
        """合成最终洞察"""
        
        insights = accumulated_insights.insights
        
        # 1. 质量过滤
        quality_filter = QualityFilter()
        filtered = quality_filter.filter_insights(insights)
        
        # 2. 去重合并
        dedup_merger = DedupMerger()
        merged = dedup_merger.deduplicate_and_merge(filtered)
        
        # 3. 优先级排序
        sorted_insights = self._sort_by_priority(merged)
        
        # 4. 关联分析
        related_groups = self._find_related_insights(sorted_insights)
        
        # 5. 构建最终洞察
        final_insights = self._build_final_insights(sorted_insights, related_groups)
        
        return final_insights
    
    def _sort_by_priority(
        self,
        insights: List[ChunkInsight]
    ) -> List[ChunkInsight]:
        """按优先级排序"""
        
        # 优先级 = 重要性 * 0.6 + 置信度 * 0.4
        def priority_score(insight):
            return insight.importance * 0.6 + insight.confidence * 0.4
        
        return sorted(insights, key=priority_score, reverse=True)
    
    def _find_related_insights(
        self,
        insights: List[ChunkInsight]
    ) -> Dict[int, List[int]]:
        """查找关联洞察"""
        
        related = defaultdict(list)
        
        for i, insight1 in enumerate(insights):
            for j, insight2 in enumerate(insights[i+1:], start=i+1):
                # 检查是否关联（简化：检查数据点重叠）
                if self._are_related(insight1, insight2):
                    related[i].append(j)
        
        return related
    
    def _are_related(
        self,
        insight1: ChunkInsight,
        insight2: ChunkInsight
    ) -> bool:
        """检查两个洞察是否关联"""
        
        # 检查数据点重叠
        points1 = set(str(p) for p in insight1.data_points)
        points2 = set(str(p) for p in insight2.data_points)
        
        overlap = len(points1 & points2)
        
        return overlap > 0
    
    def _build_final_insights(
        self,
        insights: List[ChunkInsight],
        related_groups: Dict[int, List[int]]
    ) -> List[FinalInsight]:
        """构建最终洞察"""
        
        final_insights = []
        used = set()
        
        for i, insight in enumerate(insights):
            if i in used:
                continue
            
            # 查找支持洞察
            supporting_indices = related_groups.get(i, [])
            supporting_insights = [
                f"insight_{j}" for j in supporting_indices
                if j not in used
            ]
            
            # 生成标题
            title = self._generate_title(insight)
            
            # 创建最终洞察
            final_insight = FinalInsight(
                insight_id=f"insight_{i}",
                type=insight.insight_type,
                title=title,
                description=insight.description,
                evidence=insight.evidence,
                confidence=insight.confidence,
                importance=insight.importance,
                supporting_insights=supporting_insights,
                data_points=insight.data_points
            )
            
            final_insights.append(final_insight)
            used.add(i)
            used.update(supporting_indices)
        
        return final_insights
    
    def _generate_title(self, insight: ChunkInsight) -> str:
        """生成洞察标题"""
        
        # 简化：从描述中提取前10个字
        return insight.description[:20] + "..." if len(insight.description) > 20 else insight.description
```

---

