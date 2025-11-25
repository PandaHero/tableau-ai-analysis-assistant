"""
渐进式累积洞察分析 - 核心代码示例

展示"AI 宝宝吃饭"理念的完整实现
"""
from typing import List, Dict, Any, AsyncGenerator, Tuple
from enum import Enum
import pandas as pd
import asyncio


class Priority(Enum):
    """优先级"""
    URGENT = 4      # 异常值，立即分析
    HIGH = 3        # Top 数据，必须分析
    MEDIUM = 2      # 中间数据，选择性分析
    LOW = 1         # 尾部数据，可选分析
    STATS_ONLY = 0  # 只统计，不分析


class Insight:
    """洞察"""
    def __init__(
        self,
        type: str,
        title: str,
        description: str,
        confidence: float,
        evidence: List[str],
        priority: str
    ):
        self.type = type
        self.title = title
        self.description = description
        self.confidence = confidence
        self.evidence = evidence
        self.priority = priority
        self.replan_reason = None


class ProgressiveInsightAnalyzer:
    """
    渐进式累积洞察分析器
    
    核心理念："AI 宝宝吃饭"
    """
    
    async def analyze(
        self,
        data: pd.DataFrame,
        question_context: Dict
    ) -> AsyncGenerator[Dict, None]:
        """
        主分析流程
        
        流程：
        1. 智能分块（准备饭菜）
        2. 按优先级分析（先吃肉）
        3. 流式输出洞察（实时反馈）
        4. 早停判断（吃饱了）
        5. 合成最终洞察（营养充足）
        """
        
        # 1. 智能优先级分块
        yield {"event": "chunking", "message": "正在智能分块..."}
        chunks = self._intelligent_chunking(data, question_context)
        yield {"event": "chunks_ready", "chunks": len(chunks)}
        
        # 2. 初始化累积器
        accumulator = InsightAccumulator(question_context)
        
        # 3. 按优先级分析
        for i, (chunk, priority, chunk_type) in enumerate(chunks):
            
            # 跳过 STATS_ONLY
            if priority == Priority.STATS_ONLY:
                stats = self._calculate_statistics(chunk)
                yield {
                    "event": "stats_only",
                    "chunk_type": chunk_type,
                    "stats": stats
                }
                continue
            
            # 3.1 分析当前块
            yield {
                "event": "chunk_start",
                "chunk_index": i,
                "chunk_type": chunk_type,
                "priority": priority.name
            }
            
            insights = await self._analyze_chunk(
                chunk=chunk,
                chunk_type=chunk_type,
                priority=priority,
                accumulated_context=accumulator.get_context(),
                question_context=question_context
            )
            
            # 3.2 质量过滤（吐出不好吃的）
            filtered = self._filter_quality(insights)
            
            # 3.3 累积洞察
            accumulator.add(filtered, chunk_type)
            
            # 3.4 流式输出每个洞察
            for insight in filtered:
                yield {
                    "event": "insight_found",
                    "insight": insight.__dict__,
                    "chunk_type": chunk_type,
                    "accumulated_count": len(accumulator.insights)
                }
                
                # 3.5 检查是否触发 Replan
                if self._should_trigger_replan(insight):
                    yield {
                        "event": "replan_trigger",
                        "reason": insight.replan_reason,
                        "insight": insight.__dict__
                    }
            
            # 3.6 早停判断（吃饱了）
            if self._should_stop_early(accumulator, i, len(chunks)):
                yield {
                    "event": "early_stop",
                    "reason": "已获得足够洞察",
                    "analyzed": i + 1,
                    "total": len(chunks),
                    "saved_ratio": f"{(1 - (i+1)/len(chunks)) * 100:.1f}%"
                }
                break
        
        # 4. 合成最终洞察
        yield {"event": "synthesizing", "message": "正在合成最终洞察..."}
        final = accumulator.synthesize()
        
        yield {
            "event": "complete",
            "final_insights": final
        }
    
    def _intelligent_chunking(
        self,
        data: pd.DataFrame,
        question_context: Dict
    ) -> List[Tuple[pd.DataFrame, Priority, str]]:
        """
        智能优先级分块
        
        策略："先吃肉，再吃蔬菜，最后喝汤"
        """
        chunks = []
        total_rows = len(data)
        
        # 1. 异常值检测（URGENT）- "不好吃的，先挑出来"
        anomalies = self._detect_anomalies(data)
        if len(anomalies) > 0:
            chunks.append((anomalies, Priority.URGENT, "anomalies"))
        
        # 2. Top 100 行（HIGH）- "肉"
        if total_rows > 0:
            top_chunk = data.head(100)
            chunks.append((top_chunk, Priority.HIGH, "top_data"))
        
        # 3. 101-500 行（MEDIUM）- "蔬菜"
        if total_rows > 100:
            mid_chunk = data.iloc[100:min(500, total_rows)]
            chunks.append((mid_chunk, Priority.MEDIUM, "mid_data"))
        
        # 4. 501-1000 行（LOW）- "汤"
        if total_rows > 500:
            low_chunk = data.iloc[500:min(1000, total_rows)]
            chunks.append((low_chunk, Priority.LOW, "low_data"))
        
        # 5. 1000+ 行（STATS_ONLY）- "剩菜，不吃了"
        if total_rows > 1000:
            tail_data = data.iloc[1000:]
            chunks.append((tail_data, Priority.STATS_ONLY, "tail_stats"))
        
        return chunks


class InsightAccumulator:
    """
    洞察累积器（带上下文感知）
    """
    
    def __init__(self, question_context: Dict):
        self.question_context = question_context
        self.insights: List[Insight] = []
        self.known_facts: Dict[str, Any] = {}  # 已知事实
        self.analyzed_chunks: List[str] = []
    
    def add(self, new_insights: List[Insight], chunk_type: str):
        """
        添加新洞察（上下文感知）
        
        关键：避免重复找第一名
        """
        self.analyzed_chunks.append(chunk_type)
        
        for insight in new_insights:
            # 1. 检查是否与已知事实冲突
            if self._conflicts_with_facts(insight):
                # 转换为补充信息
                insight = self._convert_to_supplementary(insight)
            
            # 2. 检查是否重复
            if self._is_redundant(insight):
                continue
            
            # 3. 尝试增强现有洞察
            if self._try_enhance_existing(insight):
                continue
            
            # 4. 添加新洞察
            self.insights.append(insight)
            
            # 5. 更新已知事实
            self._update_facts(insight)
    
    def _conflicts_with_facts(self, insight: Insight) -> bool:
        """
        检查是否与已知事实冲突
        
        示例：
        - 已知：A 店是全局第1
        - 新洞察：B 店是第1（这个分块的第1）
        - 判断：冲突 ✓
        """
        if insight.type == "ranking":
            if "top_entity" in self.known_facts:
                # 已经知道全局第1，新的"第1"是局部的
                return insight.entity != self.known_facts["top_entity"]
        
        return False
    
    def _convert_to_supplementary(self, insight: Insight) -> Insight:
        """
        将冲突的洞察转换为补充信息
        
        示例：
        - 原洞察：B 店是第1
        - 转换后：B 店在中间数据中表现突出，但整体排名第2
        """
        if "top_entity" in self.known_facts:
            insight.description = (
                f"{insight.entity} 在当前数据段中表现突出，"
                f"但整体排名低于 {self.known_facts['top_entity']}"
            )
            insight.type = "comparison"
        
        return insight
    
    def _update_facts(self, insight: Insight):
        """
        更新已知事实
        
        只有高置信度的洞察才能成为事实
        """
        if insight.confidence > 0.9:
            if insight.type == "ranking":
                self.known_facts["top_entity"] = insight.entity
                self.known_facts["top_value"] = insight.value
    
    def get_context(self) -> str:
        """
        获取当前上下文（给下一块分析用）
        """
        if not self.insights:
            return "暂无发现"
        
        # 1. 已知事实
        facts_str = "已知事实：\n"
        for key, value in self.known_facts.items():
            facts_str += f"  - {key}: {value}\n"
        
        # 2. 关键洞察（Top 3）
        top_insights = sorted(
            self.insights,
            key=lambda x: x.confidence,
            reverse=True
        )[:3]
        
        insights_str = "关键发现：\n"
        for ins in top_insights:
            insights_str += f"  - {ins.title}\n"
        
        return facts_str + "\n" + insights_str
    
    def synthesize(self) -> Dict[str, Any]:
        """合成最终洞察"""
        return {
            "insights": [ins.__dict__ for ins in self.insights],
            "facts": self.known_facts,
            "summary": self._generate_summary()
        }
